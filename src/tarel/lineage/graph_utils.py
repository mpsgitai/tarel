"""Small pure helpers shared by the compact lineage and focus projections."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Protocol


def omit_empty(mapping: Mapping[str, object]) -> dict[str, object]:
    """Drop ``None``, empty strings and empty collections; keep ``False`` and ``0``."""
    return {
        key: value
        for key, value in mapping.items()
        if value is not None and not (isinstance(value, (str, list, tuple, dict)) and not value)
    }


# Present even when empty, so a reader can tell "none" from "not reported".
_ALWAYS = frozenset({"edges", "nodes", "origins", "truncated", "warnings"})


def finish_compact(payload: dict[str, object]) -> dict[str, object]:
    """Sort a compact payload's keys and drop its empty optional sections."""
    return {
        key: value
        for key, value in sorted(payload.items())
        if key in _ALWAYS or value not in (None, 0, [], {})
    }


class _Hop(Protocol):
    @property
    def relation(self) -> str: ...

    @property
    def state(self) -> str: ...


def claim_states(hops: Iterable[_Hop]) -> set[str]:
    """Review states of lineage claims; ``field_of`` is graph structure, always "observed"."""
    return {item.state for item in hops if item.relation != "field_of"}


def collapse_cycles(
    edges: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Replace the edges inside each strongly connected component by one ``cycles`` entry.

    Edges that enter or leave a cycle stay, so the path through it is still visible; only the
    edges between members, which say nothing beyond "these depend on each other", are folded.
    """
    pairs = [(str(item["from"]), str(item["to"])) for item in edges]
    components = tarjan_sccs((node for pair in pairs for node in pair), pairs)
    if not components:
        return [], edges
    membership = {member: index for index, members in enumerate(components) for member in members}
    internal = [0] * len(components)
    kept = []
    for item, (source, target) in zip(edges, pairs, strict=True):
        group = membership.get(source)
        if group is not None and group == membership.get(target):
            internal[group] += 1
        else:
            kept.append(item)
    cycles: list[dict[str, object]] = [
        {"internal_edges": count, "members": list(members)}
        for members, count in zip(components, internal, strict=True)
    ]
    return cycles, kept


def unique_keys(
    ids: Iterable[str],
    *candidates: Callable[[str], str],
) -> dict[str, str]:
    """Map each id to the first candidate label that no other id shares, else to the id itself.

    Candidates are tried in order (for example ``reference`` then ``source:reference``), so the
    readable label wins whenever it is unambiguous and the result never depends on input order.
    """
    pending = sorted(set(ids))
    result: dict[str, str] = {}
    taken: set[str] = set()
    for candidate in candidates:
        labels: dict[str, list[str]] = {}
        for item in pending:
            labels.setdefault(candidate(item), []).append(item)
        remaining = []
        for item in pending:
            label = candidate(item)
            if len(labels[label]) == 1 and label not in taken:
                result[item] = label
            else:
                remaining.append(item)
        taken.update(result.values())
        pending = remaining
    for item in pending:
        result[item] = item
    return result


def tarjan_sccs(
    nodes: Iterable[str],
    edges: Iterable[tuple[str, str]],
) -> list[tuple[str, ...]]:
    """Strongly connected components with more than one member, each sorted, in sorted order.

    Iterative Tarjan, so a deep lineage chain cannot hit Python's recursion limit. Self-loops
    are not cycles here; callers report them separately.
    """
    adjacency: dict[str, list[str]] = {item: [] for item in nodes}
    for source, target in edges:
        if source != target:
            adjacency.setdefault(source, []).append(target)
            adjacency.setdefault(target, [])
    for targets in adjacency.values():
        targets.sort()

    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []
    counter = 0
    for root in sorted(adjacency):
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, position = work.pop()
            if position == 0:
                index[node] = lowlink[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            targets = adjacency[node]
            if position < len(targets):
                work.append((node, position + 1))
                target = targets[position]
                if target not in index:
                    work.append((target, 0))
                elif target in on_stack:
                    lowlink[node] = min(lowlink[node], index[target])
                continue
            if lowlink[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    components.append(tuple(sorted(component)))
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return sorted(components)
