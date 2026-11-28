"""Tests for opt-in anomaly signals reader and context packet integration (Slice 1)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tarel.anomaly_signals import (
    ANOMALY_SIGNALS_CONTRACT_VERSION,
    MAX_ANOMALY_SIGNAL_BYTES,
    AnomalySignalsError,
    load_anomaly_signals_file,
    load_anomaly_signals_for_graphs,
)
from tarel.context.application import (
    compile_context_use_case,
    describe_context_use_case,
)
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import graph_revision, physical_graph_revision
from tarel.runtime import TarelRuntime


def _sample_graph(name: str = "retail") -> GraphDocument:
    return GraphDocument(
        name=name,
        source_type="sqlite",
        connector="sqlite",
        catalog=name,
        dialect="sqlite",
        nodes=(
            GraphNode(
                id="table:main.orders",
                type="table",
                label="main.orders",
                metadata={"namespace": "main", "name": "orders", "primary_key": ["order_id"]},
            ),
            GraphNode(
                id="field:main.orders.order_id",
                type="field",
                label="order_id",
                metadata={
                    "object_id": "table:main.orders",
                    "data_type": "INTEGER",
                    "nullable": False,
                    "is_primary_key": True,
                    "position": 1,
                },
            ),
            GraphNode(
                id="table:main.order_lines",
                type="table",
                label="main.order_lines",
                metadata={"namespace": "main", "name": "order_lines", "primary_key": ["line_id"]},
            ),
            GraphNode(
                id="field:main.order_lines.line_id",
                type="field",
                label="line_id",
                metadata={
                    "object_id": "table:main.order_lines",
                    "data_type": "INTEGER",
                    "nullable": False,
                    "is_primary_key": True,
                    "position": 1,
                },
            ),
            GraphNode(
                id="table:main.empty_staging",
                type="table",
                label="main.empty_staging",
                metadata={"namespace": "main", "name": "empty_staging"},
            ),
        ),
        edges=(),
    )


def _valid_signals_payload(
    graph: GraphDocument,
    *,
    physical_rev: str | None = None,
) -> dict[str, object]:
    return {
        "contract_version": ANOMALY_SIGNALS_CONTRACT_VERSION,
        "graph": graph.name,
        "graph_revision": graph_revision(graph),
        "physical_revision": (
            physical_rev if physical_rev is not None else physical_graph_revision(graph)
        ),
        "observed_at": "2026-11-25T23:00:00+00:00",
        "objects": {
            "table:main.orders": {
                "observed_rows": 142100,
                "state": "anomalous",
                "origin": "window_query",
                "delta_7d_pct": -18.5,
                "sparkline_14d": [2000, 2100, 1950, 1600],
                "expected_range": [1900, 2200],
                "schema_change_report": None,
                "active_findings": [
                    {
                        "finding_id": "f-orders-1",
                        "category": "distribution_shift",
                        "rule": "js_divergence",
                        "field": "status",
                        "summary": "status share shifted toward CANCELLED",
                        "evidence_sql": "SELECT status, COUNT(*) FROM main.orders GROUP BY status",
                        "distribution_comparison": {
                            "baseline": {"COMPLETED": 0.85, "CANCELLED": 0.15},
                            "current": {"COMPLETED": 0.40, "CANCELLED": 0.60},
                        },
                        "downstream_affected": ["table:main.order_lines"],
                    }
                ],
            },
            "table:main.order_lines": {
                "observed_rows": 410000,
                "state": "active",
                "origin": "window_query",
                "delta_7d_pct": 2.1,
                "sparkline_14d": [5000, 5100, 5050, 5200],
                "expected_range": [4800, 5400],
                "schema_change_report": None,
                "active_findings": [],
            },
            "table:main.empty_staging": {
                "observed_rows": 0,
                "state": "empty",
                "origin": "catalog_stats",
                "delta_7d_pct": None,
                "sparkline_14d": [],
                "expected_range": None,
                "schema_change_report": None,
                "active_findings": [],
            },
        },
        "edge_shifts": [
            {
                "upstream_object_id": "table:main.orders",
                "downstream_object_id": "table:main.order_lines",
                "metric": "rows",
                "ratio": 2.4,
                "expected_range": [2.8, 3.0],
                "delta_pct": -17.2,
                "finding_id": "f-edge-1",
            }
        ],
    }


class AnomalySignalsReaderTests(unittest.TestCase):
    def test_valid_sidecar_loads_cleanly_and_detects_fresh_revision(self) -> None:
        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            anomaly_dir = Path(tmp) / "anomaly"
            anomaly_dir.mkdir()
            (anomaly_dir / "retail.signals.json").write_text(
                json.dumps(_valid_signals_payload(graph)), encoding="utf-8"
            )
            loaded = load_anomaly_signals_for_graphs((graph,), anomaly_dir=anomaly_dir)
            self.assertEqual(loaded.missing_graphs, ())
            self.assertEqual(loaded.stale_graphs, ())
            signal_file = loaded.files["retail"]
            self.assertFalse(signal_file.stale)
            self.assertEqual(signal_file.objects["table:main.orders"].state, "anomalous")
            self.assertEqual(len(signal_file.edge_shifts), 1)
            self.assertEqual(signal_file.edge_shifts[0].delta_pct, -17.2)

    def test_stale_physical_revision_is_marked_stale(self) -> None:
        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            anomaly_dir = Path(tmp) / "anomaly"
            anomaly_dir.mkdir()
            (anomaly_dir / "retail.signals.json").write_text(
                json.dumps(_valid_signals_payload(graph, physical_rev="old-rev")),
                encoding="utf-8",
            )
            loaded = load_anomaly_signals_for_graphs((graph,), anomaly_dir=anomaly_dir)
            self.assertEqual(loaded.stale_graphs, ("retail",))
            self.assertTrue(loaded.files["retail"].stale)

    def test_missing_file_is_reported_without_crashing(self) -> None:
        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            loaded = load_anomaly_signals_for_graphs((graph,), anomaly_dir=Path(tmp) / "anomaly")
            self.assertEqual(loaded.missing_graphs, ("retail",))
            self.assertEqual(loaded.files, {})

    def test_rejects_corrupt_json_wrong_contract_and_oversized_file(self) -> None:
        graph = _sample_graph()
        current_rev = physical_graph_revision(graph)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_json = root / "bad.signals.json"
            bad_json.write_text("{not json", encoding="utf-8")
            with self.assertRaises(AnomalySignalsError) as ctx:
                load_anomaly_signals_file(
                    bad_json, expected_graph="retail", current_physical_revision=current_rev
                )
            self.assertEqual(ctx.exception.code, "invalid_anomaly_signals")

            wrong_contract = root / "wrong.signals.json"
            payload = _valid_signals_payload(graph)
            payload["contract_version"] = "tarel.anomaly.signals.v9.9"
            wrong_contract.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AnomalySignalsError) as ctx:
                load_anomaly_signals_file(
                    wrong_contract, expected_graph="retail", current_physical_revision=current_rev
                )
            self.assertEqual(ctx.exception.code, "unsupported_anomaly_signals_contract")

            oversized = root / "big.signals.json"
            oversized.write_bytes(b"x" * (MAX_ANOMALY_SIGNAL_BYTES + 1))
            with self.assertRaises(AnomalySignalsError) as ctx:
                load_anomaly_signals_file(
                    oversized, expected_graph="retail", current_physical_revision=current_rev
                )
            self.assertEqual(ctx.exception.code, "anomaly_signals_too_large")


class ContextAnomalyIntegrationTests(unittest.TestCase):
    def test_opt_in_preserves_stable_hash_and_brief_only_surfaces_anomalous_or_empty(self) -> None:
        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TarelRuntime.local(Path(tmp) / ".tarel")
            runtime.graph_store().save(graph)
            anomaly_dir = runtime.root / "anomaly"
            anomaly_dir.mkdir(parents=True)
            # Write corrupt sidecar first to prove default build never reads it.
            sidecar = anomaly_dir / "retail.signals.json"
            sidecar.write_text("{corrupt", encoding="utf-8")

            baseline = compile_context_use_case(
                "retail",
                "orders",
                object_ids=("table:main.orders", "table:main.order_lines"),
                runtime=runtime,
            )
            self.assertNotIn("anomaly_signals", baseline.dynamic_dict())
            self.assertNotIn("Active data signals:", describe_context_use_case(baseline).text())

            # Now write valid signals and opt in.
            sidecar.write_text(json.dumps(_valid_signals_payload(graph)), encoding="utf-8")
            with_anomaly = compile_context_use_case(
                "retail",
                "orders",
                object_ids=("table:main.orders", "table:main.order_lines"),
                include_anomaly=True,
                runtime=runtime,
            )
            self.assertEqual(baseline.stable_hash, with_anomaly.stable_hash)
            self.assertNotEqual(baseline.dynamic_hash, with_anomaly.dynamic_hash)

            dynamic_signals = with_anomaly.dynamic_dict()["anomaly_signals"]
            assert isinstance(dynamic_signals, dict)
            self.assertEqual(dynamic_signals["stale_graphs"], [])
            self.assertEqual(dynamic_signals["missing_graphs"], [])
            self.assertEqual(len(dynamic_signals["edge_shifts"]), 1)
            self.assertIn("table:main.orders", dynamic_signals["objects"])
            self.assertNotIn("table:main.empty_staging", dynamic_signals["objects"])

            brief = describe_context_use_case(with_anomaly)
            self.assertIn("Active data signals:", brief.text())
            self.assertIn("main.orders: anomalous", brief.text())

            # Quiet-only packet should not emit Active data signals in brief.
            quiet = compile_context_use_case(
                "retail",
                "order_lines",
                object_ids=("table:main.order_lines",),
                include_anomaly=True,
                runtime=runtime,
            )
            self.assertNotIn("Active data signals:", describe_context_use_case(quiet).text())

    def test_anomaly_signals_respect_max_characters_and_remeasure_counts(self) -> None:
        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TarelRuntime.local(Path(tmp) / ".tarel")
            runtime.graph_store().save(graph)
            anomaly_dir = runtime.root / "anomaly"
            anomaly_dir.mkdir(parents=True)
            payload = _valid_signals_payload(graph)
            objects = payload["objects"]
            assert isinstance(objects, dict)
            orders = objects["table:main.orders"]
            assert isinstance(orders, dict)
            findings = orders["active_findings"]
            assert isinstance(findings, list)
            findings[0]["evidence_sql"] = "SELECT " + ("x" * 50_000)
            (anomaly_dir / "retail.signals.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            baseline = compile_context_use_case(
                "retail",
                "orders",
                object_ids=("table:main.orders", "table:main.order_lines"),
                max_characters=10_000,
                runtime=runtime,
            )
            with_anomaly = compile_context_use_case(
                "retail",
                "orders",
                object_ids=("table:main.orders", "table:main.order_lines"),
                max_characters=10_000,
                include_anomaly=True,
                runtime=runtime,
            )
            self.assertEqual(baseline.stable_hash, with_anomaly.stable_hash)
            self.assertEqual(with_anomaly.context_characters, len(with_anomaly.canonical_json()))
            self.assertLessEqual(with_anomaly.context_characters, 10_000)
            signals = with_anomaly.dynamic_dict()["anomaly_signals"]
            assert isinstance(signals, dict)
            self.assertTrue(signals.get("truncated"))
            self.assertIn("table:main.orders", signals["objects"])


class UIAnomalyBackendTests(unittest.TestCase):
    def test_bootstrap_is_identical_without_flag_and_enriches_with_flag(self) -> None:
        from tarel.ui.backend import TarelUIBackend
        from tarel.ui.contracts import UIConfig

        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TarelRuntime.local(Path(tmp) / ".tarel")
            runtime.graph_store().save(graph)
            anomaly_dir = runtime.root / "anomaly"
            anomaly_dir.mkdir(parents=True)
            sidecar = anomaly_dir / "retail.signals.json"
            # Corrupt sidecar proves default UI does not touch .tarel/anomaly/.
            sidecar.write_text("{corrupt", encoding="utf-8")

            baseline = TarelUIBackend(UIConfig(graph="retail"), runtime=runtime).bootstrap()
            self.assertNotIn("anomaly", baseline)
            for item in baseline["objects"]:
                self.assertNotIn("anomaly", item)
            self.assertEqual(baseline["health_summary"]["empty"], 0)

            # Now write valid signals and enable --anomaly.
            sidecar.write_text(json.dumps(_valid_signals_payload(graph)), encoding="utf-8")
            enriched = TarelUIBackend(
                UIConfig(graph="retail", anomaly=True), runtime=runtime
            ).bootstrap()
            self.assertEqual(enriched["anomaly"]["enabled"], True)
            self.assertEqual(enriched["anomaly"]["stale_graphs"], [])
            self.assertEqual(enriched["anomaly"]["missing_graphs"], [])
            self.assertEqual(
                enriched["anomaly"]["summary"],
                {"active": 1, "anomalous": 1, "empty": 1, "static": 0},
            )
            self.assertEqual(len(enriched["anomaly"]["edge_shifts"]), 1)
            # Empty table observed_rows == 0 flows into Health lens signals.
            self.assertEqual(enriched["health_summary"]["empty"], 1)
            by_oid = {item["object_id"]: item for item in enriched["objects"]}
            self.assertEqual(by_oid["table:main.empty_staging"]["signals"]["population"], "empty")
            self.assertEqual(by_oid["table:main.orders"]["anomaly"]["state"], "anomalous")
            self.assertEqual(
                by_oid["table:main.orders"]["anomaly"]["sparkline_14d"],
                [2000.0, 2100.0, 1950.0, 1600.0],
            )
            self.assertEqual(len(by_oid["table:main.orders"]["anomaly"]["active_findings"]), 1)

            # Stale physical_revision is reported explicitly.
            sidecar.write_text(
                json.dumps(_valid_signals_payload(graph, physical_rev="stale-rev")),
                encoding="utf-8",
            )
            stale_payload = TarelUIBackend(
                UIConfig(graph="retail", anomaly=True), runtime=runtime
            ).bootstrap()
            self.assertEqual(stale_payload["anomaly"]["stale_graphs"], ["retail"])
            stale_orders = next(
                item
                for item in stale_payload["objects"]
                if item["object_id"] == "table:main.orders"
            )
            self.assertTrue(stale_orders["anomaly"]["stale"])

    def test_browser_edge_shifts_respect_object_scope(self) -> None:
        from tarel.ui.payloads.graph import browser_workspace
        from tarel.workspaces.contracts import WorkspaceDocument
        from tarel.workspaces.scope import ResolvedScope, ResolvedScopeObject, ScopeSelection

        graph = _sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            anomaly_dir = Path(tmp) / "anomaly"
            anomaly_dir.mkdir()
            (anomaly_dir / "retail.signals.json").write_text(
                json.dumps(_valid_signals_payload(graph)), encoding="utf-8"
            )
            loaded = load_anomaly_signals_for_graphs((graph,), anomaly_dir=anomaly_dir)
            scope = ResolvedScope(
                workspace="ws",
                selection=ScopeSelection(objects=("retail:table:main.empty_staging",)),
                graph_names=("retail",),
                objects=(
                    ResolvedScopeObject(
                        graph="retail",
                        object_id="table:main.empty_staging",
                        label="main.empty_staging",
                        type="table",
                        namespace="main",
                        system="core",
                        area="staging",
                        zones=(),
                    ),
                ),
                warnings=(),
                scope_hash="scope-1",
            )
            payload = browser_workspace(
                (graph,),
                scope,
                workspace=WorkspaceDocument(name="ws", systems=()),
                anomaly_signals=loaded,
            )
            self.assertEqual(payload["anomaly"]["edge_shifts"], [])


if __name__ == "__main__":
    unittest.main()
