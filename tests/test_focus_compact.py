import json
import os
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_focus import _fixture, _run_cli

from tarel.focus.contracts import FocusDocument, FocusHop, FocusMember, FocusSource
from tarel.graph.store import FileGraphStore
from tarel.lineage.store import FileLineageStore


class CompactFocusTests(TestCase):
    def test_members_are_keyed_by_reference_with_their_full_id(self) -> None:
        compact = _focus().to_compact_dict()

        self.assertEqual(compact["start"], "DW.Fact.Sale")
        self.assertEqual(
            compact["nodes"]["DW.Fact.Sale"],
            {"depth": 0, "id": "graph:dw:object:Fact.Sale", "kind": "table"},
        )
        self.assertEqual(compact["origins"], ["DW.Raw.Orders"])
        self.assertEqual(compact["sources"], ["graph:dw", "lineage:etl"])

    def test_self_loops_and_duplicates_are_gone(self) -> None:
        compact = _focus().to_compact_dict()
        edges = compact["edges"]

        self.assertFalse([item for item in edges if item["from"] == item["to"]])
        triples = Counter((item["from"], item["to"], item["rel"]) for item in edges)
        self.assertEqual(max(triples.values()), 1)
        self.assertEqual(compact["self_loops_omitted"], 1)
        self.assertEqual(compact["summary"]["duplicates_merged"], 1)
        merged = [item for item in edges if item.get("edge_count")]
        self.assertEqual(merged, [{"d": 1, "edge_count": 2, "from": "DW.Integration.Sale_Staging",
                                   "rel": "derived_from", "to": "DW.Fact.Sale"}])

    def test_cycles_are_folded_into_one_entry(self) -> None:
        compact = _focus().to_compact_dict()

        self.assertEqual(
            compact["cycles"],
            [{"internal_edges": 2,
              "members": ["DW.Dimension.Customer", "DW.Integration.Sale_Staging"]}],
        )
        self.assertNotIn(
            ("DW.Dimension.Customer", "DW.Integration.Sale_Staging"),
            [(item["from"], item["to"]) for item in compact["edges"]],
        )

    def test_projection_does_not_change_the_snapshot(self) -> None:
        focus = _focus()
        before = focus.to_dict()

        first = json.dumps(focus.to_compact_dict(), sort_keys=True)
        second = json.dumps(focus.to_compact_dict(), sort_keys=True)

        self.assertEqual(first, second)
        self.assertEqual(focus.to_dict(), before)

    def test_cli_show_compact(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                graph, lineage = _fixture()
                FileGraphStore().save(graph)
                FileLineageStore().save(lineage)
                _run_cli(["focus", "build", "sales", "--seed", "Demo.mart.Sales",
                          "--lineage", "dbt-sales", "--graph", "demo"])
                compact = _run_cli(["focus", "show", "sales", "--view", "compact",
                                    "--format", "json"])
                full = _run_cli(["focus", "show", "sales", "--format", "json"])
            finally:
                os.chdir(previous)

        payload = json.loads(compact[1])
        self.assertEqual(payload["start"], "Demo.mart.Sales")
        self.assertEqual(payload["revision"], json.loads(full[1])["revision"])
        self.assertEqual(payload["origins"], ["Demo.raw.Sales"])


def _member(reference: str, depth: int, *, origin: bool = False) -> FocusMember:
    return FocusMember(
        id=f"graph:dw:object:{reference.removeprefix('DW.')}",
        reference=reference,
        name=reference,
        kind="table",
        source="graph:dw",
        depth=depth,
        reasons=("seed",) if depth == 0 else ("upstream:derived_from",),
        origin=origin,
    )


def _focus() -> FocusDocument:
    sale = _member("DW.Fact.Sale", 0)
    staging = _member("DW.Integration.Sale_Staging", 1)
    customer = _member("DW.Dimension.Customer", 2)
    orders = _member("DW.Raw.Orders", 3, origin=True)

    def hop(hop_id: str, depth: int, source: FocusMember, target: FocusMember) -> FocusHop:
        return FocusHop(hop_id, depth, source.id, target.id, "derived_from", "draft", "etl")

    return FocusDocument(
        name="sales",
        seed="DW.Fact.Sale",
        seed_id=sale.id,
        max_hops=12,
        states=("draft",),
        sources=(FocusSource("graph", "dw", "0" * 64), FocusSource("lineage", "etl", "1" * 64)),
        members=(sale, staging, customer, orders),
        hops=(
            hop("h1", 1, staging, sale),
            hop("h2", 1, staging, sale),
            hop("h3", 2, customer, staging),
            hop("h4", 3, staging, customer),
            hop("h5", 3, orders, customer),
            hop("h6", 2, staging, staging),
        ),
        warnings=("Lineage cycle detected at: DW.Integration.Sale_Staging",),
        truncated=False,
    )
