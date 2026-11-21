"""Use cases around a takeover: reading a file, granting trust, status and physical cleanup."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.sync.contracts import (
    StreamHead,
    SyncFailure,
    TrustedKey,
    TrustedPublisher,
    TrustEntry,
    instant,
    require_identity,
)
from tarel.sync.envelope import frozen_copy, open_publication
from tarel.sync.export import object_count
from tarel.sync.impacts import ActiveImpacts, dangling_for_graph, load_workspaces
from tarel.sync.results import PruneResult, PublicationReport, StreamStatus
from tarel.sync.signing import key_fingerprint, normalize_public_key
from tarel.workspaces.contracts import WorkspaceDocument


def inspect_publication_use_case(path: Path) -> PublicationReport:
    """Read and verify a file without any state. A readable file is not yet a trusted one."""
    with (
        tempfile.TemporaryDirectory(prefix="tarel-inspect-") as temporary,
        frozen_copy(Path(path), Path(temporary)) as (copy, digest),
    ):
        opened = open_publication(copy, digest)
    return PublicationReport(
        publication_id=opened.publication_id,
        artifact_sha256=opened.artifact_sha256,
        signed=opened.signed,
        publication=opened.publication,
        graph=opened.graph.name,
        objects=object_count(opened.graph),
    )


def add_trust_use_case(
    *,
    publisher_id: str,
    stream_id: str,
    graph_id: str,
    local_graph: str,
    workspace: str,
    system: str,
    namespaces: tuple[str, ...],
    annotations: bool = False,
    technical_descriptions: bool = False,
    runtime: TarelRuntime | None = None,
) -> TrustEntry:
    """Allow one stream to write one local graph. Only this local command can grant that."""
    store = resolve_runtime(runtime).sync_store()
    entry = TrustEntry.from_dict(
        {
            "graph_id": graph_id,
            "local_graph": local_graph,
            "publisher_id": publisher_id,
            "stream_id": stream_id,
            "system": system,
            "workspace": workspace,
            "namespaces": list(namespaces),
            "annotations": annotations,
            "technical_descriptions": technical_descriptions,
        }
    )
    with store.configuration_lock():
        entries = store.trust_entries()
        for other in entries:
            if other.stream_id == stream_id:
                raise SyncFailure("trust_exists", f"Stream is already trusted: {stream_id}")
            if other.local_graph == local_graph:
                raise SyncFailure("trust_exists", f"Graph already has a stream: {local_graph}")
        store.save_trust_entries((*entries, entry))
    return entry


def set_trust_scope_use_case(
    stream_id: str,
    *,
    namespaces: tuple[str, ...],
    annotations: bool = False,
    technical_descriptions: bool = False,
    runtime: TarelRuntime | None = None,
) -> TrustEntry:
    """Replace what a stream may publish. A file can ask for more; only this grants it."""
    store = resolve_runtime(runtime).sync_store()
    with store.configuration_lock():
        entries = store.trust_entries()
        entry = next((item for item in entries if item.stream_id == stream_id), None)
        if entry is None:
            raise SyncFailure("stream_not_found", f"Stream is not trusted: {stream_id}")
        updated = TrustEntry.from_dict(
            {
                **entry.to_dict(),
                "annotations": annotations,
                "namespaces": list(namespaces),
                "technical_descriptions": technical_descriptions,
            }
        )
        store.save_trust_entries(
            tuple(updated if item.stream_id == stream_id else item for item in entries)
        )
    return updated


def trust_key_use_case(
    publisher_id: str,
    *,
    public_key: str,
    not_after: str | None = None,
    runtime: TarelRuntime | None = None,
) -> TrustedKey:
    """Accept one more key. Adding it before revoking the old one rotates without a gap."""
    store = resolve_runtime(runtime).sync_store()
    require_identity(publisher_id, "pub", "publisher ID")
    normalized = normalize_public_key(public_key)
    key = TrustedKey.from_dict(
        {
            "fingerprint": key_fingerprint(normalized),
            "not_after": not_after,
            "public_key": normalized,
        }
    )
    with store.configuration_lock():
        publishers = store.trusted_publishers()
        current = next((i for i in publishers if i.publisher_id == publisher_id), None)
        known = current.keys if current else ()
        if any(item.fingerprint == key.fingerprint for item in known):
            raise SyncFailure("trust_exists", f"Key is already known: {key.fingerprint}")
        updated = TrustedPublisher(publisher_id, (*known, key))
        store.save_trusted_publishers(
            (*(i for i in publishers if i.publisher_id != publisher_id), updated)
        )
    return key


def revoke_key_use_case(
    publisher_id: str,
    fingerprint: str,
    *,
    runtime: TarelRuntime | None = None,
) -> TrustedKey:
    """Stop accepting a key here. It reaches other states only when someone delivers it there."""
    store = resolve_runtime(runtime).sync_store()
    with store.configuration_lock():
        publishers = store.trusted_publishers()
        current = next((i for i in publishers if i.publisher_id == publisher_id), None)
        known = current.keys if current else ()
        key = next((k for k in known if k.fingerprint == fingerprint), None)
        if current is None or key is None:
            raise SyncFailure("unknown_signing_key", f"Key is not known here: {fingerprint}")
        revoked = replace(key, revoked=True)
        updated = replace(
            current,
            keys=tuple(revoked if k.fingerprint == fingerprint else k for k in current.keys),
        )
        store.save_trusted_publishers(
            tuple(updated if i.publisher_id == publisher_id else i for i in publishers)
        )
    return revoked


def sync_status_use_case(
    *,
    max_age_hours: float | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[StreamStatus, ...]:
    """Report every trusted origin, including one that never delivered anything."""
    resolved = resolve_runtime(runtime)
    workspaces = load_workspaces(resolved)
    return tuple(
        _stream_status(resolved, entry, max_age_hours, workspaces)
        for entry in resolved.sync_store().trust_entries()
    )


def prune_revisions_use_case(
    stream_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> PruneResult:
    """Delete revisions the active state no longer needs.

    Withdrawing removes metadata from the active view only; old revisions keep holding it until
    this runs. Copies already delivered elsewhere are out of reach, and change reports keep the
    names of what changed.
    """
    store = resolve_runtime(runtime).sync_store()
    require_identity(stream_id, "str", "stream ID")
    with store.stream_lock(stream_id):
        head = store.head(stream_id)
        if head is None:
            raise SyncFailure("stream_not_found", f"Stream has no active state: {stream_id}")
        if head.pending is not None:
            raise SyncFailure(
                "activation_pending", "Finish the unfinished activation before pruning.",
            )
        store.clear_abandoned_incoming()
        kept = {head.publication_id, head.content_activated_by}
        removed = tuple(item for item in store.revisions(stream_id) if item not in kept)
        for publication_id in removed:
            shutil.rmtree(store.revision_directory(stream_id, publication_id))
    return PruneResult(stream_id, removed, tuple(sorted(kept)))


def _stream_status(
    runtime: TarelRuntime,
    entry: TrustEntry,
    max_age_hours: float | None,
    workspaces: tuple[WorkspaceDocument, ...],
) -> StreamStatus:
    store = runtime.sync_store()
    head = store.head(entry.stream_id)
    status = store.status(entry.stream_id)
    received, failure = status.get("last_received"), status.get("last_failure")
    if head is None:
        return StreamStatus(
            stream_id=entry.stream_id,
            publisher_id=entry.publisher_id,
            local_graph=entry.local_graph,
            last_received=received,
            last_failure=failure,
        )
    impacts = store.impacts(entry.stream_id, head.content_activated_by) or ActiveImpacts()
    age = _age_seconds(head)
    return StreamStatus(
        stream_id=entry.stream_id,
        publisher_id=entry.publisher_id,
        local_graph=entry.local_graph,
        active_publication_id=head.publication_id,
        active_sequence=head.sequence,
        active_content_revision=head.content_revision,
        observed_at=head.observed_at,
        accepted_at=head.accepted_at,
        observation_age_seconds=age,
        stale=None if max_age_hours is None else age > max_age_hours * 3600,
        activation_pending=head.pending is not None,
        last_received=received,
        last_failure=failure,
        removals=impacts.removals,
        retired_claims=impacts.retired_claims,
        dangling_references=dangling_for_graph(
            runtime, entry.local_graph, impacts.removals, workspaces=workspaces,
        ),
        retained_revisions=len(store.revisions(entry.stream_id)),
    )


def _age_seconds(head: StreamHead) -> int:
    observed = instant(head.observed_at)
    return int((datetime.now(UTC) - observed).total_seconds())
