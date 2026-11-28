import json
import os
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_focus import _fixture, _run_cli

from tarel.compact import omit_empty, tarjan_sccs, unique_keys
from tarel.graph.store import FileGraphStore
from tarel.lineage.contracts import LineageEvidence, LineageReview
from tarel.lineage.store import FileLineageStore
from tarel.lineage.traversal import LineageHop, LineageReference, UpstreamTrace


class GraphUtilsTests(TestCase):
    def test_omit_empty_keeps_false_and_zero(self) -> None:
        self.assertEqual(
            omit_empty({"a": None, "b": "", "c": [], "d": {}, "e": False, "f": 0, "g": "x"}),
            {"e": False, "f": 0, "g": "x"},
        )

    def test_tarjan_finds_cycles_but_not_self_loops(self) -> None:
        edges = [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "d"), ("e", "f")]

        self.assertEqual(tarjan_sccs("abcdef", edges), [("a", "b", "c")])

    def test_tarjan_handles_long_chains_without_recursion(self) -> None:
        nodes = [f"n{index}" for index in range(5000)]
        edges = [*pairwise(nodes), (nodes[-1], nodes[0])]

        self.assertEqual(len(tarjan_sccs(nodes, edges)[0]), 5000)

    def test_unique_keys_falls_back_only_for_colliding_labels(self) -> None:
        labels = {"1": ("graph:a", "X"), "2": ("graph:b", "X"), "3": ("graph:a", "Y")}

        keys = unique_keys(
            labels,
            lambda item: labels[item][1],
            lambda item: f"{labels[item][0]}:{labels[item][1]}",
        )

        self.assertEqual(keys, {"1": "graph:a:X", "2": "graph:b:X", "3": "Y"})


