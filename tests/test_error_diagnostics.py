import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_focus import _fixture, _run_cli

from tarel.errors import TarelError, name_preview, unknown_name_error
from tarel.graph.store import FileGraphStore
from tarel.lineage.application import require_source_roles, trace_upstream_use_case
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.store import FileLineageStore
from tarel.runtime import TarelRuntime


class TarelErrorPayloadTests(TestCase):
    def test_to_dict_omits_empty_hint_and_details(self) -> None:
        self.assertEqual(
            TarelError("stale_lineage", "Reload first.").to_dict(),
            {"error": {"code": "stale_lineage", "message": "Reload first.", "retryable": False}},
        )

    def test_to_dict_carries_repair_fields(self) -> None:
        error = TarelError(
            "bad", "Bad input.", hint="Use x.", retryable=True, details={"param": "graphs"},
        )

        self.assertEqual(
            error.to_dict(),
            {
                "error": {
                    "code": "bad",
                    "details": {"param": "graphs"},
                    "hint": "Use x.",
                    "message": "Bad input.",
                    "retryable": True,
                }
            },
        )

    def test_unknown_name_previews_close_spellings_first_and_is_retryable(self) -> None:
        names = [f"graph-{index:02d}" for index in range(10)] + ["lakehouse-iceberg"]

        error = unknown_name_error(
            LineageFailure,
            "graph_not_found",
            "Graph not found: lakehouse-icebrg",
            param="graph",
            value="lakehouse-icebrg",
            accepted=names,
            noun="graph",
        )

        self.assertIsInstance(error, LineageFailure)
        self.assertTrue(error.retryable)
        self.assertEqual(error.hint, "Did you mean 'lakehouse-iceberg'?")
        self.assertEqual(error.details["accepted_count"], 11)
        self.assertEqual(
            error.details["accepted_preview"],
            ["lakehouse-iceberg", "graph-00", "graph-01", "graph-02", "graph-03"],
        )

    def test_unknown_name_without_close_match_lists_known_names(self) -> None:
        error = unknown_name_error(
            TarelError, "focus_not_found", "Focus not found: zz", param="focus", value="zz",
            accepted=("b", "a"), noun="focus",
        )

        self.assertEqual(error.hint, "Known focus names: a, b.")
        self.assertEqual(name_preview("zz", ()), [])


class SourceRoleTests(TestCase):
    def test_lineage_passed_as_graph_suggests_the_corrected_sources(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            require_source_roles(
                ("airflow",),
                ("dbt", "iceberg"),
                known_lineages=("airflow", "dbt"),
                known_graphs=("delta", "iceberg"),
            )

        error = raised.exception
        self.assertEqual(error.code, "invalid_graph_role")
        self.assertTrue(error.retryable)
        self.assertEqual(
            error.details["suggestion"],
            {"graphs": ["iceberg"], "lineages": ["airflow", "dbt"]},
        )
        self.assertEqual(error.details["param"], "graphs")
        self.assertEqual(error.details["value"], "dbt")
        self.assertEqual(error.details["accepted_count"], 2)

    def test_graph_passed_as_lineage_is_reported_as_invalid_lineage_role(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            require_source_roles(
                ("iceberg",), (), known_lineages=("dbt",), known_graphs=("iceberg",),
            )

        self.assertEqual(raised.exception.code, "invalid_lineage_role")
        self.assertEqual(
            raised.exception.details["suggestion"], {"graphs": ["iceberg"], "lineages": []},
        )

    def test_unknown_names_fall_through_to_not_found(self) -> None:
        require_source_roles(("x",), ("y",), known_lineages=(), known_graphs=())

    def test_trace_use_case_rejects_a_misplaced_lineage(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = TarelRuntime(Path(directory) / ".tarel")
            graph, lineage = _fixture()
            runtime.graph_store().save(graph)
            runtime.lineage_store().save(lineage)

            with self.assertRaises(LineageFailure) as raised:
                trace_upstream_use_case(
                    "Demo.mart.Sales",
                    lineage_names=("dbt-sales",),
                    graph_names=("dbt-sales",),
                    runtime=runtime,
                )

        self.assertEqual(raised.exception.code, "invalid_graph_role")


class CliErrorOutputTests(TestCase):
    def test_json_format_writes_structured_error_to_stderr_only(self) -> None:
        code, output, errors = _in_fixture_state(
            ["lineage", "upstream", "Demo.mart.Sales", "--lineage", "dbt-sales",
             "--graph", "dbt-sales", "--format", "json"]
        )

        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        payload = json.loads(errors)
        self.assertEqual(payload["error"]["code"], "invalid_graph_role")
        self.assertTrue(payload["error"]["retryable"])
        self.assertEqual(
            payload["error"]["details"]["suggestion"],
            {"graphs": ["demo"], "graphs_from": "declared_catalogs", "lineages": ["dbt-sales"]},
        )

    def test_text_format_prints_the_hint_line(self) -> None:
        code, output, errors = _in_fixture_state(["focus", "show", "missing"])

        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertEqual(
            errors.splitlines(),
            ["error [focus_not_found]: Focus not found: missing",
             "hint: No focus exists in this TAREL state yet."],
        )

    def test_not_found_names_close_spellings(self) -> None:
        _code, _output, errors = _in_fixture_state(
            ["graph", "show", "demo1", "--format", "json"]
        )

        error = json.loads(errors)["error"]
        self.assertEqual(error["code"], "graph_not_found")
        self.assertEqual(error["details"]["accepted_preview"], ["demo"])
        self.assertEqual(error["hint"], "Did you mean 'demo'?")


def _in_fixture_state(arguments: list[str]) -> tuple[int, str, str]:
    previous = Path.cwd()
    with TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            graph, lineage = _fixture()
            FileGraphStore().save(graph)
            FileLineageStore().save(lineage)
            return _run_cli(arguments)
        finally:
            os.chdir(previous)
