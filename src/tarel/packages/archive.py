"""Bounded ZIP mechanics for portable TAREL packages."""

from __future__ import annotations

import json
import stat
import unicodedata
import zipfile
from typing import Any

from tarel.packages.contracts import (
    MANIFEST_PATH,
    MAX_MEMBER_BYTES,
    MIMETYPE_BYTES,
    MIMETYPE_PATH,
    PackageFailure,
    PackageManifest,
    pretty_json,
    sha256,
    validate_portable_path,
)

_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_MAX_ENTRIES = 100_000
_MAX_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 1_000


class PackageArchive:
    def __init__(self, path: str) -> None:
        self.path = path
        self.archive: zipfile.ZipFile | None = None

    def __enter__(self) -> zipfile.ZipFile:
        try:
            self.archive = zipfile.ZipFile(self.path, "r", allowZip64=True)
            _validate_archive_members(self.archive)
            return self.archive
        except FileNotFoundError as exc:
            raise PackageFailure("package_not_found", f"Package not found: {self.path}") from exc
        except PackageFailure:
            if self.archive is not None:
                self.archive.close()
                self.archive = None
            raise
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            if self.archive is not None:
                self.archive.close()
                self.archive = None
            raise PackageFailure("invalid_package", f"Could not read package: {self.path}") from exc

    def __exit__(self, *_: object) -> None:
        if self.archive is not None:
            self.archive.close()


def read_manifest(archive: zipfile.ZipFile) -> PackageManifest:
    try:
        mimetype = read_member(archive, MIMETYPE_PATH, len(MIMETYPE_BYTES))
        manifest_info = archive.getinfo(MANIFEST_PATH)
    except KeyError as exc:
        raise PackageFailure("invalid_package", "Package manifest or mimetype is missing.") from exc
    if mimetype != MIMETYPE_BYTES:
        raise PackageFailure("invalid_package", "Package mimetype is invalid.")
    if manifest_info.file_size > _MAX_MANIFEST_BYTES:
        raise PackageFailure("package_too_large", "Package manifest is too large.")
    payload = parse_json_object(
        read_member(archive, MANIFEST_PATH, manifest_info.file_size), "manifest"
    )
    return PackageManifest.from_dict(payload)


def validate_declared_members(archive: zipfile.ZipFile, manifest: PackageManifest) -> None:
    actual = {info.filename for info in archive.infolist()}
    declared = {MIMETYPE_PATH, MANIFEST_PATH, *(entry.path for entry in manifest.entries)}
    if actual != declared:
        extra = sorted(actual - declared)
        missing = sorted(declared - actual)
        detail = "; ".join(
            item
            for item in (
                f"extra={extra}" if extra else "",
                f"missing={missing}" if missing else "",
            )
            if item
        )
        raise PackageFailure("invalid_package_manifest", f"Manifest membership mismatch: {detail}")
    infos = {info.filename: info for info in archive.infolist()}
    for entry in manifest.entries:
        if infos[entry.path].file_size != entry.size:
            raise PackageFailure(
                "invalid_package_manifest", f"Manifest size mismatch: {entry.path}"
            )


def read_member(archive: zipfile.ZipFile, name: str, expected_size: int) -> bytes:
    if expected_size > MAX_MEMBER_BYTES:
        raise PackageFailure("package_too_large", f"Package entry is too large: {name}")
    try:
        with archive.open(name, "r") as handle:
            data = handle.read(expected_size + 1)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise PackageFailure("invalid_package", f"Could not read package entry: {name}") from exc
    if len(data) != expected_size:
        raise PackageFailure("invalid_package", f"Package entry size changed while reading: {name}")
    return data


def write_document(archive: zipfile.ZipFile, name: str, data: bytes) -> tuple[str, int]:
    if len(data) > MAX_MEMBER_BYTES:
        raise PackageFailure("package_too_large", f"Package entry is too large: {name}")
    write_bytes(archive, name, data, compressed=True)
    return sha256(data), len(data)


def write_manifest(archive: zipfile.ZipFile, manifest: PackageManifest) -> None:
    write_bytes(archive, MANIFEST_PATH, pretty_json(manifest.to_dict()), compressed=True)


def write_bytes(
    archive: zipfile.ZipFile, name: str, data: bytes, *, compressed: bool
) -> None:
    archive.writestr(_zip_info(name, compressed=compressed), data)


def parse_json_object(data: bytes, label: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PackageFailure("invalid_package_json", f"Invalid {label} JSON.") from exc
    if not isinstance(payload, dict):
        raise PackageFailure("invalid_package_json", f"{label.title()} must be a JSON object.")
    return payload


def _validate_archive_members(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > _MAX_ENTRIES:
        raise PackageFailure("package_too_large", "Package contains too many entries.")
    names: set[str] = set()
    normalized: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        validate_portable_path(name)
        if name in names:
            raise PackageFailure("invalid_package", f"Duplicate package path: {name}")
        folded = unicodedata.normalize("NFC", name).casefold()
        if folded in normalized:
            raise PackageFailure("invalid_package", f"Case-colliding package path: {name}")
        names.add(name)
        normalized.add(folded)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise PackageFailure("invalid_package", f"Symlinks are not allowed: {name}")
        if info.flag_bits & 0x1:
            raise PackageFailure("unsupported_package", "Encrypted ZIP members are not supported.")
        if info.file_size > MAX_MEMBER_BYTES:
            raise PackageFailure("package_too_large", f"Package entry is too large: {name}")
        total += info.file_size
        if total > _MAX_TOTAL_BYTES:
            raise PackageFailure("package_too_large", "Package expands beyond the size limit.")
        if (
            info.file_size > 0
            and info.compress_size > 0
            and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO
        ):
            raise PackageFailure("invalid_package", f"Unsafe compression ratio: {name}")


def _zip_info(name: str, *, compressed: bool) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info
