"""``--format pretty``: deterministic layout, ASCII fallback, CLI wiring and coverage."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from test_focus import _fixture

from tarel.annotations.coverage import measure_coverage
from tarel.cli import main
from tarel.cli._pretty import Pretty, render_error, visible_len
from tarel.cli._pretty_lineage import render_lineage
from tarel.cli._terminal import Style
from tarel.errors import TarelError
from tarel.graph.contracts import GraphAnnotation
from tarel.graph.store import FileGraphStore
from tarel.lineage.store import FileLineageStore
from tarel.workspaces.core import create_workspace, define_system
from tarel.workspaces.store import FileWorkspaceStore

_PLAIN = Style(color=False, unicode=True, live=False)
_ASCII = Style(color=False, unicode=False, live=False)


class _Utf8Buffer(io.StringIO):
    """A captured stdout that, like a real UTF-8 terminal, can encode box-drawing symbols."""

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return "utf-8"


class PrimitiveTests(TestCase):
    def test_table_aligns_numbers_and_drops_empty_columns(self) -> None:
        page = Pretty(_PLAIN, 60)

        page.table(("NAME", "COUNT", "NOTE"), [("a", "1", ""), ("bbb", "1,234", "")], right=(1,))

        self.assertEqual(
            page.lines,
            ["  NAME  COUNT", "  " + "─" * 58, "  a         1", "  bbb   1,234"],
        )

    def test_table_shrinks_other_columns_before_the_name(self) -> None:
        page = Pretty(_PLAIN, 60)

        page.table(("OBJECT", "MEANING"), [("dbo.FactInternetSales", "x" * 80)])

        row = page.lines[-1]
        self.assertTrue(row.startswith("  dbo.FactInternetSales  "))
        self.assertEqual(len(row), 60)
        self.assertTrue(row.endswith("…"))

    def test_paths_lose_their_beginning(self) -> None:
        page = Pretty(_PLAIN, 60)

        self.assertEqual(page.fit("/very/long/path/to/model.sql", 12, left=True), "…o/model.sql")

    def test_tree_marks_repeated_nodes_instead_of_expanding_them(self) -> None:
        page = Pretty(_PLAIN, 80)
        children = {
            "root": [("reads", "a", ""), ("reads", "b", "r1:3")],
            "a": [("reads", "shared", "")],
            "b": [("reads", "shared", "")],
            "shared": [("reads", "leaf", "")],
        }

        page.tree("root", children, lambda key: key)

        self.assertEqual(
            page.lines,
            [
                "  root",
                "  ├─ reads a",
                "  │  └─ reads shared",
                "  │     └─ reads leaf",
                "  └─ reads b  r1:3",
                "     └─ reads shared  (see above)",
            ],
        )

    def test_branches_through_a_folded_cycle_stay_attached(self) -> None:
        payload = {
            "direction": "up", "start": "A", "summary": {"nodes": 4, "edges": 2},
            "nodes": {key: {"kind": "table"} for key in "ABCD"},
            "edges": [
                {"d": 2, "rel": "derived_from", "from": "D", "to": "B"},
                {"d": 3, "rel": "derived_from", "from": "C", "to": "D"},
            ],
            "cycles": [{"members": ["A", "B"], "internal_edges": 2}],
            "origins": ["C"], "warnings": [],
        }
        output = _Utf8Buffer()
        with mock.patch.dict(os.environ, {"COLUMNS": "80"}), redirect_stdout(output):
            render_lineage(payload)

        text = output.getvalue()
        self.assertIn("↻ same cycle as B [table]", text)
        self.assertIn("derived_from ← D [table]", text)
        self.assertIn("derived_from ← C [table]", text)
        self.assertNotIn("no edges in this direction", text)

    def test_deep_trees_render_without_recursion(self) -> None:
        page = Pretty(_PLAIN, 80)
        children = {f"n{index}": [("reads", f"n{index + 1}", "")] for index in range(5000)}

        page.tree("n0", children, lambda key: key)

        self.assertEqual(len(page.lines), 5001)

    def test_ascii_fallback_uses_only_ascii(self) -> None:
        page = Pretty(_ASCII, 60)
        page.header("Lineage", "x", ["table"])
        page.tree("x", {"x": [("reads <-", "y", "")]}, lambda key: key)
        page.add(page.bar(0.5, 8))
        page.bullets(["one"])

        text = "\n".join(page.lines)
        text.encode("ascii")
        self.assertIn("`- reads <- y", text)
        self.assertIn("####....", text)

    def test_colour_codes_do_not_count_as_width(self) -> None:
        page = Pretty(Style(color=True, unicode=True, live=True), 60)
        coloured = page.style.bold("x" * 70)

        self.assertEqual(visible_len(coloured), 70)
        self.assertEqual(page.fit(coloured, 10), "x" * 9 + "…")

    def test_error_block_lists_the_repair(self) -> None:
        stream = _Utf8Buffer()
        error = TarelError(
            "invalid_graph_role", "'dbt' is a lineage document, not a catalog graph.",
            hint="Pass 'dbt' as a lineage.", retryable=True,
            details={"suggestion": {"lineages": ["dbt"], "graphs": ["iceberg"]},
                     "accepted_preview": ["iceberg"], "accepted_count": 3},
        )
        with mock.patch.dict(os.environ, {"COLUMNS": "80"}):
            render_error(error, stream)

        lines = stream.getvalue().splitlines()
        self.assertEqual(lines[0], "✗ Error [invalid_graph_role]")
        self.assertIn("  Suggestion: --lineage dbt --graph iceberg", lines)
        self.assertIn("  Accepted:   iceberg … (3 total)", lines)
        self.assertIn("  Retry:      yes, with the changes above", lines)


class CoverageTests(TestCase):
    def test_counts_states_and_orders_unannotated_by_row_count(self) -> None:
        graph, _lineage = _fixture()
        nodes = [node for node in graph.nodes if node.type == "table"]
        annotated = replace(
            nodes[0],
            annotation=GraphAnnotation(description="Raw sales.", role="fact", state="validated"),
        )
        big = replace(nodes[1], metadata={**nodes[1].metadata, "row_count": 500})

        coverage = measure_coverage(
            "graph:demo", [(graph, annotated), (graph, big), (graph, nodes[2])], limit=1,
        ).to_dict()

        self.assertEqual(coverage["objects"], 3)
        self.assertEqual(coverage["annotated_pct"], 33.3)
        self.assertEqual(coverage["role_coverage_pct"], 33.3)
        self.assertEqual(coverage["states"]["unannotated"], 2)
        self.assertEqual(coverage["unannotated"][0]["row_count"], 500)
        self.assertTrue(coverage["truncated"])


class PrettyCliTests(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous = Path.cwd()
        os.chdir(directory.name)
        self.addCleanup(os.chdir, previous)
        graph, lineage = _fixture()
        FileGraphStore().save(graph)
        FileLineageStore().save(lineage)
        FileWorkspaceStore().save(
            define_system(create_workspace("estate"), "sales", graph_names=("demo",),
                          graphs={"demo": graph})
        )
        patcher = mock.patch.dict(os.environ, {"NO_COLOR": "1", "COLUMNS": "100"})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("TAREL_FORMAT", None)

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        output, errors = _Utf8Buffer(), _Utf8Buffer()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(list(arguments))
        return code, output.getvalue(), errors.getvalue()

    def test_every_pretty_command_renders_deterministically(self) -> None:
        self.run_cli("focus", "build", "sales", "--seed", "Demo.mart.Sales",
                     "--lineage", "dbt-sales", "--graph", "demo", "--format", "json")
        commands = {
            "LINEAGE UPSTREAM": ("lineage", "trace", "Demo.mart.Sales"),
            "LINEAGE DOWNSTREAM (IMPACT)": ("lineage", "downstream", "Demo.raw.Sales"),
            "LINEAGE BATCH": ("lineage", "batch", "Demo.mart.Sales", "Demo.raw.Sales"),
            "FOCUS": ("focus", "show", "sales"),
            "WORKSPACE": ("workspace", "show", "estate", "--depth", "zones"),
            "GRAPH": ("graph", "header", "demo"),
            "GRAPH SLICE": ("graph", "slice", "demo", "--object", "raw.Sales"),
            "SEARCH": ("search", "demo", "sales"),
            "CONTEXT PACKET": ("context", "build", "demo", "sales"),
            "ANNOTATION COVERAGE": ("annotation", "coverage", "--graph", "demo"),
        }
        for title, arguments in commands.items():
            with self.subTest(command=" ".join(arguments)):
                first = self.run_cli(*arguments, "--format", "pretty")
                second = self.run_cli(*arguments, "--format", "pretty")
                self.assertEqual(first[0], 0, first[2])
                self.assertEqual(first, second)
                self.assertTrue(first[1].startswith(title + "  "), first[1][:80])
                self.assertNotIn("\033[", first[1])
                self.assertTrue(all(visible_len(line) <= 100 or "─ " in line
                                    for line in first[1].splitlines()))

    def test_upstream_tree_shows_the_path_to_the_origin(self) -> None:
        _code, output, _errors = self.run_cli("lineage", "trace", "Demo.mart.Sales",
                                              "--format", "pretty")

        self.assertIn("  Demo.mart.Sales [table]", output)
        self.assertIn("  └─ materializes_as ← dbt.model.sales [query]", output)
        self.assertIn("     └─ reads_from ← Demo.raw.Sales [table]  r1:1", output)
        self.assertIn("Sources:   auto: 1 lineage (all_local), 1 graph (declared_catalogs)", output)
        self.assertIn("  ORIGINS (1)", output)

    def test_pretty_error_goes_to_stderr(self) -> None:
        code, output, errors = self.run_cli(
            "lineage", "upstream", "Demo.mart.Sales", "--graph", "dbt-sales", "--format", "pretty",
        )

        self.assertEqual((code, output), (2, ""))
        self.assertTrue(errors.startswith("✗ Error [invalid_graph_role]"))
        self.assertIn("Suggestion: --lineage dbt-sales --graph demo", errors)

    def test_tarel_format_sets_the_default_only_where_pretty_exists(self) -> None:
        with mock.patch.dict(os.environ, {"TAREL_FORMAT": "pretty"}):
            pretty = self.run_cli("graph", "header", "demo")
            listed = self.run_cli("graph", "list")
            workfile = self.run_cli("annotation", "next", "demo")

        self.assertTrue(pretty[1].startswith("GRAPH  demo"))
        self.assertEqual(listed[1].strip(), "demo")
        self.assertIsInstance(json.loads(workfile[1]), dict)

    def test_unknown_tarel_format_warns_and_is_ignored(self) -> None:
        with mock.patch.dict(os.environ, {"TAREL_FORMAT": "fancy"}):
            code, output, errors = self.run_cli("graph", "header", "demo")

        self.assertEqual(code, 0)
        self.assertTrue(output.startswith("Graph: demo"))
        self.assertIn("ignoring TAREL_FORMAT='fancy'", errors)

    def test_commands_without_a_pretty_view_reject_it(self) -> None:
        with self.assertRaises(SystemExit):
            self.run_cli("lineage", "find", "sales", "--format", "pretty")

    def test_ascii_console_gets_ascii_symbols(self) -> None:
        output = io.StringIO()  # encoding None: treated like an ASCII console
        with redirect_stdout(output):
            main(["lineage", "trace", "Demo.mart.Sales", "--format", "pretty"])

        output.getvalue().encode("ascii")
        self.assertIn("`- materializes_as <- dbt.model.sales [query]", output.getvalue())