class CompactTraceTests(TestCase):
    def test_nodes_appear_once_and_edges_are_short_rows(self) -> None:
        compact = _trace().to_compact_dict()

        self.assertEqual(compact["start"], "DW.mart.Sales")
        self.assertEqual(
            sorted(compact["nodes"]),
            ["DW.mart.Sales", "DW.raw.Orders", "DW.raw.Sales", "etl.load_sales"],
        )
        self.assertEqual(
            compact["nodes"]["etl.load_sales"], {"kind": "procedure", "src": "lineage:etl"},
        )
        self.assertEqual(
            [(item["d"], item["rel"], item["from"], item["to"]) for item in compact["edges"]],
            [
                (1, "materializes_as", "etl.load_sales", "DW.mart.Sales"),
                (2, "reads_from", "DW.raw.Orders", "etl.load_sales"),
                (2, "reads_from", "DW.raw.Sales", "etl.load_sales"),
            ],
        )
        self.assertEqual(compact["origins"], ["DW.raw.Orders", "DW.raw.Sales"])
        self.assertEqual(compact["view"], "compact")
        self.assertEqual(compact["null_policy"], "omitted")
        self.assertEqual(compact["next"], {"full": "view=full"})

    def test_no_empty_values_reach_nodes_or_edges(self) -> None:
        compact = _trace().to_compact_dict()

        for item in [*compact["nodes"].values(), *compact["edges"]]:
            for value in item.values():
                self.assertNotIn(value, (None, "", [], {}))

    def test_repeated_edges_merge_and_self_loops_are_counted(self) -> None:
        compact = _trace().to_compact_dict()

        reads = [item for item in compact["edges"] if item["from"] == "DW.raw.Sales"]
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["edge_count"], 2)
        self.assertEqual(compact["self_loops_omitted"], 1)
        self.assertEqual(compact["summary"]["hops"], 5)
        self.assertEqual(compact["summary"]["edges"], 3)

    def test_evidence_files_are_listed_once_and_cited_by_key(self) -> None:
        compact = _trace().to_compact_dict()

        self.assertEqual(
            compact["files"], {"r1": "/repo/etl/load_sales.sql", "r2": "/repo/manifest.json"},
        )
        by_source = {item["from"]: item.get("ev") for item in compact["edges"]}
        self.assertEqual(by_source["etl.load_sales"], "r2#proc.load_sales:1")
        self.assertEqual(by_source["DW.raw.Sales"], "r1:3-9")
        self.assertIsNone(by_source["DW.raw.Orders"])

    def test_only_tarel_semantics_are_kept_as_descriptions(self) -> None:
        nodes = _trace().to_compact_dict()["nodes"]

        self.assertEqual(
            nodes["DW.mart.Sales"],
            {
                "desc": "One row per sale.",
                "desc_kind": "semantic",
                "kind": "table",
                "src": "graph:dw",
                "state": "validated",
            },
        )
        self.assertNotIn("desc", nodes["DW.raw.Sales"])

    def test_uniform_state_and_lineage_are_reported_once(self) -> None:
        compact = _trace().to_compact_dict()

        self.assertEqual(compact["summary"]["states"], {"draft": 4})
        self.assertEqual(compact["summary"]["lineages"], {"etl": 4})
        self.assertTrue(all("state" not in item and "lin" not in item for item in compact["edges"]))

    def test_limits_are_derived_from_structure(self) -> None:
        self.assertEqual(_trace().to_compact_dict()["limits"], ["table_level"])

    def test_cycles_fold_internal_edges(self) -> None:
        a, b, c = (_ref(name, "table") for name in ("DW.a", "DW.b", "DW.c"))
        trace = UpstreamTrace(
            query="DW.a",
            start=a,
            hops=(
                _hop("h1", 1, b, a, "derived_from"),
                _hop("h2", 2, a, b, "derived_from"),
                _hop("h3", 2, c, b, "derived_from"),
            ),
            origins=(c,),
            warnings=("Lineage cycle detected at: DW.a",),
            truncated=False,
        )

        compact = trace.to_compact_dict()

        self.assertEqual(compact["cycles"], [{"internal_edges": 2, "members": ["DW.a", "DW.b"]}])
        self.assertEqual(
            [(item["from"], item["to"]) for item in compact["edges"]], [("DW.c", "DW.b")],
        )

    def test_colliding_references_are_qualified_by_source(self) -> None:
        start = _ref("DW.mart.Sales", "table")
        left = _ref("DW.raw.Sales", "table", source="graph:a")
        right = _ref("DW.raw.Sales", "table", source="graph:b")
        trace = UpstreamTrace(
            query="DW.mart.Sales",
            start=start,
            hops=(
                _hop("h1", 1, left, start, "derived_from"),
                _hop("h2", 1, right, start, "derived_from"),
            ),
            origins=(left, right),
            warnings=(),
            truncated=False,
        )

        self.assertEqual(
            trace.to_compact_dict()["origins"], ["graph:a:DW.raw.Sales", "graph:b:DW.raw.Sales"],
        )

    def test_projection_is_deterministic_and_leaves_the_full_view_alone(self) -> None:
        trace = _trace()
        shuffled = UpstreamTrace(
            query=trace.query,
            start=trace.start,
            hops=tuple(reversed(trace.hops)),
            origins=tuple(reversed(trace.origins)),
            warnings=trace.warnings,
            truncated=trace.truncated,
        )
        full = json.dumps(trace.to_dict(), sort_keys=True)

        self.assertEqual(
            json.dumps(trace.to_compact_dict(), sort_keys=True),
            json.dumps(shuffled.to_compact_dict(), sort_keys=True),
        )
        trace.to_compact_dict()
        self.assertEqual(json.dumps(trace.to_dict(), sort_keys=True), full)

    def test_cli_compact_view_prints_one_json_line(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                graph, lineage = _fixture()
                FileGraphStore().save(graph)
                FileLineageStore().save(lineage)
                base = ["lineage", "upstream", "Demo.mart.Sales", "--lineage", "dbt-sales",
                        "--graph", "demo", "--format", "json"]
                compact = _run_cli([*base, "--view", "compact"])
                full = _run_cli(base)
                text = _run_cli([*base[:-2], "--view", "compact"])
            finally:
                os.chdir(previous)

        self.assertEqual(compact[0], 0)
        self.assertEqual(len(compact[1].splitlines()), 1)
        payload = json.loads(compact[1])
        self.assertEqual(payload["start"], "Demo.mart.Sales")
        self.assertEqual(payload["origins"], ["Demo.raw.Sales"])
        self.assertIn("hops", json.loads(full[1]))
        self.assertIn("d1 Demo.mart.Sales <-materializes_as- dbt.model.sales", text[1])


def _ref(
    reference: str,
    kind: str,
    *,
    source: str = "graph:dw",
    description: str | None = None,
    description_kind: str | None = None,
    annotation_state: str | None = None,
) -> LineageReference:
    return LineageReference(
        id=f"{source}:{reference}",
        reference=reference,
        name=reference.rsplit(".", 1)[-1],
        kind=kind,
        source=source,
        description=description,
        description_kind=description_kind,
        annotation_state=annotation_state,
    )


def _hop(
    hop_id: str,
    depth: int,
    source: LineageReference,
    target: LineageReference,
    relation: str,
    *,
    evidence: LineageEvidence | None = None,
    reviews: tuple[LineageReview, ...] = (),
) -> LineageHop:
    return LineageHop(
        id=hop_id,
        depth=depth,
        source=source,
        target=target,
        relation=relation,
        state="draft",
        lineage="etl",
        evidence=evidence,
        reviews=reviews,
    )


def _evidence(reference: str, start: int, end: int) -> LineageEvidence:
    return LineageEvidence(
        source="sql_analysis", reference=reference, reason="reads", line_start=start, line_end=end,
    )


_SQL = "/repo/etl/load_sales.sql"


def _trace() -> UpstreamTrace:
    mart = _ref(
        "DW.mart.Sales",
        "table",
        description="One row per sale.",
        description_kind="semantic_annotation",
        annotation_state="validated",
    )
    job = _ref("etl.load_sales", "procedure", source="lineage:etl")
    raw = _ref(
        "DW.raw.Sales",
        "table",
        description="Observed table; location s3://bucket/raw/sales.",
        description_kind="technical_metadata",
    )
    orders = _ref("DW.raw.Orders", "table")
    return UpstreamTrace(
        query="DW.mart.Sales",
        start=mart,
        hops=(
            _hop(
                "m1", 1, job, mart, "materializes_as",
                evidence=_evidence("/repo/manifest.json#proc.load_sales", 1, 1),
            ),
            _hop("c1", 2, raw, job, "reads_from", evidence=_evidence(_SQL, 3, 9)),
            _hop("c2", 3, raw, job, "reads_from", evidence=_evidence(_SQL, 12, 14)),
            _hop("c3", 2, orders, job, "reads_from"),
            _hop("loop", 3, raw, raw, "derived_from"),
        ),
        origins=(raw, orders),
        warnings=("The trace contains lineage that has not been human-validated.",),
        truncated=False,
    )
