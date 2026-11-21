"""The browser's data-flow lineage: tables on nodes, processes on edges, details on demand."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.lineage.contracts import (
    LineageAnalysis,
    LineageAnalysisFailure,
    LineageClaim,
    LineageDefinition,
    LineageDocument,
    LineageEvidence,
    LineageMaterialization,
    LineageReview,
    LineageStep,
    LineageWriteSource,
    LineageWriteUnit,
    validate_lineage_document,
)
from tarel.sdk import Tarel
from tarel.ui.backend import TarelUIBackend
from tarel.ui.contracts import UIConfig
from tarel.ui.payloads.graph import browser_graph
from tarel.ui.payloads.lineage_flows import LineageFlowModel, browser_lineage_flows
from tarel.ui.payloads.lineage_source import definition_source, excerpt_lines
from tarel.ui.server import _Server

_LOAD_SQL = "\n".join(f"-- line {number}" for number in range(1, 21))


class DataFlowPayloadTests(TestCase):
    def test_tables_connect_directly_with_the_process_on_the_edge(self) -> None:
        flows = _flows(_document("etl", _definition("load"), units=(
            _unit("u1", "load", "Shop.main.Target", "Shop.main.Source"),
        )))

        self.assertEqual(flows["version"], 2)
        self.assertEqual(_labels(flows), {("Source", "Target")})
        self.assertEqual({node["kind"] for node in flows["nodes"]}, {"table"})
        edge = flows["edges"][0]
        self.assertEqual(
            {key: edge["processes"][0][key] for key in ("label", "operation", "role", "state")},
            {"label": "load", "operation": "insert", "role": "business_data", "state": "draft"},
        )
        self.assertEqual(flows["processes"][0]["edges"], [edge["id"]])

    def test_short_script_names_resolve_to_graph_tables_not_external_assets(self) -> None:
        flows = _flows(_document("etl", _definition("load"), units=(
            _unit("u1", "load", "main.Target", "Source"),
        )))

        self.assertEqual(_labels(flows), {("Source", "Target")})
        self.assertEqual({node["kind"] for node in flows["nodes"]}, {"table"})

    def test_two_processes_share_one_edge_with_the_weakest_state(self) -> None:
        flows = _flows(_document(
            "etl", _definition("first"), _definition("second"),
            units=(
                _unit("u1", "first", "Shop.main.Target", "Shop.main.Source", state="validated"),
                _unit("u2", "second", "Shop.main.Target", "Shop.main.Source", state="draft"),
            ),
        ))

        self.assertEqual(len(flows["edges"]), 1)
        edge = flows["edges"][0]
        self.assertEqual(edge["state"], "draft")
        self.assertEqual({item["label"] for item in edge["processes"]}, {"first", "second"})

    def test_state_order_keeps_the_uncertain_visible(self) -> None:
        for states, expected in (
            (("validated", "review_required"), "review_required"),
            (("review_required", "draft"), "draft"),
            (("validated", "validated"), "validated"),
        ):
            with self.subTest(states=states):
                flows = _flows(_document(
                    "etl", _definition("first"), _definition("second"),
                    units=(
                        _unit(
                            "u1", "first", "Shop.main.Target", "Shop.main.Source",
                            state=states[0],
                        ),
                        _unit(
                            "u2", "second", "Shop.main.Target", "Shop.main.Source",
                            state=states[1],
                        ),
                    ),
                ))
                self.assertEqual(flows["edges"][0]["state"], expected)

    def test_rejected_statements_draw_no_flow(self) -> None:
        flows = _flows(_document("etl", _definition("load"), units=(
            _unit("u1", "load", "Shop.main.Target", "Shop.main.Source", state="rejected"),
        )))

        self.assertEqual(flows["edges"], [])

    def test_read_only_process_makes_a_note_not_a_phantom_edge(self) -> None:
        flows = _flows(_document("reports", _definition("card"), claims=(
            _claim("c1", "card", "Shop.main.Target"),
        )))

        self.assertEqual(flows["edges"], [])
        process = flows["processes"][0]
        self.assertEqual(process["label"], "card")
        self.assertEqual(process["reads_only"], ["shop::target"])

    def test_read_of_a_writing_process_links_to_its_target_and_is_marked_indirect(self) -> None:
        flows = _flows(_document(
            "etl", _definition("load"),
            claims=(_claim("c1", "load", "Shop.main.Source"),),
            units=(_unit("u1", "load", "Shop.main.Target", None),),
        ))

        self.assertEqual(_labels(flows), {("Source", "Target")})
        self.assertTrue(flows["edges"][0]["indirect"])
        self.assertEqual(flows["edges"][0]["processes"][0]["operation"], "read")

    def test_named_write_source_is_not_indirect_or_doubled_by_its_claim(self) -> None:
        flows = _flows(_document(
            "etl", _definition("load"),
            claims=(_claim("c1", "load", "Shop.main.Source"),),
            units=(_unit("u1", "load", "Shop.main.Target", "Shop.main.Source"),),
        ))

        edge = flows["edges"][0]
        self.assertFalse(edge["indirect"])
        self.assertEqual([item["operation"] for item in edge["processes"]], ["insert"])

    def test_write_from_a_named_process_keeps_the_state_of_its_reads(self) -> None:
        document = _document(
            "etl", _definition("load"), _definition("extract"),
            claims=(_claim("c1", "extract", "Shop.main.Source"),),
            units=(
                _unit("u1", "load", "Shop.main.Target", "pipeline.extract", state="validated"),
            ),
        )
        model = LineageFlowModel((document,), _objects())
        flows = model.payload()

        self.assertEqual(_labels(flows), {("Source", "Target")})
        edge = flows["edges"][0]
        self.assertEqual(edge["state"], "draft")
        detail = model.edge_detail(edge["id"], roots=())
        contribution = detail["processes"][0]["contributions"][0]
        self.assertEqual(contribution["state"], "draft")
        self.assertEqual(contribution["items"], ["u1", "c1"])

    def test_materialization_connects_the_reads_of_its_definition(self) -> None:
        flows = _flows(_document(
            "dbt", _definition("model"),
            claims=(_claim("c1", "model", "Shop.main.Source"),),
            materializations=(_materialization("m1", "model", "Shop.main.Target"),),
        ))

        self.assertEqual(_labels(flows), {("Source", "Target")})
        self.assertEqual(flows["edges"][0]["processes"][0]["operation"], "materialize")

    def test_called_process_without_writes_passes_its_reads_through(self) -> None:
        flows = _flows(_document(
            "etl", _definition("binding"), _definition("extract"),
            claims=(
                _claim("c1", "extract", "Shop.main.Source"),
                _claim("c2", "binding", "pipeline.extract"),
            ),
            materializations=(_materialization("m1", "binding", "Shop.main.Target"),),
        ))

        self.assertEqual(_labels(flows), {("Source", "Target")})

    def test_calling_cycle_terminates(self) -> None:
        flows = _flows(_document(
            "etl", _definition("one"), _definition("two"),
            claims=(
                _claim("c1", "one", "pipeline.two"),
                _claim("c2", "two", "pipeline.one"),
                _claim("c3", "two", "Shop.main.Source"),
            ),
            materializations=(_materialization("m1", "one", "Shop.main.Target"),),
        ))

        self.assertEqual(_labels(flows), {("Source", "Target")})

    def test_same_table_as_source_and_target_draws_no_loop(self) -> None:
        flows = _flows(_document("etl", _definition("load"), units=(
            _unit("u1", "load", "Shop.main.Target", "Shop.main.Target"),
        )))

        self.assertEqual(flows["edges"], [])

    def test_ambiguous_name_stays_a_flagged_asset_rather_than_a_guess(self) -> None:
        objects = [*_objects(), _object("other", "Other", "main.Source")]
        flows = browser_lineage_flows(
            (_document("etl", _definition("load"), units=(
                _unit("u1", "load", "main.Target", "main.Source"),
            )),),
            objects,
        )

        asset = next(node for node in flows["nodes"] if node["kind"] == "asset")
        self.assertEqual(
            asset["ambiguous_candidates"], ["Other.main.Source", "Shop.main.Source"],
        )
        self.assertEqual(flows["edges"][0]["source"], asset["id"])

    def test_unresolved_reference_remains_a_visible_asset(self) -> None:
        flows = _flows(_document("etl", _definition("load"), units=(
            _unit("u1", "load", "Shop.main.Target", "#temp"),
        )))

        asset = next(node for node in flows["nodes"] if node["kind"] == "asset")
        self.assertEqual((asset["reference"], asset["ambiguous_candidates"]), ("#temp", []))

    def test_write_without_any_source_is_reported_on_the_process(self) -> None:
        flows = _flows(_document("etl", _definition("load"), units=(
            _unit("u1", "load", "Shop.main.Target", None),
        )))

        self.assertEqual(flows["edges"], [])
        self.assertEqual(flows["processes"][0]["writes_without_source"], ["shop::target"])

    def test_process_order_is_available_for_the_step_chain(self) -> None:
        flows = _flows(_document(
            "etl", _definition("first"), _definition("second"),
            units=(_unit("u1", "second", "Shop.main.Target", "Shop.main.Source"),
                   _unit("u2", "first", "Shop.main.Source", "#raw")),
            steps=(_step("s1", "first", ()), _step("s2", "second", ("s1",))),
        ))

        by_label = {item["label"]: item for item in flows["processes"]}
        self.assertEqual(by_label["second"]["after"], [by_label["first"]["id"]])

    def test_analysis_categories_match_the_legend(self) -> None:
        for source_kind, analyzer, expected in (
            ("manual", None, "manual"),
            ("dbt-manifest", None, "dbt"),
            ("script", "sqlglot", "sqlglot"),
            ("script", "provider:openrouter", "provider"),
            ("script", None, "declared"),
        ):
            with self.subTest(expected=expected):
                document = _document("etl", _definition("load"), units=(
                    _unit("u1", "load", "Shop.main.Target", "Shop.main.Source"),
                ), source_kind=source_kind, analyzer=analyzer)
                self.assertEqual(_flows(document)["processes"][0]["analyzer"], expected)


class ScopeAndNeighbourhoodTests(TestCase):
    def setUp(self) -> None:
        names = [f"T{number}" for number in range(6)]
        self.objects = [_object(name.casefold(), "Shop", f"main.{name}") for name in names]
        self.document = _document(
            "chain", *(_definition(f"p{number}") for number in range(5)),
            units=tuple(
                _unit(
                    f"u{number}", f"p{number}",
                    f"Shop.main.T{number + 1}", f"Shop.main.T{number}",
                )
                for number in range(5)
            ),
        )
        self.model = LineageFlowModel((self.document,), self.objects)

    def test_bootstrap_limit_is_reported_as_truncated(self) -> None:
        limited = self.model.payload(limit=2)

        self.assertEqual(len(limited["edges"]), 2)
        self.assertTrue(limited["truncated"])
        self.assertEqual(limited["total_edges"], 5)

    def test_bootstrap_keeps_only_flows_touching_the_scope(self) -> None:
        model = LineageFlowModel((self.document,), self.objects[:2])
        payload = model.payload()

        self.assertEqual(payload["total_edges"], 2)
        self.assertEqual(payload["omitted_edges"], 3)
        self.assertFalse(payload["truncated"])

    def test_directions_and_hops(self) -> None:
        for direction, hops, expected in (
            ("upstream", 1, 1),
            ("upstream", 2, 2),
            ("downstream", 1, 1),
            ("downstream", 40, 2),
            ("both", 1, 2),
            ("both", 40, 5),
        ):
            with self.subTest(direction=direction, hops=hops):
                result = self.model.neighbourhood(
                    "Shop.main.T3", direction=direction, hops=hops,
                )
                self.assertEqual(len(result["edges"]), expected)
                self.assertFalse(result["truncated"])

    def test_neighbourhood_limit_keeps_the_nearest_flows(self) -> None:
        result = self.model.neighbourhood(
            "Shop.main.T5", direction="upstream", hops=40, limit=2,
        )
        labels = {(_label(result, edge["source"]), _label(result, edge["target"]))
                  for edge in result["edges"]}

        self.assertTrue(result["truncated"])
        self.assertEqual(result["total_edges"], 5)
        self.assertEqual(labels, {("main.T4", "main.T5"), ("main.T3", "main.T4")})

    def test_unknown_reference_finds_nothing(self) -> None:
        self.assertIsNone(self.model.neighbourhood("nope", direction="both", hops=1))

    def test_a_process_name_starts_from_what_it_connects(self) -> None:
        result = self.model.neighbourhood("pipeline.p2", direction="both", hops=1)

        self.assertEqual(result["start"], ["shop::t2", "shop::t3"])


class SourceExcerptTests(TestCase):
    def test_context_lines_numbers_and_marks(self) -> None:
        excerpt = excerpt_lines(_LOAD_SQL, ((10, 11),))

        self.assertEqual([line["number"] for line in excerpt["lines"]], list(range(7, 15)))
        self.assertEqual(
            [line["number"] for line in excerpt["lines"] if line["evidence"]], [10, 11],
        )
        self.assertFalse(excerpt["truncated"])

    def test_excerpt_is_bounded(self) -> None:
        text = "\n".join(str(number) for number in range(1, 1001))
        excerpt = excerpt_lines(text, ((1, 1000),))

        self.assertEqual(len(excerpt["lines"]), 200)
        self.assertTrue(excerpt["truncated"])

    def test_source_is_shown_only_while_its_hash_matches(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "load.sql").write_text(_LOAD_SQL, "utf-8")
            definition = _definition("load", source_reference="load.sql")
            document = _document("etl", definition)

            self.assertEqual(definition_source(document, definition, (root,)).text, _LOAD_SQL)

            (root / "load.sql").write_text("-- edited", "utf-8")
            changed = definition_source(document, definition, (root,))
            (root / "load.sql").unlink()
            missing = definition_source(document, definition, (root,))

        self.assertIsNone(changed.text)
        self.assertIn("changed after this analysis", changed.unavailable_reason)
        self.assertIsNone(missing.text)
        self.assertIn("stores only a hash", missing.unavailable_reason)

    def test_an_unrelated_file_is_never_shown(self) -> None:
        with TemporaryDirectory() as temporary:
            secret = Path(temporary) / "secret.txt"
            secret.write_text("password", "utf-8")
            definition = _definition("load", source_reference=str(secret))

            result = definition_source(_document("etl", definition), definition, ())

        self.assertIsNone(result.text)
        self.assertNotIn("password", result.unavailable_reason)

    def test_text_is_found_in_json_inputs(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.json").write_text(
                json.dumps({"definitions": [{"external_id": "load", "content": _LOAD_SQL}]}),
                "utf-8",
            )
            pointed = _definition("load", source_reference="input.json#/definitions/0/content")
            named = _definition("load", source_reference="SERVER:dbo.load")
            document = replace(_document("etl", named), source_reference="input.json")

            self.assertEqual(
                definition_source(_document("etl", pointed), pointed, (root,)).text, _LOAD_SQL,
            )
            self.assertEqual(definition_source(document, named, (root,)).text, _LOAD_SQL)


class EdgeRouteTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(temporary.name)
        self.root = Path(temporary.name)
        (self.root / "load.sql").write_text(_LOAD_SQL, "utf-8")
        sdk = Tarel(self.root / ".tarel")
        sdk.runtime.graph_store().save(_graph())
        self.document = _document(
            "etl", _definition("load", source_reference="load.sql"),
            units=(_unit("u1", "load", "Shop.main.Target", "Shop.main.Source"),),
            failure=True,
        )
        sdk.runtime.lineage_store().save(self.document)

    def _serve(self, *, editable: bool) -> str:
        server = _Server(
            ("127.0.0.1", 0),
            TarelUIBackend(UIConfig(graph="shop", lineages=("etl",), editable=editable)),
            "fixture-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def _get(self, url: str, *, token: str = "fixture-token", host: str | None = None):
        headers = {"X-Tarel-Token": token}
        if host:
            headers["Host"] = host
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            return json.loads(response.read())

    def _post(self, base: str, route: str, payload: dict[str, object]):
        request = Request(
            base + route, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Tarel-Token": "fixture-token"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    def _edge_id(self, base: str) -> str:
        return self._get(f"{base}/api/bootstrap")["lineage_flows"]["edges"][0]["id"]

    def test_detail_has_process_lines_evidence_review_and_failure(self) -> None:
        base = self._serve(editable=False)

        detail = self._get(f"{base}/api/lineage/edge?id={self._edge_id(base)}")

        process = detail["processes"][0]
        self.assertEqual(process["label"], "load")
        self.assertEqual(
            [line["number"] for line in process["excerpt"]["lines"] if line["evidence"]], [4],
        )
        self.assertEqual(process["evidence"][0]["reason"], "Fixture evidence.")
        self.assertEqual(process["items"][0]["id"], "u1")
        self.assertEqual(process["items"][0]["state"], "draft")
        self.assertEqual(process["analysis"]["kind"], "declared")
        self.assertEqual(process["failure"]["code"], "sqlglot_dynamic_sql")
        self.assertIn("dynamic SQL", process["failure"]["message"])
        self.assertFalse(detail["column_lineage"])
        self.assertFalse(detail["editable"])

    def test_routes_require_token_and_host(self) -> None:
        base = self._serve(editable=False)
        url = f"{base}/api/lineage/edge?id=anything"
        for arguments, code in (
            ({"token": "wrong"}, "invalid_session"),
            ({"host": "evil.example"}, "untrusted_host"),
        ):
            with self.subTest(code=code), self.assertRaises(HTTPError) as raised:
                self._get(url, **arguments)
            self.assertEqual(raised.exception.code, 403)
            self.assertEqual(json.load(raised.exception)["error"]["code"], code)
        request = Request(
            f"{base}/api/lineage/neighbourhood",
            data=json.dumps({"reference": "x", "direction": "both"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 403)

    def test_unknown_edge_and_bad_requests_fail_visibly(self) -> None:
        base = self._serve(editable=False)
        for url, status, code in (
            (f"{base}/api/lineage/edge?id=gone", 404, "lineage_edge_not_found"),
            (f"{base}/api/lineage/edge", 400, "invalid_request"),
        ):
            with self.subTest(url=url), self.assertRaises(HTTPError) as raised:
                self._get(url)
            self.assertEqual(raised.exception.code, status)
            self.assertEqual(json.load(raised.exception)["error"]["code"], code)
        for payload, status in (
            ({"reference": "Shop.main.Target", "direction": "sideways"}, 400),
            ({"reference": "Shop.main.Target", "direction": "both", "hops": 500}, 400),
            ({"reference": "unknown.table", "direction": "both"}, 404),
        ):
            with self.subTest(payload=payload), self.assertRaises(HTTPError) as raised:
                self._post(base, "/api/lineage/neighbourhood", payload)
            self.assertEqual(raised.exception.code, status)

    def test_neighbourhood_route_returns_the_flow(self) -> None:
        base = self._serve(editable=False)

        result = self._post(base, "/api/lineage/neighbourhood", {
            "reference": "Shop.main.Target", "direction": "upstream", "hops": 3,
        })

        self.assertEqual(len(result["edges"]), 1)
        self.assertFalse(result["truncated"])

    def test_edge_decision_needs_edit_mode(self) -> None:
        base = self._serve(editable=False)
        detail = self._get(f"{base}/api/lineage/edge?id={self._edge_id(base)}")
        process = detail["processes"][0]

        with self.assertRaises(HTTPError) as raised:
            self._post(base, "/api/lineage/decision", {
                "lineage": "etl", "item_id": process["items"][0]["id"],
                "decision": "validate", "reason": "Checked.", "revision": process["revision"],
            })

        self.assertEqual(raised.exception.code, 403)

    def test_edge_decision_is_revision_guarded_and_changes_the_edge(self) -> None:
        base = self._serve(editable=True)
        edge_id = self._edge_id(base)
        detail = self._get(f"{base}/api/lineage/edge?id={edge_id}")
        process = detail["processes"][0]
        self.assertTrue(detail["editable"])

        with self.assertRaises(HTTPError) as raised:
            self._post(base, "/api/lineage/decision", {
                "lineage": "etl", "item_id": "u1", "decision": "validate",
                "reason": "Checked.", "revision": "0" * 64,
            })
        self.assertEqual(raised.exception.code, 409)

        self._post(base, "/api/lineage/decision", {
            "lineage": "etl", "item_id": "u1", "decision": "validate",
            "reason": "Checked against the script.", "revision": process["revision"],
        })

        after = self._get(f"{base}/api/lineage/edge?id={edge_id}")
        self.assertEqual(after["state"], "validated")
        self.assertEqual(
            after["processes"][0]["items"][0]["reviews"][0]["reason"],
            "Checked against the script.",
        )


class BrowserPayloadTests(TestCase):
    def test_graph_payload_uses_the_flow_form(self) -> None:
        payload = browser_graph(_graph(), lineage_documents=(
            _document("etl", _definition("load"), units=(
                _unit("u1", "load", "Shop.main.Target", "Shop.main.Source"),
            )),
        ))

        flows = payload["lineage_flows"]
        self.assertEqual(flows["version"], 2)
        object_ids = {item["id"] for item in payload["objects"]}
        self.assertLessEqual({flows["edges"][0]["source"], flows["edges"][0]["target"]}, object_ids)


def _labels(flows: dict[str, object]) -> set[tuple[str, str]]:
    names = {node["id"]: node["label"] for node in flows["nodes"]}
    return {(names[edge["source"]], names[edge["target"]]) for edge in flows["edges"]}


def _label(flows, identifier: str) -> str:
    return next(node["reference"].removeprefix("Shop.") for node in flows["nodes"]
                if node["id"] == identifier)


def _flows(document: LineageDocument) -> dict[str, object]:
    return browser_lineage_flows((document,), _objects())


def _objects() -> list[dict[str, object]]:
    return [_object("source", "Shop", "main.Source"), _object("target", "Shop", "main.Target")]


def _object(identifier: str, catalog: str, label: str) -> dict[str, object]:
    return {
        "fields": [],
        "graph": catalog.casefold(),
        "id": f"{catalog.casefold()}::{identifier}",
        "label": label,
        "name": label.partition(".")[2],
        "object_id": identifier,
        "reference": f"{catalog}.{label}",
        "type": "table",
    }


def _graph() -> GraphDocument:
    return GraphDocument(
        name="shop", connector="fixture", source_type="sql", catalog="Shop", dialect="sqlite",
        nodes=(
            GraphNode("source", "table", "main.Source", {}),
            GraphNode("target", "table", "main.Target", {}),
        ),
        edges=(),
    )


def _definition(name: str, *, source_reference: str = "fixture.sql") -> LineageDefinition:
    return LineageDefinition(
        id=name,
        external_id=name,
        kind="script",
        name=name,
        qualified_name=f"pipeline.{name}",
        language="sqlite",
        source_reference=source_reference,
        content_hash=hashlib.sha256(_LOAD_SQL.encode()).hexdigest(),
        revision="1" * 64,
    )


def _evidence(line: int = 4) -> LineageEvidence:
    return LineageEvidence(
        source="fixture", reference=f"fixture.sql:{line}", reason="Fixture evidence.",
        line_start=line, line_end=line,
    )


def _claim(identifier: str, definition: str, target: str) -> LineageClaim:
    return LineageClaim(
        id=identifier, definition_id=definition, operation="read", target=target,
        state="draft", evidence=_evidence(),
    )


def _unit(
    identifier: str, definition: str, target: str, source: str | None, *, state: str = "draft",
) -> LineageWriteUnit:
    return LineageWriteUnit(
        id=identifier, definition_id=definition, operation="insert", target=target, state=state,
        evidence=_evidence(),
        reviews=(
            (LineageReview(
                decision="reject" if state == "rejected" else "validate", reason="Checked.",
            ),) if state in {"rejected", "validated"} else ()
        ),
        sources=(
            (LineageWriteSource(
                target=source, role="business_data", via=(), evidence=_evidence(),
            ),) if source else ()
        ),
    )


def _materialization(identifier: str, definition: str, target: str) -> LineageMaterialization:
    return LineageMaterialization(
        id=identifier, definition_id=definition, target=target, mode="table", state="draft",
        evidence=_evidence(),
    )


def _step(identifier: str, definition: str, after: tuple[str, ...]) -> LineageStep:
    return LineageStep(
        id=identifier, external_id=identifier, name=identifier,
        definition_id=definition, depends_on=after,
    )


def _document(
    name: str,
    *definitions: LineageDefinition,
    claims: tuple[LineageClaim, ...] = (),
    units: tuple[LineageWriteUnit, ...] = (),
    materializations: tuple[LineageMaterialization, ...] = (),
    steps: tuple[LineageStep, ...] = (),
    source_kind: str = "script",
    analyzer: str | None = None,
    failure: bool = False,
) -> LineageDocument:
    document = LineageDocument(
        name=name,
        source_kind=source_kind,
        source_name=name,
        source_reference=f"test:{name}",
        source_revision="2" * 64,
        workflow_id=f"workflow-{name}",
        workflow_name=name,
        definitions=definitions,
        steps=steps,
        claims=claims,
        write_units=units,
        materializations=materializations,
        analyses=(
            tuple(
                LineageAnalysis(
                    definition_id=item.id, definition_revision=item.revision,
                    summary="Fixture analysis.", warnings=(), analyzer=analyzer,
                )
                for item in definitions
            ) if analyzer else ()
        ),
        analysis_failures=(
            tuple(
                LineageAnalysisFailure(
                    definition_id=item.id, definition_revision=item.revision,
                    code="sqlglot_dynamic_sql", provider="sqlglot", model=None,
                )
                for item in definitions
            ) if failure else ()
        ),
    )
    validate_lineage_document(document)
    return document
