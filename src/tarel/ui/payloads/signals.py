"""At-a-glance object health signals and summary counts for the browser UI.

Truth principle:
- ``population`` is ``"empty"`` only when ``observed_rows == 0`` was actually observed;
  otherwise ``"populated"`` (> 0) or ``"unknown"`` (never guessed).
- ``lineage`` is ``"orphan"`` only when at least one lineage document is loaded and the
  object has no upstream or downstream lineage flow; otherwise ``"no_lineage_loaded"``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_PHYSICAL_TYPES = frozenset({"table", "view"})
_RELATION_EDGE_TYPES = frozenset({"foreign_key", "relationship_candidate"})
_REVIEWED_STATES = frozenset({"validated", "reviewed"})
_DRAFT_STATES = frozenset({"draft", "review_required", "deferred"})


def extract_observed_rows(metadata: Mapping[str, Any]) -> int | None:
    """Read an observed row count from node metadata without inventing values."""
    for key in ("observed_rows", "rows_profiled", "row_count"):
        value = _non_negative_int(metadata.get(key))
        if value is not None:
            return value
    profile = metadata.get("profile")
    if isinstance(profile, Mapping):
        for key in ("observed_rows", "rows_profiled", "row_count"):
            value = _non_negative_int(profile.get(key))
            if value is not None:
                return value
    return None


def attach_object_signals(
    payload: dict[str, Any],
    *,
    observed_rows_by_id: Mapping[str, int | None] | None = None,
    lineage_loaded: bool = False,
) -> dict[str, Any]:
    """Attach per-object ``signals`` and payload-level ``health_summary`` in place."""
    objects = payload.get("objects")
    edges = payload.get("edges")
    lineage_flows = payload.get("lineage_flows")
    if not isinstance(objects, list):
        return payload

    relation_counts: dict[str, int] = {}
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, Mapping):
                continue
            if edge.get("type") not in _RELATION_EDGE_TYPES:
                continue
            source = edge.get("source")
            target = edge.get("target")
            if isinstance(source, str):
                relation_counts[source] = relation_counts.get(source, 0) + 1
            if isinstance(target, str) and target != source:
                relation_counts[target] = relation_counts.get(target, 0) + 1

    upstream_counts: dict[str, int] = {}
    downstream_counts: dict[str, int] = {}
    flow_edges = lineage_flows.get("edges") if isinstance(lineage_flows, Mapping) else None
    if isinstance(flow_edges, list):
        for edge in flow_edges:
            if not isinstance(edge, Mapping):
                continue
            source = edge.get("source")
            target = edge.get("target")
            if isinstance(source, str):
                downstream_counts[source] = downstream_counts.get(source, 0) + 1
            if isinstance(target, str):
                upstream_counts[target] = upstream_counts.get(target, 0) + 1

    rows_lookup = observed_rows_by_id or {}
    total = 0
    empty = 0
    populated = 0
    unknown_population = 0
    lineage_orphan = 0
    isolated = 0
    unannotated = 0

    for item in objects:
        if not isinstance(item, dict) or item.get("type") not in _PHYSICAL_TYPES:
            continue
        total += 1
        obj_id = str(item.get("id") or "")
        observed_rows = rows_lookup.get(obj_id)
        if observed_rows is None:
            existing_signals = item.get("signals")
            if isinstance(existing_signals, Mapping):
                observed_rows = _non_negative_int(existing_signals.get("observed_rows"))

        if observed_rows is None:
            population = "unknown"
            unknown_population += 1
        elif observed_rows == 0:
            population = "empty"
            empty += 1
        else:
            population = "populated"
            populated += 1

        up_count = upstream_counts.get(obj_id, 0) if lineage_loaded else 0
        down_count = downstream_counts.get(obj_id, 0) if lineage_loaded else 0
        if not lineage_loaded:
            lineage_state = "no_lineage_loaded"
        elif up_count + down_count > 0:
            lineage_state = "connected"
        else:
            lineage_state = "orphan"
            lineage_orphan += 1

        rel_count = relation_counts.get(obj_id, 0)
        relations_state = "connected" if rel_count > 0 else "isolated"
        if rel_count == 0:
            isolated += 1

        annotation_state = _annotation_signal(item.get("annotation"))
        if annotation_state == "missing":
            unannotated += 1

        item["signals"] = {
            "annotation": annotation_state,
            "lineage": lineage_state,
            "lineage_downstream_count": down_count,
            "lineage_upstream_count": up_count,
            "observed_rows": observed_rows,
            "population": population,
            "relation_count": rel_count,
            "relations": relations_state,
        }

    payload["health_summary"] = {
        "empty": empty,
        "isolated": isolated,
        "lineage_loaded": lineage_loaded,
        "lineage_orphan": lineage_orphan,
        "populated": populated,
        "total": total,
        "unannotated": unannotated,
        "unknown_population": unknown_population,
    }
    return payload


def _annotation_signal(annotation: object) -> str:
    if not isinstance(annotation, Mapping):
        return "missing"
    state = annotation.get("state")
    if state in _REVIEWED_STATES:
        return "reviewed"
    if state in _DRAFT_STATES:
        return "draft"
    return "missing"


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None
