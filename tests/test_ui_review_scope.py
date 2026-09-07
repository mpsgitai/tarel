from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.graph.contracts import GraphAnnotation, GraphNode
from tarel.graph.store import FileGraphStore
from tarel.sdk import Tarel
from tarel.ui.presentation import browser_graph, browser_workspace
from tests.test_family_focus import _focus
from tests.test_object_families_ui import _family, _graph, _workspace


def _annotated_graph(count: int):
    graph = _graph(count)
    return replace(graph, nodes=tuple(
        replace(node, annotation=GraphAnnotation(
            description="Synthetic annotation for review-scope tests.",
            state="validated" if node.type == "table" else "draft",
        )) if node.type in {"table", "field"} else node
        for node in graph.nodes
    ))


class ReviewScopeProjectionTests(TestCase):
    def test_family_collapse_preserves_pending_field_work_without_member_payloads(self):
        graph = _annotated_graph(80)
        family = _family(graph)
        original = graph.to_dict()
        physical = browser_graph(graph)
        collapsed = browser_graph(
            graph, family_mode="confirmed_only", object_families=(family,),
        )

        self.assertEqual(physical["review_summary"], collapsed["review_summary"])
        self.assertEqual(collapsed["review_summary"], {
            "known": True, "total_objects": 80, "review_objects": 80,
            "pending_tables": 0, "pending_fields": 80,
            "missing_tables": 0, "missing_fields": 0,
        })
        self.assertEqual(collapsed["review"], [])
        serialized = json.dumps(collapsed)
        for member_id in family.member_ids:
            self.assertNotIn(member_id, serialized)
        self.assertLess(len(serialized), 12000)
        self.assertEqual(graph.to_dict(), original)
        self.assertTrue(all(record["has_pending"] for record in physical["review"]))
        self.assertTrue(all(record["state"] == "validated" for record in physical["review"]))

    def test_summary_intersects_workspace_and_focus_before_visual_collapse(self):
        graph = _annotated_graph(8)
        family = _family(graph)
        workspace, scope = _workspace(graph, family.member_ids[2:5])
        focus = _focus(graph, "synthetic-report", family.member_ids[1:4])
        payload = browser_workspace(
            (graph,), scope, workspace=workspace, family_mode="confirmed_only",
            object_families=(family,), focus_documents=(focus,),
        )

        self.assertEqual(payload["review_summary"]["total_objects"], 2)
        self.assertEqual(payload["review_summary"]["pending_fields"], 2)
        self.assertEqual(payload["review_summary"]["review_objects"], 2)
        self.assertEqual(payload["objects"][0]["object_family"]["member_count"], 2)
        self.assertNotIn(family.member_ids[0], json.dumps(payload))

    def test_unrelated_focus_is_an_explicit_empty_review_scope(self):
        graph = _annotated_graph(4)
        family = _family(graph)
        workspace, scope = _workspace(graph, family.member_ids[:2])
        payload = browser_workspace(
            (graph,), scope, workspace=workspace,
            focus_documents=(_focus(graph, "outside-scope", family.member_ids[2:]),),
        )

        self.assertEqual(payload["review"], [])
        self.assertTrue(payload["review_summary"]["known"])
        self.assertTrue(all(
            value == 0 for key, value in payload["review_summary"].items() if key != "known"
        ))

    def test_missing_annotations_and_decisions_are_not_pending_proposals(self):
        graph = _graph(5)
        object_ids = tuple(node.id for node in graph.nodes if node.type == "table")
        table_states = ("draft", "validated", "rejected", None, "deferred")
        field_states = (None, "draft", "validated", "review_required", "rejected")
        nodes = []
        for node in graph.nodes:
            if node.type not in {"table", "field"}:
                nodes.append(node)
                continue
            object_id = node.id if node.type == "table" else node.metadata["object_id"]
            index = object_ids.index(object_id)
            state = table_states[index] if node.type == "table" else field_states[index]
            annotation = (
                GraphAnnotation(description="Synthetic proposal", state=state) if state else None
            )
            nodes.append(replace(node, annotation=annotation))
        payload = browser_graph(replace(graph, nodes=tuple(nodes)))

        self.assertEqual(payload["review_summary"], {
            "known": True, "total_objects": 5, "review_objects": 4,
            "pending_tables": 2, "pending_fields": 2,
            "missing_tables": 1, "missing_fields": 1,
        })
        records = {item["object_id"]: item for item in payload["review"]}
        self.assertTrue(records[object_ids[1]]["has_pending"])
        self.assertEqual(records[object_ids[1]]["pending_table_count"], 0)
        self.assertEqual(records[object_ids[1]]["pending_field_count"], 1)
        self.assertFalse(records[object_ids[2]]["has_pending"])
        self.assertEqual(records[object_ids[0]]["missing_field_count"], 1)
        self.assertNotIn("fields", records[object_ids[0]])

    def test_partial_family_summary_includes_visible_and_collapsed_physical_objects(self):
        graph = _annotated_graph(5)
        family = _family(graph)
        family = replace(family, member_ids=family.member_ids[:3])
        payload = browser_graph(
            graph, family_mode="confirmed_only", object_families=(family,),
        )

        self.assertEqual(payload["review_summary"]["pending_fields"], 5)
        self.assertEqual(payload["review_summary"]["total_objects"], 5)
        self.assertEqual(len(payload["review"]), 2)


class LazyReviewScopeTests(TestCase):
    def test_lazy_review_counts_are_deferred_without_hydrating_collapsed_fields(self):
        with TemporaryDirectory() as temporary:
            sdk = Tarel(Path(temporary) / ".tarel")
            graph = _annotated_graph(80)
            family = _family(graph)
            store = sdk.runtime.graph_store()
            store.save(graph)
            sdk.runtime.object_family_store().save(family)
            store.header(graph.name)
            original = GraphNode.from_dict

            def metadata_only(data):
                self.assertNotEqual(data["type"], "field")
                return original(data)

            with (
                patch.object(FileGraphStore, "load", side_effect=AssertionError("full load")),
                patch.object(GraphNode, "from_dict", side_effect=metadata_only),
            ):
                payload = sdk.view.graph(graph.name, family_mode="confirmed_only")

            summary = payload["review_summary"]
            self.assertFalse(summary["known"])
            self.assertEqual(summary["total_objects"], 80)
            for key in (
                "pending_tables", "pending_fields", "missing_tables", "missing_fields",
                "review_objects",
            ):
                self.assertIsNone(summary[key])
            self.assertFalse(payload["storage"]["full_document_read"])
            self.assertEqual(payload["review"], [])
            self.assertNotIn(family.member_ids[0], json.dumps(payload))
            self.assertEqual(sdk.view.graph(graph.name)["review_summary"]["pending_fields"], 80)
