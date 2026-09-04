from __future__ import annotations

import json
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import Tarel
from tarel.ui.query_tools import (
    UIQueryFailure,
    UIQueryScope,
    preview_context,
    query_scope_snapshot,
    search_metadata,
)
from tarel.workspaces.core import create_workspace, define_system
from tests.test_object_families import _graph as _family_graph
from tests.test_ui import _graph


class UIQueryToolsTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.scope = UIQueryScope(graph=self.graph.name)

    def _request(self, scope=None, **updates):
        scope = scope or self.scope
        snapshot = query_scope_snapshot(scope, runtime=self.sdk.runtime)
        return {
            "query": "DateKey", "expected_revisions": snapshot["revisions"],
            "expected_scope_identity": snapshot["scope_identity"], **updates,
        }

    def _preview(self, **updates):
        return preview_context(self.scope, self._request(**updates), runtime=self.sdk.runtime)

    def _workspace(self):
        graph = _family_graph()
        self.sdk.runtime.graph_store().save(graph)
        workspace = define_system(
            create_workspace("estate"), "analytics", graph_names=(graph.name,),
            graphs={graph.name: graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        return UIQueryScope(workspace="estate", systems=("analytics",), schemas=("commerce:sales",))

    def _change_graph(self):
        changed = replace(self.graph, nodes=tuple(
            replace(node, annotation=GraphAnnotation("Revised description", state="validated"))
            if node.type == "table" else node for node in self.graph.nodes
        ))
        self.sdk.runtime.graph_store().save(changed)

    def test_field_search_exactly_matches_sdk_and_returns_scope_identity(self):
        result = search_metadata(self.scope, {"query": "DateKey"}, runtime=self.sdk.runtime)
        self.assertEqual(result["results"], self.sdk.search.graph("sales", "DateKey").to_dict())
        self.assertEqual(len(result["results"]["hits"]), 2)
        self.assertTrue(all(hit["fields"] for hit in result["results"]["hits"]))
        self.assertEqual(result["scope"], {"mode": "graph", "graph": "sales"})
        self.assertIn("do not constrain", result["notice"])
        self.assertEqual(len(result["scope_identity"]), 64)

    def test_preview_exactly_matches_sdk_and_cli_json(self):
        actual = self._preview()["packet"]
        self.assertEqual(
            actual, self.sdk.context.graph("sales", "DateKey", validated_only=True).to_dict()
        )
        output = StringIO()
        with (
            patch("tarel.application.FileGraphStore", return_value=self.sdk.runtime.graph_store()),
            redirect_stdout(output),
        ):
            status = main(["context", "sales", "DateKey", "--validated-only", "--format", "json"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue()), actual)

    def test_review_filter_hides_unreviewed_semantics_not_physical_tables(self):
        reviewed = self._preview()["packet"]
        full = self._preview(reviewed_annotations_only=False)["packet"]
        self.assertEqual(reviewed["stable"]["annotation_states"], ["validated"])
        self.assertEqual(len(reviewed["stable"]["objects"]), 2)
        self.assertEqual(
            {item["id"] for item in reviewed["stable"]["objects"]},
            {item["id"] for item in full["stable"]["objects"]},
        )
        self.assertNotIn("Sales by transaction line.", json.dumps(reviewed))
        self.assertIn("Sales by transaction line.", json.dumps(full))

    def test_workspace_scope_matches_sdk_without_unselected_schema(self):
        scope = self._workspace()
        payload = self._request(scope, query="sale_id")
        search = search_metadata(scope, {"query": "sale_id"}, runtime=self.sdk.runtime)
        result = preview_context(scope, payload, runtime=self.sdk.runtime)
        self.assertEqual(search["results"], self.sdk.search.workspace(
            "estate", "sale_id", systems=("analytics",), schemas=("commerce:sales",),
        ).to_dict())
        self.assertEqual(result["packet"], self.sdk.context.workspace(
            "estate", "sale_id", systems=("analytics",), schemas=("commerce:sales",),
            validated_only=True,
        ).to_dict())
        encoded = json.dumps(result["packet"])
        self.assertNotIn("sales_2023_12", encoded)
        self.assertNotIn("events_data", encoded)
        self.assertEqual(result["scope"]["selection"]["schemas"], ["commerce:sales"])

    def test_request_cannot_replace_scope_or_enable_execution(self):
        scope = self._workspace()
        forbidden = {
            "graph": "outside", "workspace": "outside", "graphs": ["outside"],
            "systems": [], "schemas": [], "zones": [], "areas": [], "namespace": "archive",
            "object_ids": [], "focuses": [], "mode": "hybrid", "model_path": "private.gguf",
            "provider": "remote", "raw_samples": True,
        }
        for key, value in forbidden.items():
            for function in (search_metadata, preview_context):
                with (
                    self.subTest(key=key, function=function.__name__),
                    self.assertRaises(UIQueryFailure) as error,
                ):
                    function(scope, self._request(scope, **{key: value}), runtime=self.sdk.runtime)
                self.assertEqual(error.exception.code, "invalid_query_request")
                self.assertEqual(error.exception.status, 400)

    def test_family_name_search_never_expands_members_into_context(self):
        graph = _family_graph()
        self.sdk.runtime.graph_store().save(graph)
        scope = UIQueryScope(graph="commerce")
        candidate = self.sdk.families.propose(
            "commerce", "revenue", name="revenue_history",
            members=("sales.sales_2024_01", "sales.sales_2024_02"), grain=("sale_id",),
        )
        ordinary = search_metadata(scope, {"query": "revenue_history"}, runtime=self.sdk.runtime)
        exploratory = search_metadata(
            scope, {"query": "revenue_history", "family_mode": "include_candidates"},
            runtime=self.sdk.runtime,
        )
        self.assertEqual(ordinary["results"]["hits"], [])
        hit = exploratory["results"]["hits"][0]
        self.assertEqual(hit["family"]["usage"], "exploratory_only")
        self.assertFalse(hit["family"]["executable"])
        self.assertNotIn("sales_2024", json.dumps(exploratory["results"]))
        self.sdk.families.review(
            "commerce", candidate.id, expected_revision=candidate.revision,
            decision="approve", reason="Synthetic schema review.",
        )
        self.assertTrue(search_metadata(
            scope, {"query": "revenue_history"}, runtime=self.sdk.runtime,
        )["results"]["hits"])
        packet = preview_context(
            scope, self._request(scope, query="revenue_history"), runtime=self.sdk.runtime,
        )["packet"]
        self.assertEqual(packet["stable"]["objects"], [])

    def test_optional_logical_hints_keep_the_sdk_policy(self):
        for mode in (None, "off", "confirmed_only", "include_candidates"):
            with self.subTest(mode=mode):
                result = self._preview(logical_hints=mode)["packet"]
                self.assertEqual(result, self.sdk.context.graph(
                    "sales", "DateKey", validated_only=True,
                    logical_hints=None if mode == "off" else mode,
                ).to_dict())

    def test_provider_connector_and_embedding_are_never_called(self):
        with (
            patch("tarel.application.load_provider", side_effect=AssertionError("provider")),
            patch("tarel.application.load_connector", side_effect=AssertionError("connector")),
            patch("tarel.application.LlamaCppEmbedding", side_effect=AssertionError("embedding")),
            patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            self.assertTrue(search_metadata(
                self.scope, {"query": "DateKey"}, runtime=self.sdk.runtime,
            )["results"]["hits"])
            self.assertTrue(self._preview()["packet"]["stable"]["objects"])

    def test_old_graph_revision_is_rejected_before_compilation(self):
        request = self._request()
        self._change_graph()
        with (
            patch(
                "tarel.ui.query_tools.compile_context_use_case", side_effect=AssertionError("stale")
            ),
            self.assertRaises(UIQueryFailure) as error,
        ):
            preview_context(self.scope, request, runtime=self.sdk.runtime)
        self.assertEqual(error.exception.code, "stale_query_scope")
        self.assertEqual(error.exception.status, 409)

    def test_workspace_revision_changes_even_without_object_scope_change(self):
        scope = self._workspace()
        before = query_scope_snapshot(scope, runtime=self.sdk.runtime)
        request = self._request(scope, query="sale_id")
        workspace = self.sdk.runtime.workspace_store().load("estate")
        self.sdk.runtime.workspace_store().save(replace(workspace, description="Changed workspace"))
        after = query_scope_snapshot(scope, runtime=self.sdk.runtime)
        self.assertEqual(before["scope"]["scope_hash"], after["scope"]["scope_hash"])
        self.assertEqual(before["revisions"], after["revisions"])
        self.assertNotEqual(before["scope_identity"], after["scope_identity"])
        with self.assertRaises(UIQueryFailure) as error:
            preview_context(scope, request, runtime=self.sdk.runtime)
        self.assertEqual(error.exception.status, 409)

    def test_graph_changed_during_compilation_never_returns_a_preview(self):
        def changed(*args, **kwargs):
            result = self.sdk.context.graph("sales", "DateKey", validated_only=True)
            self._change_graph()
            return result

        with (
            patch("tarel.ui.query_tools.compile_context_use_case", side_effect=changed),
            self.assertRaises(UIQueryFailure) as error,
        ):
            self._preview()
        self.assertEqual(error.exception.status, 409)

    def test_search_can_bind_to_expected_revision_and_rejects_stale_results(self):
        request = self._request()
        self._change_graph()
        with self.assertRaises(UIQueryFailure) as error:
            search_metadata(self.scope, request, runtime=self.sdk.runtime)
        self.assertEqual(error.exception.status, 409)

    def test_preview_requires_complete_revision_identity(self):
        for fields in ({}, {"expected_revisions": {}}, {"expected_scope_identity": "old"}):
            with self.subTest(fields=fields), self.assertRaises(UIQueryFailure) as error:
                preview_context(
                    self.scope, {"query": "DateKey", **fields}, runtime=self.sdk.runtime
                )
            self.assertEqual(error.exception.code, "query_revision_required")

    def test_invalid_queries_limits_and_policies_are_visible_without_echoing_values(self):
        for query in (None, [], "", " ", "sensitive-value" * 200):
            with (
                self.subTest(query_type=type(query).__name__),
                self.assertRaises(UIQueryFailure) as error,
            ):
                search_metadata(self.scope, {"query": query}, runtime=self.sdk.runtime)
            self.assertNotIn("sensitive-value", str(error.exception))
        for limit in (False, 0, 101, 1.5, "20"):
            with self.subTest(limit=limit), self.assertRaises(UIQueryFailure):
                search_metadata(
                    self.scope, {"query": "DateKey", "limit": limit}, runtime=self.sdk.runtime
                )
        bad = (
            {"max_characters": 100_001}, {"max_objects": 0}, {"max_joins": True},
            {"max_hops": 5}, {"seed_limit": 3, "max_objects": 2},
            {"max_fields_per_object": 101}, {"reviewed_annotations_only": "true"},
            {"logical_hints": "invented"},
        )
        for options in bad:
            with self.subTest(options=options), self.assertRaises(UIQueryFailure):
                self._preview(**options)

    def test_query_budget_and_packet_are_not_silently_adjusted(self):
        packet = self._preview(
            seed_limit=1, max_objects=1, max_joins=0, max_hops=0,
            max_fields_per_object=1, max_characters=2_000,
        )["packet"]
        self.assertEqual(packet, self.sdk.context.graph(
            "sales", "DateKey", validated_only=True, seed_limit=1, max_objects=1,
            max_joins=0, max_hops=0, max_fields_per_object=1, max_characters=2_000,
        ).to_dict())
        self.assertLessEqual(packet["dynamic"]["budgets"]["context_characters"], 2_000)

    def test_server_scope_requires_one_valid_launch_target(self):
        for options in ({}, {"graph": "a", "workspace": "b"}, {"graph": 12},
                        {"graph": "a", "schemas": ("a:sales",)}, {"workspace": "a", "zones": []}):
            with self.subTest(options=options), self.assertRaises(UIQueryFailure):
                UIQueryScope(**options)
