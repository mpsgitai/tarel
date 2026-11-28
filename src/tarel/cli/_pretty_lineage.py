"""``--format pretty`` for lineage traces, batches and focuses.

Each view is drawn from the compact projection the agent sees, so a person and an agent read the
same facts: the edges become a tree rooted at the start, nodes keep their kind, evidence keys
point into a short file list, and sources, freshness, limits and warnings close the page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tarel.cli._pretty import Pretty

_TITLES = {"up": "Lineage upstream", "down": "Lineage downstream (impact)", "both": "Lineage"}


def render_lineage(payload: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    direction = str(payload["direction"])
    nodes: Mapping[str, Mapping[str, Any]] = payload["nodes"]
    start = str(payload["start"])
    summary = payload.get("summary", {})
    page.header(_TITLES[direction], start, _node_tags(nodes.get(start, {})))
    page.summary(
        [
            f"{summary.get('nodes', len(nodes)):,} nodes",
            f"{summary.get('edges', 0):,} edges",
            f"max depth {summary.get('max_depth', 0)}",
            _count(payload.get("self_loops_omitted"), "self-loop omitted", "self-loops omitted"),
            _count(len(payload.get("cycles", ())), "cycle folded", "cycles folded"),
        ]
    )
    edges = list(payload.get("edges", ()))
    if direction in {"up", "both"}:
        if direction == "both":
            page.section("Upstream")
        page.add()
        upstream = [item for item in edges if item.get("dir") != "down"]
        _tree(page, start, upstream, nodes, up=True, cycles=payload.get("cycles", ()))
    if direction in {"down", "both"}:
        if direction == "both":
            page.section("Downstream")
        page.add()
        # Only a "both" trace marks its downstream rows; a "down" trace has no other rows.
        down = edges if direction == "down" else [item for item in edges if item.get("dir")]
        _tree(page, start, down, nodes, up=False, cycles=payload.get("cycles", ()))
    _node_list(page, "Origins", payload.get("origins", ()), nodes)
    _node_list(page, "Impacts", payload.get("impacts", ()), nodes)
    _cycles(page, payload.get("cycles", ()))
    files = payload.get("files", {})
    if files:
        page.section("Evidence files", len(files))
        rows = [(key, str(files[key])) for key in sorted(files, key=_file_key)]
        page.table(("KEY", "FILE"), rows, cut_left=(1,))
    page.footer(
        _facts(payload),
        limits=[str(item) for item in payload.get("limits", ())],
        warnings=[str(item) for item in payload.get("warnings", ())],
        hints=["--format json --view full for every recorded field"],
    )
    page.emit()


def render_focus(payload: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    nodes: Mapping[str, Mapping[str, Any]] = payload["nodes"]
    start = str(payload["start"])
    summary = payload.get("summary", {})
    page.header("Focus", str(payload["name"]), [f"seed: {start}"])
    page.summary(
        [
            f"{summary.get('nodes', len(nodes)):,} members",
            f"{summary.get('edges', 0):,} edges",
            _count(summary.get("duplicates_merged"), "duplicate merged", "duplicates merged"),
            _count(payload.get("self_loops_omitted"), "self-loop omitted", "self-loops omitted"),
            _count(len(payload.get("cycles", ())), "cycle folded", "cycles folded"),
        ]
    )
    page.summary([f"sources: {', '.join(payload.get('sources', ()))}"])
    page.section("Lineage flow")
    page.add()
    _tree(
        page, start, list(payload.get("edges", ())), nodes, up=True,
        cycles=payload.get("cycles", ()),
    )
    _node_list(page, "Origins", payload.get("origins", ()), nodes, limit=12)
    _cycles(page, payload.get("cycles", ()))
    page.footer(
        [*_facts(payload), ("Revision", str(payload.get("revision", ""))[:12])],
        warnings=[str(item) for item in payload.get("warnings", ())],
        hints=["--format json --view full for the stored snapshot"],
    )
    page.emit()


def render_batch(payload: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    summary = payload.get("summary", {})
    direction = str(payload.get("direction", "up"))
    page.header(
        "Lineage batch", f"{summary.get('references', 0)} references",
        [{"up": "upstream", "down": "downstream", "both": "both directions"}[direction]],
    )
    page.summary(
        [
            f"{summary.get('with_lineage', 0)} with lineage",
            f"{summary.get('without_lineage', 0)} without",
            _count(summary.get("failed"), "failed", "failed"),
            f"{summary.get('jobs', 0)} jobs",
            f"max depth {summary.get('max_depth', 0)}",
        ]
    )
    chains: Mapping[str, str] = payload.get("chains", {})
    arrow = {"up": page.style.symbol("left"), "down": page.style.symbol("right")}
    linked = {key: value for key, value in chains.items() if value != key}
    if linked:
        page.section("Chains", len(linked))
        for reference, chain in linked.items():
            page.add()
            page.add(f"  {page.style.bold(reference)}")
            for part in chain.split(" | "):
                steps = part.replace(" <- ", f" {arrow['up']} ")
                steps = steps.replace(" -> ", f" {arrow['down']} ")
                # The chain starts with the reference itself; the heading already shows it.
                body = steps.split(" ", 1)[1] if " " in steps else steps
                page.text(body, indent=4)
    without = [key for key, value in chains.items() if value == key]
    if without:
        page.section("No lineage recorded", len(without))
        page.bullets(without)
    errors: Mapping[str, Mapping[str, Any]] = payload.get("errors", {})
    if errors:
        page.section("Not traced", len(errors))
        page.table(
            ("REFERENCE", "ERROR", "MESSAGE"),
            [
                (key, str(value.get("code")), str(value.get("message")))
                for key, value in errors.items()
            ],
            stylers={1: page.style.bad},
        )
    grouped: Mapping[str, Sequence[str]] = payload.get("warnings", {})
    page.footer(
        _facts(payload),
        warnings=[
            f"{text} ({'all references' if refs == ['*'] else ', '.join(refs)})"
            for text, refs in grouped.items()
        ],
        hints=["tarel lineage trace REF for one tree with evidence"],
    )
    page.emit()


def _tree(
    page: Pretty,
    start: str,
    edges: list[Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
    *,
    up: bool,
    cycles: Any = (),
) -> None:
    children: dict[str, list[tuple[str, str, str]]] = {}
    arrow = page.style.symbol("left" if up else "right")
    for edge in sorted(edges, key=lambda item: (item["d"], str(item["from"]), str(item["to"]))):
        parent, child = (edge["to"], edge["from"]) if up else (edge["from"], edge["to"])
        notes = [str(edge[key]) for key in ("ev",) if key in edge]
        if "via" in edge:
            notes.insert(0, f"via {edge['via']}")
        if "role" in edge:
            notes.insert(0, f"role {edge['role']}")
        if edge.get("edge_count"):
            notes.append(f"x{edge['edge_count']}")
        relation = page.style.dim(f"{edge['rel']} {arrow}")
        children.setdefault(str(parent), []).append((relation, str(child), "  ".join(notes)))
    # A folded cycle drops the edges between its members, so the members are linked here again;
    # otherwise branches entering the cycle elsewhere would hang loose from the start.
    link = page.style.dim(f"{page.style.symbol('cycle')} same cycle as")
    for cycle in cycles:
        members = [str(item) for item in cycle.get("members", ())]
        for member in members:
            children.setdefault(member, []).extend(
                (link, other, "") for other in members if other != member
            )
    if not children.get(start):
        page.add("  " + _label(page, start, nodes))
        page.text("no edges in this direction", indent=4, styler=page.style.dim)
        return
    page.tree(start, children, lambda key: _label(page, key, nodes))


def _label(page: Pretty, key: str, nodes: Mapping[str, Mapping[str, Any]]) -> str:
    node = nodes.get(key, {})
    tags = _node_tags(node)
    suffix = f" {page.style.dim('[' + ' · '.join(tags) + ']')}" if tags else ""
    name = page.style.warn(key) if node.get("kind") == "unresolved" else page.style.bold(key)
    return page.style.text(name + suffix)


def _node_tags(node: Mapping[str, Any]) -> list[str]:
    tags = [str(node[key]) for key in ("kind",) if key in node]
    if "state" in node:
        tags.append(str(node["state"]))
    return tags


def _node_list(
    page: Pretty, title: str, keys: Any, nodes: Mapping[str, Mapping[str, Any]],
    *, limit: int | None = None,
) -> None:
    values = list(keys)
    if not values:
        return
    page.section(title, len(values))
    page.bullets([_label(page, str(item), nodes) for item in values], limit=limit)


def _cycles(page: Pretty, cycles: Any) -> None:
    values = list(cycles)
    if not values:
        return
    page.section("Folded cycles", len(values))
    symbol = page.style.symbol("cycle")
    for index, cycle in enumerate(values, start=1):
        members = ", ".join(str(item) for item in cycle.get("members", ()))
        page.text(
            f"{symbol} #{index}: {members} ({cycle.get('internal_edges', 0)} internal edges)",
            indent=4,
        )


def _facts(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    resolution = payload.get("resolution")
    if isinstance(resolution, Mapping):
        facts.append(
            (
                "Sources",
                f"auto: {_count(len(resolution.get('lineages', ())), 'lineage', 'lineages')} "
                f"({resolution.get('lineages_from')}), "
                f"{_count(len(resolution.get('graphs', ())), 'graph', 'graphs') or '0 graphs'} "
                f"({resolution.get('graphs_from')})",
            )
        )
    freshness = payload.get("freshness")
    if isinstance(freshness, Mapping):
        parts = [f"{key} read {value}" for key, value in freshness.get("observed", {}).items()]
        missing = freshness.get("missing", ())
        if missing:
            parts.append(f"no observation for {', '.join(missing)}")
        failed = freshness.get("failed", {})
        parts += [f"{key} last read failed ({value})" for key, value in failed.items()]
        facts.append(("Freshness", f"{'; '.join(parts)} (stale: {freshness.get('stale')})"))
    if payload.get("truncated"):
        facts.append(("Truncated", "yes, raise --max-hops to see more"))
    return facts


def _count(value: Any, singular: str, plural: str) -> str:
    if not value:
        return ""
    return f"{value:,} {singular if value == 1 else plural}"


def _file_key(value: str) -> tuple[int, str]:
    return (int(value[1:]) if value[1:].isdigit() else 0, value)
