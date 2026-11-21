"""Use cases of a central state; CLI, SDK and any transport call these.

Order of events: freeze the file -> read it -> check trust -> relate it to history -> plan
-> commit ``head.json`` -> write the graph. The head is the commit point: once it names a pending
activation, a later run finishes that activation instead of leaving a half-updated view.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tarel.errors import TarelError
from tarel.graph.contracts import GraphDocument, GraphFailure
from tarel.graph.observation import utc_now
from tarel.graph.refresh import GraphRefreshReport
from tarel.graph.revision import graph_revision
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.sync.authorization import check_sender, trusted_entry
from tarel.sync.contracts import (
    PendingActivation,
    Publication,
    StreamHead,
    SyncFailure,
    TrustEntry,
    stable_digest,
)
from tarel.sync.envelope import (
    OpenedPublication,
    SignedStatement,
    file_sha256,
    frozen_copy,
    open_content,
    open_publication,
    open_statement,
)
from tarel.sync.export import check_exported_graph
from tarel.sync.impacts import ActiveImpacts, dangling_for_graph, next_impacts, scope_change
from tarel.sync.merge import (
    ACTION_FIRST,
    ACTION_FRESHNESS,
    ACTION_NONE,
    ACTION_UPDATE,
    Merged,
    base_materialization,
    classify,
    merge,
)
from tarel.sync.results import ApplyResult, SyncPlan
from tarel.sync.store import FileSyncStore
from tarel.workspaces.contracts import WorkspaceFailure
from tarel.workspaces.core import create_workspace, define_system


def plan_publication_use_case(
    path: Path,
    *,
    allow_unsigned_dev: bool = False,
    accept_history_gap: bool = False,
    runtime: TarelRuntime | None = None,
) -> SyncPlan:
    """Say what applying this file would do, without changing active state."""
    resolved = resolve_runtime(runtime)
    store = resolved.sync_store()
    with frozen_copy(Path(path), store.incoming_directory()) as (copy, digest):
        statement = open_statement(copy, digest)
        entry = trusted_entry(store, statement.publication)
        check_sender(store, statement, entry, allow_unsigned_dev=allow_unsigned_dev)
        head = store.head(entry.stream_id)
        if head is not None and head.pending is not None:
            # Planning against a half-finished switch would describe a state nobody can see.
            raise SyncFailure(
                "activation_pending",
                f"Stream {entry.stream_id} has an unfinished activation; run tarel sync recover.",
            )
        opened = _open_checked(copy, statement)
        return _prepare(resolved, opened, entry, accept_history_gap).plan


def apply_publication_use_case(
    path: Path,
    *,
    plan_id: str | None = None,
    allow_unsigned_dev: bool = False,
    accept_history_gap: bool = False,
    runtime: TarelRuntime | None = None,
) -> ApplyResult:
    """Activate one file. ``plan_id`` refuses the work if any basis of a reviewed plan moved."""
    resolved = resolve_runtime(runtime)
    store = resolved.sync_store()
    with frozen_copy(Path(path), store.incoming_directory()) as (copy, digest):
        statement = open_statement(copy, digest)
        entry = trusted_entry(store, statement.publication)
        with store.stream_lock(entry.stream_id):
            try:
                # Until the sender is checked, the file's own claims are not recorded as facts.
                check_sender(store, statement, entry, allow_unsigned_dev=allow_unsigned_dev)
            except SyncFailure as exc:
                _record_failure(store, statement, exc)
                raise
            _record_received(store, statement)
            try:
                opened = _open_checked(copy, statement)
                _finish_pending(resolved, entry)
                prepared = _prepare(resolved, opened, entry, accept_history_gap)
                if plan_id is not None and plan_id != prepared.plan.plan_id:
                    raise SyncFailure(
                        "stale_plan",
                        "The file, central state or trust changed since this plan; plan again.",
                    )
                head = _activate(resolved, opened, entry, prepared, copy)
            except TarelError as exc:
                # A refused or failed attempt must show up, whichever domain refused it.
                _record_failure(store, statement, exc)
                raise
            return ApplyResult(
                plan=prepared.plan,
                applied=prepared.plan.action != ACTION_NONE,
                head=head,
            )


def recover_activations_use_case(*, runtime: TarelRuntime | None = None) -> tuple[str, ...]:
    """Finish every activation a stopped process committed but did not complete."""
    resolved = resolve_runtime(runtime)
    store = resolved.sync_store()
    finished: list[str] = []
    for entry in store.trust_entries():
        with store.stream_lock(entry.stream_id):
            head = store.head(entry.stream_id)
            if head is not None and head.pending is not None:
                _finish_pending(resolved, entry)
                finished.append(entry.stream_id)
    return tuple(finished)


@dataclass(frozen=True, slots=True)
class _Prepared:
    plan: SyncPlan
    head: StreamHead | None
    current: GraphDocument | None
    merged: Merged | None
    impacts: ActiveImpacts


def _open_checked(copy: Path, statement: SignedStatement) -> OpenedPublication:
    opened = open_content(copy, statement)
    check_exported_graph(opened.graph, statement.publication.scope)
    return opened


def _prepare(
    runtime: TarelRuntime,
    opened: OpenedPublication,
    entry: TrustEntry,
    accept_history_gap: bool,
) -> _Prepared:
    store = runtime.sync_store()
    publication = opened.publication
    head = store.head(publication.stream_id)
    action, warnings = classify(
        publication, opened.publication_id, head, accept_history_gap=accept_history_gap,
    )
    current = _current_graph(runtime, entry.local_graph)
    if action == ACTION_FIRST and current is not None:
        raise SyncFailure(
            "local_graph_exists",
            f"Graph {entry.local_graph} exists and no stream owns it; refusing to overwrite it.",
        )
    active = (store.impacts(head.stream_id, head.content_activated_by) if head else None)
    impacts = active or ActiveImpacts()
    if action in {ACTION_NONE, ACTION_FRESHNESS}:
        merged = None
    else:
        incoming = base_materialization(opened.graph, publication, entry.local_graph)
        merged = merge(
            current,
            _active_base(store, head, entry) if head else None,
            incoming,
            impacts.retired_annotations(),
        )
        if current is not None and merged.report is not None:
            impacts = next_impacts(
                impacts,
                merged.report,
                current,
                merged.graph,
                publication.scope,
                opened.publication_id,
                merged.restored,
            )
    changed_scope = scope_change(head, publication.scope, publication.profile_version)
    if changed_scope is not None:
        warnings = (*warnings, _scope_warning(changed_scope))
    plan = _build_plan(
        runtime, opened, entry, head, current, action, warnings, merged, impacts, changed_scope,
    )
    return _Prepared(plan=plan, head=head, current=current, merged=merged, impacts=impacts)


def _scope_warning(change: dict[str, Any]) -> str:
    removed = change["namespaces_removed"]
    if not removed:
        return f"Scope changed under profile version {change['to_version']}."
    return (
        f"The site stopped approving {removed}. This withdraws them from the active view; older "
        "revisions here keep them until tarel sync prune runs."
    )


def _current_graph(runtime: TarelRuntime, name: str) -> GraphDocument | None:
    try:
        return runtime.graph_store().load(name)
    except GraphFailure as exc:
        if exc.code == "graph_not_found":
            return None
        raise


def _active_base(store: FileSyncStore, head: StreamHead, entry: TrustEntry) -> GraphDocument:
    """What the last activation wrote before anyone here changed it."""
    path = store.artifact_path(head.stream_id, head.content_activated_by)
    with (
        tempfile.TemporaryDirectory(prefix="tarel-base-") as temporary,
        frozen_copy(path, Path(temporary)) as (copy, digest),
    ):
        opened = open_publication(copy, digest)
    return base_materialization(opened.graph, opened.publication, entry.local_graph)


def _build_plan(
    runtime: TarelRuntime,
    opened: OpenedPublication,
    entry: TrustEntry,
    head: StreamHead | None,
    current: GraphDocument | None,
    action: str,
    warnings: tuple[str, ...],
    merged: Merged | None,
    impacts: ActiveImpacts,
    changed_scope: dict[str, Any] | None,
) -> SyncPlan:
    store = runtime.sync_store()
    publication = opened.publication
    added, changed, removed = _object_changes(action, merged, opened.graph)
    deleted, withdrawn = _split_removed(merged, removed, publication)
    dangling = dangling_for_graph(
        runtime,
        entry.local_graph,
        impacts.removals,
        merged.graph if merged is not None else None,
    )
    claims = (
        tuple(item.to_dict() for item in merged.report.stale_claims)
        if merged is not None and merged.report is not None
        else ()
    )
    basis = {
        "action": action,
        "artifact_sha256": opened.artifact_sha256,
        "current_graph": graph_revision(current) if current is not None else None,
        "head": head.publication_id if head is not None else None,
        "dangling": dangling,
        "publication_id": opened.publication_id,
        "trust": store.trust_digest(),
    }
    return SyncPlan(
        plan_id=stable_digest(basis),
        action=action,
        stream_id=publication.stream_id,
        publisher_id=publication.publisher_id,
        local_graph=entry.local_graph,
        publication_id=opened.publication_id,
        artifact_sha256=opened.artifact_sha256,
        sequence=publication.sequence,
        previous_publication_id=head.publication_id if head else None,
        previous_sequence=head.sequence if head else None,
        content_changed=action in {ACTION_FIRST, ACTION_UPDATE},
        objects_added=added,
        objects_changed=changed,
        objects_deleted=deleted,
        objects_withdrawn=withdrawn,
        scope_change=changed_scope,
        affected_claims=claims,
        restored_claims=merged.restored if merged is not None else (),
        dangling_references=dangling,
        warnings=warnings,
    )


def _split_removed(
    merged: Merged | None, removed: tuple[str, ...], publication: Publication,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if merged is None or merged.report is None:
        return (), ()
    outside = {
        item.reference
        for item in merged.report.changes
        if item.kind == "object_removed" and item.namespace not in publication.scope.namespaces
    }
    return tuple(i for i in removed if i not in outside), tuple(i for i in removed if i in outside)


def _object_changes(
    action: str, merged: Merged | None, published: GraphDocument,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if action == ACTION_FIRST:
        objects = sorted(node.label for node in published.nodes if node.type in {"table", "view"})
        return tuple(objects), (), ()
    if merged is None or merged.report is None:
        return (), (), ()
    return _report_changes(merged.report)


def _report_changes(
    report: GraphRefreshReport,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    added = {item.reference for item in report.changes if item.kind == "object_added"}
    removed = {item.reference for item in report.changes if item.kind == "object_removed"}
    whole = {
        item.object_id
        for item in report.changes
        if item.kind in {"object_added", "object_removed"}
    }
    changed = {
        (item.reference if item.object_id is None else item.object_id)
        for item in report.changes
        if item.kind not in {"object_added", "object_removed"} and item.object_id not in whole
    }
    return tuple(sorted(added)), tuple(sorted(changed)), tuple(sorted(removed))


def _activate(
    runtime: TarelRuntime,
    opened: OpenedPublication,
    entry: TrustEntry,
    prepared: _Prepared,
    frozen: Path,
) -> StreamHead | None:
    store = runtime.sync_store()
    action = prepared.plan.action
    if action == ACTION_NONE:
        return prepared.head
    publication = opened.publication
    if file_sha256(frozen) != opened.artifact_sha256:
        raise SyncFailure("invalid_package", "The private copy changed after it was checked.")
    store.retain_artifact(frozen, publication.stream_id, opened.publication_id)
    head = StreamHead(
        stream_id=publication.stream_id,
        publisher_id=publication.publisher_id,
        graph_id=publication.graph_id,
        local_graph=entry.local_graph,
        publication_id=opened.publication_id,
        sequence=publication.sequence,
        content_revision=publication.content_revision,
        observed_at=publication.observed_at,
        accepted_at=utc_now(),
        scope=publication.scope,
        profile_version=publication.profile_version,
        content_activated_by=(
            prepared.head.content_activated_by
            if action == ACTION_FRESHNESS and prepared.head is not None
            else opened.publication_id
        ),
    )
    if action == ACTION_FRESHNESS:
        store.save_head(head)
        return head
    assert prepared.merged is not None
    return _commit_content(runtime, entry, head, prepared)


def _commit_content(
    runtime: TarelRuntime, entry: TrustEntry, head: StreamHead, prepared: _Prepared,
) -> StreamHead:
    store = runtime.sync_store()
    assert prepared.merged is not None
    graph = prepared.merged.graph
    before = graph_revision(prepared.current) if prepared.current is not None else None
    after = graph_revision(graph)
    store.save_activation(head.stream_id, head.publication_id, graph)
    store.save_impacts(head.stream_id, head.publication_id, prepared.impacts)
    report = prepared.merged.report
    if report is not None and report.before_revision != report.after_revision:
        runtime.graph_change_store().save(entry.local_graph, report)
    pending = replace(
        head,
        pending=PendingActivation(before, after, first_activation=prepared.current is None),
    )
    graphs = runtime.graph_store()
    if prepared.current is None:
        store.save_head(pending)
        graphs.create(graph, durable=True)
    else:

        def switch(latest: GraphDocument) -> GraphDocument:
            # Runs under the graph lock, so no central writer can slip in after this check.
            if graph_revision(latest) != before:
                raise SyncFailure(
                    "stale_plan", f"Graph {entry.local_graph} changed during planning; plan again."
                )
            store.save_head(pending)
            return graph

        graphs.update(entry.local_graph, switch, durable=True)
    _join_workspace(runtime, entry)
    store.save_head(head)
    return head


def _finish_pending(runtime: TarelRuntime, entry: TrustEntry) -> None:
    """Complete an activation whose head was committed before the process stopped."""
    store = runtime.sync_store()
    head = store.head(entry.stream_id)
    if head is None or head.pending is None:
        return
    graphs = runtime.graph_store()
    current = _current_graph(runtime, entry.local_graph)
    revision = graph_revision(current) if current is not None else None
    if revision != head.pending.graph_after:
        if revision != head.pending.graph_before:
            raise SyncFailure(
                "activation_blocked",
                f"Graph {entry.local_graph} matches neither side of the unfinished activation of "
                f"{head.publication_id}; inspect it before continuing.",
            )
        graph = store.load_activation(entry.stream_id, head.publication_id)
        if current is None:
            graphs.create(graph, durable=True)
        else:
            graphs.save(graph, expected_revision=head.pending.graph_before, durable=True)
    _join_workspace(runtime, entry)
    store.save_head(replace(head, pending=None))


def _join_workspace(runtime: TarelRuntime, entry: TrustEntry) -> None:
    """Make the origin part of the shared view. Central areas and relationships stay as they are.

    Several streams can join one workspace at once, and this reads before it writes.
    """
    with runtime.sync_store().configuration_lock():
        _join_workspace_locked(runtime, entry)


def _join_workspace_locked(runtime: TarelRuntime, entry: TrustEntry) -> None:
    workspaces = runtime.workspace_store()
    try:
        workspace = workspaces.load(entry.workspace)
    except WorkspaceFailure as exc:
        if exc.code != "workspace_not_found":
            raise
        workspace = create_workspace(entry.workspace)
    system = next((item for item in workspace.systems if item.name == entry.system), None)
    if system is not None and entry.local_graph in system.graphs:
        return
    names = tuple(sorted({*(system.graphs if system else ()), entry.local_graph}))
    graphs = {name: runtime.graph_store().load(name) for name in names}
    workspaces.save(
        define_system(
            workspace,
            entry.system,
            graph_names=names,
            graphs=graphs,
            description=system.description if system else None,
        )
    )


def _record_received(store: FileSyncStore, statement: SignedStatement) -> None:
    publication = statement.publication
    status = store.status(publication.stream_id)
    status["last_received"] = {
        "observed_at": publication.observed_at,
        "publication_id": statement.publication_id,
        "received_at": utc_now(),
        "sequence": publication.sequence,
    }
    store.save_status(publication.stream_id, status)


def _record_failure(
    store: FileSyncStore, statement: SignedStatement, failure: TarelError,
) -> None:
    publication = statement.publication
    status = store.status(publication.stream_id)
    status["last_failure"] = {
        "at": utc_now(),
        "code": failure.code,
        "message": str(failure),
        "publication_id": statement.publication_id,
        "sequence": publication.sequence,
    }
    store.save_status(publication.stream_id, status)
