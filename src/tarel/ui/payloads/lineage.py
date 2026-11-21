"""The lineage documents a browser session has loaded, for its manual-overlay views."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tarel.lineage.contracts import LineageDocument
from tarel.lineage.revision import lineage_revision


def browser_lineages(documents: Iterable[LineageDocument]) -> list[dict[str, Any]]:
    payload = []
    for document in sorted(documents, key=lambda item: item.name):
        definitions = document.definition_by_id()
        analyses = {item.definition_id: item for item in document.analyses}
        jobs = [
            {
                "analysis": (
                    {
                        "analyzer": analyses[item.id].analyzer,
                        "analyzer_version": analyses[item.id].analyzer_version,
                        "dialect": analyses[item.id].dialect,
                    }
                    if item.id in analyses
                    else None
                ),
                "description": analyses[item.id].summary if item.id in analyses else None,
                "id": item.id,
                "kind": item.kind,
                "language": item.language,
                "name": item.name,
                "qualified_name": item.qualified_name,
                "source_reference": item.source_reference,
            }
            for item in sorted(
                document.definitions,
                key=lambda item: item.qualified_name.casefold(),
            )
        ]
        hops = []
        for unit in sorted(document.write_units, key=lambda item: item.id):
            definition = definitions[unit.definition_id]
            for source in unit.sources:
                hops.append(
                    {
                        "evidence": source.evidence.to_dict(),
                        "item_id": unit.id,
                        "job": definition.qualified_name,
                        "operation": unit.operation,
                        "reviews": [item.to_dict() for item in unit.reviews],
                        "role": source.role,
                        "source": source.target,
                        "state": unit.state,
                        "target": unit.target,
                    }
                )
        payload.append(
            {
                "hops": hops,
                "jobs": jobs,
                "manual": document.source_kind == "manual",
                "name": document.name,
                "revision": lineage_revision(document),
                "source_kind": document.source_kind,
            }
        )
    return payload
