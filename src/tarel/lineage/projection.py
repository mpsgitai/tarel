"""The compact projection of an upstream trace: each node once, each edge as one short row.

``UpstreamTrace.to_dict()`` repeats the full source and target reference on every hop, so its
size grows with the graph rather than with the question. The compact view keeps the same facts
in a shape that scales with the trace:

- ``nodes`` holds every reference exactly once, keyed by its readable reference;
- ``edges`` are rows that point at node keys, merged when they repeat ``(from, to, rel)``, so
  that triple identifies a row;
- evidence files are listed once in ``files`` and edges cite them as ``"r1:12-30"``;
- empty values are omitted (``null_policy: "omitted"``); fields that are the same on every
  edge (state, lineage) are reported once in ``summary`` instead of on each row.

It is a read-only projection: nothing here changes or persists the trace, and ``view=full``
remains the complete record.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from tarel.lineage.graph_utils import (
    claim_states,
    collapse_cycles,
    finish_compact,
    omit_empty,
    unique_keys,
)

if TYPE_CHECKING:
    from tarel.lineage.contracts import LineageEvidence
    from tarel.lineage.traversal import LineageHop, LineageReference, UpstreamTrace

_TRAILING_LINES = re.compile(r":\d+(?:-\d+)?$")


def compact_trace_dict(trace: UpstreamTrace) -> dict[str, object]:
    """The compact, deterministic projection of ``trace`` (see the module docstring)."""
    references = _references(trace)
    keys = unique_keys(
        references,
        lambda item: _label(references[item]),
        lambda item: f"{references[item].source}:{_label(references[item])}",
    )
    hops = [item for item in trace.hops if item.source.id != item.target.id]
    files = _evidence_files(item.evidence for item in hops)
    lineages = Counter(item.lineage for item in hops if item.lineage)
    states = Counter(item.state for item in hops)
    edges = _merged_edges(
        hops,
        keys,
        files,
        show_lineage=len(lineages) > 1,
        show_state=len(claim_states(hops)) > 1,
    )
    cycles, edges = collapse_cycles(edges)
    payload: dict[str, object] = {
        "direction": "up",
        "edges": edges,
        "files": {key: path for path, key in files.items()},
        "next": {"full": "view=full"},
        "nodes": {keys[item]: _node(value) for item, value in sorted(references.items())},
        "null_policy": "omitted",
        "origins": sorted(keys[item.id] for item in trace.origins),
        "query": trace.query,
        "start": keys[trace.start.id],
        "summary": omit_empty(
            {
                "edges": len(edges),
                "evidence": dict(sorted(_evidence_kinds(hops).items())),
                "hops": len(trace.hops),
                "lineages": dict(sorted(lineages.items())),
                "max_depth": max((item.depth for item in trace.hops), default=0),
                "nodes": len(references),
                "origins": len(trace.origins),
                "states": dict(sorted(states.items())),
                "unresolved": sum(item.kind == "unresolved" for item in references.values()),
            }
        ),
        "truncated": trace.truncated,
        "view": "compact",
        "warnings": list(trace.warnings),
    }
    payload["cycles"] = cycles
    payload["limits"] = _limits(hops, references.values())
    payload["self_loops_omitted"] = len(trace.hops) - len(hops)
    return finish_compact(payload)


def _references(trace: UpstreamTrace) -> dict[str, LineageReference]:
    values = [trace.start, *trace.origins]
    for hop in trace.hops:
        values.extend((hop.source, hop.target))
    return {item.id: item for item in values}


def _label(value: LineageReference) -> str:
    """An unresolved name's ``name`` says which scope it belongs to; its reference cannot."""
    return value.name if value.kind == "unresolved" else value.reference


def _node(value: LineageReference) -> dict[str, object]:
    """Kind, source and TAREL's own meaning of a node.

    Raw technical metadata (table comments, storage locations) stays in ``view=full``: it is the
    bulk of a full trace and answers "what is this object", which graph reads answer better.
    """
    kind = _DESCRIPTION_KINDS.get(value.description_kind or "")
    return omit_empty(
        {
            "desc": value.description if kind else None,
            "desc_kind": kind,
            "kind": value.kind,
            "src": value.source,
            "state": value.annotation_state,
        }
    )


