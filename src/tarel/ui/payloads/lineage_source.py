"""SQL excerpts for the lineage panel, read on demand from the definition's own source.

Lineage documents deliberately store only a content hash, never a copy of the code. The panel
therefore rereads the source and shows it only if the bytes still match that hash, so a moved or
edited file is reported instead of displaying text the evidence lines no longer refer to.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.lineage.contracts import LineageDefinition, LineageDocument

_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_CONTEXT_LINES = 3
_MAX_EXCERPT_LINES = 200


@dataclass(frozen=True, slots=True)
class DefinitionSource:
    text: str | None
    unavailable_reason: str | None = None


def definition_source(
    document: LineageDocument,
    definition: LineageDefinition,
    roots: tuple[Path, ...],
) -> DefinitionSource:
    """Find this definition's text in its source reference or its document's input file."""
    found_changed = False
    for text in _candidate_texts(document, definition, roots):
        if hashlib.sha256(text.encode()).hexdigest() == definition.content_hash:
            return DefinitionSource(text)
        found_changed = True
    return DefinitionSource(
        None,
        (
            "The source file changed after this analysis, so its lines no longer match."
            if found_changed
            else f"TAREL stores only a hash of this code; {definition.source_reference} "
            "could not be read from here."
        ),
    )


def excerpt_lines(
    text: str, evidence: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    """The evidence lines with a little context, bounded, each with its original number."""
    lines = text.splitlines()
    marked = {
        number
        for start, end in evidence
        for number in range(max(1, start), min(len(lines), end) + 1)
    }
    if not marked:
        wanted = list(range(1, min(len(lines), _MAX_EXCERPT_LINES) + 1))
    else:
        wanted = sorted({
            number
            for line in marked
            for number in range(line - _CONTEXT_LINES, line + _CONTEXT_LINES + 1)
            if 1 <= number <= len(lines)
        })
    shown = wanted[:_MAX_EXCERPT_LINES]
    return {
        "lines": [
            {"number": number, "text": lines[number - 1], "evidence": number in marked}
            for number in shown
        ],
        "truncated": len(wanted) > len(shown),
        "total_lines": len(lines),
    }


def _candidate_texts(
    document: LineageDocument,
    definition: LineageDefinition,
    roots: tuple[Path, ...],
) -> list[str]:
    reference, _, pointer = definition.source_reference.partition("#")
    texts = []
    for path in _paths(reference, roots):
        raw = _read(path)
        if raw is None:
            continue
        if pointer:
            value = _at_pointer(raw, pointer)
            if value is not None:
                texts.append(value)
        else:
            texts.append(raw)
    for path in _paths(document.source_reference, roots):
        raw = _read(path)
        if raw is not None and path.suffix.casefold() == ".json":
            value = _input_definition(raw, definition)
            if value is not None:
                texts.append(value)
    return texts


def _paths(reference: str, roots: tuple[Path, ...]) -> tuple[Path, ...]:
    if not reference or "://" in reference:
        return ()
    path = Path(reference).expanduser()
    return (path,) if path.is_absolute() else tuple(root / path for root in roots)


def _read(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_SOURCE_BYTES:
            return None
        return path.read_text("utf-8")
    except (OSError, UnicodeError, ValueError):
        return None


def _at_pointer(raw: str, pointer: str) -> str | None:
    try:
        value: Any = json.loads(raw)
        for part in pointer.strip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _input_definition(raw: str, definition: LineageDefinition) -> str | None:
    try:
        definitions = json.loads(raw)["definitions"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(definitions, list):
        return None
    for item in definitions:
        if isinstance(item, dict) and item.get("external_id") == definition.external_id:
            content = item.get("content")
            return content if isinstance(content, str) else None
    return None
