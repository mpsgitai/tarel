"""Unit tests for UI object health signals and summary counts."""

from __future__ import annotations

from unittest import TestCase

from tarel.graph.contracts import GraphAnnotation, GraphDocument, GraphEdge, GraphNode
from tarel.lineage.contracts import LineageDocument
from tarel.ui.payloads.graph import browser_graph
from tarel.ui.payloads.signals import extract_observed_rows
from tests.test_ui_lineage_flows import _definition, _document, _unit


def _sample_graph() -> GraphDocument:
    nodes = (
        GraphNode(
            id="object:demo/dw/fact_sales",
            type="table",
            label="dw.fact_sales",
            metadata={
                "namespace": "dw",
                "name": "fact_sales",
                "observed_rows": 12500,
            },
            annotation=GraphAnnotation(
                description="Sales fact table.",
                role="fact",
                state="validated",
            ),
        ),
        GraphNode(
            id="object:demo/dw/dim_empty",
            type="table",
            label="dw.dim_empty",
            metadata={
                "namespace": "dw",
                "name": "dim_empty",
                "observed_rows": 0,
            },
            annotation=GraphAnnotation(
                description="Empty dimension draft.",
                role="dimension",
                state="draft",
            ),
        ),
        GraphNode(
            id="object:demo/dw/stg_unknown",
            type="table",
            label="dw.stg_unknown",
            metadata={
                "namespace": "dw",
                "name": "stg_unknown",
            },
            annotation=None,
        ),
    )
    edges = (
        GraphEdge(
            id="fk:fact_sales_to_dim_empty",
            type="foreign_key",
            source_id="object:demo/dw/fact_sales",
            target_id="object:demo/dw/dim_empty",
            metadata={"state": "declared"},
        ),
    )
    return GraphDocument(
        name="demo",
        source_type="sqlite",
        connector="sqlite",
        catalog="demo",
        dialect="sqlite",
        nodes=nodes,
        edges=edges,
    )


def _sample_lineage() -> LineageDocument:
    return _document(
        "demo-etl",
        _definition("load_sales"),
        units=(
            _unit(
                "u1",
                "load_sales",
                "demo.dw.fact_sales",
                "demo.dw.stg_unknown",
                state="validated",
            ),
        ),
    )


class ObjectSignalsTests(TestCase):
    def test_extract_observed_rows_rejects_invalid_or_boolean_values(self) -> None:
        self.assertIsNone(extract_observed_rows({}))
        self.assertIsNone(extract_observed_rows({"observed_rows": True}))
        self.assertIsNone(extract_observed_rows({"observed_rows": -1}))
        self.assertEqual(extract_observed_rows({"observed_rows": 0}), 0)
        self.assertEqual(extract_observed_rows({"rows_profiled": 42}), 42)
        self.assertEqual(extract_observed_rows({"profile": {"observed_rows": 7}}), 7)

    def test_signals_without_lineage_never_mark_objects_as_orphan(self) -> None:
        payload = browser_graph(_sample_graph())
        by_name = {obj["name"]: obj["signals"] for obj in payload["objects"]}

        self.assertEqual(by_name["fact_sales"]["population"], "populated")
        self.assertEqual(by_name["fact_sales"]["observed_rows"], 12500)
        self.assertEqual(by_name["fact_sales"]["lineage"], "no_lineage_loaded")
        self.assertEqual(by_name["fact_sales"]["relations"], "connected")
        self.assertEqual(by_name["fact_sales"]["relation_count"], 1)
        self.assertEqual(by_name["fact_sales"]["annotation"], "reviewed")

        self.assertEqual(by_name["dim_empty"]["population"], "empty")
        self.assertEqual(by_name["dim_empty"]["observed_rows"], 0)
        self.assertEqual(by_name["dim_empty"]["lineage"], "no_lineage_loaded")
        self.assertEqual(by_name["dim_empty"]["relations"], "connected")
        self.assertEqual(by_name["dim_empty"]["annotation"], "draft")

        self.assertEqual(by_name["stg_unknown"]["population"], "unknown")
        self.assertIsNone(by_name["stg_unknown"]["observed_rows"])
        self.assertEqual(by_name["stg_unknown"]["lineage"], "no_lineage_loaded")
        self.assertEqual(by_name["stg_unknown"]["relations"], "isolated")
        self.assertEqual(by_name["stg_unknown"]["relation_count"], 0)
        self.assertEqual(by_name["stg_unknown"]["annotation"], "missing")

        summary = payload["health_summary"]
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["empty"], 1)
        self.assertEqual(summary["populated"], 1)
        self.assertEqual(summary["unknown_population"], 1)
        self.assertFalse(summary["lineage_loaded"])
        self.assertEqual(summary["lineage_orphan"], 0)
        self.assertEqual(summary["isolated"], 1)
        self.assertEqual(summary["unannotated"], 1)

    def test_signals_with_lineage_distinguish_connected_and_orphan(self) -> None:
        payload = browser_graph(_sample_graph(), lineage_documents=(_sample_lineage(),))
        by_name = {obj["name"]: obj["signals"] for obj in payload["objects"]}

        self.assertEqual(by_name["fact_sales"]["lineage"], "connected")
        self.assertEqual(by_name["fact_sales"]["lineage_upstream_count"], 1)
        self.assertEqual(by_name["fact_sales"]["lineage_downstream_count"], 0)

        self.assertEqual(by_name["stg_unknown"]["lineage"], "connected")
        self.assertEqual(by_name["stg_unknown"]["lineage_upstream_count"], 0)
        self.assertEqual(by_name["stg_unknown"]["lineage_downstream_count"], 1)

        self.assertEqual(by_name["dim_empty"]["lineage"], "orphan")
        self.assertEqual(by_name["dim_empty"]["lineage_upstream_count"], 0)
        self.assertEqual(by_name["dim_empty"]["lineage_downstream_count"], 0)

        summary = payload["health_summary"]
        self.assertTrue(summary["lineage_loaded"])
        self.assertEqual(summary["lineage_orphan"], 1)
