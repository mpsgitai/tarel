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

from tarel.focus.contracts import FocusFailure
from tarel.graph.contracts import GraphAnnotation
from tarel.graph.revision import graph_revision
from tarel.sdk import Tarel
from tarel.ui.server import TarelUIBackend, UIConfig, UIFailure, _Server
from tarel.workspaces.contracts import Area, SchemaReference
from tests.test_family_focus import _focus
from tests.test_object_families_ui import _family, _graph, _workspace


class ReviewViewBackendTests(TestCase):
    """Exercise the read-only review endpoint against isolated persisted metadata."""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        old_directory = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, old_directory)
        self.sdk = Tarel(self.project / ".tarel")
        graph = _graph(80)
        self.graph = replace(graph, nodes=tuple(
            replace(node, annotation=GraphAnnotation(description="Synthetic review proposal."))
            if node.type in {"table", "field"} else node for node in graph.nodes
        ))
        self.family = _family(self.graph)
        self.focus = _focus(self.graph, "test-report", self.family.member_ids[:3])
        self.sdk.runtime.graph_store().save(self.graph)
        self.sdk.runtime.object_family_store().save(self.family)
        self.sdk.runtime.focus_store().save(self.focus)
        self.backend = TarelUIBackend(UIConfig(
            graph=self.graph.name, family_mode="confirmed_only", editable=False,
        ))

    def _save_scoped_workspace(self, member_ids):
        workspace, _scope = _workspace(self.graph, member_ids)
        system = replace(workspace.systems[0], areas=(Area(
            name="sales", schemas=(SchemaReference(self.graph.name, "sales"),),
        ),))
        workspace = replace(workspace, systems=(system,))
        self.sdk.runtime.workspace_store().save(workspace)
        return workspace

    def test_review_loads_eighty_physical_records_without_optional_artifact_loaders(self):
        compact = self.backend.bootstrap()
        self.assertEqual(len(compact["objects"]), 1)
        self.assertEqual(compact["review"], [])
        self.assertEqual(compact["review_summary"]["pending_tables"], 80)
        self.assertEqual(compact["review_summary"]["pending_fields"], 80)
        self.assertEqual(compact["review_summary"]["review_objects"], 80)

        with ExitStack() as stack:
            for name in (
                "project_families_for_graphs_use_case",
                "project_logical_topologies_for_graphs_use_case",
                "find_entity_resolution_candidates_for_graph_use_case",
                "find_reference_mapping_candidates_for_graph_use_case",
                "list_query_linked_coverages_use_case",
                "list_semantic_imports_use_case",
                "load_lineage_use_case",
            ):
                stack.enter_context(patch(
                    f"tarel.ui.server.{name}", side_effect=AssertionError(f"Unexpected {name}"),
                ))
            review = self.backend.mutate("/api/review/view", {})

        self.assertEqual(len(review["review"]), 80)
        self.assertEqual(review["review_summary"], compact["review_summary"])
        self.assertTrue(all(record["has_pending"] for record in review["review"]))
        self.assertNotIn("objects", review)
        self.assertNotIn("object_families", review)
        self.assertFalse(review["editable"])
        self.assertEqual(review["revisions"], {self.graph.name: graph_revision(self.graph)})
        self.assertEqual(self.sdk.runtime.graph_store().load(self.graph.name), self.graph)

    def test_requested_and_configured_focus_return_the_same_three_records(self):
        requested = self.backend.mutate("/api/review/view", {"focuses": [self.focus.name]})
        configured = TarelUIBackend(UIConfig(
            graph=self.graph.name, focuses=(self.focus.name,), family_mode="confirmed_only",
        )).mutate("/api/review/view", {})

        self.assertEqual(requested, configured)
        self.assertEqual({record["object_id"] for record in requested["review"]},
                         set(self.family.member_ids[:3]))
        self.assertEqual(requested["review_summary"]["pending_tables"], 3)
        self.assertEqual(requested["review_summary"]["pending_fields"], 3)
        self.assertEqual(requested["focuses"], [self.focus.name])

    def test_focused_bootstrap_counts_match_review_without_restricting_graph_projection(self):
        backend = TarelUIBackend(UIConfig(graph=self.graph.name, focuses=(self.focus.name,)))
        bootstrap = backend.bootstrap()
        review = backend.mutate("/api/review/view", {})

        # The normal graph retains its existing client-side focus navigation. Only
        # the annotation review scope and its badge must match the selected report.
        self.assertEqual(len(bootstrap["objects"]), 80)
        self.assertEqual(bootstrap["review_summary"], review["review_summary"])
        self.assertEqual(bootstrap["review"], review["review"])
        compact = backend.mutate("/api/families/view", {
            "mode": "confirmed_only", "focuses": [self.focus.name],
        })
        self.assertEqual(compact["review_summary"], review["review_summary"])

    def test_workspace_focused_bootstrap_counts_match_its_review_intersection(self):
        workspace = self._save_scoped_workspace(self.family.member_ids[1:5])
        backend = TarelUIBackend(UIConfig(
            workspace=workspace.name, zones=("selected",), focuses=(self.focus.name,),
        ))
        bootstrap = backend.bootstrap()
        review = backend.mutate("/api/review/view", {})

        self.assertEqual(len(bootstrap["objects"]), 4)
        self.assertEqual(bootstrap["review_summary"], review["review_summary"])
        self.assertEqual(bootstrap["review_summary"]["total_objects"], 2)
        self.assertEqual(bootstrap["review"], review["review"])

    def test_client_ids_cannot_expand_workspace_zone_or_focus_intersection(self):
        workspace = self._save_scoped_workspace(self.family.member_ids[1:4])
        backend = TarelUIBackend(UIConfig(
            workspace=workspace.name, zones=("analytics:selected",), family_mode="confirmed_only",
        ))
        review = backend.mutate("/api/review/view", {
            "focuses": [self.focus.name], "graph": "outside",
            "object_ids": list(self.family.member_ids),
            "allowed_object_ids": list(self.family.member_ids),
            "zones": [],
        })

        self.assertEqual({record["object_id"] for record in review["review"]},
                         set(self.family.member_ids[1:3]))
        self.assertEqual(review["review_summary"]["total_objects"], 2)
        self.assertEqual(review["review_summary"]["pending_fields"], 2)
        serialized = json.dumps(review)
        self.assertNotIn(self.family.member_ids[0], serialized)
        self.assertNotIn(self.family.member_ids[3], serialized)

    def test_nonintersecting_focus_has_a_known_empty_scope_not_unrelated_records(self):
        workspace = self._save_scoped_workspace(self.family.member_ids[4:7])
        backend = TarelUIBackend(UIConfig(workspace=workspace.name, zones=("selected",)))
        review = backend.mutate("/api/review/view", {"focuses": [self.focus.name]})

        self.assertEqual(review["review"], [])
        self.assertTrue(review["review_summary"]["known"])
        self.assertEqual(review["review_summary"]["total_objects"], 0)
        self.assertEqual(review["review_summary"]["pending_fields"], 0)

    def test_unknown_duplicate_and_stale_focus_fail_visibly(self):
        for names, code in ((["not-a-focus"], "focus_outside_scope"),
                            ([self.focus.name, self.focus.name], "duplicate_focus")):
            with self.subTest(names=names), self.assertRaises(UIFailure) as raised:
                self.backend.mutate("/api/review/view", {"focuses": names})
            self.assertEqual(raised.exception.code, code)
        stale = replace(self.focus, sources=tuple(
            replace(source, revision="0" * 64) for source in self.focus.sources
        ))
        self.sdk.runtime.focus_store().save(stale)
        with self.assertRaises(FocusFailure) as raised:
            self.backend.mutate("/api/review/view", {"focuses": [self.focus.name]})
        self.assertEqual(raised.exception.code, "focus_stale")

    def test_approved_table_with_draft_field_remains_pending(self):
        first_id = self.family.member_ids[0]
        changed = replace(self.graph, nodes=tuple(
            replace(node, annotation=replace(node.annotation, state="validated"))
            if node.id == first_id else node for node in self.graph.nodes
        ))
        self.sdk.runtime.graph_store().save(changed)
        review = self.backend.mutate("/api/review/view", {})
        record = next(item for item in review["review"] if item["object_id"] == first_id)

        self.assertEqual(record["state"], "validated")
        self.assertTrue(record["has_pending"])
        self.assertEqual(record["pending_table_count"], 0)
        self.assertEqual(record["pending_field_count"], 1)
        self.assertEqual(review["review_summary"]["pending_tables"], 79)
        self.assertEqual(review["review_summary"]["pending_fields"], 80)
        self.assertEqual(review["review_summary"]["review_objects"], 80)

    def test_readonly_http_review_requires_session_token_and_does_not_write_graph(self):
        server = _Server(("127.0.0.1", 0), self.backend, "review-test-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/api/review/view"
        body = json.dumps({"focuses": [self.focus.name]}).encode()
        try:
            request = Request(url, body, {"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 403)
            self.assertEqual(json.load(raised.exception)["error"]["code"], "invalid_session")
            request = Request(url, body, {
                "Content-Type": "application/json", "X-Tarel-Token": "review-test-token",
            })
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 200)
                review = json.load(response)
            self.assertFalse(review["editable"])
            self.assertEqual(len(review["review"]), 3)
            self.assertEqual(self.sdk.runtime.graph_store().load(self.graph.name), self.graph)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
