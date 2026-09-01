"""Atomic private persistence for reference-mapping candidates."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol

from tarel.reference_mapping.contracts import (
    ReferenceMappingCandidate,
    ReferenceMappingFailure,
    validate_reference_mapping_candidate,
)

_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ReferenceMappingStore(Protocol):
    def save(self, candidate: ReferenceMappingCandidate) -> Path | str | None: ...

    def load(self, candidate_id: str) -> ReferenceMappingCandidate: ...

    def list(self) -> tuple[str, ...]: ...

    def exists(self, candidate_id: str) -> bool: ...


class FileReferenceMappingStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "reference-mappings"

    def save(self, candidate: ReferenceMappingCandidate) -> Path:
        validate_reference_mapping_candidate(candidate)
        path = self.path(candidate.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            candidate.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".reference-mapping-",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise ReferenceMappingFailure(
                "reference_mapping_save_failed",
                f"Could not save reference-mapping candidate: {candidate.id}",
            ) from exc
        return path

    def load(self, candidate_id: str) -> ReferenceMappingCandidate:
        try:
            payload = json.loads(
                self.path(candidate_id).read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
        except FileNotFoundError as exc:
            raise ReferenceMappingFailure(
                "reference_mapping_not_found",
                f"Reference-mapping candidate not found: {candidate_id}",
            ) from exc
        except (OSError, ValueError) as exc:
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                f"Could not read reference-mapping candidate: {candidate_id}",
            ) from exc
        if not isinstance(payload, dict):
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                "Reference-mapping candidate root must be an object.",
            )
        candidate = ReferenceMappingCandidate.from_dict(payload)
        if candidate.id != candidate_id:
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                "Stored reference-mapping ID does not match its directory.",
            )
        return candidate

    def list(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            sorted(
                path.parent.name
                for path in self.root.glob("*/candidate.json")
                if path.is_file()
            )
        )

    def exists(self, candidate_id: str) -> bool:
        return self.path(candidate_id).is_file()

    def path(self, candidate_id: str) -> Path:
        if _CANDIDATE_ID.fullmatch(candidate_id) is None:
            raise ReferenceMappingFailure(
                "invalid_reference_mapping_id",
                "Reference-mapping IDs may contain letters, numbers, dots, underscores, "
                "and hyphens.",
            )
        return self.root / candidate_id / "candidate.json"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result
