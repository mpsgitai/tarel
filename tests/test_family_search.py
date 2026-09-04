from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_object_families import _graph

from tarel.cli import main
from tarel.sdk import Tarel
from tarel.workspaces.core import create_workspace, define_system


class FamilyNameSearchTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.family = self.sdk.families.propose(
            "commerce",
            "revenue",
            name="revenue_history",
            members=("sales.sales_2024_01", "sales.sales_2024_02"),
            grain=("sale_id",),
        )

    def test_normal_search_finds_reviewed_logical_name_without_expansion(self) -> None:
        self.assertEqual(self.sdk.search.graph("commerce", "revenue history").hits, ())
        reviewed = self.sdk.families.review(
            "commerce",
            self.family.id,
            expected_revision=self.family.revision,
            decision="approve",
            reason="Reviewed scope.",
        )
        for mode in ("lexical", "bm25"):
            results = self.sdk.search.graph("commerce", "revenue history", mode=mode)
            (hit,) = results.hits
            self.assertEqual(hit.type, "object_family")
            self.assertEqual(hit.family.revision, reviewed.revision)
            self.assertEqual(hit.family.member_count, 2)
            payload = json.dumps(results.to_dict())
            self.assertNotIn("sales_2024", payload)
            self.assertFalse(hit.family.to_dict()["executable"])

    def test_exploratory_scope_and_off_are_explicit(self) -> None:
        result = self.sdk.search.graph(
            "commerce",
            "revenue",
            family_mode="include_candidates",
            namespace="sales",
        )
        self.assertEqual(result.hits[0].family.to_dict()["usage"], "exploratory_only")
        self.assertFalse(
            self.sdk.search.graph(
                "commerce",
                "revenue",
                family_mode="include_candidates",
                namespace="archive",
            ).hits
        )
        self.assertFalse(self.sdk.search.graph("commerce", "revenue", family_mode=None).hits)

    def test_stale_and_rejected_families_do_not_leak_into_search(self) -> None:
        reviewed = self.sdk.families.review(
            "commerce",
            self.family.id,
            expected_revision=self.family.revision,
            decision="reject",
            reason="Not equivalent.",
        )
        self.assertEqual(reviewed.state, "rejected")
        self.assertFalse(
            self.sdk.search.graph(
                "commerce",
                "revenue",
                family_mode="include_candidates",
            ).hits
        )
        self.sdk.families.propose(
            "commerce",
            "new-revenue",
            name="revenue_history",
            members=("sales.sales_2024_01", "sales.sales_2024_02"),
            grain=("sale_id",),
        )
        node = next(node for node in self.graph.nodes if node.type == "field")
        changed = replace(node, metadata={**node.metadata, "data_type": "NEW_TYPE"})
        self.sdk.runtime.graph_store().save(
            replace(
                self.graph,
                nodes=tuple(changed if item.id == node.id else item for item in self.graph.nodes),
            )
        )
        self.assertFalse(
            self.sdk.search.graph(
                "commerce",
                "revenue",
                family_mode="include_candidates",
            ).hits
        )

    def test_workspace_search_does_not_leak_outside_selected_schema(self) -> None:
        workspace = define_system(
            create_workspace("estate"),
            "sales",
            graph_names=("commerce",),
            graphs={"commerce": self.graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        result = self.sdk.search.workspace(
            "estate",
            "revenue",
            schemas=("commerce:sales",),
            family_mode="include_candidates",
        )
        self.assertEqual(result.hits[0].id, "scope::commerce::object_family:revenue")
        self.assertEqual(result.hits[0].family.member_count, 2)
        self.assertFalse(
            self.sdk.search.workspace(
                "estate",
                "revenue",
                schemas=("commerce:archive",),
                family_mode="include_candidates",
            ).hits
        )

    def test_context_does_not_treat_family_as_physical_table(self) -> None:
        self.sdk.families.review(
            "commerce",
            self.family.id,
            expected_revision=self.family.revision,
            decision="approve",
            reason="Reviewed scope.",
        )
        for mode in ("lexical", "bm25"):
            packet = self.sdk.context.graph("commerce", "revenue history", mode=mode)
            self.assertNotIn("object_family:revenue", packet.canonical_json())

    def test_cli_uses_same_policy_and_result(self) -> None:
        previous = Path.cwd()
        output = StringIO()
        try:
            os.chdir(self.project)
            with redirect_stdout(output):
                code = main(
                    [
                        "search",
                        "commerce",
                        "revenue",
                        "--families",
                        "include_candidates",
                        "--format",
                        "json",
                    ]
                )
        finally:
            os.chdir(previous)
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            self.sdk.search.graph(
                "commerce",
                "revenue",
                family_mode="include_candidates",
            ).to_dict(),
        )