_DESCRIPTION_KINDS = {"analysis_summary": "analysis", "semantic_annotation": "semantic"}


def _merged_edges(
    hops: list[LineageHop],
    keys: Mapping[str, str],
    files: Mapping[str, str],
    *,
    show_lineage: bool,
    show_state: bool,
) -> list[dict[str, object]]:
    """One row per ``(from, to, rel)``; the shallowest hop speaks for its repeats."""
    groups: dict[tuple[str, str, str], list[LineageHop]] = {}
    for hop in hops:
        groups.setdefault((keys[hop.source.id], keys[hop.target.id], hop.relation), []).append(hop)
    rows = []
    for (source, target, relation), members in groups.items():
        first = min(members, key=lambda item: (item.depth, item.id))
        via = first.via_definition
        endpoint_sources = {first.source.source, first.target.source}
        # A claim or materialization touches its definition node, whose ``src`` already names
        # the lineage; only a write between two tables needs the lineage spelled out.
        lineage = (
            first.lineage
            if show_lineage and f"lineage:{first.lineage}" not in endpoint_sources
            else None
        )
        rows.append(
            omit_empty(
                {
                    "d": first.depth,
                    "edge_count": len(members) if len(members) > 1 else None,
                    "ev": _evidence_label(first.evidence, files),
                    "from": source,
                    "gran": first.granularity_change if relation != "field_of" else None,
                    "lin": lineage,
                    "rel": relation,
                    "review": first.reviews[-1].decision if first.reviews else None,
                    "role": first.role,
                    "state": first.state if show_state and relation != "field_of" else None,
                    "through": list(first.via),
                    "to": target,
                    "via": None if via in {first.source.reference, first.target.reference} else via,
                }
            )
        )
    return sorted(
        rows,
        key=lambda item: (item["d"], item["rel"], item["from"], item["to"]),
    )


def _evidence_files(evidence: Iterable[LineageEvidence | None]) -> dict[str, str]:
    """Evidence file path -> short key (``r1``, ``r2``, ...) in sorted path order."""
    paths = sorted({_split_reference(item.reference)[0] for item in evidence if item is not None})
    return {path: f"r{index}" for index, path in enumerate(paths, start=1)}


def _evidence_label(evidence: LineageEvidence | None, files: Mapping[str, str]) -> str | None:
    if evidence is None:
        return None
    path, anchor = _split_reference(evidence.reference)
    lines = (
        str(evidence.line_start)
        if evidence.line_end == evidence.line_start
        else f"{evidence.line_start}-{evidence.line_end}"
    )
    return f"{files[path]}{anchor}:{lines}"


def _split_reference(reference: str) -> tuple[str, str]:
    """``/a/b.sql:1-6`` -> (``/a/b.sql``, ``""``); ``/a/m.json#model.x`` -> (path, ``#model.x``).

    Line numbers are dropped from the path because the evidence carries them separately.
    """
    path, separator, fragment = _TRAILING_LINES.sub("", reference).partition("#")
    return _TRAILING_LINES.sub("", path), f"#{fragment}" if separator else ""


def _evidence_kinds(hops: list[LineageHop]) -> Counter[str]:
    return Counter(item.evidence.source if item.evidence else "none" for item in hops)


def _limits(hops: list[LineageHop], nodes: Iterable[LineageReference]) -> list[str]:
    """Known blind spots of this trace, derived from structure, never from free-text reasons."""
    if not hops:
        return []
    limits = []
    sources = {item.evidence.source for item in hops if item.evidence is not None}
    if sources and all(item.startswith("declared_") for item in sources):
        limits.append("declared_only")
    if any(item.relation == "derived_from" and item.write_evidence is None for item in hops):
        limits.append("no_write_evidence")
    if not any(item.kind == "field" for item in nodes):
        limits.append("table_level")
    return limits
