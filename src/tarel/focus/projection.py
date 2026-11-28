"""The compact projection of a focus snapshot: readable node keys, one row per real edge.

A stored focus addresses hops by member id, repeats a ``(source, target, relation)`` once per
contributing claim, and keeps self-loops and cycles as the trace met them. That is the right
persisted record but a poor read. The compact view, without changing the snapshot:

- keys every member by its readable reference and keeps the full ``id`` inside the node;
- merges repeated ``(from, to, rel)`` hops into one row with ``edge_count``;
- drops self-loops and reports how many in ``self_loops_omitted``;
- folds the edges inside each cycle into one ``cycles`` entry (entry and exit edges stay).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import TYPE_CHECKING

from tarel.compact import (
    claim_states,
    collapse_cycles,
    finish_compact,
    omit_empty,
    unique_keys,
)

if TYPE_CHECKING:
    from tarel.focus.contracts import FocusDocument, FocusHop, FocusMember


def compact_focus_dict(
    focus: FocusDocument, *, freshness: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """The compact, deterministic projection of ``focus`` (see the module docstring)."""
    members = {item.id: item for item in focus.members}
    keys = unique_keys(
        members,
        lambda item: members[item].reference,
        lambda item: f"{members[item].source}:{members[item].reference}",
    )
    hops = [item for item in focus.hops if item.source_id != item.target_id]
    lineages = Counter(item.lineage for item in hops if item.lineage)
    states = Counter(item.state for item in hops)
    edges = _merged_edges(
        hops,
        members,
        keys,
        show_lineage=len(lineages) > 1,
        show_state=len(claim_states(hops)) > 1,
    )
    merged = len(hops) - len(edges)
    cycles, edges = collapse_cycles(edges)
    payload: dict[str, object] = {
        "cycles": cycles,
        "edges": edges,
        "freshness": dict(freshness) if freshness else None,
        "name": focus.name,
        "next": {"full": "view=full"},
        "nodes": {keys[item.id]: _node(item) for item in focus.members},
        "null_policy": "omitted",
        "origins": sorted(keys[item.id] for item in focus.members if item.origin),
        "query": focus.seed,
        "revision": focus.revision,
        "self_loops_omitted": len(focus.hops) - len(hops),
        "sources": [f"{item.kind}:{item.name}" for item in focus.sources],
        "start": keys[focus.seed_id],
        "summary": omit_empty(
            {
                "duplicates_merged": merged,
                "edges": len(edges),
                "hops": len(focus.hops),
                "lineages": dict(sorted(lineages.items())),
                "max_depth": max((item.depth for item in focus.hops), default=0),
                "nodes": len(focus.members),
                "origins": sum(item.origin for item in focus.members),
                "states": dict(sorted(states.items())),
            }
        ),
        "truncated": focus.truncated,
        "view": "compact",
        "warnings": list(focus.warnings),
    }
    return finish_compact(payload)


def _node(member: FocusMember) -> dict[str, object]:
    return omit_empty(
        {
            "depth": member.depth,
            "id": member.id,
            "kind": member.kind,
            "state": member.annotation_state,
        }
    )


def _merged_edges(
    hops: list[FocusHop],
    members: Mapping[str, FocusMember],
    keys: Mapping[str, str],
    *,
    show_lineage: bool,
    show_state: bool,
) -> list[dict[str, object]]:
    """One row per ``(from, to, rel)``; the shallowest hop speaks for its repeats."""
    groups: dict[tuple[str, str, str], list[FocusHop]] = {}
    for hop in hops:
        groups.setdefault((keys[hop.source_id], keys[hop.target_id], hop.relation), []).append(hop)
    rows = []
    for (source, target, relation), items in groups.items():
        first = min(items, key=lambda item: (item.depth, item.id))
        endpoint_sources = {members[first.source_id].source, members[first.target_id].source}
        # A claim or materialization touches its definition node, whose source already names
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
                    "edge_count": len(items) if len(items) > 1 else None,
                    "from": source,
                    "lin": lineage,
                    "rel": relation,
                    "state": first.state if show_state and relation != "field_of" else None,
                    "to": target,
                }
            )
        )
    return sorted(rows, key=lambda item: (item["d"], item["rel"], item["from"], item["to"]))
