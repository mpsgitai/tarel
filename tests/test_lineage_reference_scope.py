"""Upstream traces follow an unresolved name only as far as that name can reach."""

from __future__ import annotations

import contextlib
import io
import json
import os
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.request import Request, urlopen

from tarel.cli import main
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.lineage.contracts import LineageDocument, LineageFailure
from tarel.lineage.traversal import UpstreamTrace, find_lineage_references, trace_upstream
from tarel.sdk import Tarel
from tarel.ui.backend import TarelUIBackend
from tarel.ui.contracts import UIConfig
from tarel.ui.payloads.lineage_flows import LineageFlowModel
from tarel.ui.server import _Server
from tests.test_ui_lineage_flows import (
    _claim,
    _definition,
    _document,
    _graph,
    _objects,
    _step,
    _unit,
)

SOURCE = "Shop.main.Source"
TARGET = "Shop.main.Target"
ALL_STATES = frozenset({"draft", "review_required", "validated"})


def _two_documents(reference: str) -> tuple[LineageDocument, ...]:
    return (
        _document("one", _definition("a"), units=(_unit("ua", "a", reference, SOURCE),)),
        _document("two", _definition("b"), units=(_unit("ub", "b", TARGET, reference),)),
    )


def _one_document(reference: str, **extra: object) -> tuple[LineageDocument, ...]:
    return (_document(
        "etl", _definition("a"), _definition("b"),
        units=(_unit("ua", "a", reference, SOURCE), _unit("ub", "b", TARGET, reference)),
        **extra,  # type: ignore[arg-type]
    ),)


_STEPS = {"steps": (_step("s1", "a", ()), _step("s2", "b", ("s1",)))}
_CALL = {"claims": (_claim("calls", "b", "pipeline.a"),)}


def _trace(
    *documents: LineageDocument, start: str = TARGET, **options: object,
) -> UpstreamTrace:
    return trace_upstream(documents, (_graph(),), start, **options)  # type: ignore[arg-type]


def _reaches_source(*documents: LineageDocument, **options: object) -> bool:
    trace = _trace(*documents, **options)
    return SOURCE in {hop.source.reference for hop in trace.hops}


class TemporaryNameTests(TestCase):
    def test_temporary_tables_of_two_documents_stay_apart(self) -> None:
        trace = _trace(*_two_documents("#tmp"))

        self.assertEqual(
            [(hop.source.reference, hop.target.reference) for hop in trace.hops],
            [("#tmp", TARGET)],
        )
        self.assertEqual([item.reference for item in trace.origins], ["#tmp"])
        self.assertIn("Unresolved upstream reference: #tmp", trace.warnings)

    def test_the_scope_is_named_so_a_reader_can_tell_the_tables_apart(self) -> None:
        origin = _trace(*_two_documents("#tmp")).origins[0]

        self.assertEqual(origin.name, "#tmp · two")
        self.assertEqual(origin.kind, "unresolved")
        self.assertEqual(origin.source, "external")

    def test_notation_does_not_change_the_scope(self) -> None:
        for reference in ("[#tmp]", "tempdb..#tmp", "dbo.#TMP"):
            with self.subTest(reference=reference):
                self.assertFalse(_reaches_source(*_two_documents(reference)))

    def test_unrelated_definitions_of_one_document_do_not_share_a_session(self) -> None:
        self.assertFalse(_reaches_source(*_one_document("#tmp")))

    def test_a_step_dependency_shares_the_session(self) -> None:
        self.assertTrue(_reaches_source(*_one_document("#tmp", **_STEPS)))

    def test_steps_connect_through_an_intermediate_step(self) -> None:
        document = _document(
            "etl", _definition("a"), _definition("middle"), _definition("b"),
            units=(_unit("ua", "a", "#tmp", SOURCE), _unit("ub", "b", TARGET, "#tmp")),
            steps=(
                _step("s1", "a", ()), _step("s2", "middle", ("s1",)), _step("s3", "b", ("s2",)),
            ),
        )

        self.assertTrue(_reaches_source(document))

    def test_a_call_shares_the_session(self) -> None:
        self.assertTrue(_reaches_source(*_one_document("#tmp", **_CALL)))

    def test_a_call_outside_the_selected_states_does_not_share_the_session(self) -> None:
        document = _document(
            "etl", _definition("a"), _definition("b"),
            claims=(_claim("calls", "b", "pipeline.a"),),
            units=(
                _unit("ua", "a", "#tmp", SOURCE, state="validated"),
                _unit("ub", "b", TARGET, "#tmp", state="validated"),
            ),
        )

        self.assertTrue(_reaches_source(document, states=ALL_STATES))
        self.assertFalse(_reaches_source(document, states=frozenset({"validated"})))

    def test_a_variable_belongs_to_its_definition_even_across_steps(self) -> None:
        self.assertFalse(_reaches_source(*_one_document("@rows", **_STEPS)))

    def test_a_global_temporary_table_is_shared_inside_its_document_only(self) -> None:
        self.assertTrue(_reaches_source(*_one_document("##tmp")))
        self.assertFalse(_reaches_source(*_two_documents("##tmp")))


