from __future__ import annotations

import json
import os
import threading
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import Tarel
from tarel.ui.server import TarelUIBackend, UIConfig, _Server
from tarel.workspaces.contracts import Area, SchemaReference, Zone, ZoneMember
from tarel.workspaces.core import create_workspace, define_system
from tests.test_entity_resolution import _candidate, _graph
from tests.test_family_focus import _focus
from tests.test_logical_topology_ui import _graph as _logical_graph
from tests.test_logical_topology_ui import _reviewed_topology


class OptionalMetadataHTTPTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(temporary.name)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.candidate = _candidate(self.graph)
        self.sdk.entity_resolution.import_candidate(self.candidate)
        nodes = self.graph.node_by_id()
        self.source_id = nodes[self.candidate.source_field_id].metadata["object_id"]
        self.target_id = nodes[self.candidate.target_field_id].metadata["object_id"]
        self.backend = TarelUIBackend(UIConfig(graph=self.graph.name))
        self.server = _Server(("127.0.0.1", 0), self.backend, "optional-test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def _configure(self, config):
        self.backend = TarelUIBackend(config)
        self.server.backend = self.backend

    def _post(self, route, payload, *, token=True):
        request = Request(
            f"http://127.0.0.1:{self.server.server_port}{route}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **(
                {"X-Tarel-Token": "optional-test-token"} if token else {}
            )},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def _bootstrap(self):
        address = f"http://127.0.0.1:{self.server.server_port}/api/bootstrap"
        with urlopen(address, timeout=5) as response:
            return json.load(response)

    def _request(self, *, kind="identity", focuses=None, **changes):
        names = self.backend.config.focuses if focuses is None else tuple(focuses)
        bootstrap = self._post("/api/families/view", {"mode": None, "focuses": list(names)})
        return {
            "graph": self.graph.name, "object_id": self.source_id, "kind": kind,
            "revision": bootstrap["revisions"][self.graph.name],
            "scope_revision": bootstrap["scope_revision"], "focuses": list(names), **changes,
        }

    def _assert_error(self, route, payload, *, status, code=None, token=True):
        with self.assertRaises(HTTPError) as raised:
            self._post(route, payload, token=token)
        self.assertEqual(raised.exception.code, status)
        response = json.load(raised.exception)
        if code:
            self.assertEqual(response["error"]["code"], code)
        return response

    def _workspace(self, members):
        workspace = define_system(
            create_workspace("estate"), "analytics", graph_names=(self.graph.name,),
            graphs={self.graph.name: self.graph},
        )
        system = workspace.systems[0]
        return replace(workspace, systems=(replace(
            system,
            areas=(Area("music", (SchemaReference(self.graph.name, "mb"),)),),
            zones=(Zone(
                "selected", tuple(ZoneMember(self.graph.name, member) for member in members),
            ),),
        ),))

    def test_default_bootstrap_never_reads_optional_artifacts(self):
        calls = (
            "find_entity_resolution_candidates_for_graph_use_case",
            "list_query_linked_coverages_use_case",
            "project_logical_topologies_for_graphs_use_case",
            "find_reference_mapping_candidates_for_graph_use_case",
            "list_semantic_imports_use_case",
            "list_knowledge_documents_use_case",
        )
        with ExitStack() as stack:
            for name in calls:
                stack.enter_context(patch(
                    f"tarel.ui.server.{name}",
                    side_effect=AssertionError("Optional read at bootstrap"),
                ))
            payload = self._bootstrap()
        self.assertEqual(len(payload["objects"]), 2)
        self.assertTrue(all(item["type"] == "table" for item in payload["objects"]))
        self.assertEqual(payload["entity_resolution"], [])
        self.assertEqual(payload["query_linked_coverages"], [])
        self.assertFalse(payload["derived_enabled"])
        self.assertEqual(payload["optional_metadata"]["state"], "not_loaded")
        self.assertNotIn(self.candidate.id, json.dumps(payload))

    def test_readonly_explicit_details_load_only_the_requested_kind(self):
        graph_before = self.sdk.graph.load(self.graph.name).to_dict()
        candidate_store = self.sdk.runtime.entity_resolution_store()
        candidate_before = candidate_store.load(self.candidate.id).to_dict()
        for kind in ("identity", "mappings", "coverage", "imports"):
            with self.subTest(kind=kind):
                payload = self._post("/api/optional/details", self._request(kind=kind))
                self.assertEqual(payload["kind"], kind)
                self.assertEqual(payload["state"], "loaded")
                self.assertIsInstance(payload["items"], list)
                self.assertIsInstance(payload["omissions"], list)
                self.assertEqual(payload["object_id"], self.source_id)
                self.assertLessEqual(len(payload["items"]), 20)
                self.assertEqual(len(payload["edges"]), 1 if kind == "identity" else 0)
        self.assertFalse(self.backend.config.editable)
        self.assertEqual(graph_before, self.sdk.graph.load(self.graph.name).to_dict())
        self.assertEqual(
            candidate_before, candidate_store.load(self.candidate.id).to_dict()
        )

    def test_optional_routes_require_session_token(self):
        details = self._request()
        for route, request in (
            ("/api/optional/details", details),
            ("/api/optional/view", {"kind": "derived_relations", "enabled": True}),
        ):
            with self.subTest(route=route):
                self._assert_error(route, request, status=403, code="invalid_session", token=False)

    def test_unknown_kind_and_scope_replacement_keys_fail_before_metadata_reads(self):
        request = self._request()
        options = (
            {"kind": "invented"}, {"allowed_object_ids": [self.source_id, self.target_id]},
            {"workspace": "outside"}, {"query": "PRIVATE_QUERY"},
            {"mode": "include_candidates"},
        )
        with patch("tarel.ui.server.optional_object_metadata") as read:
            for changes in options:
                with self.subTest(changes=changes):
                    error = self._assert_error(
                        "/api/optional/details", {**request, **changes}, status=400,
                        code="invalid_optional_request",
                    )
                    self.assertNotIn("PRIVATE_QUERY", json.dumps(error))
            read.assert_not_called()

    def test_optional_limits_are_bounded_and_invalid_layer_requests_are_rejected(self):
        request = self._request()
        with patch("tarel.ui.server.optional_object_metadata") as read:
            for value in (0, 21, True, "20"):
                with self.subTest(limit=value):
                    self._assert_error(
                        "/api/optional/details", {**request, "limit": value}, status=400,
                    )
            read.assert_not_called()
        with patch("tarel.ui.server.project_logical_topologies_for_graphs_use_case") as read:
            for changes in ({"kind": "invented"}, {"enabled": "true"}, {"query": "PRIVATE"}):
                with self.subTest(changes=changes):
                    self._assert_error("/api/optional/view", {
                        "kind": "derived_relations", "enabled": True, **changes,
                    }, status=400, code="invalid_optional_request")
            read.assert_not_called()

    def test_foreign_graph_and_object_fail_before_reading_candidate_store(self):
        outside = replace(self.graph, name="outside")
        self.sdk.runtime.graph_store().save(outside)
        request = self._request()
        with patch("tarel.ui.server.optional_object_metadata") as read:
            self._assert_error(
                "/api/optional/details", {**request, "graph": "outside"}, status=400,
                code="graph_outside_scope",
            )
            self._assert_error(
                "/api/optional/details", {**request, "object_id": "table:outside"}, status=400,
                code="optional_object_outside_scope",
            )
            read.assert_not_called()

    def test_missing_or_stale_revisions_fail_before_metadata_reads(self):
        request = self._request()
        with patch("tarel.ui.server.optional_object_metadata") as read:
            for key in ("revision", "scope_revision"):
                for invalid in (None, "0" * 64):
                    with self.subTest(key=key, invalid=invalid):
                        self._assert_error(
                            "/api/optional/details", {**request, key: invalid}, status=409,
                            code="stale_optional_scope",
                        )
            read.assert_not_called()

    def test_corrupt_optional_candidate_does_not_block_base_but_fails_on_request(self):
        path = self.sdk.runtime.entity_resolution_store().path(self.candidate.id)
        path.write_text("PRIVATE_ALIAS_BROKEN_JSON", encoding="utf-8")
        bootstrap = self._bootstrap()
        self.assertEqual(len(bootstrap["objects"]), 2)
        self.assertEqual(bootstrap["optional_metadata"]["state"], "not_loaded")
        error = self._assert_error(
            "/api/optional/details", self._request(), status=400, code="invalid_entity_resolution",
        )
        self.assertNotIn("PRIVATE_ALIAS_BROKEN_JSON", json.dumps(error))
        self.assertNotIn("items", error)
        other = self._post("/api/optional/details", self._request(kind="mappings"))
        self.assertEqual(other["items"], [])

    def test_revision_changed_while_loading_details_is_a_conflict(self):
        request = self._request()

        def change_graph(*args, **kwargs):
            graph = replace(self.graph, nodes=tuple(
                replace(node, annotation=GraphAnnotation("Changed during read", state="validated"))
                if node.type == "table" else node for node in self.graph.nodes
            ))
            self.sdk.runtime.graph_store().save(graph)
            return {"items": [], "edges": [], "state": "loaded"}

        with patch("tarel.ui.server.optional_object_metadata", side_effect=change_graph):
            self._assert_error(
                "/api/optional/details", request, status=409, code="stale_optional_scope",
            )

    def test_workspace_scope_excludes_partial_relationships_and_foreign_objects(self):
        workspace = self._workspace((self.source_id,))
        self.sdk.runtime.workspace_store().save(workspace)
        self._configure(UIConfig(workspace=workspace.name, zones=("analytics:selected",)))
        request = self._request()
        payload = self._post("/api/optional/details", request)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["edges"], [])
        self.assertEqual(payload["artifact_revisions"], [])
        self.assertNotIn(json.dumps(self.target_id), json.dumps(payload))
        self.assertNotIn(self.candidate.id, json.dumps(payload))
        self._assert_error(
            "/api/optional/details", {**request, "object_id": self.target_id}, status=400,
            code="optional_object_outside_scope",
        )

    def test_selected_focus_intersects_workspace_scope_instead_of_widening_it(self):
        workspace = self._workspace((self.source_id,))
        self.sdk.runtime.workspace_store().save(workspace)
        focus = _focus(self.graph, "whole-report", (self.source_id, self.target_id))
        self.sdk.runtime.focus_store().save(focus)
        self._configure(UIConfig(workspace=workspace.name, zones=("analytics:selected",)))
        request = self._request(focuses=[focus.name])
        payload = self._post("/api/optional/details", request)
        self.assertEqual(payload["edges"], [])
        self.assertNotIn(json.dumps(self.target_id), json.dumps(payload))
        self._assert_error(
            "/api/optional/details", {**request, "object_id": self.target_id}, status=400,
            code="optional_object_outside_scope",
        )

    def test_initial_report_focus_limits_details_and_scope_hash_cannot_be_reused(self):
        focus = _focus(self.graph, "credit-report", (self.source_id,))
        self.sdk.runtime.focus_store().save(focus)
        self._configure(UIConfig(graph=self.graph.name, focuses=(focus.name,)))
        request = self._request()
        payload = self._post("/api/optional/details", request)
        self.assertEqual(payload["items"], [])
        self.assertNotIn(json.dumps(self.target_id), json.dumps(payload))
        self._assert_error(
            "/api/optional/details", {**request, "focuses": []}, status=409,
            code="stale_optional_scope",
        )

    def test_metadata_result_limit_is_visible_and_bounded(self):
        for index in range(25):
            self.sdk.entity_resolution.import_candidate(_candidate(
                self.graph, candidate_id=f"artist-extra-{index:02}",
            ))
        payload = self._post("/api/optional/details", self._request())
        self.assertEqual(payload["limit"], 20)
        self.assertEqual(payload["items"], [])
        self.assertEqual(len(payload["edges"]), 20)
        self.assertTrue(payload["more_available"])
        self.assertIn({"code": "metadata_result_limit", "count": 6}, payload["omissions"])

    def test_derivations_are_loaded_only_after_explicit_layer_request(self):
        self.graph = _logical_graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.sdk.runtime.logical_topology_store().save(_reviewed_topology(self.graph))
        self._configure(UIConfig(graph=self.graph.name))
        ordinary = self._bootstrap()
        self.assertFalse(any(item["type"] == "derived_relation" for item in ordinary["objects"]))
        enabled = self._post("/api/optional/view", {
            "kind": "derived_relations", "enabled": True, "mode": None, "focuses": [],
        })
        self.assertTrue(enabled["derived_enabled"])
        self.assertEqual(
            len([item for item in enabled["objects"] if item["type"] == "derived_relation"]), 1,
        )
        self.assertEqual(len([edge for edge in enabled["edges"] if edge["type"] == "derives"]), 1)
        disabled = self._post("/api/optional/view", {
            "kind": "derived_relations", "enabled": False, "mode": None, "focuses": [],
        })
        self.assertFalse(disabled["derived_enabled"])
        self.assertFalse(any(item["type"] == "derived_relation" for item in disabled["objects"]))
        self.assertFalse(self._bootstrap()["derived_enabled"])

    def test_family_view_does_not_implicitly_enable_derived_layer(self):
        self.graph = _logical_graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.sdk.runtime.logical_topology_store().save(_reviewed_topology(self.graph))
        self._configure(UIConfig(graph=self.graph.name))
        ordinary = self._post("/api/families/view", {"mode": None, "focuses": []})
        self.assertFalse(ordinary["derived_enabled"])
        explicit = self._post("/api/families/view", {
            "mode": None, "focuses": [], "derived": True,
        })
        self.assertTrue(explicit["derived_enabled"])

    def test_corrupt_derivation_is_visible_only_when_its_layer_is_requested(self):
        path = self.sdk.runtime.logical_topology_store().path(self.graph.name)
        path.parent.mkdir(parents=True)
        path.write_text("PRIVATE_BROKEN_DERIVATION", encoding="utf-8")
        self.assertEqual(len(self._bootstrap()["objects"]), 2)
        error = self._assert_error("/api/optional/view", {
            "kind": "derived_relations", "enabled": True, "mode": None, "focuses": [],
        }, status=400, code="invalid_logical_topology")
        self.assertNotIn("PRIVATE_BROKEN_DERIVATION", json.dumps(error))
