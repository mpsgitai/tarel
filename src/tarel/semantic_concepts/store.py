"""Atomic local semantic-concept sidecars with strict identity validation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from tarel.semantic_concepts.contracts import SemanticConceptDocument, SemanticConceptFailure


class FileSemanticConceptStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "semantic-concepts"

    def save(self, document: SemanticConceptDocument) -> Path:
        checked = SemanticConceptDocument.from_dict(document.to_dict())
        path = self.path(checked.graph_name)
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".concept-", suffix=".tmp")
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(checked.to_dict(), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise SemanticConceptFailure(
                "semantic_concepts_save_failed",
                "Could not save semantic concept declarations.",
            ) from exc
        return path

    def load(self, graph_name: str) -> SemanticConceptDocument:
        path = self.path(graph_name)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        except FileNotFoundError as exc:
            raise SemanticConceptFailure(
                "semantic_concepts_not_found",
                "Semantic concept declarations not found.",
            ) from exc
        except (OSError, ValueError) as exc:
            raise SemanticConceptFailure(
                "invalid_semantic_concepts",
                "Could not read semantic concept declarations.",
            ) from exc
        if not isinstance(payload, dict) or "revision" not in payload:
            raise SemanticConceptFailure(
                "invalid_semantic_concepts",
                "Stored concepts require a content revision.",
            )
        document = SemanticConceptDocument.from_dict(payload)
        if document.graph_name != graph_name:
            raise SemanticConceptFailure(
                "invalid_semantic_concepts",
                "Stored concept identity does not match its path.",
            )
        return document

    def exists(self, graph_name: str) -> bool:
        return self.path(graph_name).is_file()

    def path(self, graph_name: str) -> Path:
        if not isinstance(graph_name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
            graph_name,
        ):
            raise SemanticConceptFailure(
                "invalid_semantic_concepts_path",
                "Graph names must be safe identifiers.",
            )
        path = self.root / graph_name / "concepts.json"
        try:
            contained = path.resolve().is_relative_to(self.root.resolve())
        except (OSError, RuntimeError) as exc:
            raise SemanticConceptFailure(
                "invalid_semantic_concepts_path",
                "Could not resolve semantic concept path.",
            ) from exc
        if not contained:
            raise SemanticConceptFailure(
                "invalid_semantic_concepts_path",
                "Concept files must remain inside their store.",
            )
        return path


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field in semantic concepts.")
        result[key] = value
    return result
