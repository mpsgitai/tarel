"""The ``.tarelpub`` file: an unchanged ``.tarel`` package plus a statement about it.

Hash order has no cycle: package bytes -> ``package_sha256`` inside ``publication.json`` -> the
signature over that file's exact bytes. The statement is parsed but never written again, so no JSON
canonicalization has to agree between sites.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from tarel.graph.contracts import GraphDocument
from tarel.packages.application import verify_package
from tarel.packages.archive import (
    PackageArchive,
    parse_json_object,
    read_manifest,
    read_member,
    write_bytes,
)
from tarel.packages.contracts import PackageFailure, PackageManifest, pretty_json
from tarel.sync.contracts import Publication, SyncFailure, sha256_hex

PUBLICATION_SUFFIX = ".tarelpub"
PACKAGE_MEMBER = "package.tarel"
PUBLICATION_MEMBER = "publication.json"
SIGNATURE_MEMBER = "publication.sig"
# Far below the general package limits: this input arrives from another installation.
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_RATIO_CHECK_FROM_BYTES = 1024 * 1024
_MAX_STATEMENT_BYTES = 1024 * 1024
_MAX_SIGNATURE_BYTES = 64 * 1024
_MAX_ENVELOPE_MEMBERS = 3
_MAX_PACKAGE_MEMBERS = 16
_ZIP_TRAILER_SEARCH = 22 + 65535
_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class OpenedPublication:
    """A verified package and the exact statement bytes, read from a private copy."""

    publication_id: str
    artifact_sha256: str
    signed: bool
    publication: Publication
    graph: GraphDocument


@dataclass(frozen=True, slots=True)
class SignedStatement:
    """A file's statement and signature. Nothing of its package has been expanded yet."""

    publication_id: str
    artifact_sha256: str
    publication: Publication
    statement: bytes
    signature: bytes | None


def content_revision(manifest: PackageManifest) -> str:
    """Identity of the transferred content, free of TAREL versions and ZIP implementations."""
    lines = sorted(f"{entry.path} {entry.sha256}\n" for entry in manifest.entries)
    return sha256_hex("".join(lines).encode("utf-8"))


def statement_bytes(publication: Publication) -> bytes:
    return pretty_json(publication.to_dict())


