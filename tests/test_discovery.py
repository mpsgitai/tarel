import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.discovery.contracts import DiscoveryFailure
from tarel.entity_resolution.contracts import EntityResolutionFailure
from tarel.graph.build import build_graph_from_catalog
from tarel.relationships.core import usable_relationships
from tarel.sdk import Tarel


class DiscoveryTests(TestCase):
    def test_provider_advisor_adds_metadata_only_hypotheses_without_decision_power(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "join_discovery",
                graph="warehouse",
                advisor_provider="local-advisor",
                run_id="advisor-run",
            ).run
            provider = Mock()
            provider.name = "local-advisor"
            provider.default_model = "local-model"
            provider.generate_structured.return_value = {
                "proposals": [
                    _proposal("provider-join-v1", "join_discovery", comparison="exact")
                ]
            }
            with patch(
                "tarel.discovery.application.load_provider", return_value=provider
            ):
                advised = sdk.discovery.advise(
                    run.id,
                    expected_revision=run.revision,
                    count=2,
                )
            request = provider.generate_structured.call_args.args[0]
            prompt = request.messages[-1].content
            with self.assertRaises(DiscoveryFailure) as forbidden:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=advised.run.revision,
                    actor="provider",
                    action="pause_run",
                    payload={"reason": "Provider cannot control the run."},
                )

        self.assertEqual(advised.proposed_count, 1)
        self.assertEqual(advised.run.steps[0].actor, "provider")
        self.assertEqual(advised.run.candidates[0].state, "proposed")
        self.assertIn("main.orders.customer_key", prompt)
        self.assertNotIn("samples", prompt)
        self.assertNotIn("query_text", prompt)
        self.assertEqual(forbidden.exception.code, "discovery_action_not_allowed")

    def test_join_run_is_resumable_challenged_and_retrievable(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            started = sdk.discovery.start(
                "join_discovery",
                graph="warehouse",
                question="How do orders relate to customers?",
                probe_budget=4,
                candidate_budget=3,
                run_id="join-run",
            )
            task = sdk.discovery.next(started.run.id)

            proposed = sdk.discovery.submit(
                started.run.id,
                expected_revision=task.revision,
                action="propose_candidate",
                payload=_proposal("join-v1", "join_discovery", comparison="exact"),
            ).run
            supported = sdk.discovery.submit(
                proposed.id,
                expected_revision=proposed.revision,
                action="record_observation",
                payload=_observation_payload("join-v1", "join-support", phase="support"),
            ).run
            challenged = sdk.discovery.submit(
                supported.id,
                expected_revision=supported.revision,
                action="record_observation",
                payload=_observation_payload("join-v1", "join-challenge", phase="challenge"),
            ).run
            selected = sdk.discovery.submit(
                challenged.id,
                expected_revision=challenged.revision,
                action="select_candidate",
                payload={
                    "candidate_id": "join-v1",
                    "reason": "Support and held-out challenge remained collision-free.",
                },
            ).run
            matches = sdk.discovery.find(graph="warehouse")
            ranked = sdk.discovery.find(
                graph="warehouse", query="customer key join coverage"
            )
            roundtrip = sdk.discovery.load(selected.id)

        self.assertEqual(roundtrip, selected)
        self.assertEqual(selected.candidates[0].state, "selected")
        self.assertEqual(selected.probes_used, 2)
        self.assertEqual([step.sequence for step in selected.steps], [1, 2, 3, 4])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].usage, "exploratory_selected")
        self.assertIn("not a human-reviewed", matches[0].to_dict()["warning"])
        self.assertEqual(ranked[0].candidate.id, "join-v1")
        self.assertGreater(ranked[0].score, 0)

    def test_entity_run_preserves_variation_lineage_and_aggregate_evidence_only(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                probe_budget=6,
                candidate_budget=3,
                run_id="entity-run",
            ).run
            baseline = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="propose_candidate",
                payload=_proposal(
                    "entity-v1", "entity_matching", comparison="normalized_exact"
                ),
            ).run
            variation = _proposal(
                "entity-v2",
                "entity_matching",
                comparison="normalized_levenshtein_v1",
                threshold=0.9,
            )
            variation["parent_ids"] = ["entity-v1"]
            variation["variation_operator"] = "add_fuzzy_comparator"
            evolved = sdk.discovery.submit(
                run.id,
                expected_revision=baseline.revision,
                action="propose_candidate",
                payload=variation,
            ).run
            stored = sdk.discovery.load(run.id)
            persisted = sdk.runtime.discovery_store().path(run.id).read_text("utf-8")

        self.assertEqual(evolved.candidates[1].generation, 1)
        self.assertEqual(evolved.candidates[1].parent_ids, ("entity-v1",))
        self.assertEqual(stored.revision, evolved.revision)
        for forbidden in ("raw_rows", "samples", "query_text", "connection_url"):
            self.assertNotIn(forbidden, persisted)

    def test_entity_next_offers_deterministic_field_hints_and_probe_ladder(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                run_id="guided-entity-run",
            ).run
            task = sdk.discovery.next(run.id)

        self.assertEqual(task.raw_sample_access, "host_controlled")
        self.assertIn(
            "normalized_exact_baseline",
            [step["code"] for step in task.probe_ladder],
        )
        self.assertTrue(
            any(
                "customer_key" in str(hint["source_field"])
                or "customer_key" in str(hint["target_field"])
                for hint in task.field_hints
            )
        )

    def test_cli_and_sdk_share_the_same_run_and_reject_stale_submissions(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "discovery",
                            "start",
                            "joins",
                            "--graph",
                            "warehouse",
                            "--id",
                            "cli-run",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
            payload = json.loads(output.getvalue())
            loaded = sdk.discovery.load("cli-run")
            first = sdk.discovery.submit(
                loaded.id,
                expected_revision=loaded.revision,
                action="propose_candidate",
                payload=_proposal("join-v1", "join_discovery", comparison="exact"),
            ).run
            with self.assertRaises(DiscoveryFailure) as stale:
                sdk.discovery.submit(
                    first.id,
                    expected_revision=loaded.revision,
                    action="pause_run",
                    payload={"reason": "stale writer"},
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run"]["id"], loaded.id)
        self.assertEqual(stale.exception.code, "stale_discovery_run")

    def test_contract_rejects_free_sql_raw_fields_and_selection_without_challenge(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "join_discovery", graph="warehouse", run_id="safe-run"
            ).run
            unsafe = _proposal("unsafe", "join_discovery", comparison="exact")
            unsafe["sql"] = "select secret from users"
            with self.assertRaises(DiscoveryFailure) as unsafe_error:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="propose_candidate",
                    payload=unsafe,
                )
            proposed = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="propose_candidate",
                payload=_proposal("join-v1", "join_discovery", comparison="exact"),
            ).run
            with self.assertRaises(DiscoveryFailure) as premature:
                sdk.discovery.submit(
                    proposed.id,
                    expected_revision=proposed.revision,
                    action="select_candidate",
                    payload={"candidate_id": "join-v1", "reason": "Looks plausible."},
                )

        self.assertEqual(unsafe_error.exception.code, "invalid_discovery")
        self.assertEqual(premature.exception.code, "discovery_action_not_allowed")

    def test_failed_probe_is_sanitized_and_cannot_claim_metrics(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "join_discovery", graph="warehouse", run_id="failed-run"
            ).run
            proposed = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="propose_candidate",
                payload=_proposal("join-v1", "join_discovery", comparison="exact"),
            ).run
            failed_payload = _observation_payload(
                "join-v1", "join-error", phase="support"
            )
            failed_payload["observation"].update(
                {"error_category": "syntax_error", "metrics": None, "status": "failed"}
            )
            changed = sdk.discovery.submit(
                run.id,
                expected_revision=proposed.revision,
                action="record_observation",
                payload=failed_payload,
            ).run

        observation = changed.candidates[0].observations[0]
        self.assertEqual(observation.error_category, "syntax_error")
        self.assertIsNone(observation.metrics)

    def test_source_bound_run_requires_aggregate_permission_for_observations(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            sdk.source.configure(
                "metadata-only",
                connector="sqlite",
                graphs=("warehouse",),
            )
            run = sdk.discovery.start(
                "join_discovery",
                graph="warehouse",
                sources=("metadata-only",),
                run_id="policy-run",
            ).run
            proposed = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="propose_candidate",
                payload=_proposal("join-v1", "join_discovery", comparison="exact"),
            ).run
            with self.assertRaises(DiscoveryFailure) as denied:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=proposed.revision,
                    action="record_observation",
                    payload=_observation_payload(
                        "join-v1", "denied-observation", phase="support"
                    ),
                )

        self.assertEqual(
            denied.exception.code, "discovery_aggregates_not_allowed"
        )

    def test_pause_resume_and_graph_revision_fail_closed(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "join_discovery", graph="warehouse", run_id="resume-run"
            ).run
            paused = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="pause_run",
                payload={"reason": "Continue after an external probe window."},
            ).run
            paused_task = sdk.discovery.next(run.id)
            resumed = sdk.discovery.submit(
                run.id,
                expected_revision=paused.revision,
                action="resume_run",
                payload={"reason": "External probe window is available."},
            ).run
            sdk.runtime.graph_store().save(
                replace(sdk.graph.load("warehouse"), catalog="changed")
            )
            with self.assertRaises(DiscoveryFailure) as stale_graph:
                sdk.discovery.next(resumed.id)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(paused_task.allowed_actions, ("resume_run",))
        self.assertEqual(resumed.status, "open")
        self.assertEqual(
            stale_graph.exception.code, "discovery_graph_revision_mismatch"
        )

    def test_join_program_rejects_fuzzy_entity_semantics(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "join_discovery", graph="warehouse", run_id="fuzzy-join-run"
            ).run
            proposal = _proposal(
                "unsafe-fuzzy-join",
                "join_discovery",
                comparison="normalized_levenshtein_v1",
                threshold=0.9,
            )
            with self.assertRaises(DiscoveryFailure) as rejected:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="propose_candidate",
                    payload=proposal,
                )

        self.assertEqual(rejected.exception.code, "invalid_discovery")

    def test_selected_composite_join_promotes_to_one_reviewable_graph_draft(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            completed = _complete_selected_run(
                sdk,
                run_id="composite-promotion",
                proposals=(
                    _proposal(
                        "tenant-customer-join",
                        "join_discovery",
                        comparison="exact",
                        source_fields=(
                            "main.orders.customer_key",
                            "main.orders.tenant_key",
                        ),
                        target_fields=(
                            "main.customers.customer_key",
                            "main.customers.tenant_key",
                        ),
                    ),
                ),
            )

            promoted = sdk.discovery.promote(
                completed.id,
                candidates=("tenant-customer-join",),
                reason="Move the population-tested composite into human review.",
            )
            edge = promoted.edges[0]
            draft_graph = sdk.graph.load("warehouse")
            reviewed = sdk.relationship.decide(
                "warehouse",
                edge.id,
                state="validated",
                reason="Confirmed by the data owner.",
            )
            context = sdk.context.prefix_graph("warehouse")

        self.assertEqual(len(promoted.edges), 1)
        self.assertEqual(edge.metadata["state"], "draft")
        self.assertEqual(edge.metadata["origin"], "discovery_run")
        self.assertEqual(
            edge.metadata["from_fields"], ["customer_key", "tenant_key"]
        )
        self.assertEqual(
            edge.metadata["to_fields"], ["customer_key", "tenant_key"]
        )
        self.assertNotIn("from_field", edge.metadata)
        provenance = edge.metadata["provenance"]
        self.assertIsInstance(provenance, dict)
        self.assertEqual(provenance["run_id"], completed.id)
        self.assertEqual(usable_relationships(draft_graph), ())
        self.assertEqual(reviewed.edge.metadata["state"], "validated")
        promoted_join = next(item for item in context.joins if item.id == edge.id)
        self.assertEqual(promoted_join.from_fields, ("customer_key", "tenant_key"))
        self.assertEqual(promoted_join.to_fields, ("customer_key", "tenant_key"))

    def test_cli_promotes_a_completed_selected_join_through_the_same_path(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            completed = _complete_selected_run(
                sdk,
                run_id="cli-promotion",
                proposals=(
                    _proposal("join-v1", "join_discovery", comparison="exact"),
                ),
            )
            output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "discovery",
                            "promote",
                            completed.id,
                            "--candidate",
                            "join-v1",
                            "--reason",
                            "Place this selected join in the review queue.",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
            payload = json.loads(output.getvalue())
            edge = sdk.relationship.list("warehouse")[0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run_id"], completed.id)
        self.assertEqual(payload["graph"], "warehouse")
        self.assertEqual(len(payload["edges"]), 1)
        self.assertEqual(edge.metadata["state"], "draft")
        provenance = edge.metadata["provenance"]
        self.assertIsInstance(provenance, dict)
        self.assertEqual(provenance["candidate_id"], "join-v1")

    def test_selected_fuzzy_entity_promotes_through_sdk_into_existing_review_path(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            completed = _complete_selected_entity_run(
                sdk,
                run_id="entity-promotion",
                with_execution=True,
            )

            promoted = sdk.discovery.promote(
                completed.id,
                candidates=("entity-fuzzy-v1",),
                reason="Offer the challenged fuzzy rule for explicit review.",
            )
            entity = promoted.entity_candidates[0]
            fallback = sdk.entity_resolution.find("warehouse")
            ui = sdk.view.graph("warehouse")
            reviewed = sdk.entity_resolution.decide(
                entity.id,
                decision="approve",
                reason="The owner reviewed the population evidence and guards.",
            ).candidate
            confirmed = sdk.entity_resolution.find(
                "warehouse",
                mode="confirmed_only",
            )

        self.assertEqual(promoted.edges, ())
        self.assertEqual(entity.contract_version, "tarel.entity-resolution-candidate.v0.2")
        self.assertEqual(entity.state, "candidate")
        self.assertEqual(entity.program.comparison, "token_set_ratio_v1")
        self.assertIsNone(entity.self_match)
        self.assertEqual(entity.execution.executor_id, "test.matcher")
        self.assertEqual(entity.execution.blocking_strategy, "token_prefix")
        self.assertEqual(entity.quality.rating, "strong")
        self.assertEqual(entity.quality.score, 0.9)
        self.assertEqual(entity.evidence.confidence, entity.quality.score)
        self.assertEqual(entity.provenance.discovery_candidate_id, "entity-fuzzy-v1")
        self.assertEqual(fallback[0].usage, "exploratory_only")
        self.assertEqual(fallback[0].to_dict()["scope"], "cross_object")
        projected = next(
            edge
            for edge in ui["edges"]
            if edge["type"] == "entity_resolution_candidate"
        )
        self.assertEqual(projected["metadata"]["quality_rating"], "strong")
        self.assertEqual(projected["metadata"]["executor_id"], "test.matcher")
        self.assertEqual(reviewed.state, "reviewed")
        self.assertEqual(confirmed[0].candidate.id, entity.id)

    def test_self_entity_matching_is_validated_early_and_promotes_as_exploratory(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                run_id="self-entity-validation",
            ).run
            hints = sdk.discovery.next(run.id).field_hints
            implicit = _self_entity_proposal("implicit-self")
            implicit_program = implicit["program"]
            assert isinstance(implicit_program, dict)
            implicit_program.pop("self_match")
            with self.assertRaises(DiscoveryFailure) as missing_mode:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="propose_candidate",
                    payload=implicit,
                )
            missing_key = _self_entity_proposal("missing-key")
            missing_key_program = missing_key["program"]
            assert isinstance(missing_key_program, dict)
            missing_key_program["self_match"] = {
                "pair_policy": "distinct_unordered"
            }
            with self.assertRaises(DiscoveryFailure) as record_key:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="propose_candidate",
                    payload=missing_key,
                )
            invalid_pair_policy = _self_entity_proposal("ordered-pairs")
            policy_program = invalid_pair_policy["program"]
            assert isinstance(policy_program, dict)
            policy_program["self_match"] = {
                "pair_policy": "ordered",
                "record_key_field": "main.orders.order_id",
            }
            with self.assertRaises(DiscoveryFailure) as pair_policy:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="propose_candidate",
                    payload=invalid_pair_policy,
                )
            unchanged = sdk.discovery.load(run.id)

            completed = _complete_selected_self_entity_run(
                sdk,
                run_id="self-entity-promotion",
            )
            promoted = sdk.discovery.promote(
                completed.id,
                candidates=("self-customer-v1",),
                reason="Offer challenged within-object identity evidence for review.",
            )
            entity = promoted.entity_candidates[0]
            matches = sdk.entity_resolution.find("warehouse")
            ui = sdk.view.graph("warehouse")
            projected = next(
                edge
                for edge in ui["edges"]
                if edge["type"] == "entity_resolution_candidate"
            )

        self.assertEqual(missing_mode.exception.code, "invalid_discovery")
        self.assertEqual(record_key.exception.code, "invalid_discovery")
        self.assertEqual(pair_policy.exception.code, "invalid_discovery")
        self.assertEqual(unchanged.candidates, ())
        self.assertTrue(
            any(
                hint.get("source_field") == hint.get("target_field")
                and hint.get("record_key_field") == "main.orders.order_id"
                for hint in hints
            )
        )
        self.assertEqual(entity.source_field_id, entity.target_field_id)
        self.assertIsNotNone(entity.self_match)
        assert entity.self_match is not None
        self.assertEqual(entity.self_match.pair_policy, "distinct_unordered")
        self.assertEqual(len(entity.self_match.comparison_field_ids), 1)
        self.assertEqual(len(entity.self_match.contradiction_field_ids), 1)
        self.assertNotIn(
            entity.self_match.record_key_field_id,
            entity.self_match.comparison_field_ids,
        )
        self.assertEqual(matches[0].usage, "exploratory_only")
        self.assertTrue(matches[0].requires_runtime_validation)
        self.assertEqual(matches[0].to_dict()["scope"], "self_object")
        self.assertEqual(projected["metadata"]["entity_scope"], "self_object")
        self.assertEqual(projected["metadata"]["record_key_field"], "order_id")
        self.assertEqual(projected["metadata"]["comparison_fields"], ["customer_key"])
        self.assertEqual(projected["metadata"]["guard_fields"], ["tenant_key"])

    def test_self_entity_pairs_and_supersede_are_explicit(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                run_id="self-pair-policy",
            ).run
            proposed = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="propose_candidate",
                payload=_self_entity_proposal("self-pair-v1"),
            ).run
            with self.assertRaises(DiscoveryFailure) as pair_basis:
                sdk.discovery.submit(
                    proposed.id,
                    expected_revision=proposed.revision,
                    action="record_observation",
                    payload=_observation_payload(
                        "self-pair-v1",
                        "self-pair-invalid",
                        phase="support",
                        with_execution=True,
                    ),
                )

            first_run = _complete_selected_self_entity_run(
                sdk,
                run_id="self-evidence-v1",
            )
            first = sdk.discovery.promote(
                first_run.id,
                candidates=("self-customer-v1",),
                reason="First population evidence revision.",
            ).entity_candidates[0]
            second_run = _complete_selected_self_entity_run(
                sdk,
                run_id="self-evidence-v2",
            )
            with self.assertRaises(DiscoveryFailure) as explicit_required:
                sdk.discovery.promote(
                    second_run.id,
                    candidates=("self-customer-v1",),
                    reason="New population evidence must name its predecessor.",
                )
            output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "discovery",
                            "promote",
                            second_run.id,
                            "--candidate",
                            "self-customer-v1",
                            "--supersedes",
                            first.id,
                            "--reason",
                            "Supersede the earlier unreviewed evidence revision.",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
            promoted_id = json.loads(output.getvalue())["entity_candidates"][0]["id"]
            active = sdk.entity_resolution.find("warehouse", mode="include_candidates")
            audit = sdk.entity_resolution.list(graph="warehouse")
            promoted = sdk.entity_resolution.load(promoted_id)
            with self.assertRaises(EntityResolutionFailure) as stale_review:
                sdk.entity_resolution.decide(
                    first.id,
                    decision="approve",
                    reason="A superseded evidence revision cannot be reviewed.",
                )

        self.assertEqual(pair_basis.exception.code, "invalid_discovery")
        self.assertEqual(
            explicit_required.exception.code,
            "entity_resolution_supersede_required",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual([item.candidate.id for item in active], [promoted.id])
        self.assertEqual(len(audit), 2)
        self.assertEqual(promoted.provenance.supersedes_candidate_id, first.id)
        self.assertEqual(stale_review.exception.code, "entity_resolution_superseded")

    def test_cli_promotes_one_entity_candidate_and_rejects_missing_execution(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            completed = _complete_selected_entity_run(
                sdk,
                run_id="cli-entity-promotion",
                with_execution=True,
            )
            output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "discovery",
                            "promote",
                            completed.id,
                            "--candidate",
                            "entity-fuzzy-v1",
                            "--reason",
                            "Move this fuzzy rule into entity review.",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
            payload = json.loads(output.getvalue())
            stored = sdk.entity_resolution.list(graph="warehouse")

            incomplete = _complete_selected_entity_run(
                sdk,
                run_id="missing-execution",
                with_execution=False,
            )
            with self.assertRaises(DiscoveryFailure) as rejected:
                sdk.discovery.promote(
                    incomplete.id,
                    candidates=("entity-fuzzy-v1",),
                    reason="This lacks reproducible executor metadata.",
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["edges"], [])
        self.assertEqual(len(payload["entity_candidates"]), 1)
        self.assertEqual(len(stored), 1)
        self.assertEqual(rejected.exception.code, "incomplete_entity_execution")

    def test_identity_inventory_promotes_protected_aliases_and_resolves_via_sdk_and_cli(
        self,
    ) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            sdk.source.configure(
                "warehouse-source",
                connector="sqlite",
                graphs=("warehouse",),
                enrichment_permissions=(
                    "aggregates",
                    "entity_aliases",
                ),
            )
            completed = _complete_identity_inspection_run(sdk, run_id="identity-loop")
            promoted = sdk.discovery.promote(
                completed.id,
                candidates=("same-customer-17",),
                reason="Two independent probes support this same-object alias group.",
            ).entity_candidates[0]
            exploratory = sdk.entity_resolution.resolve(
                "warehouse", object="main.orders", key="1001"
            )
            confirmed_before = sdk.entity_resolution.resolve(
                "warehouse",
                object="main.orders",
                key="1001",
                mode="confirmed_only",
            )
            ui = sdk.view.graph("warehouse")
            ui_text = json.dumps(ui, sort_keys=True)
            edge = next(
                item
                for item in ui["edges"]
                if item["type"] == "entity_resolution_candidate"
            )
            stored_mode = (
                sdk.runtime.entity_resolution_store().path(promoted.id).stat().st_mode
                & 0o777
            )
            output = StringIO()
            show_output = StringIO()
            discovery_output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(output):
                    cli_exit = main(
                        [
                            "entity",
                            "resolve",
                            "warehouse",
                            "--object",
                            "main.orders",
                            "--key",
                            "1001",
                            "--mode",
                            "include_candidates",
                            "--format",
                            "json",
                        ]
                    )
                with redirect_stdout(show_output):
                    show_exit = main(
                        ["entity", "show", promoted.id, "--format", "json"]
                    )
                with redirect_stdout(discovery_output):
                    discovery_exit = main(
                        ["discovery", "show", completed.id, "--format", "json"]
                    )
            finally:
                os.chdir(previous)
            cli_payload = json.loads(output.getvalue())
            show_payload = json.loads(show_output.getvalue())
            discovery_payload = json.loads(discovery_output.getvalue())
            reviewed = sdk.entity_resolution.decide(
                promoted.id,
                decision="approve",
                reason="The concrete alias group and its counterexample probe were reviewed.",
            ).candidate
            confirmed_after = sdk.entity_resolution.resolve(
                "warehouse",
                object="main.orders",
                key="1001",
                mode="confirmed_only",
            )
            sdk.source.configure(
                "warehouse-source",
                connector="sqlite",
                graphs=("warehouse",),
                enrichment_permissions=("aggregates",),
                replace=True,
            )
            with self.assertRaises(EntityResolutionFailure) as revoked:
                sdk.entity_resolution.resolve(
                    "warehouse", object="main.orders", key="not-present"
                )

        self.assertEqual(completed.identity_inspection.phase, "group_validation")
        self.assertEqual(exploratory[0].group.member_keys, ("1001", "1004"))
        self.assertEqual(exploratory[0].usage, "exploratory_only")
        self.assertEqual(confirmed_before, ())
        self.assertEqual(stored_mode, 0o600)
        self.assertEqual(edge["metadata"]["identity_member_count"], 2)
        self.assertTrue(edge["metadata"]["identity_mapping_persisted"])
        self.assertNotIn("1001", ui_text)
        self.assertNotIn("1004", ui_text)
        self.assertNotIn("ordered identity inventory", ui_text)
        self.assertEqual(cli_exit, 0)
        self.assertEqual(cli_payload["aliases"][0]["group"]["member_keys"], ["1001", "1004"])
        self.assertEqual(show_exit, 0)
        self.assertNotIn("member_keys", show_payload["identity_group"])
        self.assertNotIn("rationale", show_payload["identity_group"])
        discovery_group = discovery_payload["identity_inspection"]["groups"][0]
        self.assertEqual(discovery_exit, 0)
        self.assertNotIn("member_keys", discovery_group)
        self.assertNotIn("rationale", discovery_group)
        self.assertEqual(reviewed.state, "reviewed")
        self.assertEqual(confirmed_after[0].usage, "confirmed")
        self.assertEqual(revoked.exception.code, "entity_aliases_not_allowed")

    def test_identity_inspection_fails_closed_on_policy_budget_and_scope(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            sdk.source.configure(
                "identity-enabled",
                connector="sqlite",
                graphs=("warehouse",),
                enrichment_permissions=("aggregates", "entity_aliases"),
            )
            run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                sources=("identity-enabled",),
                identity_inspection=True,
                run_id="identity-policy",
            ).run
            over_budget = _identity_manifest(run)
            over_budget["source_name"] = "identity-enabled"
            over_budget["estimated_tokens"] = 2_000
            over_budget["token_budget"] = 1_000
            with self.assertRaises(DiscoveryFailure) as budget:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="register_identity_inventory",
                    payload=over_budget,
                )
            wrong_scope = _identity_manifest(run)
            wrong_scope["source_name"] = "identity-enabled"
            wrong_scope["label_field"] = "main.customers.customer_name"
            with self.assertRaises(DiscoveryFailure) as scope:
                sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action="register_identity_inventory",
                    payload=wrong_scope,
                )
            sdk.source.configure(
                "sample-only",
                connector="sqlite",
                graphs=("warehouse",),
                enrichment_permissions=("aggregates", "raw_samples"),
            )
            denied_run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                sources=("sample-only",),
                identity_inspection=True,
                run_id="identity-denied",
            ).run
            with self.assertRaises(DiscoveryFailure) as aliases:
                sdk.discovery.submit(
                    denied_run.id,
                    expected_revision=denied_run.revision,
                    action="register_identity_inventory",
                    payload=_identity_manifest(denied_run),
                )

        self.assertEqual(budget.exception.code, "identity_token_budget_exceeded")
        self.assertEqual(scope.exception.code, "invalid_identity_inventory")
        self.assertEqual(aliases.exception.code, "entity_aliases_not_allowed")

    def test_cli_starts_the_same_identity_state_loaded_by_sdk(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            sdk.source.configure(
                "warehouse-source",
                connector="sqlite",
                graphs=("warehouse",),
                enrichment_permissions=("aggregates", "entity_aliases"),
            )
            output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "discovery",
                            "start",
                            "entities",
                            "--graph",
                            "warehouse",
                            "--source",
                            "warehouse-source",
                            "--identity-inspection",
                            "--id",
                            "cli-identity",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
            loaded = sdk.discovery.load("cli-identity")
            task = sdk.discovery.next("cli-identity")

        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(loaded.identity_inspection)
        self.assertEqual(task.allowed_actions[0], "register_identity_inventory")
        self.assertEqual(task.identity_inspection["phase"], "started")

    def test_identity_inspection_can_complete_without_a_candidate(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            sdk.source.configure(
                "warehouse-source",
                connector="sqlite",
                graphs=("warehouse",),
                enrichment_permissions=("aggregates", "entity_aliases"),
            )
            run = sdk.discovery.start(
                "entity_matching",
                graph="warehouse",
                sources=("warehouse-source",),
                identity_inspection=True,
                run_id="identity-no-match",
            ).run
            manifest = _identity_manifest(run)
            manifest["source_name"] = "warehouse-source"
            manifest["row_count"] = 0
            manifest["identity_count"] = 0
            manifest["estimated_tokens"] = 0
            run = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="register_identity_inventory",
                payload=manifest,
            ).run
            page = _identity_page()
            page["identity_count"] = 0
            run = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="record_inventory_page",
                payload=page,
            ).run
            task = sdk.discovery.next(run.id)
            completed = sdk.discovery.submit(
                run.id,
                expected_revision=run.revision,
                action="complete_run",
                payload={"reason": "The complete inventory contained no entity aliases."},
            ).run

        self.assertTrue(task.identity_inspection["coverage_complete"])
        self.assertIn("complete_run", task.allowed_actions)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.candidates, ())

    def test_promotion_is_fail_closed_and_atomic(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            completed = _complete_selected_run(
                sdk,
                run_id="atomic-promotion",
                proposals=(
                    _proposal("duplicate-a", "join_discovery", comparison="exact"),
                    _proposal("duplicate-b", "join_discovery", comparison="exact"),
                ),
            )
            with self.assertRaises(DiscoveryFailure) as duplicate:
                sdk.discovery.promote(
                    completed.id,
                    candidates=("duplicate-a", "duplicate-b"),
                    reason="This batch must not be partially written.",
                )
            stored_candidates = sdk.relationship.list("warehouse")

        self.assertEqual(duplicate.exception.code, "discovery_promotion_failed")
        self.assertEqual(stored_candidates, ())

    def test_promotion_does_not_flatten_normalized_join_semantics(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = _sdk(temporary_directory)
            completed = _complete_selected_run(
                sdk,
                run_id="normalized-promotion",
                proposals=(
                    _proposal(
                        "normalized-join",
                        "join_discovery",
                        comparison="normalized_exact",
                    ),
                ),
            )
            with self.assertRaises(DiscoveryFailure) as rejected:
                sdk.discovery.promote(
                    completed.id,
                    candidates=("normalized-join",),
                    reason="This must retain its executable transform semantics.",
                )

        self.assertEqual(rejected.exception.code, "unsupported_discovery_promotion")

    def test_agent_setup_installs_a_valid_repo_scoped_skill(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "agent",
                        "setup",
                        "codex",
                        "--target",
                        str(project),
                        "--format",
                        "json",
                    ]
                )
            installed = project / ".agents/skills/tarel-discovery/SKILL.md"
            skill_text = installed.read_text("utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("tarel discovery next", skill_text)

    def test_cli_does_not_echo_rejected_payload_values(self) -> None:
        previous = Path.cwd()
        protected = "PROTECTED_CUSTOMER_VALUE"
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = _sdk(temporary_directory)
            run = sdk.discovery.start(
                "join_discovery", graph="warehouse", run_id="redaction-run"
            ).run
            source = project / "unsafe.json"
            unsafe = _proposal("join-v1", "join_discovery", comparison="exact")
            unsafe["samples"] = [protected]
            source.write_text(json.dumps(unsafe), encoding="utf-8")
            errors = StringIO()
            try:
                os.chdir(project)
                with redirect_stderr(errors):
                    exit_code = main(
                        [
                            "discovery",
                            "submit",
                            run.id,
                            "--expected-revision",
                            run.revision,
                            "--action",
                            "propose_candidate",
                            "--source",
                            str(source),
                        ]
                    )
            finally:
                os.chdir(previous)

        self.assertEqual(exit_code, 2)
        self.assertNotIn(protected, errors.getvalue())


def _sdk(root: str) -> Tarel:
    sdk = Tarel(Path(root) / ".tarel")
    sdk.runtime.graph_store().save(_graph())
    return sdk


def _graph():
    return build_graph_from_catalog(
        "warehouse",
        CatalogResult(
            connector="sqlite",
            source_type="database",
            catalog="warehouse",
            dialect="sqlite",
            objects=(
                CatalogObject(
                    namespace="main",
                    name="orders",
                    kind="table",
                    primary_key=("order_id",),
                    fields=(
                        CatalogField("order_id", 1, "INTEGER", False),
                        CatalogField("customer_key", 2, "TEXT", False),
                        CatalogField("tenant_key", 3, "TEXT", False),
                    ),
                ),
                CatalogObject(
                    namespace="main",
                    name="customers",
                    kind="table",
                    primary_key=("customer_key",),
                    fields=(
                        CatalogField("customer_key", 1, "TEXT", False),
                        CatalogField("customer_name", 2, "TEXT", False),
                        CatalogField("tenant_key", 3, "TEXT", False),
                    ),
                ),
            ),
        ),
    )


def _proposal(
    candidate_id: str,
    kind: str,
    *,
    comparison: str,
    threshold: float | None = None,
    source_fields: tuple[str, ...] | None = None,
    target_fields: tuple[str, ...] | None = None,
) -> dict[str, object]:
    selected_source_fields = source_fields or ("main.orders.customer_key",)
    selected_target_fields = target_fields or ("main.customers.customer_key",)
    transforms = (
        []
        if comparison == "exact"
        else [
            {"kind": "trim", "length": None, "start": None},
            {"kind": "casefold", "length": None, "start": None},
        ]
    )
    return {
        "candidate_id": candidate_id,
        "parent_ids": [],
        "program": {
            "blocking_field_indexes": [] if kind == "join_discovery" else [0],
            "comparison": comparison,
            "contradiction_field_indexes": [],
            "kind": kind,
            "source_fields": list(selected_source_fields),
            "source_transforms": [transforms for _field in selected_source_fields],
            "target_fields": list(selected_target_fields),
            "target_transforms": [transforms for _field in selected_target_fields],
            "threshold": threshold,
        },
        "variation_operator": "seed_from_graph",
    }


def _identity_manifest(run) -> dict[str, object]:
    return {
        "estimated_tokens": 240,
        "graph_name": run.graph_name,
        "graph_revision": run.graph_revision,
        "identity_count": 4,
        "inventory_hash": "d" * 64,
        "label_field": "main.orders.customer_key",
        "object_reference": "main.orders",
        "order": "label_then_key",
        "page_count": 1,
        "record_key_field": "main.orders.order_id",
        "row_count": 6,
        "source_name": "warehouse-source" if run.id == "identity-loop" else "sample-only",
        "token_budget": 1_000,
        "truncated": False,
    }


def _identity_page() -> dict[str, object]:
    return {
        "content_hash": "e" * 64,
        "error_category": None,
        "id": "identity-page-0",
        "identity_count": 4,
        "index": 0,
        "status": "succeeded",
    }


def _identity_proposal() -> dict[str, object]:
    return {
        "candidate_id": "same-customer-17",
        "parent_ids": [],
        "program": {
            "blocking_field_indexes": [0],
            "comparison": "llm_assessed",
            "contradiction_field_indexes": [],
            "kind": "entity_matching",
            "self_match": {
                "pair_policy": "distinct_unordered",
                "record_key_field": "main.orders.order_id",
            },
            "source_fields": ["main.orders.customer_key"],
            "source_transforms": [[]],
            "target_fields": ["main.orders.customer_key"],
            "target_transforms": [[]],
            "threshold": None,
        },
        "variation_operator": "llm_identity_inventory",
    }


def _identity_group() -> dict[str, object]:
    return {
        "candidate_id": "same-customer-17",
        "confidence": 0.87,
        "evidence_refs": ["identity-page-0"],
        "id": "customer-alias-17",
        "member_keys": ["1004", "1001"],
        "model": "provider/model:test@v1",
        "producer": "test-provider",
        "rationale": "The ordered identity inventory suggests one business entity.",
    }


def _identity_observation(*, phase: str) -> dict[str, object]:
    return {
        "candidate_id": "same-customer-17",
        "observation": {
            "dialect": "sqlite",
            "duration_ms": 6,
            "error_category": None,
            "evidence_level": "sample_tested",
            "execution": {
                "artifact_hash": "b" * 64,
                "blocking_strategy": "exact_value",
                "blocking_version": "v1",
                "executor_id": "test.read-only-sql",
                "executor_version": "v1",
            },
            "id": f"identity-{phase}",
            "metrics": {
                "basis": "pairs",
                "collision_count": 0,
                "collision_rate": 0.0,
                "confidence": 0.9,
                "counterexample_count": 0,
                "coverage": 1.0,
                "distinct_source_count": 2,
                "distinct_target_count": 2,
                "evaluated_count": 1,
                "matched_count": 1,
            },
            "phase": phase,
            "query_hash": ("a" if phase == "support" else "c") * 64,
            "row_limit": 50,
            "status": "succeeded",
            "truncated": False,
        },
    }


def _complete_identity_inspection_run(sdk: Tarel, *, run_id: str):
    current = sdk.discovery.start(
        "entity_matching",
        graph="warehouse",
        sources=("warehouse-source",),
        identity_inspection=True,
        run_id=run_id,
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="register_identity_inventory",
        payload=_identity_manifest(current),
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="record_inventory_page",
        payload=_identity_page(),
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        actor="provider",
        action="propose_candidate",
        payload=_identity_proposal(),
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        actor="provider",
        action="record_entity_group",
        payload=_identity_group(),
    ).run
    for phase in ("support", "challenge"):
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="record_observation",
            payload=_identity_observation(phase=phase),
        ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        actor="provider",
        action="record_entity_reflection",
        payload={
            "candidate_id": "same-customer-17",
            "confidence": 0.86,
            "decision": "accept_as_exploratory",
            "evidence_refs": ["customer-alias-17"],
            "id": "identity-reflection-17",
            "model": "provider/model:test@v1",
            "observation_id": "identity-challenge",
            "producer": "test-provider",
            "summary": "The independent guard probe found no contradiction.",
        },
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="select_candidate",
        payload={
            "candidate_id": "same-customer-17",
            "reason": "The concrete key group survived support and challenge probes.",
        },
    ).run
    return sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="complete_run",
        payload={"reason": "The selected alias group is ready for protected promotion."},
    ).run


