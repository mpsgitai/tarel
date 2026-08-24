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
        self.assertEqual(entity.execution.executor_id, "test.matcher")
        self.assertEqual(entity.execution.blocking_strategy, "token_prefix")
        self.assertEqual(entity.quality.rating, "strong")
        self.assertEqual(entity.quality.score, 0.9)
        self.assertEqual(entity.evidence.confidence, entity.quality.score)
        self.assertEqual(entity.provenance.discovery_candidate_id, "entity-fuzzy-v1")
        self.assertEqual(fallback[0].usage, "exploratory_only")
        projected = next(
            edge
            for edge in ui["edges"]
            if edge["type"] == "entity_resolution_candidate"
        )
        self.assertEqual(projected["metadata"]["quality_rating"], "strong")
        self.assertEqual(projected["metadata"]["executor_id"], "test.matcher")
        self.assertEqual(reviewed.state, "reviewed")
        self.assertEqual(confirmed[0].candidate.id, entity.id)

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


def _observation_payload(
    candidate_id: str,
    observation_id: str,
    *,
    phase: str,
    with_execution: bool = False,
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
                "basis": "source_distinct",
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
