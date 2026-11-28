"""``--format pretty`` for catalog reads: workspaces, graphs, search, context and coverage.

Like the lineage views, every page is drawn from the payload the other formats print, so the
pretty page adds layout, never facts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from tarel.cli._pretty import Pretty

if TYPE_CHECKING:
    from tarel.context.compiler import ContextResult
    from tarel.context.guidance import ContextBrief
    from tarel.graph.selective import GraphHeader, GraphObjectPage
    from tarel.search import SearchResults


def render_workspace(overview: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    systems: Sequence[Mapping[str, Any]] = overview.get("systems", ())
    page.header("Workspace", str(overview["name"]), [f"{overview.get('depth', 'index')} view"])
    if overview.get("description"):
        page.text(str(overview["description"]), indent=2, styler=page.style.dim)
    members = sum(int(item.get("zone_member_count", 0)) for item in systems)
    zones = sum(int(item.get("zone_count", 0)) for item in systems)
    total = int(overview.get("system_count", len(systems)))
    filtered = bool(overview.get("systems_filter"))
    graphs = (
        len({name for item in systems for name in item.get("graphs", ())})
        if filtered else int(overview.get("graph_count", 0))
    )
    page.summary(
        [
            f"{len(systems)} of {total} systems" if filtered else f"{total:,} systems",
            f"{graphs:,} graphs",
            f"{zones:,} zones",
            f"{members:,} zone members",
            f"{overview.get('relationship_count', 0):,} relationships",
        ]
    )
    stats = any("objects" in item for item in systems)
    headers = ["SYSTEM", "GRAPHS", "AREAS", "ZONES", "MEMBERS"]
    if stats:
        headers += ["OBJECTS", "ANNOTATED"]
    headers.append("DESCRIPTION")
    rows = []
    for item in systems:
        row = [
            str(item["name"]), str(item.get("graph_count", 0)), str(item.get("area_count", 0)),
            str(item.get("zone_count", 0)), f"{item.get('zone_member_count', 0):,}",
        ]
        if stats:
            pct = item.get("annotated_pct")
            row += [f"{item.get('objects', 0):,}", "n/a" if pct is None else f"{pct:.1f}%"]
        row.append(str(item.get("description") or "").split("\n")[0])
        rows.append(row)
    page.add()
    page.table(headers, rows, right=range(1, len(headers) - 1), stylers={0: page.style.bold})
    for item in systems:
        if "areas" not in item and "zones" not in item:
            continue
        page.section(f"System {item['name']}")
        page.text("graphs: " + ", ".join(item.get("graphs", ())), styler=page.style.dim)
        areas = item.get("areas", ())
        if areas:
            page.add()
            width = max(len(str(area["name"])) for area in areas)
            for area in areas:
                grouped: dict[str, list[str]] = {}
                for schema in area.get("schemas", ()):
                    graph, _, namespace = str(schema).partition(":")
                    grouped.setdefault(graph, []).append(namespace)
                listed = "; ".join(
                    f"{graph}: {', '.join(names)}" for graph, names in grouped.items()
                )
                name = page.style.bold(str(area["name"]).ljust(width))
                page.text(f"{name}  {listed}", indent=4, hang=width + 2)
        zone_rows = [
            (
                str(zone["name"]), f"{zone.get('member_count', 0):,}",
                str(zone.get("description") or ""),
            )
            for zone in item.get("zones", ())
        ]
        if zone_rows:
            page.add()
            page.table(("ZONE", "MEMBERS", "DESCRIPTION"), zone_rows, right=(1,), indent=4)
    hint = (
        f"tarel workspace show {overview['name']} --depth zones --system NAME"
        if overview.get("depth") == "index"
        else "--format json --depth full for every zone member"
    )
    page.footer(hints=[hint])
    page.emit()


def render_graph_header(header: GraphHeader, freshness: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    tags = [header.connector, f"catalog: {header.catalog}"]
    if header.dialect:
        tags.append(header.dialect)
    page.header("Graph", header.name, tags)
    page.summary(
        [f"{header.object_count:,} tables/views", f"{header.node_count:,} nodes",
         f"{header.edge_count:,} edges"]
    )
    page.add()
    page.table(
        ("FACT", "VALUE"),
        [
            ("revision", header.revision),
            ("physical revision", header.physical_revision),
            ("contract", header.contract_version),
            ("source type", header.source_type),
            ("index", header.read_stats.mode),
        ],
        stylers={0: page.style.dim},
    )
    page.footer([("Freshness", _freshness(freshness))])
    page.emit()


def render_graph_objects(result: GraphObjectPage) -> None:
    page = Pretty.for_stdout()
    header = result.header
    page.header("Graph", header.name, [f"catalog: {header.catalog}", "objects"])
    first, last = result.offset + 1, result.offset + len(result.objects)
    page.summary([f"objects {first:,}-{last:,} of {result.total_objects:,}"])
    rows = []
    for node in result.objects:
        annotation = node.annotation
        rows.append(
            (
                node.label, node.type,
                annotation.role or "" if annotation else "",
                annotation.state if annotation else "",
                (annotation.description if annotation else "").split("\n")[0],
            )
        )
    page.add()
    page.table(
        ("OBJECT", "TYPE", "ROLE", "STATE", "DESCRIPTION"), rows,
        stylers={0: page.style.bold, 3: page.state},
    )
    hints = []
    if result.next_offset is not None:
        hints.append(f"--offset {result.next_offset} --limit {result.limit} for the next page")
    page.footer(hints=hints)
    page.emit()


def render_slice(payload: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    objects: Sequence[Mapping[str, Any]] = payload.get("objects", ())
    page.header(
        "Graph slice", str(payload["graph"]),
        [
            f"catalog: {payload.get('catalog')}",
            f"{len(objects)} of {payload.get('object_count')} objects",
        ],
    )
    labels = _field_labels(objects)
    references: dict[str, str] = {}
    relations = []
    for edge in payload.get("edges", ()):
        source, target = str(edge["from"]), str(edge["to"])
        if source in labels and target in labels and labels[source][1]:
            references[source] = labels[target][0]
        elif source in labels or target in labels:
            relations.append((labels.get(source, (source, ""))[0], str(edge["rel"]),
                              labels.get(target, (target, ""))[0]))
    for item in objects:
        annotation = item.get("annotation", {})
        tags = [str(item.get("type"))]
        if "role" in annotation:
            tags.append(str(annotation["role"]))
        tags.append(page.state(annotation.get("state")))
        page.add()
        square = page.style.symbol("square")
        page.add(f"  {square} {page.style.bold(str(item['label']))} {page.style.dim('[')}"
                 f"{' · '.join(tags)}{page.style.dim(']')}")
        if "description" in annotation:
            page.text(str(annotation["description"]), indent=4)
        grain = item.get("meta", {}).get("grain")
        if grain:
            page.text(f"grain: {grain}", indent=4, styler=page.style.dim)
        rows = []
        for field in item.get("fields", ()):
            meta = field.get("meta", {})
            key = "PK" if meta.get("is_primary_key") else ""
            foreign = references.get(str(field.get("id")))
            if foreign:
                key = f"{key} FK {page.style.symbol('right')} {foreign}".strip()
            meaning = str(field.get("annotation", {}).get("description", "")).split("\n")[0]
            rows.append(
                (
                    str(field["label"]), str(meta.get("data_type", "")),
                    "NULL" if meta.get("nullable", True) else "NOT NULL", key, meaning,
                )
            )
        if rows:
            page.add()
            page.table(
                ("COLUMN", "TYPE", "NULLABLE", "KEY", "MEANING"), rows, indent=4,
                stylers={3: page.style.accent},
            )
    if relations:
        page.section("Relationships", len(relations))
        arrow = page.style.symbol("right")
        for source, relation, target in relations:
            page.text(f"{source} {page.style.dim(relation + ' ' + arrow)} {target}", indent=4)
    context = payload.get("annotation_context_documents", ())
    facts = [("Freshness", _freshness(payload.get("freshness", {})))]
    if context:
        titles = ", ".join(str(item.get("title") or item.get("id")) for item in context)
        facts.append(("Annotated from", titles))
    page.footer(facts, hints=["--format json --view full for audit fields and containment"])
    page.emit()


def render_search(results: SearchResults) -> None:
    page = Pretty.for_stdout()
    tags = [results.mode]
    if results.workspace:
        tags.append(f"workspace: {results.workspace}")
    else:
        tags.append(f"graph: {results.graph}")
    page.header("Search", f'"{results.query}"', tags)
    inventory = results.inventory
    scope = []
    if results.workspace:
        scope.append(f"{len(results.graphs):,} graphs")
    if inventory is not None:
        scope.append(f"{inventory.objects_in_scope:,} objects")
        if inventory.objects_after_filters != inventory.objects_in_scope:
            scope.append(f"{inventory.objects_after_filters:,} after filters")
    scope.append(f"top {len(results.hits)}")
    if results.diversity:
        scope.append(f"diversity: {results.diversity}")
    if results.duplicates_collapsed:
        scope.append(f"{results.duplicates_collapsed} duplicates folded")
    page.summary(scope)
    for rank, hit in enumerate(results.hits, start=1):
        page.add()
        page.add(f"  {page.style.dim(f'{rank:>2}')}  {page.style.dim(f'{hit.score:>4}')}  "
                 f"{page.style.bold(page.fit(hit.label, page.width - 12))}")
        tags = [hit.type, f"role: {hit.role or '-'}", page.state(hit.annotation_state)]
        page.add(" " * 11 + f" {page.style.symbol('dot')} ".join(tags))
        if hit.grain:
            page.add(" " * 11 + page.style.dim(page.fit(f"grain: {hit.grain}", page.width - 11)))
        if hit.description:
            first = hit.description.split("\n")[0]
            page.add(" " * 11 + page.fit(first, page.width - 11))
        if hit.fields:
            names = ", ".join(field.label for field in hit.fields)
            page.add(" " * 11 + page.style.dim(page.fit(f"matched: {names}", page.width - 11)))
        if hit.duplicates:
            note = f"+{len(hit.duplicates)} copies in other graphs folded"
            page.add(" " * 11 + page.style.dim(note))
    facts: list[tuple[str, str]] = []
    if inventory is not None and inventory.objects_in_scope:
        unknown = dict(inventory.roles).get("unknown", 0)
        ratio = (inventory.objects_in_scope - unknown) / inventory.objects_in_scope
        facts.append(("Role coverage", f"{page.bar(ratio)} {100 * ratio:.1f}%"))
    if results.excluded_graphs:
        facts.append(("Excluded", ", ".join(results.excluded_graphs)))
    if results.omitted_by_diversity:
        omitted = sum(count for _, count in results.omitted_by_diversity)
        facts.append(("Diversity", f"{omitted:,} lower hits held back across "
                      f"{len(results.omitted_by_diversity)} graphs"))
    page.footer(facts, warnings=list(results.warnings))
    page.emit()


def render_context(result: ContextResult, brief: ContextBrief) -> None:
    page = Pretty.for_stdout()
    scope = result.scope
    tags = [result.contract_version]
    if scope.workspace:
        tags.append(f"workspace: {scope.workspace}")
    labels = [item.label for item in result.objects]
    prefix = _common_graph_prefix(labels)
    if prefix:
        tags.append(f"graph: {prefix[:-1]}")

    def short(label: str) -> str:
        return label.removeprefix(prefix)

    page.header("Context packet", result.graph, tags)
    if result.retrieval_mode != "scope":
        page.text(f'question: "{result.query}"', indent=2, styler=page.style.dim)
    ratio = result.context_characters / result.max_characters if result.max_characters else 0.0
    page.summary(
        [
            f"budget {page.bar(ratio)} {result.context_characters:,} / "
            f"{result.max_characters:,} characters",
            f"{len(result.objects)}/{result.max_objects} objects",
            f"{len(result.joins)}/{result.max_joins} joins",
        ]
    )
    rows = []
    for item in result.objects:
        meaning = (item.description or "").split("\n")[0]
        rows.append(
            (
                short(item.label), item.role or "", item.annotation_state or "",
                str(len(item.fields)),
                item.grain or "", meaning,
            )
        )
    if rows:
        page.section("Selected objects", len(rows))
        page.table(
            ("OBJECT", "ROLE", "STATE", "FIELDS", "GRAIN", "MEANING"), rows, right=(3,),
            stylers={0: page.style.bold, 2: page.state},
        )
    if result.joins:
        page.section("Joins", len(result.joins))
        for join in result.joins:
            page.text(
                f"{short(join.from_object)}({', '.join(join.from_fields)}) = "
                f"{short(join.to_object)}({', '.join(join.to_fields)})  "
                + page.style.dim(f"[{join.kind}; {join.state}]"),
                indent=4, hang=4,
            )
    omissions = result.omissions
    if omissions.objects or omissions.fields or omissions.joins:
        page.section("Left out")
        page.text(
            f"{omissions.objects:,} objects, {omissions.fields:,} fields, "
            f"{omissions.joins:,} joins ({', '.join(omissions.reasons) or 'no reason recorded'})",
        )
    gaps = [f"[{gap.category}] {gap.message} Next: {gap.action}" for gap in brief.gaps]
    page.footer(
        [("Packet", result.packet_hash[:12]), ("Stable", result.stable_hash[:12])],
        warnings=[*scope.warnings, *result.retrieval_warnings, *gaps],
    )
    page.emit()


def render_coverage(payload: Mapping[str, Any]) -> None:
    page = Pretty.for_stdout()
    objects = int(payload.get("objects", 0))
    page.header("Annotation coverage", str(payload["scope"]), [f"{objects:,} objects"])
    page.summary([f"graphs: {', '.join(payload.get('graphs', ()))}"])
    page.add()
    states: Mapping[str, int] = payload.get("states", {})
    for label, key, part in (
        ("Annotated", "annotated_pct", int(payload.get("annotated", 0))),
        ("Role filled", "role_coverage_pct", None),
        ("Grain filled", "grain_coverage_pct", None),
    ):
        pct = payload.get(key)
        ratio = (pct or 0.0) / 100
        count = f"  ({part:,} / {objects:,})" if part is not None else ""
        shown = "n/a" if pct is None else f"{pct:5.1f}%"
        page.add(f"  {label.ljust(13)} {page.bar(ratio)} {shown}{count}")
    page.add()
    page.table(
        ("STATE", "OBJECTS", "SHARE"),
        [
            (state, f"{count:,}", f"{100 * count / objects:.1f}%" if objects else "n/a")
            for state, count in states.items()
        ],
        right=(1, 2), stylers={0: page.state},
    )
    missing: Sequence[Mapping[str, Any]] = payload.get("unannotated", ())
    if missing:
        page.section("Unannotated objects", int(payload.get("unannotated_total", len(missing))))
        page.table(
            ("GRAPH", "OBJECT", "TYPE", "FIELDS", "ROWS"),
            [
                (str(item["graph"]), str(item["label"]), str(item["type"]), str(item["fields"]),
                 f"{item['row_count']:,}" if "row_count" in item else "-")
                for item in missing
            ],
            right=(3, 4), flex=1,
        )
    hints = []
    if payload.get("truncated"):
        hints.append("--limit N to list more unannotated objects")
    page.footer(hints=hints)
    page.emit()


def _common_graph_prefix(labels: Sequence[str]) -> str:
    """``"graph:"`` when every workspace label starts with the same graph, else ``""``."""
    prefixes = {label.split(":", 1)[0] + ":" for label in labels if ":" in label}
    if len(prefixes) == 1 and all(":" in label for label in labels):
        return prefixes.pop()
    return ""


def _field_labels(objects: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, bool]]:
    """Id -> (readable label, is a field) for every object and field in the slice."""
    labels: dict[str, tuple[str, bool]] = {}
    for item in objects:
        labels[str(item["id"])] = (str(item["label"]), False)
        for field in item.get("fields", ()):
            labels[str(field["id"])] = (f"{item['label']}.{field['label']}", True)
    return labels


def _freshness(block: Mapping[str, Any]) -> str:
    if not block:
        return "not reported"
    parts = [f"{key} read {value}" for key, value in block.get("observed", {}).items()]
    missing = block.get("missing", ())
    if missing:
        parts.append(f"no observation for {', '.join(missing)}")
    parts += [f"{key} last read failed ({value})" for key, value in block.get("failed", {}).items()]
    return f"{'; '.join(parts)} (stale: {block.get('stale')})"
