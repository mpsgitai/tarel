"""Name collisions across systems: filters and identity must hold, whatever the ranking does.

No test here demands a global order. Without a relevance oracle a ranking assertion would only
freeze one algorithm's output; scope, identity and evidence boundaries are what must not break.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import Tarel
from tarel.workspaces.core import create_workspace, define_system

_FIXTURES = Path(__file__).parent / "fixtures"


class ScopeBoundaryTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        graphs = {
            "crm-core": _graph(
                "crm-core", "crm", ("Account", "AccountId"), ("Opportunity", "AccountId"),
            ),
            "stocks": _graph("stocks", "main", ("CRM", "Close"), ("IBM", "Close")),
            "adventure": _graph(
                "adventure", "dbo", ("FactInternetSales", "SalesAmount"),
                extra=(("synthetic", "FactInternetSales", "SalesAmount"),),
            ),
            "hospital": _graph(
                "hospital", "public", ("encounters", "encounter_id"), ("patients", "patient_id"),
            ),
            "dw-diagnostics": _graph(
                "dw-diagnostics", "dbo", ("diagnostic_sessions", "diagnosis_severity"),
            ),
        }
        workspace = create_workspace("estate")
        for system, members in (
            ("crm", ("crm-core",)),
            ("markets", ("stocks",)),
            ("adventureworks", ("adventure",)),
            ("clinical", ("hospital",)),
            ("sqlserver", ("dw-diagnostics",)),
        ):
            workspace = define_system(workspace, system, graph_names=members, graphs=graphs)
        for graph in graphs.values():
            self.sdk.runtime.graph_store().save(graph)
        self.sdk.runtime.workspace_store().save(workspace)

    def _search(self, query: str, **scope):
        return self.sdk.search.workspace("estate", query, mode="bm25", limit=50, **scope)

    def _labels(self, results) -> set[tuple[str | None, str]]:
        return {(hit.source_graph, hit.label) for hit in results.hits}

    def test_crm_system_and_crm_ticker_stay_apart(self) -> None:
        everywhere = self._labels(self._search("CRM"))
        crm = self._labels(self._search("CRM Account", systems=("crm",)))
        markets = self._labels(self._search("CRM", systems=("markets",)))

        # The ticker is a legitimate global hit; a filter is what tells the two meanings apart.
        self.assertIn(("stocks", "stocks:main.CRM"), everywhere)
        self.assertTrue(crm)
        self.assertEqual({graph for graph, _label in crm}, {"crm-core"})
        self.assertEqual(markets, {("stocks", "stocks:main.CRM")})

    def test_same_table_in_two_schemas_keeps_both_identities(self) -> None:
        results = self._search("FactInternetSales", systems=("adventureworks",))
        hits = {hit.label: hit.id for hit in results.hits}

        self.assertEqual(
            set(hits), {"adventure:dbo.FactInternetSales", "adventure:synthetic.FactInternetSales"},
        )
        self.assertEqual(len(set(hits.values())), 2)

        only_dbo = self._search(
            "FactInternetSales", systems=("adventureworks",), schemas=("adventure:dbo",),
        )
        self.assertEqual({hit.label for hit in only_dbo.hits}, {"adventure:dbo.FactInternetSales"})

    def test_clinical_scope_does_not_borrow_sql_server_diagnostics(self) -> None:
        everywhere = self._labels(self._search("diagnosis"))
        clinical = self._labels(self._search("diagnosis", systems=("clinical",)))

        self.assertIn(("dw-diagnostics", "dw-diagnostics:dbo.diagnostic_sessions"), everywhere)
        self.assertEqual(clinical, set())

    def test_matching_field_names_create_no_relationship_across_systems(self) -> None:
        context = self.sdk.context.workspace("estate", "Account Opportunity AccountId Close")

        self.assertEqual(self.sdk.workspace.relationships("estate"), ())
        self.assertEqual(context.joins, ())

    def test_draft_annotation_stays_a_draft_and_can_be_excluded(self) -> None:
        graph = self.sdk.runtime.graph_store().load("hospital")
        node = next(item for item in graph.nodes if item.label == "public.encounters")
        self.sdk.runtime.graph_store().save(_annotated(graph, node.id))

        found = self._search("inpatient stay", systems=("clinical",))
        reviewed = self.sdk.search.workspace(
            "estate", "inpatient stay", mode="bm25", systems=("clinical",), validated_only=True,
        )

        self.assertEqual(
            self.sdk.runtime.graph_store().load("hospital").node_by_id()[node.id].annotation.state,
            "draft",
        )
        self.assertEqual({hit.label for hit in found.hits}, {"hospital:public.encounters"})
        self.assertEqual(reviewed.hits, ())


class AuditQuestionTests(TestCase):
    """Optional: the ten audit questions against a real estate state, read from a fresh copy."""

    def setUp(self) -> None:
        configured = os.getenv("TAREL_EVAL_STATE")
        if not configured:
            self.skipTest("Set TAREL_EVAL_STATE to a .tarel state; TAREL_EVAL_WORKSPACE names it.")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = Path(temporary.name) / ".tarel"
        shutil.copytree(Path(configured), state)
        self.sdk = Tarel(state)
        self.workspace = os.getenv("TAREL_EVAL_WORKSPACE", "gesamtsystem")
        self.questions = json.loads((_FIXTURES / "retrieval_questions.json").read_text("utf-8"))

    def test_every_question_stays_inside_its_scope_and_returns_real_objects(self) -> None:
        self.assertEqual(len(self.questions), 10)
        for question in self.questions:
            scope = {"systems": (question["system"],)} if question["system"] else {}
            for text in (question["question"], question["lexical"]):
                with self.subTest(question=question["id"], text=text[:30]):
                    results = self.sdk.search.workspace(
                        self.workspace, text, mode="bm25", limit=12, **scope,
                    )
                    self.assertLessEqual(len(results.hits), 12)
                    for hit in results.hits:
                        self.assertIn(hit.source_graph, results.graphs)
                        local = hit.id.removeprefix(f"scope::{hit.source_graph}::")
                        graph = self.sdk.runtime.graph_store().load(hit.source_graph)
                        self.assertIn(local, graph.node_by_id())

    def test_known_evidence_gaps_are_not_papered_over(self) -> None:
        # Q05: the hospital graph lists no structured diagnosis or billing table.
        hospital = self.sdk.runtime.graph_store().load("pg-windows-17-synthetic-hospital")
        tables = [node.label.casefold() for node in hospital.nodes if node.type == "table"]
        self.assertFalse([name for name in tables if "diagnos" in name or "bill" in name])
        # Q06/Q08/Q09: no cross-graph relationship has been recorded; none may appear by itself.
        self.assertEqual(self.sdk.workspace.relationships(self.workspace), ())
        # Q10: the index metadata carries no index key, so no membership can be derived from it.
        info = self.sdk.runtime.graph_store().load("sqlite-stockindex-indexinfo-database")
        fields = {node.label for node in info.nodes if node.type == "field"}
        self.assertEqual(fields, {"Exchange", "Currency"})


def _graph(name, namespace, *tables, extra=()):
    rows = [(namespace, table, field) for table, field in tables]
    rows.extend(extra)
    return build_graph_from_catalog(
        name,
        CatalogResult(
            connector="test",
            source_type="database",
            catalog=name.replace("-", "_"),
            dialect="ansi",
            objects=tuple(
                CatalogObject(
                    namespace=schema,
                    name=table,
                    kind="table",
                    fields=(CatalogField(field, 1, "text", True),),
                )
                for schema, table, field in rows
            ),
        ),
    )


def _annotated(graph, node_id):
    from dataclasses import replace

    nodes = tuple(
        replace(
            node,
            annotation=GraphAnnotation(
                description="One inpatient stay of a patient.", state="draft",
            ),
        )
        if node.id == node_id else node
        for node in graph.nodes
    )
    return replace(graph, nodes=nodes)