def _complete_selected_run(
    sdk: Tarel,
    *,
    run_id: str,
    proposals: tuple[dict[str, object], ...],
):
    current = sdk.discovery.start(
        "join_discovery", graph="warehouse", run_id=run_id
    ).run
    for proposal in proposals:
        candidate_id = str(proposal["candidate_id"])
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="propose_candidate",
            payload=proposal,
        ).run
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="record_observation",
            payload=_observation_payload(
                candidate_id, f"{candidate_id}-support", phase="support"
            ),
        ).run
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="record_observation",
            payload=_observation_payload(
                candidate_id, f"{candidate_id}-challenge", phase="challenge"
            ),
        ).run
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="select_candidate",
            payload={
                "candidate_id": candidate_id,
                "reason": "Support and population challenge agree.",
            },
        ).run
    return sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="complete_run",
        payload={"reason": "Selected candidates are ready for explicit review promotion."},
    ).run


def _complete_selected_entity_run(
    sdk: Tarel,
    *,
    run_id: str,
    with_execution: bool,
):
    proposal = _proposal(
        "entity-fuzzy-v1",
        "entity_matching",
        comparison="token_set_ratio_v1",
        threshold=0.84,
        source_fields=(
            "main.orders.customer_key",
            "main.orders.tenant_key",
        ),
        target_fields=(
            "main.customers.customer_name",
            "main.customers.tenant_key",
        ),
    )
    program = proposal["program"]
    assert isinstance(program, dict)
    program["blocking_field_indexes"] = [0]
    program["contradiction_field_indexes"] = [1]
    current = sdk.discovery.start(
        "entity_matching",
        graph="warehouse",
        run_id=run_id,
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="propose_candidate",
        payload=proposal,
    ).run
    for phase in ("support", "challenge"):
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="record_observation",
            payload=_observation_payload(
                "entity-fuzzy-v1",
                f"entity-fuzzy-v1-{phase}",
                phase=phase,
                with_execution=with_execution,
            ),
        ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="select_candidate",
        payload={
            "candidate_id": "entity-fuzzy-v1",
            "reason": "Support and hard-case challenge remained strong.",
        },
    ).run
    return sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="complete_run",
        payload={"reason": "Selected fuzzy entity candidate is ready for review."},
    ).run


