"""Public delta/API checks using the private SQLite harness's promoted logical join."""

from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.context_output import canonical_json
from tarel.expansion import ExpansionTarget
from tarel.sdk import Tarel
from tarel.workspaces.contracts import SchemaReference
from tarel.workspaces.core import create_workspace, define_area, define_system, define_zone
from tests import test_logical_joins as logical_fixture


class LogicalJoinExpansionTests(TestCase):
    def setUp(self) -> None:
        self.fixture = logical_fixture.LogicalJoinTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        # Reuse the existing end-to-end harness instead of inventing evidence here:
        # it runs read-only JSON explosion/support/anti-join SQL against private in-memory
        # SQLite, submits only aggregate observations and promotes the selected candidate.
        self.fixture.test_public_cli_sdk_workflow_and_real_sqlite_harness_use_only_aggregate_evidence()
        self.sdk = Tarel(self.fixture.runtime.root)
        self.join = self.sdk.logical_joins.list(graph="commerce")[0]
        self.base = self.sdk.context.prefix_graph("commerce")
        self.project = self.fixture.project

    def target(self, join=None) -> ExpansionTarget:
        join = join or self.join
        return ExpansionTarget("logical_join", "commerce", join.id, join.revision)

    def cli(self, arguments, *, stdin=None):
        previous = Path.cwd()
        output, errors = StringIO(), StringIO()
        try:
            os.chdir(self.project)
            with (
                redirect_stdout(output),
                redirect_stderr(errors),
                patch("sys.stdin", StringIO(stdin or "")),
            ):
                status = main(arguments)
        finally:
            os.chdir(previous)
        return status, output.getvalue(), errors.getvalue()

    def test_private_sqlite_evidence_expands_only_under_explicit_candidate_policy(self):
        before = self.base.canonical_json()
        graph_before = self.sdk.graph.load("commerce").to_dict()
        blocked = self.sdk.context.expand(self.base, (self.target(),))
        self.assertEqual(blocked.items, ())
        self.assertEqual(blocked.omissions, ((0, "expansion_policy_excluded"),))
        delta = self.sdk.context.expand(self.base, (self.target(),), mode="include_candidates")
        self.assertEqual(delta.omissions, ())
        self.assertEqual(delta.items[0].usage, "exploratory_only")
        metadata = delta.items[0].metadata
        self.assertEqual(metadata["id"], self.join.id)
        self.assertEqual(metadata["state"], "candidate")
        self.assertEqual({item["phase"] for item in metadata["evidence"]}, {"support", "challenge"})
        self.assertTrue(
            all(item["metrics"]["evaluated_count"] == 2 for item in metadata["evidence"])
        )
        encoded = canonical_json(delta.to_dict())
        for private in (
            "PRIVATE-ALPHA",
            "PRIVATE-BETA",
            "SELECT count",
            "items_json",
            "physical_object_ids",
        ):
            self.assertNotIn(private, encoded)
        self.assertEqual(self.base.canonical_json(), before)
        self.assertEqual(self.sdk.graph.load("commerce").to_dict(), graph_before)

    def test_cli_expand_and_exact_join_lookup_match_public_sdk(self):
        packet = self.project / "logical-base.json"
        packet.write_text(self.base.canonical_json(), encoding="utf-8")
        request = json.dumps([self.target().reference()])
        # Base-validation diagnostics intentionally distinguish cold cache construction
        # from warm reads; compare interfaces under the same cache state.
        self.sdk.context.expand(self.base, (self.target(),))
        for mode, expected_status in (("confirmed_only", 1), ("include_candidates", 0)):
            with self.subTest(mode=mode):
                result = self.sdk.context.expand(self.base, (self.target(),), mode=mode)
                status, output, errors = self.cli(
                    [
                        "context",
                        "expand",
                        "--packet",
                        str(packet),
                        "--requests",
                        "-",
                        "--mode",
                        mode,
                    ],
                    stdin=request,
                )
                self.assertEqual((status, errors), (expected_status, ""))
                self.assertEqual(json.loads(output), result.to_dict())
        matches = self.sdk.logical_joins.find(
            "commerce",
            join_id=self.join.id,
            mode="include_candidates",
            limit=1,
        )
        self.assertEqual(tuple(item.join.id for item in matches), (self.join.id,))
        status, output, errors = self.cli(
            [
                "logical-join",
                "find",
                "commerce",
                "--join-id",
                self.join.id,
                "--mode",
                "include_candidates",
                "--limit",
                "1",
                "--format",
                "json",
            ]
        )
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(json.loads(output)["logical_joins"], [item.to_dict() for item in matches])

    def test_rule_review_does_not_bypass_dependency_review_or_stale_revisions(self):
        reviewed = self.sdk.logical_joins.review(
            self.join.id,
            expected_revision=self.join.revision,
            decision="approve",
            reason="Join evidence reviewed; derivation remains exploratory.",
        )
        old = self.sdk.context.expand(self.base, (self.target(),), mode="include_candidates")
        self.assertEqual(old.omissions, ((0, "stale_expansion_target"),))
        candidate_dependency = self.sdk.context.expand(self.base, (self.target(reviewed),))
        self.assertEqual(candidate_dependency.omissions, ((0, "expansion_policy_excluded"),))
        exploratory = self.sdk.context.expand(
            self.base, (self.target(reviewed),), mode="include_candidates"
        )
        self.assertEqual(exploratory.items[0].usage, "exploratory_only")
        self.fixture.approve_topology()
        stale_dependency = self.sdk.context.expand(
            self.base, (self.target(reviewed),), mode="include_candidates"
        )
        self.assertEqual(stale_dependency.items, ())
        self.assertEqual(stale_dependency.omissions, ((0, "expansion_policy_excluded"),))
        # Re-test the same actual SQLite observations against the newly pinned declaration.
        observations = {item.phase: item.to_dict() for item in self.join.observations}
        fresh = self.fixture.promote(
            self.fixture.selected(
                run_id="fresh-dependency",
                observations=observations,
            )
        ).logical_joins[0]
        fresh = self.sdk.logical_joins.review(
            fresh.id,
            expected_revision=fresh.revision,
            decision="approve",
            reason="Current declaration and independent query evidence reviewed.",
        )
        confirmed = self.sdk.context.expand(self.base, (self.target(fresh),))
        self.assertEqual(confirmed.omissions, ())
        self.assertEqual(confirmed.items[0].usage, "confirmed")

    def test_rejected_candidate_and_tight_budget_have_explicit_omissions(self):
        tight = self.sdk.context.expand(
            self.base,
            (self.target(),),
            mode="include_candidates",
            max_characters=1000,
        )
        self.assertEqual(tight.items, ())
        self.assertEqual(tight.omissions, ((0, "expansion_character_budget"),))
        self.assertLessEqual(len(canonical_json(tight.to_dict())), 1000)
        rejected = self.sdk.logical_joins.review(
            self.join.id,
            expected_revision=self.join.revision,
            decision="reject",
            reason="Human declined this rule.",
        )
        result = self.sdk.context.expand(
            self.base, (self.target(rejected),), mode="include_candidates"
        )
        self.assertEqual(result.items, ())
        self.assertEqual(result.omissions, ((0, "expansion_policy_excluded"),))

    def test_workspace_zone_cannot_expand_a_join_across_hidden_physical_endpoints(self):
        graph = self.fixture.graph
        workspace = define_system(
            create_workspace("join-estate"),
            "sales",
            graph_names=("commerce",),
            graphs={"commerce": graph},
        )
        workspace = define_zone(
            define_area(
                workspace,
                "sales",
                "sales-data",
                schemas=(SchemaReference("commerce", "sales"),),
                graphs={"commerce": graph},
            ),
            "sales",
            "orders-only",
            object_references=("commerce:sales.orders",),
            graphs={"commerce": graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        base = self.sdk.context.workspace("join-estate", "orders", zones=("sales:orders-only",))
        result = self.sdk.context.expand(base, (self.target(),), mode="include_candidates")
        self.assertEqual(result.items, ())
        self.assertEqual(result.omissions, ((0, "expansion_outside_scope"),))
        wrong_graph = replace(self.target(), graph="another-graph")
        other = self.sdk.context.expand(base, (wrong_graph,), mode="include_candidates")
        self.assertEqual(other.omissions, ((0, "expansion_outside_scope"),))
