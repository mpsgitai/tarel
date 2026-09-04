"""Cross-interface regressions found during independent logical-topology review."""

from __future__ import annotations

import json
from unittest import TestCase

import test_object_bindings as binding_fixture

from tarel.expansion import ExpansionInput, ExpansionTarget
from tarel.ui.logical_metadata import logical_metadata_use_case
from tarel.workspaces.core import create_workspace, define_system


class LogicalIntegrationReviewTests(TestCase):
    def setUp(self) -> None:
        self.fixture = binding_fixture.ObjectBindingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.sdk = self.fixture.sdk
        self.binding = self.sdk.bindings.import_document(self.fixture._binding())

    def test_binding_outside_target_scope_is_omitted_consistently_with_gui(self) -> None:
        graph = self.fixture.graph
        source_id = self.binding.source.object_id
        namespace = graph.node_by_id()[source_id].metadata["namespace"]
        base = self.sdk.context.graph("commerce", "sales", namespace=namespace)
        before = base.canonical_json()
        allowed = frozenset(
            node.id
            for node in graph.nodes
            if node.type in {"table", "view"} and node.metadata.get("namespace") == namespace
        )
        self.assertFalse(set(self.fixture.family.member_ids) & allowed)
        delta = self.sdk.context.expand(
            base,
            (
                ExpansionTarget(
                    "object_binding",
                    "commerce",
                    self.binding.id,
                    self.binding.revision,
                ),
            ),
            mode="include_candidates",
        )
        self.assertEqual(delta.items, ())
        self.assertEqual(delta.omissions, ((0, "expansion_outside_scope"),))
        gui = logical_metadata_use_case(
            "commerce",
            (source_id,),
            allowed_object_ids=allowed,
            runtime=self.sdk.runtime,
        )
        self.assertEqual(gui["object_bindings"], [])
        self.assertEqual(base.canonical_json(), before)

    def test_workspace_binding_resolution_projects_only_allowed_family_subset(self) -> None:
        workspace = define_system(
            create_workspace("review-estate"),
            "sales",
            graph_names=("commerce",),
            graphs={"commerce": self.fixture.graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        base = self.sdk.context.workspace(
            "review-estate", "sales", schemas=("commerce:sales", "commerce:tenant_042")
        )
        target = ExpansionTarget(
            "object_binding",
            "commerce",
            self.binding.id,
            self.binding.revision,
            handle="PRIVATE_HANDLE_REVIEW",
        )
        delta = self.sdk.context.expand(
            base,
            (target,),
            mode="include_candidates",
            inputs={
                target.handle: ExpansionInput(
                    "a" * 64, values=("042", "043", "PRIVATE_VALUE_REVIEW")
                ),
            },
        )
        self.assertEqual(delta.omissions, ())
        metadata = delta.items[0].metadata
        self.assertEqual(metadata["scoped_target_member_count"], 1)
        self.assertEqual(metadata["resolution"]["matched_member_count"], 1)
        self.assertEqual(metadata["resolution"]["unmatched_input_count"], 2)
        encoded = json.dumps(delta.to_dict())
        self.assertNotIn("tenant_043", encoded)
        self.assertNotIn("PRIVATE_", encoded)
        for path in self.sdk.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE_", path.read_bytes())