class OtherUnresolvedNameTests(TestCase):
    def test_a_bare_name_joins_inside_its_document_only(self) -> None:
        self.assertTrue(_reaches_source(*_one_document("staging")))
        self.assertFalse(_reaches_source(*_two_documents("staging")))

    def test_a_qualified_name_stays_shared_across_documents(self) -> None:
        for reference in ("Other.dbo.Staging", "dbo.Staging"):
            with self.subTest(reference=reference):
                trace = _trace(*_two_documents(reference))

                self.assertIn(SOURCE, {hop.source.reference for hop in trace.hops})
                unresolved = next(
                    hop.source for hop in trace.hops if hop.target.reference == TARGET
                )
                self.assertEqual(unresolved.name, reference)

    def test_a_graph_table_stays_shared_across_documents(self) -> None:
        documents = (
            _document("one", _definition("a"), units=(_unit("ua", "a", "main.Target", SOURCE),)),
            _document("two", _definition("b"), units=(_unit("ub", "b", TARGET, SOURCE),)),
        )

        self.assertEqual(len({hop.id for hop in _trace(*documents).hops}), 2)

    def test_a_qualified_name_several_short_names_could_mean_stays_in_its_document(self) -> None:
        graphs = tuple(
            GraphDocument(
                name=name, connector="fixture", source_type="sql", catalog=name, dialect="sqlite",
                nodes=(
                    GraphNode("t", "table", "main.Staging", {}),
                    GraphNode("f", "field", "qty", {"object_id": "t"}),
                ),
                edges=(),
            )
            for name in ("Other", "Third")
        )

        trace = trace_upstream(
            _two_documents("Staging.qty"), (_graph(), *graphs), TARGET,
        )

        self.assertNotIn(SOURCE, {hop.source.reference for hop in trace.hops})