def write_envelope(
    path: Path, package: Path, statement: bytes, signature: bytes | None = None,
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        write_bytes(archive, PUBLICATION_MEMBER, statement, compressed=False)
        if signature is not None:
            write_bytes(archive, SIGNATURE_MEMBER, signature, compressed=False)
        info = zipfile.ZipInfo(PACKAGE_MEMBER, date_time=(1980, 1, 1, 0, 0, 0))
        with package.open("rb") as source, archive.open(info, "w", force_zip64=True) as sink:
            shutil.copyfileobj(source, sink, length=_CHUNK)


@contextmanager
def frozen_copy(path: Path, directory: Path) -> Iterator[tuple[Path, str]]:
    """Copy a delivered file to a private place and hash what was copied.

    Everything after this reads the copy, so nobody can swap the bytes between check and use. The
    copy is removed afterwards unless the caller moved it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".incoming-", suffix=".tmp")
    copy = Path(name)
    digest = _copy_hashing(path, descriptor, copy)
    try:
        yield copy, digest
    finally:
        copy.unlink(missing_ok=True)


def open_statement(path: Path, artifact_sha256: str) -> SignedStatement:
    """Read only the statement and signature, so a sender is checked before its package is."""
    with _translated_failures():
        return _read_statement(path, artifact_sha256)


def open_content(path: Path, statement: SignedStatement) -> OpenedPublication:
    """Expand and verify the package a checked statement describes."""
    with _translated_failures():
        return _read_content(path, statement)


def open_publication(path: Path, artifact_sha256: str) -> OpenedPublication:
    """Both steps at once, for a file whose sender needs no check here."""
    return open_content(path, open_statement(path, artifact_sha256))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _translated_failures() -> Iterator[None]:
    try:
        yield
    except SyncFailure:
        raise
    except PackageFailure as exc:
        # Only the code: these messages quote paths and IDs chosen by the sender.
        raise SyncFailure("invalid_package", f"Package refused ({exc.code}).") from exc
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise SyncFailure("invalid_package", "Could not read publication.") from exc


def _copy_hashing(source: Path, descriptor: int, copy: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(descriptor, "wb") as sink, source.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                total += len(chunk)
                if total > MAX_ARTIFACT_BYTES:
                    raise SyncFailure("invalid_package", f"Publication is too large: {source}")
                digest.update(chunk)
                sink.write(chunk)
            sink.flush()
            os.fsync(sink.fileno())
    except FileNotFoundError as exc:
        copy.unlink(missing_ok=True)
        raise SyncFailure("publication_not_found", f"Publication not found: {source}") from exc
    except BaseException:
        copy.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


def _read_statement(path: Path, artifact_sha256: str) -> SignedStatement:
    _check_central_directory(path, _MAX_ENVELOPE_MEMBERS)
    with PackageArchive(str(path)) as archive:
        infos = {info.filename: info for info in archive.infolist()}
        names = set(infos)
        if names - {PUBLICATION_MEMBER, PACKAGE_MEMBER, SIGNATURE_MEMBER} or not names >= {
            PUBLICATION_MEMBER,
            PACKAGE_MEMBER,
        }:
            raise SyncFailure("invalid_package", "Unexpected publication members.")
        if any(info.compress_type != zipfile.ZIP_STORED for info in infos.values()):
            raise SyncFailure("invalid_package", "A publication file stores its members unchanged.")
        statement_size = infos[PUBLICATION_MEMBER].file_size
        if statement_size > _MAX_STATEMENT_BYTES:
            raise SyncFailure("invalid_package", "Publication statement is too large.")
        statement = read_member(archive, PUBLICATION_MEMBER, statement_size)
        signature = None
        if SIGNATURE_MEMBER in infos:
            signature_size = infos[SIGNATURE_MEMBER].file_size
            if signature_size > _MAX_SIGNATURE_BYTES:
                raise SyncFailure("invalid_package", "Publication signature is too large.")
            signature = read_member(archive, SIGNATURE_MEMBER, signature_size)
    return SignedStatement(
        publication_id=sha256_hex(statement),
        artifact_sha256=artifact_sha256,
        publication=Publication.from_dict(parse_json_object(statement, "publication")),
        statement=statement,
        signature=signature,
    )


def _read_content(path: Path, statement: SignedStatement) -> OpenedPublication:
    with PackageArchive(str(path)) as archive:
        graph = _verified_graph(archive, statement.publication)
    return OpenedPublication(
        publication_id=statement.publication_id,
        artifact_sha256=statement.artifact_sha256,
        signed=statement.signature is not None,
        publication=statement.publication,
        graph=graph,
    )


def _verified_graph(archive: zipfile.ZipFile, publication: Publication) -> GraphDocument:
    with tempfile.TemporaryDirectory(prefix="tarel-publication-") as temporary:
        package = Path(temporary) / PACKAGE_MEMBER
        with archive.open(PACKAGE_MEMBER, "r") as source, package.open("wb") as sink:
            digest = _copy_member(source, sink)
        if digest != publication.package_sha256:
            raise SyncFailure("invalid_package", "Package bytes do not match the publication.")
        _check_package_bounds(package)
        verify_package(package)
        with PackageArchive(str(package)) as inner:
            manifest = read_manifest(inner)
            if content_revision(manifest) != publication.content_revision:
                raise SyncFailure("invalid_package", "Content revision does not match the package.")
            graphs = [entry for entry in manifest.entries if entry.kind == "graph"]
            others = {entry.kind for entry in manifest.entries} - {"graph", "workspace"}
            if len(graphs) != 1 or others:
                raise SyncFailure(
                    "invalid_package",
                    "A publication holds exactly one graph and its workspace; "
                    f"found {len(graphs)} graphs and {sorted(others)}.",
                )
            data = read_member(inner, graphs[0].path, graphs[0].size)
        return GraphDocument.from_dict(parse_json_object(data, "graph document"))


def _check_package_bounds(package: Path) -> None:
    """Refuse by the declared sizes, before anything is expanded."""
    _check_central_directory(package, _MAX_PACKAGE_MEMBERS)
    with PackageArchive(str(package)) as inner:
        total = 0
        for info in inner.infolist():
            total += info.file_size
            if info.file_size > MAX_EXPANDED_BYTES or total > MAX_EXPANDED_BYTES:
                raise SyncFailure("invalid_package", "Package expands beyond the sync limit.")
            if (
                info.file_size > _RATIO_CHECK_FROM_BYTES
                and info.file_size > info.compress_size * MAX_COMPRESSION_RATIO
            ):
                raise SyncFailure("invalid_package", "Unsafe compression ratio.")


def _check_central_directory(path: Path, max_members: int) -> None:
    """Read the member count from the ZIP trailer before any parser walks a huge directory."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - _ZIP_TRAILER_SEARCH))
        tail = handle.read()
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) < position + 22:
        raise SyncFailure("invalid_package", f"Not a complete ZIP file: {path.name}")
    members = int.from_bytes(tail[position + 10 : position + 12], "little")
    if members > max_members:
        raise SyncFailure("invalid_package", f"Too many members in {path.name}.")


def _copy_member(source: IO[bytes], sink: IO[bytes]) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(_CHUNK):
        digest.update(chunk)
        sink.write(chunk)
    return digest.hexdigest()
