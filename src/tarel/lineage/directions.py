"""Directional lineage: upstream, downstream (impact) or both, for one reference or a batch.

Upstream answers "where does this come from", downstream "what does this feed". Both walk the
same network that :func:`tarel.lineage.traversal.build_network` builds, so a batch of references
pays for loading and resolving its documents once.

Downstream differs from upstream in two deliberate ways:

- a table reaches each of its fields through ``field_of``; such a hop is kept only when the field
  feeds something, otherwise every unread column would show up as an "impact";
- an ambiguous reference cannot fail the walk (it is not on the path to the start), but it may
  hide a consumer, so it is reported as a warning instead of being ignored.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from tarel.errors import TarelError
from tarel.graph.contracts import GraphDocument
from tarel.lineage.contracts import LineageDocument, LineageFailure
from tarel.lineage.projection import compact_lineage_dict
from tarel.lineage.traversal import (
    DEFAULT_LINEAGE_STATES,
    LineageHop,
    LineageReference,
    Network,
    NetworkEdge,
    UpstreamTrace,
    build_network,
    hop_from_edge,
    resolve_start,
    trace_upstream_on,
    validate_trace_arguments,
)

DIRECTIONS = ("up", "down", "both")


@dataclass(frozen=True, slots=True)
class LineageTrace:
    """A trace in one or both directions; ``origins`` end upstream, ``impacts`` downstream."""

    query: str
    direction: str
    start: LineageReference
    upstream: tuple[LineageHop, ...]
    downstream: tuple[LineageHop, ...]
    origins: tuple[LineageReference, ...]
    impacts: tuple[LineageReference, ...]
    warnings: tuple[str, ...]
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "downstream": [item.to_dict() for item in self.downstream],
            "impacts": [item.to_dict() for item in self.impacts],
            "origins": [item.to_dict() for item in self.origins],
            "query": self.query,
            "start": self.start.to_dict(),
            "truncated": self.truncated,
            "upstream": [item.to_dict() for item in self.upstream],
            "warnings": list(self.warnings),
        }

    def to_compact_dict(
        self,
        *,
        resolution: dict[str, object] | None = None,
        freshness: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return compact_lineage_dict(
            query=self.query,
            direction=self.direction,
            start=self.start,
            upstream=self.upstream,
            downstream=self.downstream,
            origins=self.origins,
            impacts=self.impacts,
            warnings=self.warnings,
            truncated=self.truncated,
            resolution=resolution,
            freshness=freshness,
        )


@dataclass(frozen=True, slots=True)
class LineageBatch:
    """One trace per reference that resolved, one failure per reference that did not."""

    direction: str
    traces: tuple[LineageTrace, ...]
    failures: tuple[tuple[str, TarelError], ...]


def trace_lineage(
    documents: tuple[LineageDocument, ...],
    graphs: tuple[GraphDocument, ...],
    reference: str,
    *,
    direction: str = "up",
    max_hops: int = 12,
    states: frozenset[str] = DEFAULT_LINEAGE_STATES,
) -> LineageTrace:
    _validate_direction(direction)
    validate_trace_arguments(reference, max_hops, states)
    network = build_network(documents, graphs, states)
    return trace_lineage_on(network, reference, direction=direction, max_hops=max_hops)


def trace_lineage_batch(
    documents: tuple[LineageDocument, ...],
    graphs: tuple[GraphDocument, ...],
    references: tuple[str, ...],
    *,
    direction: str = "up",
    max_hops: int = 12,
    states: frozenset[str] = DEFAULT_LINEAGE_STATES,
) -> LineageBatch:
    """Trace every reference over one network; a failing reference never hides the others."""
    _validate_direction(direction)
    if not references or len(set(references)) != len(references):
        raise LineageFailure(
            "invalid_lineage_batch",
            "A lineage batch needs at least one reference and no duplicates.",
            retryable=True,
            hint="Pass each reference once.",
        )
    for reference in references:
        validate_trace_arguments(reference, max_hops, states)
    network = build_network(documents, graphs, states)
    traces: list[LineageTrace] = []
    failures: list[tuple[str, TarelError]] = []
    for reference in references:
        try:
            traces.append(
                trace_lineage_on(network, reference, direction=direction, max_hops=max_hops)
            )
        except LineageFailure as exc:
            failures.append((reference, exc))
    return LineageBatch(direction, tuple(traces), tuple(failures))


def trace_lineage_on(
    network: Network,
    reference: str,
    *,
    direction: str,
    max_hops: int,
) -> LineageTrace:
    up: UpstreamTrace | None = None
    if direction in {"up", "both"}:
        up = trace_upstream_on(network, reference, max_hops=max_hops)
    down = (
        _trace_downstream_on(network, reference, max_hops=max_hops)
        if direction in {"down", "both"}
        else None
    )
    warnings = {*(up.warnings if up else ()), *(down.warnings if down else ())}
    start = up.start if up else down.start if down else None
    assert start is not None
    return LineageTrace(
        query=reference,
        direction=direction,
        start=start,
        upstream=up.hops if up else (),
        downstream=down.hops if down else (),
        origins=up.origins if up else (),
        impacts=down.impacts if down else (),
        warnings=tuple(sorted(warnings)),
        truncated=bool((up and up.truncated) or (down and down.truncated)),
    )


@dataclass(frozen=True, slots=True)
class _Downstream:
    start: LineageReference
    hops: tuple[LineageHop, ...]
    impacts: tuple[LineageReference, ...]
    warnings: tuple[str, ...]
    truncated: bool


def _trace_downstream_on(network: Network, reference: str, *, max_hops: int) -> _Downstream:
    start_id = resolve_start(network, reference)
    outgoing: dict[str, list[NetworkEdge]] = {}
    for edge in network.edges:
        outgoing.setdefault(edge.source_id, []).append(edge)

    def feeds(edge: NetworkEdge) -> bool:
        return edge.relation != "field_of" or bool(outgoing.get(edge.target_id))

    hidden_by: dict[str, list[str]] = {}
    for items in network.ambiguities.values():
        for ambiguity in items:
            for candidate in ambiguity.candidates:
                hidden_by.setdefault(candidate, []).append(
                    f"Downstream may be incomplete: {ambiguity.reference} in lineage "
                    f"{ambiguity.lineage} is ambiguous and may refer to "
                    f"{network.nodes[candidate].value.reference}."
                )

    queue: deque[tuple[str, int, tuple[str, ...]]] = deque([(start_id, 0, (start_id,))])
    seen_depth = {start_id: 0}
    reached = {start_id}
    hops: list[LineageHop] = []
    warnings: set[str] = set()
    truncated = False
    while queue:
        source_id, depth, path = queue.popleft()
        warnings.update(hidden_by.get(source_id, ()))
        edges = [item for item in outgoing.get(source_id, ()) if feeds(item)]
        if depth >= max_hops:
            truncated = truncated or bool(edges)
            continue
        for edge in edges:
            target_depth = depth + 1
            hop = hop_from_edge(network, edge, target_depth)
            hops.append(hop)
            reached.add(edge.target_id)
            if edge.state in {"draft", "review_required"}:
                warnings.add("The trace contains lineage that has not been human-validated.")
            if hop.target.kind == "unresolved":
                warnings.add(f"Unresolved downstream reference: {hop.target.reference}")
            if edge.resolution_note is not None:
                warnings.add(edge.resolution_note)
            if edge.target_id in path:
                warnings.add(f"Lineage cycle detected at: {hop.target.reference}")
                continue
            previous = seen_depth.get(edge.target_id)
            if previous is None or target_depth < previous:
                seen_depth[edge.target_id] = target_depth
                queue.append((edge.target_id, target_depth, (*path, edge.target_id)))

    impacts = tuple(
        sorted(
            (
                network.nodes[node_id].value
                for node_id in reached
                if node_id != start_id
                and not any(feeds(item) for item in outgoing.get(node_id, ()))
            ),
            key=lambda item: (item.reference.casefold(), item.id),
        )
    )
    if not hops:
        warnings.add("No downstream lineage was found for the selected reference.")
    if truncated:
        warnings.add(f"Trace stopped at the configured max_hops={max_hops} boundary.")
    return _Downstream(
        start=network.nodes[start_id].value,
        hops=tuple(sorted(hops, key=lambda item: (item.depth, item.source.reference.casefold(),
                                                  item.target.reference.casefold(), item.id))),
        impacts=impacts,
        warnings=tuple(sorted(warnings)),
        truncated=truncated,
    )


def _validate_direction(direction: str) -> None:
    if direction not in DIRECTIONS:
        raise LineageFailure(
            "invalid_lineage_direction",
            f"Unsupported lineage direction: {direction}",
            retryable=True,
            hint="Use one of: up, down, both.",
            details={
                "accepted_preview": list(DIRECTIONS), "param": "direction", "value": direction,
            },
        )
