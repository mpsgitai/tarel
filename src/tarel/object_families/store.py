"""Atomic private storage for graph-bound object-family declarations."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol

from tarel.object_families.contracts import ObjectFamily, ObjectFamilyFailure, validate_family

_PATH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ObjectFamilyStore(Protocol):
    def save(self, family: ObjectFamily) -> Path | str | None: ...

    def load(self, graph_name: str, family_id: str) -> ObjectFamily: ...

    def list(self, graph_name: str) -> tuple[str, ...]: ...

    def exists(self, graph_name: str, family_id: str) -> bool: ...


class FileObjectFamilyStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "object-families"

    def save(self, family: ObjectFamily) -> Path:
        validate_family(family)
        path = self.path(family.graph_name, family.id)
        payload = json.dumps(family.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=path.parent, prefix=".family-", suffix=".tmp", text=True
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise ObjectFamilyFailure(
                "object_family_save_failed", "Could not save object-family declaration."
            ) from exc
        return path

    def load(self, graph_name: str, family_id: str) -> ObjectFamily:
        path = self.path(graph_name, family_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        except FileNotFoundError as exc:
            raise ObjectFamilyFailure(
                "object_family_not_found", "Object-family declaration not found."
            ) from exc
        except (OSError, ValueError) as exc:
            raise ObjectFamilyFailure(
                "invalid_object_family", "Could not read object-family declaration."
            ) from exc
        if not isinstance(payload, dict) or "revision" not in payload:
            raise ObjectFamilyFailure(
                "invalid_object_family", "Stored object families require a content revision."
            )
        family = ObjectFamily.from_dict(payload)
        if family.graph_name != graph_name or family.id != family_id:
            raise ObjectFamilyFailure(
                "invalid_object_family", "Stored object-family identity does not match its path."
            )
        return family

    def list(self, graph_name: str) -> tuple[str, ...]:
        directory = self._directory(graph_name)
        if not directory.exists():
            return ()
        try:
            paths = tuple(directory.glob("*.json"))
            for path in paths:
                self.path(graph_name, path.stem)
            return tuple(sorted(path.stem for path in paths if path.is_file()))
        except OSError as exc:
            raise ObjectFamilyFailure(
                "object_family_list_failed", "Could not list object-family declarations."
            ) from exc

    def exists(self, graph_name: str, family_id: str) -> bool:
        return self.path(graph_name, family_id).is_file()

    def path(self, graph_name: str, family_id: str) -> Path:
        _path_id(family_id)
        path = self._directory(graph_name) / f"{family_id}.json"
        self._within_root(path)
        return path

    def _directory(self, graph_name: str) -> Path:
        _path_id(graph_name)
        directory = self.root / graph_name
        self._within_root(directory)
        return directory

    def _within_root(self, path: Path) -> None:
        try:
            valid = path.resolve().is_relative_to(self.root.resolve())
        except (OSError, RuntimeError) as exc:
            raise ObjectFamilyFailure(
                "invalid_object_family_path", "Could not resolve object-family path safely."
            ) from exc
        if not valid:
            raise ObjectFamilyFailure(
                "invalid_object_family_path", "Object-family paths must remain inside their store."
            )


def _path_id(value: object) -> None:
    if not isinstance(value, str) or not _PATH_ID.fullmatch(value):
        raise ObjectFamilyFailure(
            "invalid_object_family_path", "Object-family graph and ID must be safe identifiers."
        )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field in object-family document.")
        result[key] = value
    return result