class StartingAtAScopedNameTests(TestCase):
    def test_one_table_of_that_name_starts_a_trace(self) -> None:
        trace = _trace(*_one_document("#tmp", **_STEPS), start="#tmp")

        self.assertEqual([item.reference for item in trace.origins], [SOURCE])

    def test_two_tables_of_that_name_are_ambiguous_and_listed_by_scope(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            _trace(*_two_documents("#tmp"), start="#tmp")

        self.assertEqual(raised.exception.code, "ambiguous_lineage_reference")
        self.assertIn("#tmp · one", str(raised.exception))
        self.assertIn("#tmp · two", str(raised.exception))

    def test_the_id_named_by_that_failure_starts_a_trace(self) -> None:
        documents = _two_documents("#tmp")
        found = find_lineage_references(documents, (_graph(),), "#tmp")

        self.assertEqual(
            sorted(item.name for item in found if item.kind == "unresolved"),
            ["#tmp · one", "#tmp · two"],
        )
        writer = next(item for item in found if item.name == "#tmp · one")
        trace = _trace(*documents, start=writer.id)
        self.assertEqual([item.reference for item in trace.origins], [SOURCE])


class FlowViewParityTests(TestCase):
    """The object trace and the data-flow canvas give one answer about what is upstream."""

    CASES = (
        ("#tmp across documents", _two_documents("#tmp")),
        ("[#tmp] across documents", _two_documents("[#tmp]")),
        ("##tmp across documents", _two_documents("##tmp")),
        ("bare across documents", _two_documents("staging")),
        ("qualified across documents", _two_documents("Other.dbo.Staging")),
        ("#tmp unrelated", _one_document("#tmp")),
        ("#tmp by steps", _one_document("#tmp", **_STEPS)),
        ("#tmp by a call", _one_document("#tmp", **_CALL)),
        ("##tmp in one document", _one_document("##tmp")),
        ("@rows across steps", _one_document("@rows", **_STEPS)),
        ("bare in one document", _one_document("staging")),
    )

    def test_both_views_reach_the_same_tables(self) -> None:
        for name, documents in self.CASES:
            with self.subTest(case=name):
                walked = LineageFlowModel(documents, _objects()).neighbourhood(
                    TARGET, direction="upstream", hops=8,
                )
                assert walked is not None
                canvas = {node["reference"] for node in walked["nodes"]}
                trace = _trace(*documents)
                traced = {
                    item.reference for hop in trace.hops for item in (hop.source, hop.target)
                    if item.kind in {"table", "unresolved"}
                }

                self.assertEqual(traced, canvas)

    def test_both_views_name_a_scope_alike(self) -> None:
        for name, documents in self.CASES:
            with self.subTest(case=name):
                model = LineageFlowModel(documents, _objects())
                labels = {
                    node["label"] for node in model.nodes.values()
                    if node["kind"] == "asset" and node["scope"] is not None
                }
                found = find_lineage_references(documents, (_graph(),), "tmp rows staging")
                network = [
                    item for item in found
                    if item.kind == "unresolved" and item.name != item.reference
                ]

                self.assertEqual({item.name for item in network}, labels)


class _SavedState(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(temporary.name)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.sdk.runtime.graph_store().save(_graph())
        for document in _two_documents("#tmp"):
            self.sdk.runtime.lineage_store().save(document)

    def _cli(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(list(arguments))
        return code, output.getvalue()


class EntryPointTests(_SavedState):
    SELECTED = ("--lineage", "one", "--lineage", "two", "--graph", "shop")

    def test_cli_trace_names_the_scope_and_stops_there(self) -> None:
        code, text = self._cli("lineage", "upstream", TARGET, *self.SELECTED)

        self.assertEqual(code, 0)
        self.assertIn("<- #tmp · two (derived_from", text)
        self.assertIn("- #tmp · two [unresolved]", text)
        self.assertNotIn(SOURCE, text)

    def test_cli_json_keeps_the_written_reference(self) -> None:
        code, text = self._cli(
            "lineage", "upstream", TARGET, *self.SELECTED, "--format", "json",
        )

        self.assertEqual(code, 0)
        payload = json.loads(text)
        self.assertEqual([item["reference"] for item in payload["origins"]], ["#tmp"])
        self.assertEqual([item["name"] for item in payload["origins"]], ["#tmp · two"])

    def test_cli_find_lists_each_table_by_its_scope(self) -> None:
        code, text = self._cli("lineage", "find", "#tmp", *self.SELECTED)

        self.assertEqual(code, 0)
        self.assertIn("- #tmp · one [unresolved; external]", text)
        self.assertIn("- #tmp · two [unresolved; external]", text)

    def test_sdk_grounding_trace_stops_at_the_scope(self) -> None:
        trace = self.sdk.grounding.upstream(TARGET, graph="shop", lineages=("one", "two"))

        self.assertNotIn(SOURCE, {hop.source.reference for hop in trace.hops})

    def test_focus_does_not_take_in_the_foreign_source(self) -> None:
        result = self.sdk.focus.build(
            "probe", seed=TARGET, lineages=("one", "two"), graphs=("shop",),
        )

        self.assertNotIn("graph:shop:source", {item.id for item in result.focus.members})

    def test_browser_route_stops_at_the_scope(self) -> None:
        server = _Server(
            ("127.0.0.1", 0),
            TarelUIBackend(UIConfig(graph="shop", lineages=("one", "two"), editable=False)),
            "fixture-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/lineage/upstream",
            data=json.dumps({"reference": TARGET, "lineages": ["one", "two"]}).encode(),
            headers={"Content-Type": "application/json", "X-Tarel-Token": "fixture-token"},
        )

        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())

        self.assertEqual([item["name"] for item in payload["origins"]], ["#tmp · two"])
