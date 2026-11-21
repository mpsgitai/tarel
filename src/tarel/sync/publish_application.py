"""Use cases of a publishing site: its identity, its streams and the files it writes."""

from __future__ import annotations

import os
import secrets
import tempfile
from dataclasses import replace
from pathlib import Path

from tarel.graph.contracts import GraphDocument
from tarel.packages.application import pack_workspace
from tarel.packages.archive import PackageArchive, read_manifest
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.sync.contracts import (
    COMPLETENESS_VALUES,
    OBSERVATION_RECORDED,
    OBSERVATION_STATED,
    RECENT_PUBLICATIONS,
    ExportScope,
    Publication,
    PublisherStream,
    SyncFailure,
    require_name,
    require_timestamp,
    sha256_hex,
)
from tarel.sync.envelope import (
    PUBLICATION_SUFFIX,
    content_revision,
    statement_bytes,
    write_envelope,
)
from tarel.sync.export import export_graph
from tarel.sync.results import PublishResult
from tarel.sync.signing import key_fingerprint, read_signing_identity, sign_statement
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceSystem


def init_publisher_use_case(*, runtime: TarelRuntime | None = None) -> str:
    """Give this site its identity once. Host, path and cloud play no part in it."""
    store = resolve_runtime(runtime).sync_store()
    with store.configuration_lock():
        existing = store.publisher_id()
        if existing is not None:
            return existing
        publisher_id = _new_identity("pub")
        store.save_publisher_id(publisher_id)
        return publisher_id


def create_stream_use_case(
    name: str,
    *,
    graph: str,
    namespaces: tuple[str, ...],
    annotations: bool = False,
    technical_descriptions: bool = False,
    runtime: TarelRuntime | None = None,
) -> PublisherStream:
    """Name one export of one graph. Overlapping exports are refused rather than arbitrated."""
    resolved = resolve_runtime(runtime)
    store = resolved.sync_store()
    resolved.graph_store().load(graph)
    if not namespaces:
        raise SyncFailure("invalid_scope", "A stream must approve at least one namespace.")
    with store.configuration_lock():
        if store.publisher_id() is None:
            raise SyncFailure("publisher_not_initialized", "Run tarel sync init first.")
        streams = store.publisher_streams()
        if any(other.name == name for other in streams):
            raise SyncFailure("stream_exists", f"Stream already exists: {name}")
        _check_overlap(streams, name, graph, namespaces)
        graph_ids = store.graph_ids()
        if graph not in graph_ids:
            graph_ids[graph] = _new_identity("gph")
            store.save_graph_ids(graph_ids)
        stream = PublisherStream(
            name=require_name(name, "stream name"),
            stream_id=_new_identity("str"),
            graph=graph,
            graph_id=graph_ids[graph],
            scope=ExportScope(tuple(sorted(set(namespaces))), annotations, technical_descriptions),
        )
        store.save_publisher_stream(stream)
        return stream


def update_stream_use_case(
    name: str,
    *,
    namespaces: tuple[str, ...],
    annotations: bool = False,
    technical_descriptions: bool = False,
    runtime: TarelRuntime | None = None,
) -> PublisherStream:
    """Change what a stream approves. The new profile version makes the change visible centrally."""
    store = resolve_runtime(runtime).sync_store()
    if not namespaces:
        raise SyncFailure("invalid_scope", "A stream must approve at least one namespace.")
    scope = ExportScope(tuple(sorted(set(namespaces))), annotations, technical_descriptions)
    with store.configuration_lock():
        stream = store.publisher_stream(name)
        if scope.digest == stream.scope.digest:
            return stream
        _check_overlap(store.publisher_streams(), name, stream.graph, namespaces)
        updated = replace(stream, scope=scope, profile_version=stream.profile_version + 1)
        store.save_publisher_stream(updated)
        return updated


