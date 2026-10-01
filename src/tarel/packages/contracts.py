"""Versioned contracts for portable TAREL metadata packages."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tarel import __version__

PACKAGE_CONTRACT_VERSION = "tarel.package.v0.1"
PACKAGE_MEDIA_TYPE = "application/vnd.tarel+zip"
MIMETYPE_PATH = "mimetype"
MANIFEST_PATH = "manifest.json"
MIMETYPE_BYTES = f"{PACKAGE_MEDIA_TYPE}\n".encode()
MAX_MEMBER_BYTES = 512 * 1024 * 1024
DOCUMENT_KINDS = frozenset({"focus", "graph", "knowledge", "lineage", "workspace"})
AUXILIARY_SCOPE = "all lineage and knowledge; compatible focuses"
OMISSIONS = (
    "analytical result sets and source rows",
    "connector and provider configuration",
    "credentials and secrets",
    "graph selective caches and search indexes",
    "lineage analysis caches",
    "logs and temporary files",
)
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class PackageFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PackageEntry:
    path: str
    kind: str
    name: str
    contract_version: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackageEntry:
        if set(data) != {"contract_version", "kind", "name", "path", "sha256", "size"}:
            raise PackageFailure("invalid_package_manifest", "Invalid package entry fields.")
        path = _required_text(data, "path")
        kind = _required_text(data, "kind")
        name = _required_text(data, "name")
        contract_version = _required_text(data, "contract_version")
        digest = _required_text(data, "sha256")
        size = data.get("size")
        if kind not in DOCUMENT_KINDS or not _is_sha256(digest):
            raise PackageFailure("invalid_package_manifest", f"Invalid package entry: {path}")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= MAX_MEMBER_BYTES
        ):
            raise PackageFailure("invalid_package_manifest", f"Invalid entry size: {path}")
        validate_portable_path(path)
        expected_kind, expected_name = entry_identity(path)
        if (kind, name) != (expected_kind, expected_name):
            raise PackageFailure(
                "invalid_package_manifest", f"Entry identity does not match its path: {path}"
            )
        return cls(path, kind, name, contract_version, digest, size)


@dataclass(frozen=True, slots=True)
class PackageManifest:
    workspace: str
    entries: tuple[PackageEntry, ...]
    package_revision: str
    producer_name: str = "tarel"
    producer_version: str = __version__
    contract_version: str = PACKAGE_CONTRACT_VERSION
    media_type: str = PACKAGE_MEDIA_TYPE

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "created_by": {"name": self.producer_name, "version": self.producer_version},
            "entries": [entry.to_dict() for entry in self.entries],
            "media_type": self.media_type,
            "omissions": list(OMISSIONS),
            "selection": {
                "auxiliary_scope": AUXILIARY_SCOPE,
                "kind": "workspace",
                "name": self.workspace,
            },
        }
        if include_revision:
            payload["package_revision"] = self.package_revision
        return payload

    @classmethod
    def create(cls, workspace: str, entries: tuple[PackageEntry, ...]) -> PackageManifest:
        provisional = cls(workspace=workspace, entries=entries, package_revision="")
        return provisional._with_computed_revision()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackageManifest:
        expected = {
            "contract_version",
            "created_by",
            "entries",
            "media_type",
            "omissions",
            "package_revision",
            "selection",
        }
        if set(data) != expected:
            raise PackageFailure("invalid_package_manifest", "Invalid package manifest fields.")
        if data.get("contract_version") != PACKAGE_CONTRACT_VERSION:
            raise PackageFailure("unsupported_package", "Unsupported TAREL package contract.")
        if data.get("media_type") != PACKAGE_MEDIA_TYPE:
            raise PackageFailure("invalid_package_manifest", "Invalid TAREL package media type.")
        created_by = data.get("created_by")
        if not isinstance(created_by, dict) or set(created_by) != {"name", "version"}:
            raise PackageFailure("invalid_package_manifest", "Invalid package producer.")
        producer_name = _required_text(created_by, "name")
        producer_version = _required_text(created_by, "version")
        if data.get("omissions") != list(OMISSIONS):
            raise PackageFailure("invalid_package_manifest", "Invalid package omission policy.")
        selection = data.get("selection")
        if not isinstance(selection, dict) or set(selection) != {
            "auxiliary_scope",
            "kind",
            "name",
        }:
            raise PackageFailure("invalid_package_manifest", "Invalid package selection.")
        if selection.get("kind") != "workspace":
            raise PackageFailure("invalid_package_manifest", "Package must select one workspace.")
        if selection.get("auxiliary_scope") != AUXILIARY_SCOPE:
            raise PackageFailure("invalid_package_manifest", "Invalid package auxiliary scope.")
        workspace = _required_text(selection, "name")
        entry_values = data.get("entries")
        if not isinstance(entry_values, list):
            raise PackageFailure("invalid_package_manifest", "Package entries must be an array.")
        entries = tuple(PackageEntry.from_dict(_object(item)) for item in entry_values)
        paths = [entry.path for entry in entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise PackageFailure(
                "invalid_package_manifest", "Package entries must be unique and sorted."
            )
        revision = _required_text(data, "package_revision")
        if not _is_sha256(revision):
            raise PackageFailure("invalid_package_manifest", "Invalid package revision.")
        manifest = cls(
            workspace=workspace,
            entries=entries,
            package_revision=revision,
            producer_name=producer_name,
            producer_version=producer_version,
        )
        if revision != manifest._with_computed_revision().package_revision:
            raise PackageFailure(
                "invalid_package_manifest", "Package manifest revision does not match its contents."
            )
        return manifest

    def _with_computed_revision(self) -> PackageManifest:
        revision = sha256(canonical_json(self.to_dict(include_revision=False)))
        return PackageManifest(
            workspace=self.workspace,
            entries=self.entries,
            package_revision=revision,
            producer_name=self.producer_name,
            producer_version=self.producer_version,
        )


@dataclass(frozen=True, slots=True)
class PackageReport:
    path: Path
    workspace: str
    entries: int
    kinds: dict[str, int]
    uncompressed_bytes: int
    package_bytes: int
    package_revision: str
    verified: bool
    destination: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "destination": str(self.destination) if self.destination is not None else None,
            "entries": self.entries,
            "kinds": self.kinds,
            "package_bytes": self.package_bytes,
            "package_revision": self.package_revision,
            "path": str(self.path),
            "uncompressed_bytes": self.uncompressed_bytes,
            "verified": self.verified,
            "workspace": self.workspace,
        }


def entry_identity(path: str) -> tuple[str, str]:
    parts = PurePosixPath(path).parts
    patterns = {
        ("focus", "focus.json"): "focus",
        ("graphs", "graph.json"): "graph",
        ("knowledge", "document.json"): "knowledge",
        ("lineage", "lineage.json"): "lineage",
        ("workspaces", "workspace.json"): "workspace",
    }
    if len(parts) != 3 or (parts[0], parts[2]) not in patterns:
        raise PackageFailure("invalid_package_path", f"Unsupported package entry path: {path}")
    return patterns[(parts[0], parts[2])], parts[1]


def validate_portable_path(name: str) -> None:
    if not name or len(name) > 512 or "\\" in name or name.endswith("/"):
        raise PackageFailure("invalid_package_path", f"Unsafe package path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PackageFailure("invalid_package_path", f"Unsafe package path: {name!r}")
    for part in path.parts:
        if part.endswith((" ", ".")) or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
            raise PackageFailure("invalid_package_path", f"Non-portable package path: {name!r}")


def package_report(
    path: Path,
    manifest: PackageManifest,
    *,
    verified: bool,
    destination: Path | None = None,
) -> PackageReport:
    kinds = dict(sorted(Counter(entry.kind for entry in manifest.entries).items()))
    try:
        package_bytes = path.stat().st_size
    except OSError:
        package_bytes = 0
    return PackageReport(
        path=path,
        workspace=manifest.workspace,
        entries=len(manifest.entries),
        kinds=kinds,
        uncompressed_bytes=sum(entry.size for entry in manifest.entries),
        package_bytes=package_bytes,
        package_revision=manifest.package_revision,
        verified=verified,
        destination=destination,
    )


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def pretty_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise PackageFailure("invalid_package_manifest", f"Manifest field must be text: {key}")
    return value


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PackageFailure("invalid_package_manifest", "Package entry must be an object.")
    return value


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
