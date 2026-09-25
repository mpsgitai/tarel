from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.connectors.contracts import CatalogObject, CatalogResult
from tarel.focus.contracts import FocusDocument, FocusMember, FocusSource
from tarel.focus.core import focus_graph_revision
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import SearchFilters, Tarel
from tarel.search import SearchFailure
from tarel.ui.query_tools import (
    UIQueryFailure,
    UIQueryScope,
    preview_context,
    preview_expansion,
    query_scope_snapshot,
    search_metadata,
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

    def test_namespace_is_applied_before_inventory_is_counted(self) -> None:
        graph = self.sdk.graph.load("sales_demo")
        graph = replace(
            graph,
            nodes=tuple(
                replace(node, metadata={**node.metadata, "namespace": "reference"})
                if node.id == self.dim_id else node
                for node in graph.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(graph)

        result = self.sdk.search.graph(
            "sales_demo", "currency", namespace="reference", mode="bm25",
        )

        self.assertEqual([hit.id for hit in result.hits], [self.dim_id])
        self.assertEqual(result.inventory.objects_in_scope, 1)
        self.assertEqual(result.inventory.objects_after_filters, 1)
        self.assertEqual(result.inventory.types, (("table", 1),))

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

    def test_focus_drops_empty_graphs_and_preserves_truncation_warnings(self) -> None:
        graph = self.sdk.graph.load("sales_demo")
        other = replace(graph, name="other")
        self.sdk.runtime.graph_store().save(other)
        workspace = define_system(
            create_workspace("estate"), "analytics",
            graph_names=(graph.name, other.name),
            graphs={graph.name: graph, other.name: other},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        focus = _focus(
            "sales-slice", graph, self.fact_id,
            warnings=("Traversal reached its configured boundary.",), truncated=True,
        )
        self.sdk.runtime.focus_store().save(replace(focus, warnings=(), truncated=False))
        complete_scope = self.sdk.workspace.scope("estate", focuses=(focus.name,))
        self.sdk.runtime.focus_store().save(focus)

        scope = self.sdk.workspace.scope("estate", focuses=(focus.name,))
        search = self.sdk.search.graph(
            graph.name, "internet revenue", focuses=(focus.name,),
        )
        context = self.sdk.context.graph(
            graph.name, "internet revenue", focuses=(focus.name,),
        )

        expected_warnings = (
            "sales-slice: Traversal reached its configured boundary.",
            "sales-slice: focus traversal was truncated",
        )
        self.assertEqual(scope.graph_names, (graph.name,))
        self.assertNotEqual(scope.scope_hash, complete_scope.scope_hash)
        self.assertEqual(scope.warnings, expected_warnings)
        self.assertEqual(search.warnings, expected_warnings)
        self.assertEqual(context.scope.warnings, expected_warnings)
        self.assertEqual(context.stable_dict()["scope"]["warnings"], list(expected_warnings))
        self.assertIn("warnings", scope.to_dict())

    def test_context_preview_uses_server_owned_bm25_mode(self) -> None:
        graph = self.sdk.graph.load("sales_demo")
        workspace = define_system(
            create_workspace("estate"), "analytics",
            graph_names=(graph.name,), graphs={graph.name: graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)

        for scope in (
            UIQueryScope(graph=graph.name, search_mode="bm25"),
            UIQueryScope(workspace=workspace.name, search_mode="bm25"),
        ):
            with self.subTest(scope=scope):
                snapshot = query_scope_snapshot(scope, runtime=self.sdk.runtime)
                response = preview_context(
                    scope,
                    {
                        "query": "internet revenue",
                        "expected_revisions": snapshot["revisions"],
                        "expected_scope_identity": snapshot["scope_identity"],
                    },
                    runtime=self.sdk.runtime,
                )
                self.assertEqual(response["packet"]["dynamic"]["retrieval"]["mode"], "bm25")

    def test_search_here_accepts_more_than_one_hundred_visible_objects(self) -> None:
        graph = build_graph_from_catalog(
            "large",
            CatalogResult(
                connector="test", source_type="database", catalog="Large",
                dialect="ansi",
                objects=tuple(
                    CatalogObject(
                        namespace="dbo", name=f"Object{index:03d}", kind="table", fields=(),
                    )
                    for index in range(101)
                ),
            ),
        )
        self.sdk.runtime.graph_store().save(graph)
        references = [
            f"{graph.name}:{node.id}" for node in graph.nodes
            if node.type in {"table", "view"}
        ]
        scope = UIQueryScope(graph=graph.name, search_mode="bm25")

        result = search_metadata(
            scope,
            {"query": "Object", "scope_objects": references, "limit": 1},
            runtime=self.sdk.runtime,
        )["results"]

        self.assertEqual(len(references), 101)
        self.assertEqual(result["inventory"]["objects_in_scope"], 101)

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


def _focus(
    name: str,
    graph,
    object_id: str,
    *,
    warnings: tuple[str, ...] = (),
    truncated: bool = False,
) -> FocusDocument:
    node = graph.node_by_id()[object_id]
    member = FocusMember(
        id=f"graph:{graph.name}:{node.id}",
        reference=f"{graph.catalog}.{node.label}",
        name=str(node.metadata.get("name") or node.label),
        kind=node.type,
        source=f"graph:{graph.name}",
        depth=0,
        reasons=("seed",),
        origin=True,
        annotation_state=node.annotation.state if node.annotation else None,
    )
    return FocusDocument(
        name=name,
        seed=member.reference,
        seed_id=member.id,
        max_hops=2,
        states=("validated",),
        sources=(FocusSource("graph", graph.name, focus_graph_revision(graph)),),
        members=(member,),
        hops=(),
        warnings=warnings,
        truncated=truncated,
    )