def publish_use_case(
    stream_name: str,
    *,
    output: Path,
    observed_at: str | None = None,
    completeness: str | None = None,
    signing_key: Path | None = None,
    unsigned_dev: bool = False,
    runtime: TarelRuntime | None = None,
) -> PublishResult:
    """Write one publication file. The counter moves first, so a number is never used twice.

    Without ``observed_at`` the facts come from this state's own record of reading the source.
    Passing it instead states them on the caller's word, and the file says which of the two it is.
    """
    resolved = resolve_runtime(runtime)
    store = resolved.sync_store()
    output = Path(os.path.abspath(output))
    if output.suffix != PUBLICATION_SUFFIX:
        raise SyncFailure("invalid_publication_path", f"Output must end in {PUBLICATION_SUFFIX}.")
    if os.path.lexists(output):
        raise SyncFailure("publication_exists", f"Publication already exists: {output}")
    if (signing_key is None) == (not unsigned_dev):
        raise SyncFailure(
            "signing_key_required",
            "Name a signing key, or choose an unsigned file for local development only.",
        )
    identity = read_signing_identity(signing_key) if signing_key is not None else None
    if observed_at is None and completeness is not None:
        raise SyncFailure(
            "invalid_completeness", "Completeness can only be stated together with observed_at.",
        )
    if completeness is not None and completeness not in COMPLETENESS_VALUES:
        raise SyncFailure("invalid_completeness", f"Unknown completeness: {completeness}")
    if observed_at is not None:
        require_timestamp(observed_at, "observed_at")
    with store.configuration_lock():
        publisher_id = store.publisher_id()
        if publisher_id is None:
            raise SyncFailure("publisher_not_initialized", "Run tarel sync init first.")
        stream = store.publisher_stream(stream_name)
        observation = _observation_facts(
            resolved, stream, observed_at, completeness,
        )
        exported = export_graph(resolved.graph_store().load(stream.graph), stream.scope)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent, prefix=".publication-") as temporary:
            package = _pack(exported, stream.stream_id, Path(temporary))
            with PackageArchive(str(package)) as archive:
                revision = content_revision(read_manifest(archive))
            publication = Publication(
                publisher_id=publisher_id,
                graph_id=stream.graph_id,
                stream_id=stream.stream_id,
                sequence=stream.sequence + 1,
                recent_publications=stream.recent_publications,
                content_revision=revision,
                profile_id=stream.name,
                profile_version=stream.profile_version,
                scope=stream.scope,
                completeness=observation[1],
                observed_at=observation[0],
                package_sha256=sha256_hex(package.read_bytes()),
                observation_source=observation[2],
                signing_key=key_fingerprint(identity[1]) if identity else None,
            )
            statement = statement_bytes(publication)
            publication_id = sha256_hex(statement)
            envelope = Path(temporary) / "envelope"
            signature = sign_statement(statement, identity[0]) if identity else None
            write_envelope(envelope, package, statement, signature)
            with envelope.open("rb") as written:
                os.fsync(written.fileno())
            store.save_publisher_stream(
                replace(
                    stream,
                    sequence=publication.sequence,
                    recent_publications=(publication_id, *stream.recent_publications)[
                        :RECENT_PUBLICATIONS
                    ],
                )
            )
            try:
                os.link(envelope, output)
            except OSError as exc:
                raise SyncFailure(
                    "publication_write_failed", f"Could not publish {output}: {exc.strerror}"
                ) from exc
            artifact_sha256 = sha256_hex(output.read_bytes())
    return PublishResult(str(output), publication_id, publication, artifact_sha256)


def _check_overlap(
    streams: tuple[PublisherStream, ...], name: str, graph: str, namespaces: tuple[str, ...],
) -> None:
    for other in streams:
        shared = set(namespaces) & set(other.scope.namespaces)
        if other.name != name and other.graph == graph and shared:
            raise SyncFailure(
                "overlapping_stream",
                f"Stream {other.name} already publishes {sorted(shared)} of graph {graph}.",
            )


def _observation_facts(
    runtime: TarelRuntime,
    stream: PublisherStream,
    observed_at: str | None,
    completeness: str | None,
) -> tuple[str, str, str]:
    """When the source was read, whether that covered the scope, and who says so."""
    if observed_at is not None:
        return observed_at, completeness or "complete", OBSERVATION_STATED
    observation = runtime.graph_store().observation(stream.graph)
    if observation is None or observation.observed_at is None:
        raise SyncFailure(
            "observation_missing",
            f"No read of graph {stream.graph} is on record; refresh it or state --observed-at.",
        )
    if observation.failure is not None:
        raise SyncFailure(
            "observation_failed",
            f"The last read of graph {stream.graph} failed ({observation.failure['code']}); "
            "publishing now would present old metadata as a new observation.",
        )
    covered = observation.namespace is None or set(stream.scope.namespaces) <= {
        observation.namespace
    }
    return observation.observed_at, "complete" if covered else "partial", OBSERVATION_RECORDED


def _new_identity(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(13)}"


def _pack(exported: GraphDocument, workspace_name: str, temporary: Path) -> Path:
    """Build a throwaway state holding only the export, so nothing else can reach the package."""
    state = TarelRuntime.local(temporary / "state")
    state.graph_store().save(exported)
    state.workspace_store().save(
        WorkspaceDocument(
            name=workspace_name,
            systems=(WorkspaceSystem(name="source", graphs=(exported.name,)),),
        )
    )
    package = temporary / "package.tarel"
    pack_workspace(state.root, workspace_name, package)
    return package
