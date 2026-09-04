from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.cli import main
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import graph_revision
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.runtime import RuntimeLineageDocument, RuntimeLineageInput
from tarel.lineage.runtime_projection import browser_runtime_lineage
from tarel.sdk import Tarel


class LogicalRuntimeLineageTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = GraphDocument(
            "commerce",
            "fixture",
            "sql",
            "commerce",
            "sqlite",
            (GraphNode("orders", "table", "sales.orders", {"namespace": "sales"}),),
            (),
        )
        self.sdk.runtime.graph_store().save(self.graph)

    def _payload(self, operations: tuple[str, ...] = ("extract", "explode", "reference_mapping")):
        source = {
            "kind": "sql_query",
            "sequence": 1,
            "call_id": "source",
            "status": "succeeded",
            "source": "orders-reader",
            "dialect": "sqlite",
            "operation": "select",
            "statement_sha256": _hash("source-plan"),
            "inputs": ["orders"],
            "result": _result(),
            "error_code": None,
        }
        events = [source]
        for operation in operations:
            events.append(_logical(operation, len(events) + 1, events[-1]["call_id"]))
        last = events[-1]["call_id"]
        events.append(
            {
                "kind": "python_analysis",
                "tool_type": "python",
                "operation": "analyze",
                "sequence": len(events) + 1,
                "call_id": "answer-frame",
                "status": "accepted",
                "code_sha256": _hash("sum grouped quantity"),
                "consumes": [last],
                "executor": {"plugin_id": "v2.python", "plugin_version": "1.0"},
                "inputs": [_frame(last)],
                "analysis": _analysis(),
                "result": _result(),
                "error_code": None,
            }
        )
        return {
            "contract_version": "tarel.runtime-lineage-input.v0.3",
            "run_id": "logical-example",
            "graph": {"name": self.graph.name, "revision": graph_revision(self.graph)},
            "events": events,
        }

    def test_source_extract_explode_mapping_python_trace_and_roundtrip(self) -> None:
        observed = RuntimeLineageInput.from_dict(self._payload())
        imported = self.sdk.lineage.import_runtime("logical-run", observed)
        loaded = self.sdk.lineage.load_runtime("logical-run")
        self.assertEqual(loaded, imported.document)
        self.assertEqual(loaded.contract_version, "tarel.runtime-lineage.v0.3")
        self.assertEqual(RuntimeLineageDocument.from_dict(loaded.to_dict()), loaded)
        trace = self.sdk.lineage.trace_runtime("logical-run", "answer-frame")
        self.assertEqual(
            tuple(item.kind for item in trace.calls),
            (
                "sql_query",
                "logical_operation",
                "logical_operation",
                "logical_operation",
                "python_analysis",
            ),
        )
        self.assertEqual(
            tuple(item.operation for item in trace.calls[1:4]),
            (
                "extract",
                "explode",
                "reference_mapping",
            ),
        )
        self.assertEqual(len(trace.dependencies), 4)
        self.assertEqual(tuple(item.node_id for item in trace.origins), ("orders",))
        self.assertNotIn("operation", trace.calls[0].to_dict())
        self.assertEqual(trace.calls[1].to_dict()["artifact_validation"], "caller_claimed")

    def test_all_fixed_operation_types_have_typed_pinned_artifact_claims(self) -> None:
        for operation in _KINDS:
            with self.subTest(operation=operation):
                payload = self._payload((operation,))
                event = RuntimeLineageInput.from_dict(payload).events[1]
                self.assertEqual(event.dependency_refs[0].kind, _KINDS[operation])
                self.assertEqual(event.artifact_validation, "caller_claimed")
                payload["events"][1]["dependency_refs"][0]["kind"] = "unknown"
                with self.assertRaises(LineageFailure):
                    RuntimeLineageInput.from_dict(payload)

    def test_only_metadata_resolution_can_start_without_prior_frames(self) -> None:
        for operation in _KINDS:
            event = _logical(operation, 1, None)
            payload = self._payload()
            payload["events"] = [event]
            if operation in {"family_resolution", "context_expand"}:
                observed = RuntimeLineageInput.from_dict(payload)
                self.assertEqual(observed.events[0].consumes, ())
            else:
                with self.subTest(operation=operation), self.assertRaises(LineageFailure):
                    RuntimeLineageInput.from_dict(payload)

    def test_failed_operations_remain_visible_but_cannot_feed_successful_analysis(self) -> None:
        payload = self._payload(("explode",))
        failed = payload["events"][1]
        failed.update(status="failed", result=None, error_code="invalid_structure")
        with self.assertRaises(LineageFailure):
            RuntimeLineageInput.from_dict(payload)
        payload["events"] = payload["events"][:2]
        self.sdk.lineage.import_runtime("failed", RuntimeLineageInput.from_dict(payload))
        loaded = self.sdk.lineage.load_runtime("failed")
        self.assertEqual(loaded.events[1].error_code, "invalid_structure")
        with self.assertRaises(LineageFailure) as failure:
            self.sdk.lineage.trace_runtime("failed", "explode")
        self.assertEqual(failure.exception.code, "runtime_call_not_evidence")

    def test_calls_must_be_prior_unique_same_document_and_frame_bound(self) -> None:
        mutations = (
            ("consumes", ["not-in-this-document"]),
            ("consumes", ["answer-frame"]),
            ("consumes", ["source", "source"]),
            ("inputs", []),
            ("inputs", [{**_frame("source"), "source": "wrong-reader"}]),
            ("operation_sha256", "select * from private"),
            ("artifact_validation", "confirmed"),
            ("dependency_refs", []),
            (
                "dependency_refs",
                [
                    {
                        "kind": "object_binding",
                        "graph": "commerce",
                        "id": "x",
                        "revision": _hash("x"),
                    }
                ],
            ),
        )
        for key, value in mutations:
            payload = self._payload(("explode",))
            payload["events"][1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(LineageFailure):
                RuntimeLineageInput.from_dict(payload)

    def test_unknown_data_code_sql_private_values_and_paths_fail_closed(self) -> None:
        for section, key in (
            (None, "sql"),
            (None, "code"),
            (None, "mapping_groups"),
            ("analysis", "raw_rows"),
            ("executor", "api_key"),
            ("result", "values"),
        ):
            payload = self._payload(("explode",))
            event = payload["events"][1]
            target = event if section is None else event[section]
            target[key] = "PRIVATE-SENTINEL"
            with self.subTest(section=section, key=key), self.assertRaises(LineageFailure):
                RuntimeLineageInput.from_dict(payload)
        payload = self._payload(("explode",))
        payload["events"][1]["dependency_refs"][0]["id"] = "/private/local/path"
        with self.assertRaises(LineageFailure):
            RuntimeLineageInput.from_dict(payload)

    def test_historical_refs_do_not_need_current_sidecars_or_promote_candidates(self) -> None:
        payload = self._payload()
        self.sdk.lineage.import_runtime("historic", RuntimeLineageInput.from_dict(payload))
        self.assertFalse((self.project / ".tarel" / "logical-topology").exists())
        self.assertFalse((self.project / ".tarel" / "reference-mappings").exists())
        stored = self.sdk.lineage.load_runtime("historic").to_dict()
        self.assertEqual(stored["events"][1]["artifact_validation"], "caller_claimed")
        self.assertNotIn("reviewed", json.dumps(stored))
        self.assertNotIn("confirmed", json.dumps(stored))

    def test_v01_and_v02_do_not_silently_accept_new_events(self) -> None:
        for version in ("v0.1", "v0.2"):
            payload = self._payload()
            payload["contract_version"] = f"tarel.runtime-lineage-input.{version}"
            with self.subTest(version=version), self.assertRaises(LineageFailure):
                RuntimeLineageInput.from_dict(payload)

    def test_v03_preserves_direct_duckdb_federated_duckdb_and_python_distinctions(self) -> None:
        payload = self._payload(("explode",))
        payload["events"][0]["dialect"] = "duckdb"
        federated = copy.deepcopy(payload["events"][-1])
        federated.update(
            kind="federated_query",
            engine="duckdb",
            operation="select",
            statement_sha256=federated.pop("code_sha256"),
        )
        federated.pop("tool_type")
        federated["executor"]["plugin_id"] = "v2.duckdb"
        payload["events"][-1] = federated
        observed = RuntimeLineageInput.from_dict(payload)
        loaded = self.sdk.lineage.import_runtime("duckdb", observed).document
        self.assertEqual(loaded.events[0].dialect, "duckdb")
        self.assertEqual(loaded.events[-1].to_dict()["engine"], "duckdb")
        self.assertNotIn("tool_type", loaded.events[-1].to_dict())
        self.assertEqual(RuntimeLineageDocument.from_dict(loaded.to_dict()), loaded)

    def test_cli_sdk_import_show_and_trace_share_the_same_event_path(self) -> None:
        payload = self._payload()
        path = self.project / "sanitized.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        old = Path.cwd()
        try:
            os.chdir(self.project)
            output, errors = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(
                    [
                        "lineage",
                        "import-runtime",
                        "cli-run",
                        "--source",
                        str(path),
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual((status, errors.getvalue()), (0, ""))
            self.assertEqual(
                json.loads(output.getvalue())["runtime_lineage"],
                self.sdk.lineage.load_runtime("cli-run").to_dict(),
            )
            output = StringIO()
            with redirect_stdout(output):
                status = main(
                    ["lineage", "trace-runtime", "cli-run", "answer-frame", "--format", "json"]
                )
            self.assertEqual(status, 0)
            self.assertEqual(
                json.loads(output.getvalue()),
                self.sdk.lineage.trace_runtime("cli-run", "answer-frame").to_dict(),
            )
        finally:
            os.chdir(old)

    def test_readonly_projection_preserves_actual_dependency_chain_and_claim_status(self) -> None:
        document = self.sdk.lineage.import_runtime(
            "gui", RuntimeLineageInput.from_dict(self._payload())
        ).document
        payload = browser_runtime_lineage(document)
        logical = [node for node in payload["nodes"] if node.get("kind") == "logical_operation"]
        self.assertEqual(len(logical), 3)
        self.assertTrue(all(node["artifact_validation"] == "caller_claimed" for node in logical))
        self.assertEqual(len(payload["edges"]), 5)
        self.assertIn(
            {"source": "call::explode", "target": "call::reference_mapping", "kind": "consumes"},
            payload["edges"],
        )
        self.assertNotIn("static_job", json.dumps(payload))

    def test_private_harness_workflow_yields_useful_evidence_without_persisting_rows(self) -> None:
        private_rows = (
            (1, '[{"product":"PRIVATE-P1","quantity":2}]'),
            (2, '[{"product":"PRIVATE-P1","quantity":3},{"product":"PRIVATE-P2","quantity":1}]'),
        )
        with sqlite3.connect(":memory:") as database:
            database.execute("CREATE TABLE orders (order_id INTEGER, items TEXT)")
            database.executemany("INSERT INTO orders VALUES (?,?)", private_rows)
            database.execute("PRAGMA query_only=ON")
            source = database.execute(
                "SELECT order_id, items FROM orders ORDER BY order_id"
            ).fetchall()
        extracted = [(key, json.loads(items)) for key, items in source]
        exploded = [
            (key, item["product"], item["quantity"]) for key, items in extracted for item in items
        ]
        mapping = {"PRIVATE-P1": "PRIVATE-CATEGORY-A", "PRIVATE-P2": "PRIVATE-CATEGORY-B"}
        mapped = [(key, mapping[product], quantity) for key, product, quantity in exploded]
        totals = {
            category: sum(qty for _, group, qty in mapped if group == category)
            for category in mapping.values()
        }
        self.assertEqual(totals, {"PRIVATE-CATEGORY-A": 5, "PRIVATE-CATEGORY-B": 1})
        payload = self._payload()
        frames = (source, extracted, exploded, mapped, sorted(totals.items()))
        columns = (
            ["order_id", "items"],
            ["order_id", "items"],
            ["order_id", "product", "quantity"],
            ["order_id", "category", "quantity"],
            ["category", "quantity"],
        )
        for index, (event, frame) in enumerate(zip(payload["events"], frames, strict=True)):
            event["result"].update(
                row_count=len(frame), sha256=_hash(frame), columns=columns[index]
            )
            if index:
                event["inputs"][0]["frame_sha256"] = _hash(frames[index - 1])
                event["analysis"]["grain"] = columns[index][:-1]
        result = self.sdk.lineage.import_runtime("harness", RuntimeLineageInput.from_dict(payload))
        persisted = result.path.read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE-", persisted)
        self.assertNotIn("SELECT", persisted)
        self.assertNotIn("items TEXT", persisted)
        self.assertEqual(self.sdk.lineage.load_runtime("harness").events[2].result.row_count, 3)


_KINDS = {
    "extract": "logical_topology",
    "explode": "logical_topology",
    "reference_mapping": "reference_mapping",
    "object_binding": "object_binding",
    "family_resolution": "object_family",
    "hierarchy_rollup": "semantic_concept",
    "context_expand": "context_expansion",
}


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _result() -> dict[str, object]:
    return {
        "columns": ["order_id", "quantity"],
        "row_count": 2,
        "sha256": _hash("output"),
        "truncated": False,
    }


def _frame(call_id: str) -> dict[str, str]:
    return {
        "call_id": call_id,
        "alias": "input",
        "source": "orders-reader" if call_id == "source" else "logical-frame",
        "frame_sha256": _hash("input"),
    }


def _analysis() -> dict[str, object]:
    return {
        "grain": ["order_id"],
        "join_coverage": None,
        "unmatched_counts": {},
        "reconciliation_status": "not_run",
        "duration_ms": 2,
        "limits": {"input_row_limit": 1000, "output_row_limit": 1000, "timeout_ms": 5000},
    }


def _logical(operation: str, sequence: int, previous: str | None) -> dict[str, object]:
    return {
        "kind": "logical_operation",
        "operation": operation,
        "sequence": sequence,
        "call_id": operation,
        "status": "succeeded",
        "operation_sha256": _hash(operation),
        "consumes": [previous] if previous else [],
        "inputs": [_frame(previous)] if previous else [],
        "dependency_refs": [
            {
                "kind": _KINDS[operation],
                "graph": "commerce",
                "id": "artifact-1",
                "revision": _hash("revision"),
            }
        ],
        "executor": {"plugin_id": "v2.logical", "plugin_version": "1.0"},
        "analysis": _analysis(),
        "result": _result(),
        "error_code": None,
        "artifact_validation": "caller_claimed",
    }