def _self_entity_proposal(candidate_id: str) -> dict[str, object]:
    proposal = _proposal(
        candidate_id,
        "entity_matching",
        comparison="token_set_ratio_v1",
        threshold=0.84,
        source_fields=(
            "main.orders.customer_key",
            "main.orders.tenant_key",
        ),
        target_fields=(
            "main.orders.customer_key",
            "main.orders.tenant_key",
        ),
    )
    program = proposal["program"]
    assert isinstance(program, dict)
    program["blocking_field_indexes"] = [0]
    program["contradiction_field_indexes"] = [1]
    program["self_match"] = {
        "pair_policy": "distinct_unordered",
        "record_key_field": "main.orders.order_id",
    }
    return proposal


def _complete_selected_self_entity_run(
    sdk: Tarel,
    *,
    run_id: str,
):
    current = sdk.discovery.start(
        "entity_matching",
        graph="warehouse",
        run_id=run_id,
    ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="propose_candidate",
        payload=_self_entity_proposal("self-customer-v1"),
    ).run
    for phase in ("support", "challenge"):
        current = sdk.discovery.submit(
            current.id,
            expected_revision=current.revision,
            action="record_observation",
            payload=_observation_payload(
                "self-customer-v1",
                f"{run_id}-{phase}",
                phase=phase,
                with_execution=True,
                basis="pairs",
            ),
        ).run
    current = sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="select_candidate",
        payload={
            "candidate_id": "self-customer-v1",
            "reason": "Canonical distinct-record pairs survived the challenge.",
        },
    ).run
    return sdk.discovery.submit(
        current.id,
        expected_revision=current.revision,
        action="complete_run",
        payload={"reason": "Self-entity candidate is ready for explicit promotion."},
    ).run


def _observation_payload(
    candidate_id: str,
    observation_id: str,
    *,
    phase: str,
    with_execution: bool = False,
    basis: str = "source_distinct",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": candidate_id,
        "observation": {
            "dialect": "sqlite",
            "duration_ms": 12,
            "error_category": None,
            "evidence_level": "population_tested",
            "id": observation_id,
            "metrics": {
                "basis": basis,
                "collision_count": 0,
                "collision_rate": 0.0,
                "confidence": 0.96,
                "counterexample_count": 0,
                "coverage": 0.9,
                "distinct_source_count": 10,
                "distinct_target_count": 9,
                "evaluated_count": 10,
                "matched_count": 9,
            },
            "phase": phase,
            "query_hash": "a" * 64,
            "row_limit": 10_000,
            "status": "succeeded",
            "truncated": False,
        },
    }
    if with_execution:
        observation = payload["observation"]
        assert isinstance(observation, dict)
        observation["execution"] = {
            "artifact_hash": "b" * 64,
            "blocking_strategy": "token_prefix",
            "blocking_version": "v1",
            "executor_id": "test.matcher",
            "executor_version": "v1",
        }
    return payload
