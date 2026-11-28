"""Annotation coverage: how much of a scope carries meaning, and what to annotate next.

Counts come only from the stored graphs. An object is *annotated* when it has an annotation that
was not rejected; role and grain coverage count objects whose annotation names a role, and objects
whose metadata states a grain. The list of unannotated objects is ordered by stored ``row_count``
(largest first, objects without one last), then by label, so the biggest blind spots come first.
TAREL never estimates a row count it was not given.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tarel.graph.contracts import GraphDocument, GraphNode

COVERAGE_STATES = ("validated", "review_required", "draft", "deferred", "rejected", "unannotated")


@dataclass(frozen=True, slots=True)
class UnannotatedObject:
    graph: str
    object_id: str
    label: str
    type: str
    fields: int
    row_count: int | None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "fields": self.fields,
            "graph": self.graph,
            "id": self.object_id,
            "label": self.label,
            "type": self.type,
        }
        if self.row_count is not None:
            payload["row_count"] = self.row_count
        return payload


@dataclass(frozen=True, slots=True)
class AnnotationCoverage:
    scope: str
    graphs: tuple[str, ...]
    objects: int
    states: tuple[tuple[str, int], ...]
    role_objects: int
    grain_objects: int
    unannotated: tuple[UnannotatedObject, ...]
    unannotated_total: int

    @property
    def annotated(self) -> int:
        counts = dict(self.states)
        return self.objects - counts.get("unannotated", 0) - counts.get("rejected", 0)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object | None] = {
            "annotated": self.annotated,
            "annotated_pct": _pct(self.annotated, self.objects),
            "grain_coverage_pct": _pct(self.grain_objects, self.objects),
            "graphs": list(self.graphs),
            "null_policy": "omitted",
            "objects": self.objects,
            "role_coverage_pct": _pct(self.role_objects, self.objects),
            "scope": self.scope,
            "states": dict(self.states),
            "truncated": len(self.unannotated) < self.unannotated_total,
            "unannotated": [item.to_dict() for item in self.unannotated],
            "unannotated_total": self.unannotated_total,
            "view": "compact",
        }
        return {key: value for key, value in payload.items() if value is not None}


def measure_coverage(
    scope: str,
    objects: Iterable[tuple[GraphDocument, GraphNode]],
    *,
    limit: int,
) -> AnnotationCoverage:
    counts = dict.fromkeys(COVERAGE_STATES, 0)
    graphs: set[str] = set()
    role = grain = total = 0
    missing: list[UnannotatedObject] = []
    field_counts: dict[str, dict[str, int]] = {}
    for graph, node in objects:
        graphs.add(graph.name)
        total += 1
        annotation = node.annotation
        state = annotation.state if annotation is not None else "unannotated"
        counts[state] = counts.get(state, 0) + 1
        if annotation is not None and annotation.state != "rejected" and annotation.role:
            role += 1
        grain_value = node.metadata.get("grain")
        if isinstance(grain_value, str) and grain_value.strip():
            grain += 1
        if annotation is None:
            fields = field_counts.setdefault(graph.name, _field_counts(graph))
            row_count = node.metadata.get("row_count")
            missing.append(
                UnannotatedObject(
                    graph=graph.name,
                    object_id=node.id,
                    label=node.label,
                    type=node.type,
                    fields=fields.get(node.id, 0),
                    row_count=row_count if type(row_count) is int else None,
                )
            )
    missing.sort(
        key=lambda item: (
            item.row_count is None, -(item.row_count or 0), item.label.casefold(), item.graph,
        )
    )
    return AnnotationCoverage(
        scope=scope,
        graphs=tuple(sorted(graphs)),
        objects=total,
        states=tuple((state, counts[state]) for state in COVERAGE_STATES),
        role_objects=role,
        grain_objects=grain,
        unannotated=tuple(missing[:limit]),
        unannotated_total=len(missing),
    )


def _field_counts(graph: GraphDocument) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in graph.nodes:
        parent = node.metadata.get("object_id")
        if node.type == "field" and isinstance(parent, str):
            counts[parent] = counts.get(parent, 0) + 1
    return counts


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None
