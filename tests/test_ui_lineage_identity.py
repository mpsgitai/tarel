"""What an unresolved lineage name means, and how sure the canvas is about the names it resolved."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from urllib.request import Request, urlopen

from tarel.lineage.contracts import LineageDefinition, LineageDocument
from tarel.lineage.resolution import resolve_reference
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
    _object,
    _objects,
    _step,
    _unit,
)

SOURCE = "Shop.main.Source"
TARGET = "Shop.main.Target"


def _model(*documents: LineageDocument, objects: Any = None) -> LineageFlowModel:
    return LineageFlowModel(documents, _objects() if objects is None else objects)


def _assets(model: LineageFlowModel, reference: str) -> list[dict[str, Any]]:
    return [
        node for node in model.nodes.values()
        if node["kind"] == "asset" and node["reference"] == reference
    ]


def _upstream(model: LineageFlowModel, start: str = TARGET) -> set[str]:
    walked = model.neighbourhood(start, direction="upstream", hops=8)
    assert walked is not None
    return {node["reference"] for node in walked["nodes"]}


def _writes_then_reads(reference: str, *, documents: int) -> tuple[LineageDocument, ...]:
    """One process fills ``reference`` from Source; another empties it into Target."""
    writer = (_unit("fill", "fill", reference, SOURCE),)
    reader = (_unit("drain", "drain", TARGET, reference),)
    if documents == 2:
        return (
            _document("one", _definition("fill"), units=writer),
            _document("two", _definition("drain"), units=reader),
        )
    return (_document(
        "etl", _definition("fill"), _definition("drain"), units=(*writer, *reader),
    ),)


class LocalReferenceScopeTests(TestCase):
    def test_same_named_temporary_tables_of_two_documents_stay_apart(self) -> None:
        model = _model(*_writes_then_reads("#tmp", documents=2))

        assets = _assets(model, "#tmp")
        self.assertEqual(len(assets), 2)
        self.assertEqual(len({asset["label"] for asset in assets}), 2, "labels must differ")
        self.assertEqual(len(model.edges), 2)

    def test_upstream_of_target_does_not_reach_the_foreign_source(self) -> None:
        model = _model(*_writes_then_reads("#tmp", documents=2))

        self.assertEqual(_upstream(model), {"#tmp", TARGET})

    def test_shared_index_never_learns_a_local_name(self) -> None:
        model = _model(*_writes_then_reads("#tmp", documents=2))

        self.assertNotIn("#tmp", model._index.aliases)

    def test_notation_of_a_temporary_table_does_not_change_its_scope(self) -> None:
        for reference in ("[#tmp]", "tempdb..#tmp", "dbo.#TMP"):
            with self.subTest(reference=reference):
                model = _model(*_writes_then_reads(reference, documents=2))

                self.assertNotIn(SOURCE, _upstream(model))

    def test_unrelated_definitions_of_one_document_do_not_share_a_session(self) -> None:
        model = _model(*_writes_then_reads("#tmp", documents=1))

        self.assertNotIn(SOURCE, _upstream(model))

    def test_steps_of_one_workflow_share_their_temporary_table(self) -> None:
        for after in (("fill-step",), ()):
            depends = (_step("fill-step", "fill", ()), _step("drain-step", "drain", after))
            document = _document(
                "etl", _definition("fill"), _definition("drain"),
                units=(
                    _unit("fill", "fill", "#tmp", SOURCE),
                    _unit("drain", "drain", TARGET, "#tmp"),
                ),
                steps=depends,
            )
            with self.subTest(linked=bool(after)):
                upstream = _upstream(_model(document))
                self.assertEqual(SOURCE in upstream, bool(after))

    def test_steps_connect_through_an_intermediate_step(self) -> None:
        document = _document(
            "etl", _definition("fill"), _definition("middle"), _definition("drain"),
            units=(
                _unit("fill", "fill", "#tmp", SOURCE),
                _unit("drain", "drain", TARGET, "#tmp"),
            ),
            steps=(
                _step("s1", "fill", ()),
                _step("s2", "middle", ("s1",)),
                _step("s3", "drain", ("s2",)),
            ),
        )

        self.assertIn(SOURCE, _upstream(_model(document)))

    def test_a_called_definition_shares_the_session_of_its_caller(self) -> None:
        document = _document(
            "etl", _definition("fill"), _definition("drain"),
            claims=(_claim("calls", "drain", "pipeline.fill"),),
            units=(
                _unit("fill", "fill", "#tmp", SOURCE),
                _unit("drain", "drain", TARGET, "#tmp"),
            ),
        )

        self.assertIn(SOURCE, _upstream(_model(document)))

    def test_a_variable_belongs_to_its_definition_even_across_steps(self) -> None:
        document = _document(
            "etl", _definition("fill"), _definition("drain"),
            units=(
                _unit("fill", "fill", "@rows", SOURCE),
                _unit("drain", "drain", TARGET, "@rows"),
            ),
            steps=(_step("s1", "fill", ()), _step("s2", "drain", ("s1",))),
        )

        self.assertNotIn(SOURCE, _upstream(_model(document)))

    def test_a_global_temporary_table_is_shared_inside_its_document_only(self) -> None:
        self.assertIn(SOURCE, _upstream(_model(*_writes_then_reads("##tmp", documents=1))))
        self.assertNotIn(SOURCE, _upstream(_model(*_writes_then_reads("##tmp", documents=2))))

    def test_a_bare_unresolved_name_joins_nothing_across_documents(self) -> None:
        self.assertIn(SOURCE, _upstream(_model(*_writes_then_reads("staging", documents=1))))
        self.assertNotIn(SOURCE, _upstream(_model(*_writes_then_reads("staging", documents=2))))

    def test_an_explicitly_qualified_table_stays_shared_across_documents(self) -> None:
        model = _model(*_writes_then_reads("Other.dbo.Staging", documents=2))

        self.assertEqual(len(_assets(model, "Other.dbo.Staging")), 1)
        self.assertEqual(_upstream(model), {SOURCE, "Other.dbo.Staging", TARGET})

    def test_a_graph_table_stays_shared_across_documents(self) -> None:
        model = _model(*_writes_then_reads("Shop.main.Target", documents=2))
        self.assertEqual(len(model.edges), 1)

        chained = _model(
            _document("one", _definition("fill"), units=(
                _unit("fill", "fill", "main.Target", SOURCE),
            )),
            _document("two", _definition("drain"), units=(
                _unit("drain", "drain", "Shop.main.Extra", "Shop.main.Target"),
            )),
        )
        self.assertIn(SOURCE, _upstream(chained, "Shop.main.Extra"))

    def test_a_local_name_can_still_start_a_trace_from_each_of_its_tables(self) -> None:
        model = _model(*_writes_then_reads("#tmp", documents=2))

        walked = model.neighbourhood("#tmp", direction="both", hops=1)

        assert walked is not None
        self.assertEqual(len(walked["start"]), 2)

    def test_ambiguous_names_of_two_documents_are_not_one_asset(self) -> None:
        objects = [*_objects(), _object("elsewhere", "Other", "main.Staging"),
                   _object("again", "Third", "main.Staging")]
        model = _model(*_writes_then_reads("main.Staging", documents=2), objects=objects)

        assets = _assets(model, "main.Staging")
        self.assertEqual(len(assets), 2)
        self.assertNotIn(SOURCE, _upstream(model))


def _realistic_objects() -> list[dict[str, object]]:
    """Object ids as real graphs store them, so a bare name can only match by short name."""
    return [
        _object("object:Shop/main/Source", "Shop", "main.Source"),
        _object("object:Shop/main/Target", "Shop", "main.Target"),
    ]


def _detail(model: LineageFlowModel, source: str, target: str) -> dict[str, Any]:
    edge = next(
        item for item in model.edges.values()
        if model.nodes[item.source]["reference"] == source
        and model.nodes[item.target]["reference"] == target
    )
    detail = model.edge_detail(edge.id, roots=())
    assert detail is not None
    return detail


def _resolutions(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        resolution
        for process in detail["processes"]
        for contribution in process["contributions"]
        for resolution in contribution["resolutions"]
    ]


class ResolutionInformationTests(TestCase):
    def _bare(self) -> tuple[LineageFlowModel, LineageDocument, LineageDefinition]:
        definition = _definition("load")
        document = _document("bare", definition, units=(
            _unit("load", "load", "Target", "Source"),
        ))
        return _model(document, objects=_realistic_objects()), document, definition

    def test_name_only_match_reaches_the_edge_detail_on_both_sides(self) -> None:
        model, document, definition = self._bare()
        resolver = resolve_reference(
            "Source", document, definition, model._index, model._declared[document.name],
        )
        self.assertIn("by name alone", resolver.resolution_note or "")

        resolutions = _resolutions(_detail(model, SOURCE, TARGET))

        by_side = {item["side"]: item for item in resolutions}
        self.assertEqual(set(by_side), {"source", "target"})
        self.assertEqual(by_side["source"], {
            "basis": "name_only",
            "candidates": [SOURCE],
            "note": resolver.resolution_note,
            "reference": "Source",
            "resolved_to": SOURCE,
            "side": "source",
            "warning": True,
        })

    def test_declared_identity_produces_no_warning(self) -> None:
        for source, target in ((SOURCE, TARGET), ("Source", TARGET)):
            with self.subTest(source=source):
                model = _model(
                    _document("sure", _definition("load"), units=(
                        _unit("load", "load", target, source),
                    )),
                    objects=_realistic_objects(),
                )

                self.assertEqual(_resolutions(_detail(model, SOURCE, TARGET)), [])

    def test_catalog_settled_name_is_a_note_rather_than_a_warning(self) -> None:
        objects = [
            *_realistic_objects(),
            _object("object:Other/main/Source", "Other", "main.Source"),
        ]
        model = _model(
            _document("sure", _definition("load"), units=(
                _unit("load", "load", TARGET, "Source"),
            )),
            objects=objects,
        )

        resolutions = _resolutions(_detail(model, SOURCE, TARGET))

        self.assertEqual([item["warning"] for item in resolutions], [False])
        self.assertEqual(resolutions[0]["basis"], "declared_catalogs")
        self.assertEqual(resolutions[0]["resolved_to"], SOURCE)

    def test_ambiguous_reference_lists_candidates_and_chooses_none(self) -> None:
        objects = [
            *_realistic_objects(),
            _object("object:Other/main/Source", "Other", "main.Source"),
        ]
        model = _model(
            _document("unsure", _definition("load"), units=(
                _unit("load", "load", "main.Target", "main.Source"),
            )),
            objects=objects,
        )
        edge = next(iter(model.edges.values()))
        self.assertEqual(model.nodes[edge.source]["kind"], "asset")

        detail = model.edge_detail(edge.id, roots=())

        assert detail is not None
        self.assertEqual(_resolutions(detail), [{
            "basis": "ambiguous",
            "candidates": ["Other.main.Source", SOURCE],
            "note": _resolutions(detail)[0]["note"],
            "reference": "main.Source",
            "resolved_to": None,
            "side": "source",
            "warning": True,
        }])
        self.assertIn(SOURCE, _resolutions(detail)[0]["note"])

    def test_contributions_of_one_edge_keep_their_own_resolution(self) -> None:
        model = _model(
            _document("bare", _definition("guess"), units=(
                _unit("guess", "guess", "Target", "Source"),
            )),
            _document("sure", _definition("certain"), units=(
                _unit("certain", "certain", TARGET, SOURCE),
            )),
            objects=_realistic_objects(),
        )

        detail = _detail(model, SOURCE, TARGET)

        by_label = {process["label"]: process for process in detail["processes"]}
        guessed = by_label["guess"]["contributions"][0]
        self.assertEqual(guessed["items"], ["guess"])
        self.assertEqual(
            [item["basis"] for item in guessed["resolutions"]], ["name_only", "name_only"],
        )
        self.assertEqual(by_label["certain"]["contributions"][0]["resolutions"], [])

    def test_note_survives_reading_through_a_called_process(self) -> None:
        model = _model(
            _document(
                "bare", _definition("outer"), _definition("inner"),
                claims=(
                    _claim("calls", "outer", "pipeline.inner"),
                    _claim("reads", "inner", "Source"),
                ),
                units=(_unit("write", "outer", "Target", "pipeline.inner"),),
            ),
            objects=_realistic_objects(),
        )

        bases = {
            (item["side"], item["reference"]): item["basis"]
            for item in _resolutions(_detail(model, SOURCE, TARGET))
        }

        self.assertEqual(bases[("source", "Source")], "name_only")
        self.assertEqual(bases[("target", "Target")], "name_only")


class DecisionRouteTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(temporary.name)
        sdk = Tarel(Path(temporary.name) / ".tarel")
        sdk.runtime.graph_store().save(_graph())
        sdk.runtime.lineage_store().save(_document(
            "etl", _definition("first"), _definition("second"),
            units=(
                _unit("u1", "first", TARGET, SOURCE),
                _unit("u2", "second", TARGET, SOURCE),
            ),
        ))
        server = _Server(
            ("127.0.0.1", 0),
            TarelUIBackend(UIConfig(graph="shop", lineages=("etl",), editable=True)),
            "fixture-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}"

    def _call(self, route: str, payload: dict[str, object] | None = None) -> dict[str, Any]:
        request = Request(
            self.base + route,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Tarel-Token": "fixture-token"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    def test_answer_says_whether_the_edge_outlived_the_decision(self) -> None:
        edge = self._call("/api/bootstrap")["lineage_flows"]["edges"][0]["id"]
        revision = self._call(f"/api/lineage/edge?id={edge}")["processes"][0]["revision"]

        first = self._call("/api/lineage/decision", {
            "lineage": "etl", "item_id": "u1", "decision": "reject", "reason": "Wrong.",
            "revision": revision, "edge": edge,
        })
        self.assertIs(first["edge_exists"], True)

        second = self._call("/api/lineage/decision", {
            "lineage": "etl", "item_id": "u2", "decision": "reject", "reason": "Wrong too.",
            "revision": first["revision"], "edge": edge,
        })
        self.assertIs(second["edge_exists"], False)

    def test_edge_is_optional_for_callers_that_do_not_show_one(self) -> None:
        edge = self._call("/api/bootstrap")["lineage_flows"]["edges"][0]["id"]
        revision = self._call(f"/api/lineage/edge?id={edge}")["processes"][0]["revision"]

        answer = self._call("/api/lineage/decision", {
            "lineage": "etl", "item_id": "u1", "decision": "validate", "reason": "Checked.",
            "revision": revision,
        })

        self.assertNotIn("edge_exists", answer)
