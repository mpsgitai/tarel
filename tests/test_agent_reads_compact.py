"""Compact graph slices, tiered workspace overviews, search diversity and freshness."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from test_focus import _fixture, _run_cli

from tarel.annotations import coverage as coverage_module
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.freshness import freshness_block
from tarel.graph.observation import GraphObservation
from tarel.graph.reads import graph_slice_use_case
from tarel.runtime import TarelRuntime
from tarel.search import (
    FieldSearchHit,
    SearchFailure,
    SearchFilters,
    SearchHit,
    SearchInventory,
    SearchResults,
    role_coverage_warning,
)
from tarel.workspaces.application import workspace_overview_use_case
from tarel.workspaces.core import create_workspace, define_system
from tarel.workspaces.retrieval import (
    combine_workspace_search,
    structural_signatures,
    validate_diversity,
)
from tarel.workspaces.scope import (
    ResolvedScope,
    ResolvedScopeObject,
    ScopeSelection,
    exclude_scope_graphs,
)


class _State(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = TarelRuntime(self.root / ".tarel")
        self.graph, lineage = _fixture()
        self.runtime.graph_store().save(self.graph)
        self.runtime.lineage_store().save(lineage)


class CompactSliceTests(_State):
    def test_fields_nest_under_objects_and_containment_is_gone(self) -> None:
        graph_slice = graph_slice_use_case("demo", ("raw.Sales",), runtime=self.runtime)

        compact = graph_slice.to_compact_dict()

        self.assertEqual(compact["view"], "compact")
        self.assertEqual(compact["edges"], [])
        (item,) = compact["objects"]
        self.assertEqual(item["label"], "raw.Sales")
        self.assertNotIn("meta", item)
        self.assertEqual(
            item["fields"],
            [{"id": item["fields"][0]["id"], "label": "SaleId",
              "meta": {"data_type": "integer", "is_primary_key": False, "nullable": False,
                       "position": 1}}],
        )

    def test_no_containment_drops_catalog_namespace_and_contains_edges(self) -> None:
        full = graph_slice_use_case("demo", ("raw.Sales",), runtime=self.runtime)
        bare = graph_slice_use_case(
            "demo", ("raw.Sales",), include_containment=False, runtime=self.runtime,
        )

        self.assertIn("catalog", {node.type for node in full.graph.nodes})
        self.assertEqual({node.type for node in bare.graph.nodes}, {"table", "field"})
        self.assertFalse([edge for edge in bare.graph.edges if edge.type == "contains"])

    def test_cli_compact_slice_reports_freshness(self) -> None:
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            code, output, _errors = _run_cli(
                ["graph", "slice", "demo", "--object", "raw.Sales", "--view", "compact",
                 "--format", "json"]
            )
        finally:
            os.chdir(previous)

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output)["freshness"], {"missing": ["demo"], "stale": "unverified"},
        )


class CoverageCostTests(TestCase):
    def test_field_counts_are_computed_once_per_graph(self) -> None:
        graph, _lineage = _fixture()
        objects = [(graph, node) for node in graph.nodes if node.type == "table"]

        with mock.patch.object(
            coverage_module, "_field_counts", wraps=coverage_module._field_counts,
        ) as counted:
            coverage_module.measure_coverage("graph:demo", objects, limit=1)

        self.assertEqual(counted.call_count, 1)


class FreshnessTests(TestCase):
    def test_observed_missing_and_failed_reads_are_kept_apart(self) -> None:
        block = freshness_block(
            {
                "a": GraphObservation(observed_at="2026-11-01T10:00:00Z"),
                "b": None,
                "c": GraphObservation(
                    observed_at="2026-10-01T10:00:00Z", failure={"code": "login_failed"},
                ),
            }
        )

        self.assertEqual(
            block,
            {"failed": {"c": "login_failed"},
             "missing": ["b"],
             "observed": {"a": "2026-11-01T10:00:00Z", "c": "2026-10-01T10:00:00Z"},
             "stale": "unverified"},
        )


class WorkspaceOverviewTests(_State):
    def setUp(self) -> None:
        super().setUp()
        workspace = define_system(
            create_workspace("estate", description="Demo estate"),
            "sales",
            graph_names=("demo",),
            graphs={"demo": self.graph},
        )
        self.runtime.workspace_store().save(workspace)

    def test_index_lists_systems_with_counts_only(self) -> None:
        overview = workspace_overview_use_case("estate", runtime=self.runtime)

        self.assertEqual(overview["depth"], "index")
        self.assertEqual(overview["depth_available"], ["index", "zones", "full"])
        self.assertEqual(
            overview["systems"],
            [{"area_count": 0, "graph_count": 1, "graphs": ["demo"], "name": "sales",
              "zone_count": 0, "zone_member_count": 0}],
        )
        self.assertFalse(overview["truncated"])

    def test_stats_count_objects_from_the_graphs(self) -> None:
        overview = workspace_overview_use_case("estate", include_stats=True, runtime=self.runtime)

        (system,) = overview["systems"]
        self.assertEqual((system["objects"], system["annotated_pct"]), (3, 0.0))

    def test_full_is_the_stored_document(self) -> None:
        overview = workspace_overview_use_case("estate", depth="full", runtime=self.runtime)

        self.assertEqual(
            overview, self.runtime.workspace_store().load("estate").to_dict(),
        )


class SearchDiversityTests(TestCase):
    def test_duplicates_fold_into_the_best_hit_and_diversity_caps_each_graph(self) -> None:
        scope, results = _search_fixture()
        signatures = {
            ("ddl-a", "object:a"): "customer|customerid",
            ("ddl-b", "object:b"): "customer|customerid",
        }

        combined = combine_workspace_search(
            scope, results, query="customer", mode="lexical", limit=10,
            signatures=signatures, diversity="per_graph", max_per_graph=1,
        )

        self.assertEqual(
            [hit.reference for hit in combined.hits], ["ddl-a:object:a", "mart:object:m1"],
        )
        self.assertEqual(combined.hits[0].duplicates, ("ddl-b:object:b",))
        self.assertEqual(combined.omitted_by_diversity, (("mart", 1),))
        payload = combined.to_dict()
        self.assertEqual(payload["duplicates_collapsed"], 1)
        self.assertEqual(
            payload["diversity"], {"mode": "per_graph", "omitted_by_graph": {"mart": 1}},
        )

    def test_plain_results_keep_their_old_shape(self) -> None:
        scope, results = _search_fixture()

        payload = combine_workspace_search(
            scope, results, query="customer", mode="lexical", limit=10,
        ).to_dict()

        self.assertNotIn("diversity", payload)
        self.assertNotIn("duplicates_collapsed", payload)
        self.assertTrue(all("duplicates" not in hit for hit in payload["hits"]))

    def test_signatures_ignore_namespace_case_and_punctuation(self) -> None:
        graph, _lineage = _fixture()
        ids = frozenset(node.id for node in graph.nodes if node.type == "table")

        signatures = structural_signatures(graph, ids)

        self.assertEqual(sorted(set(signatures.values())), ["sales|saleid", "unusedsales|saleid"])

    def test_signatures_keep_letters_of_any_script(self) -> None:
        graph = build_graph_from_catalog(
            "cjk",
            CatalogResult(
                connector="test", source_type="database", catalog="C", dialect="ansi",
                objects=tuple(
                    CatalogObject(
                        namespace="main", name=name, kind="table",
                        fields=(CatalogField("SaleId", 1, "integer", False),),
                    )
                    for name in ("客户", "订单")
                ),
            ),
        )
        ids = frozenset(node.id for node in graph.nodes if node.type == "table")

        self.assertEqual(
            sorted(structural_signatures(graph, ids).values()), ["客户|saleid", "订单|saleid"],
        )

    def test_equal_objects_inside_one_graph_never_fold(self) -> None:
        scope, results = _search_fixture()
        signatures = {("mart", "object:m1"): "same", ("mart", "object:m2"): "same"}

        combined = combine_workspace_search(
            scope, results, query="customer", mode="lexical", limit=10, signatures=signatures,
        )

        self.assertEqual(len(combined.hits), 4)
        self.assertEqual(combined.duplicates_collapsed, 0)

    def test_excluding_graphs_changes_the_scope_hash(self) -> None:
        scope, _results = _search_fixture()
        real = ResolvedScope(scope.workspace, scope.selection, scope.graph_names, scope.objects,
                             "")
        real = exclude_scope_graphs(real, ())

        hashes = {
            exclude_scope_graphs(real, excluded).scope_hash
            for excluded in ((), ("ddl-a",), ("ddl-b",))
        }

        self.assertEqual(len(hashes), 3)
        self.assertEqual(exclude_scope_graphs(real, ("ddl-a",)).graph_names, ("ddl-b", "mart"))

    def test_invalid_diversity_options_are_retryable(self) -> None:
        with self.assertRaises(SearchFailure) as raised:
            validate_diversity("none", 2)

        self.assertTrue(raised.exception.retryable)

    def test_role_filter_on_sparse_annotations_warns(self) -> None:
        inventory = SearchInventory(100, 3, (("table", 100),), (("fact", 3), ("unknown", 97)))

        warning = role_coverage_warning(SearchFilters(roles=("fact",)), inventory)

        self.assertIn("role_coverage_pct=3.0", warning or "")
        self.assertIsNone(role_coverage_warning(SearchFilters(), inventory))

    def test_cli_rejects_workspace_options_for_a_single_graph(self) -> None:
        code, _output, errors = _run_cli(
            ["search", "demo", "sales", "--diversity", "per_graph", "--format", "json"]
        )

        self.assertEqual(code, 2)
        self.assertEqual(json.loads(errors)["error"]["code"], "invalid_search_option")


def _search_fixture() -> tuple[ResolvedScope, tuple[SearchResults, ...]]:
    def hit(object_id: str, label: str, score: int) -> SearchHit:
        return SearchHit(
            id=object_id, label=label, type="table", score=score, matched_terms=("customer",),
            reasons=("name",), fields=(FieldSearchHit("", "CustomerId", 1, ("name",)),),
        )

    per_graph = {
        "ddl-a": (hit("object:a", "main.Customer", 14),),
        "ddl-b": (hit("object:b", "public.customer", 13),),
        "mart": (hit("object:m1", "gold.customer_sales", 12), hit("object:m2", "gold.c2", 11)),
    }
    objects = tuple(
        ResolvedScopeObject(graph, "s", None, "main", item.id, item.label, "table", ())
        for graph, hits in per_graph.items()
        for item in hits
    )
    scope = ResolvedScope("estate", ScopeSelection(), tuple(per_graph), objects, "hash")
    results = tuple(
        SearchResults(graph=graph, query="customer", terms=("customer",), hits=hits)
        for graph, hits in per_graph.items()
    )
    return scope, results


class BudgetScriptTests(TestCase):
    def test_a_failed_slice_never_passes_the_share_check(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "tools" / "evals" / "check_agent_output_budgets.py"
        spec = importlib.util.spec_from_file_location("check_agent_output_budgets", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # Its dataclasses resolve their module through sys.modules while it executes.
        with mock.patch.dict(sys.modules, {spec.name: module}):
            spec.loader.exec_module(module)

        replies = {
            ("lineage", "upstream"): {"summary": {"unresolved": 0}},
            ("lineage", "downstream"): {"nodes": {}},
            ("graph", "objects"): {"objects": []},
            ("search", "--workspace"): {"hits": []},
        }

        def tarel(*arguments: str) -> object:
            if arguments[:2] == ("graph", "slice"):
                if "--view" in arguments:
                    return module.Run(2, "", '{"error": {"code": "invalid_graph"}}')
                return module.Run(0, "x" * 100, "")
            return module.Run(0, json.dumps(replies.get(arguments[:2], {})), "")

        checks = {item.name: item for item in module._phase_two_checks(tarel)}

        self.assertFalse(checks["5-object slice compact share"].passed)
