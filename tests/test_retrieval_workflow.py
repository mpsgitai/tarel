from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import SearchFilters, Tarel
from tarel.search import SearchFailure
from tarel.ui.query_tools import (
    UIQueryFailure,
    UIQueryScope,
    preview_context,
    preview_expansion,
    query_scope_snapshot,
)
from tarel.workspaces.core import create_workspace, define_system
from tests.test_search import _sales_graph


class RetrievalWorkflowTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        graph = _sales_graph()
        fact_id = next(node.id for node in graph.nodes if node.label.endswith("FactInternetSales"))
        dim_id = next(node.id for node in graph.nodes if node.label.endswith("DimCurrency"))
        self.fact_id, self.dim_id = fact_id, dim_id
        graph = replace(
            graph,
            nodes=tuple(
                replace(
                    node,
                    annotation=GraphAnnotation(
                        description="Internet revenue at sales-line grain.",
                        role="fact",
                        state="validated",
                    ),
                )
                if node.id == fact_id
                else replace(
                    node,
                    annotation=GraphAnnotation(
                        description="Currency reporting dimension.",
                        role="dimension",
                        state="draft",
                    ),
                )
                if node.id == dim_id
                else node
                for node in graph.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(graph)

    def test_filters_are_applied_before_lexical_and_bm25_ranking(self) -> None:
        filters = SearchFilters(
            types=("table",), roles=("fact",), required_fields=("SalesAmount",),
        )

        lexical = self.sdk.search.graph(
            "sales_demo", "internet sales amount", mode="lexical",
            validated_only=True, filters=filters,
        )
        bm25 = self.sdk.search.graph(
            "sales_demo", "internet sales amount", mode="bm25",
            validated_only=True, filters=filters,
        )

        for result in (lexical, bm25):
            self.assertEqual([hit.id for hit in result.hits], [self.fact_id])
            self.assertEqual(result.inventory.objects_in_scope, 2)
            self.assertEqual(result.inventory.objects_after_filters, 1)
            self.assertEqual(result.hits[0].role, "fact")
            self.assertEqual(result.hits[0].namespace, "sales")
            self.assertEqual(result.hits[0].annotation_state, "validated")
            self.assertEqual(result.hits[0].reference, f"sales_demo:{self.fact_id}")

        for values in ({"types": ("cube",)}, {"roles": ("",)}, {"roles": ["fact"]}):
            with self.subTest(values=values), self.assertRaises(SearchFailure):
                SearchFilters(**values)

    def test_working_scope_is_a_hard_search_and_context_boundary(self) -> None:
        search = self.sdk.search.graph(
            "sales_demo", "currency", scope_object_ids=(self.dim_id,),
        )
        prefix = self.sdk.context.prefix_graph(
            "sales_demo", scope_object_ids=(self.fact_id,), max_fields_per_object=1,
        )

        self.assertEqual([hit.id for hit in search.hits], [self.dim_id])
        self.assertEqual(search.inventory.objects_in_scope, 1)
        self.assertEqual([item.id for item in prefix.objects], [self.fact_id])
        self.assertEqual(prefix.contract_version, "tarel.context.v0.3")
        self.assertEqual(prefix.scope.objects, (self.fact_id,))
        self.assertEqual(prefix.graph_revision, self.sdk.runtime.graph_store().header(
            "sales_demo"
        ).revision)

    def test_exact_workspace_objects_drop_unneeded_graph_revisions(self) -> None:
        first = self.sdk.graph.load("sales_demo")
        second = replace(first, name="other")
        self.sdk.runtime.graph_store().save(second)
        workspace = define_system(
            create_workspace("estate"), "analytics",
            graph_names=(first.name, second.name),
            graphs={first.name: first, second.name: second},
        )
        self.sdk.runtime.workspace_store().save(workspace)

        scope = self.sdk.workspace.scope(
            "estate", objects=(f"sales_demo:{self.fact_id}",),
        )

        self.assertEqual(scope.graph_names, ("sales_demo",))
        self.assertEqual([(item.graph, item.object_id) for item in scope.objects], [
            ("sales_demo", self.fact_id),
        ])

    def test_selected_result_becomes_exact_context_then_bounded_delta(self) -> None:
        scope = UIQueryScope(graph="sales_demo")
        snapshot = query_scope_snapshot(scope, runtime=self.sdk.runtime)
        request = {
            "query": "internet revenue",
            "kind": "selected",
            "object_ids": [self.fact_id],
            "expected_revisions": snapshot["revisions"],
            "expected_scope_identity": snapshot["scope_identity"],
            "reviewed_annotations_only": True,
            "seed_limit": 1,
            "max_objects": 1,
            "max_fields_per_object": 1,
        }

        packet = preview_context(scope, request, runtime=self.sdk.runtime)["packet"]
        delta = preview_expansion(
            scope,
            {
                "packet": packet,
                "object_ids": [self.fact_id],
                "expected_revisions": snapshot["revisions"],
                "expected_scope_identity": snapshot["scope_identity"],
            },
            runtime=self.sdk.runtime,
        )["expansion"]

        self.assertEqual([item["id"] for item in packet["stable"]["objects"]], [self.fact_id])
        self.assertEqual(packet["dynamic"]["selection"][0]["selection"], "selected")
        self.assertGreater(packet["dynamic"]["selection"][0]["omitted_fields"], 0)
        self.assertEqual(delta["base_packet_hash"], packet["identity"]["packet_hash"])
        self.assertEqual(delta["items"][0]["target"]["id"], self.fact_id)
        self.assertEqual(len(delta["items"][0]["metadata"]["objects"][0]["fields"]), 2)

    def test_expansion_cannot_select_an_object_absent_from_the_packet(self) -> None:
        scope = UIQueryScope(graph="sales_demo")
        snapshot = query_scope_snapshot(scope, runtime=self.sdk.runtime)
        packet = preview_context(
            scope,
            {
                "query": "internet revenue", "kind": "selected",
                "object_ids": [self.fact_id],
                "expected_revisions": snapshot["revisions"],
                "expected_scope_identity": snapshot["scope_identity"],
            },
            runtime=self.sdk.runtime,
        )["packet"]

        with self.assertRaises(UIQueryFailure) as error:
            preview_expansion(
                scope,
                {
                    "packet": packet,
                    "object_ids": [self.dim_id],
                    "expected_revisions": snapshot["revisions"],
                    "expected_scope_identity": snapshot["scope_identity"],
                },
                runtime=self.sdk.runtime,
            )

        self.assertEqual(error.exception.code, "invalid_context_expansion")

    def test_expansion_cannot_reuse_a_broader_packet_to_escape_working_scope(self) -> None:
        scope = UIQueryScope(graph="sales_demo")
        broad = query_scope_snapshot(scope, runtime=self.sdk.runtime)
        packet = preview_context(
            scope,
            {
                "query": "", "kind": "prefix",
                "expected_revisions": broad["revisions"],
                "expected_scope_identity": broad["scope_identity"],
            },
            runtime=self.sdk.runtime,
        )["packet"]
        scope_objects = (f"sales_demo:{self.fact_id}",)
        narrow = query_scope_snapshot(
            scope, scope_objects=scope_objects, runtime=self.sdk.runtime,
        )

        with self.assertRaises(UIQueryFailure) as error:
            preview_expansion(
                scope,
                {
                    "packet": packet,
                    "object_ids": [self.dim_id],
                    "scope_objects": list(scope_objects),
                    "expected_revisions": narrow["revisions"],
                    "expected_scope_identity": narrow["scope_identity"],
                },
                runtime=self.sdk.runtime,
            )

        self.assertEqual(error.exception.code, "invalid_context_expansion")
