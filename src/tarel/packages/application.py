"""Application use cases for portable ``.tarel`` metadata packages.

The editable representation remains the normal directory tree. A package is a
deterministic ZIP envelope containing only authoritative, portable JSON
documents plus a checksummed manifest. Rebuildable indexes, local connector
configuration, credentials, and source data remain outside this boundary.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any

from tarel.focus.contracts import FocusDocument
from tarel.graph.contracts import GraphDocument
from tarel.knowledge.contracts import KnowledgeDocument
from tarel.lineage.contracts import LineageDocument
from tarel.packages.archive import (
    PackageArchive,
    parse_json_object,
    read_manifest,
    read_member,
    validate_declared_members,
    write_bytes,
    write_document,
    write_manifest,
)
from tarel.packages.contracts import (
    MAX_MEMBER_BYTES,
    MIMETYPE_BYTES,
    MIMETYPE_PATH,
    PACKAGE_CONTRACT_VERSION,
    PACKAGE_MEDIA_TYPE,
    PackageEntry,
    PackageFailure,
    PackageManifest,
    PackageReport,
    entry_identity,
    package_report,
    sha256,
)
from tarel.workspaces.contracts import WorkspaceDocument

_CHUNK_SIZE = 1024 * 1024
_DOCUMENT_READERS: dict[str, Callable[[dict[str, Any]], object]] = {
    "focus": FocusDocument.from_dict,
    "graph": GraphDocument.from_dict,
    "knowledge": KnowledgeDocument.from_dict,
    "lineage": LineageDocument.from_dict,
    "workspace": WorkspaceDocument.from_dict,
}


def pack_workspace(
    state_root: Path,
    workspace: str,
    output: Path,
    *,
    replace: bool = False,
) -> PackageReport:
    """Pack one workspace and its portable metadata into a ``.tarel`` file."""
    state_root = state_root.resolve()
    output = output.resolve()
    if output.suffix.lower() != ".tarel":
        raise PackageFailure("invalid_package_path", "Package output must use the .tarel suffix.")
    if output.exists() and not replace:
        raise PackageFailure("package_exists", f"Package already exists: {output}")
    temporary: Path | None = None
    entries: list[PackageEntry] = []
    try:
        sources = _select_workspace_documents(state_root, workspace)
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output.parent, prefix=f".{output.stem}-", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        os.close(descriptor)
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            write_bytes(archive, MIMETYPE_PATH, MIMETYPE_BYTES, compressed=False)
            for archive_path, source_path in sources:
                kind, name = entry_identity(archive_path)
                data = _read_source_document(source_path)
                contract_version = _validate_document(data, kind, name)
                digest, size = write_document(archive, archive_path, data)
                entries.append(
                    PackageEntry(
                        path=archive_path,
                        kind=kind,
                        name=name,
                        contract_version=contract_version,
                        sha256=digest,
                        size=size,
                    )
                )
            manifest = PackageManifest.create(workspace, tuple(entries))
            _validate_package_references(manifest, None)
            write_manifest(archive, manifest)
        verify_package(temporary)
        os.replace(temporary, output)
    except PackageFailure:
        _remove_temporary(temporary)
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        _remove_temporary(temporary)
        raise PackageFailure("package_write_failed", f"Could not write package: {output}") from exc
    except Exception:
        _remove_temporary(temporary)
        raise
    return package_report(output, manifest, verified=True)


def inspect_package(path: Path) -> PackageReport:
    """Read the bounded manifest without expanding package documents."""
    path = path.resolve()
    with PackageArchive(str(path)) as archive:
        manifest = read_manifest(archive)
        validate_declared_members(archive, manifest)
    return package_report(path, manifest, verified=False)


def verify_package(path: Path) -> PackageReport:
    """Verify archive safety, checksums, contracts, identities, and references."""
    path = path.resolve()
    with PackageArchive(str(path)) as archive:
        manifest = _verify_open_archive(archive)
    return package_report(path, manifest, verified=True)


def unpack_package(path: Path, destination: Path) -> PackageReport:
    """Verify and extract into a new state root; merge and overwrite are not supported."""
    path = path.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise PackageFailure(
            "package_destination_exists",
            "Package destination must not exist; unpacking never merges or overwrites state.",
        )
    with PackageArchive(str(path)) as archive:
        manifest = _verify_open_archive(archive)
        verified = package_report(path, manifest, verified=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}-"))
        try:
            for entry in manifest.entries:
                target = staging.joinpath(*PurePosixPath(entry.path).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry.path, "r") as source, target.open("xb") as sink:
                    shutil.copyfileobj(source, sink, length=_CHUNK_SIZE)
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return PackageReport(
        path=verified.path,
        workspace=verified.workspace,
        entries=verified.entries,
        kinds=verified.kinds,
        uncompressed_bytes=verified.uncompressed_bytes,
        package_bytes=verified.package_bytes,
        package_revision=verified.package_revision,
        verified=True,
        destination=destination,
    )


def _verify_open_archive(archive: zipfile.ZipFile) -> PackageManifest:
    manifest = read_manifest(archive)
    validate_declared_members(archive, manifest)
    documents: dict[str, object] = {}
    for entry in manifest.entries:
        data = read_member(archive, entry.path, entry.size)
        if sha256(data) != entry.sha256:
            raise PackageFailure(
                "package_checksum_mismatch", f"Checksum mismatch: {entry.path}"
            )
        contract_version = _validate_document(data, entry.kind, entry.name)
        if contract_version != entry.contract_version:
            raise PackageFailure(
                "invalid_package_document", f"Contract mismatch: {entry.path}"
            )
        documents[entry.path] = _parse_document(data, entry.kind)
    _validate_package_references(manifest, documents)
    return manifest


def _select_workspace_documents(
    state_root: Path, workspace_name: str
) -> tuple[tuple[str, Path], ...]:
    workspace_path = state_root / "workspaces" / workspace_name / "workspace.json"
    workspace = _load_local_document(workspace_path, "workspace", workspace_name)
    assert isinstance(workspace, WorkspaceDocument)
    graph_names = sorted({name for system in workspace.systems for name in system.graphs})
    selected: list[tuple[str, Path]] = [
        (f"graphs/{name}/graph.json", state_root / "graphs" / name / "graph.json")
        for name in graph_names
    ]
    selected.append((f"workspaces/{workspace_name}/workspace.json", workspace_path))

    lineage_names = _local_names(state_root / "lineage", "lineage.json")
    selected.extend(
        (f"lineage/{name}/lineage.json", state_root / "lineage" / name / "lineage.json")
        for name in lineage_names
    )
    knowledge_names = _local_names(state_root / "knowledge", "document.json")
    selected.extend(
        (f"knowledge/{name}/document.json", state_root / "knowledge" / name / "document.json")
        for name in knowledge_names
    )
    graph_set = set(graph_names)
    lineage_set = set(lineage_names)
    for name in _local_names(state_root / "focus", "focus.json"):
        focus_path = state_root / "focus" / name / "focus.json"
        focus = _load_local_document(focus_path, "focus", name)
        assert isinstance(focus, FocusDocument)
        if all(
            source.name in (graph_set if source.kind == "graph" else lineage_set)
            for source in focus.sources
        ):
            selected.append((f"focus/{name}/focus.json", focus_path))
    selected.sort(key=lambda item: item[0])
    for _, source in selected:
        if not source.is_file():
            raise PackageFailure("package_source_missing", f"Package source missing: {source}")
    return tuple(selected)


def _local_names(root: Path, filename: str) -> tuple[str, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(path.parent.name for path in root.glob(f"*/{filename}") if path.is_file()))


def _load_local_document(path: Path, kind: str, name: str) -> object:
    data = _read_source_document(path)
    _validate_document(data, kind, name)
    return _parse_document(data, kind)


def _read_source_document(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_MEMBER_BYTES:
            raise PackageFailure("package_too_large", f"Package source is too large: {path}")
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise PackageFailure("package_source_missing", f"Package source missing: {path}") from exc
    except OSError as exc:
        raise PackageFailure(
            "package_source_read_failed", f"Could not read package source: {path}"
        ) from exc
    if len(data) > MAX_MEMBER_BYTES:
        raise PackageFailure("package_too_large", f"Package source is too large: {path}")
    return data


def _remove_temporary(path: Path | None) -> None:
    if path is None:
        return
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _validate_document(data: bytes, kind: str, name: str) -> str:
    document = _parse_document(data, kind)
    identity = document.id if isinstance(document, KnowledgeDocument) else document.name
    if identity != name:
        raise PackageFailure(
            "invalid_package_document", f"{kind.title()} identity does not match its path: {name}"
        )
    return document.contract_version


def _parse_document(data: bytes, kind: str) -> object:
    payload = parse_json_object(data, f"{kind} document")
    try:
        return _DOCUMENT_READERS[kind](payload)
    except PackageFailure:
        raise
    except (AttributeError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        raise PackageFailure(
            "invalid_package_document", f"Invalid {kind} document: {exc}"
        ) from exc


def _validate_package_references(
    manifest: PackageManifest, documents: dict[str, object] | None
) -> None:
    entries_by_kind: dict[str, set[str]] = {}
    for entry in manifest.entries:
        entries_by_kind.setdefault(entry.kind, set()).add(entry.name)
    if entries_by_kind.get("workspace") != {manifest.workspace}:
        raise PackageFailure(
            "invalid_package_references", "Package must contain exactly its selected workspace."
        )
    if documents is None:
        return
    workspace_path = f"workspaces/{manifest.workspace}/workspace.json"
    workspace = documents.get(workspace_path)
    if not isinstance(workspace, WorkspaceDocument):
        raise PackageFailure("invalid_package_references", "Selected workspace is missing.")
    referenced_graphs = {name for system in workspace.systems for name in system.graphs}
    packaged_graphs = entries_by_kind.get("graph", set())
    if referenced_graphs != packaged_graphs:
        missing = sorted(referenced_graphs - packaged_graphs)
        extra = sorted(packaged_graphs - referenced_graphs)
        detail = "; ".join(
            item
            for item in (
                f"missing={missing}" if missing else "",
                f"extra={extra}" if extra else "",
            )
            if item
        )
        raise PackageFailure(
            "invalid_package_references", f"Workspace graph membership mismatch: {detail}"
        )
    for entry in manifest.entries:
        if entry.kind != "focus":
            continue
        focus = documents.get(entry.path)
        if not isinstance(focus, FocusDocument):
            continue
        for source in focus.sources:
            if source.name not in entries_by_kind.get(source.kind, set()):
                raise PackageFailure(
                    "invalid_package_references",
                    f"Focus {focus.name} source is missing: {source.kind}/{source.name}",
                )


__all__ = [
    "PACKAGE_CONTRACT_VERSION",
    "PACKAGE_MEDIA_TYPE",
    "PackageFailure",
    "PackageReport",
    "inspect_package",
    "pack_workspace",
    "unpack_package",
    "verify_package",
]
