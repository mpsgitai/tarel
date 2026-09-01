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
from tarel.discovery.application import (
    advise_discovery_run_use_case,
    promote_discovery_candidates_use_case,
    start_discovery_run_use_case,
    submit_discovery_step_use_case,
)
from tarel.discovery.contracts import DiscoveryFailure, DiscoveryRun
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.revision import graph_revision, physical_graph_revision
from tarel.reference_mapping.application import (
    decide_reference_mapping_candidate_use_case,
    find_reference_mapping_candidates_use_case,
)
from tarel.reference_mapping.contracts import (
    ReferenceMappingCandidate,
    ReferenceMappingFailure,
    review_reference_mapping_candidate,
)
from tarel.reference_mapping.store import FileReferenceMappingStore
from tarel.runtime import TarelRuntime
from tarel.sdk import Tarel


class ReferenceMappingTests(TestCase):
    def test_cli_import_rejects_duplicate_json_fields(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            candidate = _candidate_contract()
            source = project / "duplicate.json"
            encoded = json.dumps(candidate.to_dict())
            source.write_text('{"id":"shadow",' + encoded[1:], encoding="utf-8")
            errors = StringIO()
            try:
                os.chdir(project)
                with redirect_stderr(errors):
                    exit_code = main(
                        ["reference-mapping", "import", "--source", str(source)]
                    )
            finally:
                os.chdir(previous)

        self.assertEqual(exit_code, 2)
        self.assertIn("invalid_reference_mapping", errors.getvalue())

    def test_annotation_changes_preserve_mapping_but_physical_drift_hides_it(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = Tarel(Path(temporary_directory) / ".tarel")
            graph = _graph()
            sdk.runtime.graph_store().save(graph)
            source = next(node for node in graph.nodes if node.label == "country_code")
            target = next(node for node in graph.nodes if node.label == "region_name")
            candidate = replace(
                _candidate_contract(),
                graph_name=graph.name,
                graph_revision=physical_graph_revision(graph),
                source_field_id=source.id,
                target_field_id=target.id,
            )
            sdk.reference_mapping.import_candidate(candidate)
            annotated = replace(
                graph,
                nodes=tuple(
                    replace(
                        node,
                        metadata={
                            **node.metadata,
                            "annotation_review": {"state": "validated"},
                        },
                    )
                    if node.type == "table"
                    else node
                    for node in graph.nodes
                ),
            )
            sdk.runtime.graph_store().save(annotated)
            after_annotation = sdk.reference_mapping.find(graph.name)
            changed_source = replace(
                source,
                metadata={**source.metadata, "data_type": "BIGINT"},
            )
            drifted = replace(
                annotated,
                nodes=tuple(
                    changed_source if node.id == source.id else node
                    for node in annotated.nodes
                ),
            )
            sdk.runtime.graph_store().save(drifted)
            after_physical_drift = sdk.reference_mapping.find(graph.name)

        self.assertEqual(after_annotation[0].candidate.id, candidate.id)
        self.assertEqual(after_physical_drift, ())

    def test_direct_import_rejects_a_field_without_a_physical_parent(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = Tarel(Path(temporary_directory) / ".tarel")
            graph = _graph()
            source = next(node for node in graph.nodes if node.label == "country_code")
            target = next(node for node in graph.nodes if node.label == "region_name")
            orphan_source = replace(
                source,
                metadata={**source.metadata, "object_id": "missing-object"},
            )
            orphan_graph = replace(
                graph,
                nodes=tuple(
                    orphan_source if node.id == source.id else node
                    for node in graph.nodes
                ),
            )
            sdk.runtime.graph_store().save(orphan_graph)
            candidate = replace(
                _candidate_contract(),
                graph_name=graph.name,
                graph_revision=physical_graph_revision(orphan_graph),
                source_field_id=source.id,
                target_field_id=target.id,
            )
            with self.assertRaises(ReferenceMappingFailure) as orphaned:
                sdk.reference_mapping.import_candidate(candidate)

        self.assertEqual(orphaned.exception.code, "reference_mapping_field_not_found")

    def test_only_one_mapping_per_directed_pair_can_be_reviewed(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = Tarel(Path(temporary_directory) / ".tarel")
            graph = _graph()
            sdk.runtime.graph_store().save(graph)
            source = next(node for node in graph.nodes if node.label == "country_code")
            target = next(node for node in graph.nodes if node.label == "region_name")
            base = replace(
                _candidate_contract(),
                graph_name=graph.name,
                graph_revision=physical_graph_revision(graph),
                source_field_id=source.id,
                target_field_id=target.id,
            )
            alternative = replace(
                base,
                id="mapping-candidate-alternative",
                mapping_manifest_hash="9" * 64,
            )
            sdk.reference_mapping.import_candidate(base)
            sdk.reference_mapping.import_candidate(alternative)
            with self.assertRaises(ReferenceMappingFailure) as missing_revision:
                decide_reference_mapping_candidate_use_case(
                    base.id,
                    decision="approve",
                    reason="A blind review must fail.",
                    expected_revision=None,
                    runtime=sdk.runtime,
                )
            with self.assertRaises(ReferenceMappingFailure) as stale_revision:
                sdk.reference_mapping.decide(
                    base.id,
                    decision="approve",
                    reason="A stale review must fail.",
                    expected_revision="0" * 64,
                )
            reviewed = sdk.reference_mapping.decide(
                base.id,
                decision="approve",
                reason="The first mapping is the reviewed mapping for this directed pair.",
                expected_revision=base.revision,
            ).candidate
            with self.assertRaises(ReferenceMappingFailure) as conflict:
                sdk.reference_mapping.decide(
                    alternative.id,
                    decision="approve",
                    reason="A second reviewed mapping would be ambiguous.",
                    expected_revision=alternative.revision,
                )
            preferred = sdk.reference_mapping.find(graph.name)
            all_active = sdk.reference_mapping.find(
                graph.name,
                mode="include_candidates",
            )

        self.assertEqual(
            missing_revision.exception.code,
            "expected_reference_mapping_revision_required",
        )
        self.assertEqual(stale_revision.exception.code, "stale_reference_mapping_candidate")
        self.assertEqual(conflict.exception.code, "reference_mapping_review_conflict")
        self.assertEqual([match.candidate.id for match in preferred], [reviewed.id])
        self.assertEqual(len(all_active), 2)

    def test_store_rejects_duplicate_json_fields(self) -> None:
        candidate = _candidate_contract()
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            store = FileReferenceMappingStore(Path(temporary_directory) / "mappings")
            path = store.save(candidate)
            payload = path.read_text(encoding="utf-8")
            path.write_text(
                payload.replace("{", '{"id":"shadow",', 1),
                encoding="utf-8",
            )
            with self.assertRaises(ReferenceMappingFailure) as duplicate:
                store.load(candidate.id)

        self.assertEqual(duplicate.exception.code, "invalid_reference_mapping")

    def test_sdk_discovery_promotes_into_cli_retrieval_and_review(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = Tarel(project / ".tarel")
            graph = _graph()
            sdk.runtime.graph_store().save(graph)
            run = sdk.discovery.start(
                "reference_mapping",
                graph="warehouse",
                run_id="sdk-cli-map",
            ).run
            for action, payload in (
                ("propose_candidate", _proposal()),
                ("register_mapping_manifest", _manifest()),
                ("record_observation", _observation("support")),
                ("record_observation", _observation("challenge")),
                (
                    "select_candidate",
                    {
                        "candidate_id": "country-to-region",
                        "reason": "Independent aggregate challenge found no contradiction.",
                    },
                ),
                (
                    "complete_run",
                    {"reason": "The mapping is ready for review."},
                ),
            ):
                run = sdk.discovery.submit(
                    run.id,
                    expected_revision=run.revision,
                    action=action,
                    payload=payload,
                ).run
            promoted = sdk.discovery.promote(
                run.id,
                candidates=("country-to-region",),
                reason="Offer independent aggregate evidence for review.",
            ).reference_mapping_candidates[0]
            found_output = StringIO()
            reviewed_output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(found_output):
                    found_exit = main(
                        [
                            "reference-mapping",
                            "find",
                            "warehouse",
                            "--mode",
                            "confirmed_then_candidates",
                            "--format",
                            "json",
                        ]
                    )
                with redirect_stdout(reviewed_output):
                    reviewed_exit = main(
                        [
                            "reference-mapping",
                            "review",
                            promoted.id,
                            "--decision",
                            "approve",
                            "--reason",
                            "Direction, manifest, support, and challenge were reviewed.",
                            "--revision",
                            promoted.revision,
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
            found = json.loads(found_output.getvalue())
            reviewed = sdk.reference_mapping.load(promoted.id)
            confirmed = sdk.reference_mapping.find(
                "warehouse", mode="confirmed_only"
            )
            view = sdk.view.graph("warehouse")
            current_graph_revision = graph_revision(sdk.graph.load("warehouse"))

        self.assertEqual((found_exit, reviewed_exit), (0, 0))
        self.assertEqual(found["matches"][0]["usage"], "exploratory_only")
        self.assertEqual(reviewed.state, "reviewed")
        self.assertEqual(confirmed[0].usage, "confirmed")
        mapping_edge = next(
            edge for edge in view["edges"] if edge["type"] == "reference_mapping"
        )
        self.assertEqual(mapping_edge["metadata"]["usage"], "confirmed")
        self.assertEqual(current_graph_revision, graph_revision(graph))

    def test_mapping_lifecycle_is_directed_private_and_fail_closed(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            runtime = _runtime(temporary_directory)
            before_graph = runtime.graph_store().load("warehouse")
            before_revision = graph_revision(before_graph)
            before_edges = before_graph.edges
            run = start_discovery_run_use_case(
                "reference_mapping",
                graph_name="warehouse",
                run_id="country-region-map",
                runtime=runtime,
            ).run
            proposed = submit_discovery_step_use_case(
                run.id,
                expected_revision=run.revision,
                actor="provider",
                action="propose_candidate",
                payload=_proposal(),
                runtime=runtime,
            ).run
            with self.assertRaises(DiscoveryFailure) as provider_manifest:
                submit_discovery_step_use_case(
                    run.id,
                    expected_revision=proposed.revision,
                    actor="provider",
                    action="register_mapping_manifest",
                    payload=_manifest(),
                    runtime=runtime,
                )
            manifested = submit_discovery_step_use_case(
                run.id,
                expected_revision=proposed.revision,
                actor="coding_agent",
                action="register_mapping_manifest",
                payload=_manifest(),
                runtime=runtime,
            ).run
            with self.assertRaises(DiscoveryFailure) as provider_evidence:
                submit_discovery_step_use_case(
                    run.id,
                    expected_revision=manifested.revision,
                    actor="provider",
                    action="record_observation",
                    payload=_observation("support"),
                    runtime=runtime,
                )
            supported = submit_discovery_step_use_case(
                run.id,
                expected_revision=manifested.revision,
                actor="coding_agent",
                action="record_observation",
                payload=_observation("support"),
                runtime=runtime,
            ).run
            challenged = submit_discovery_step_use_case(
                run.id,
                expected_revision=supported.revision,
                actor="coding_agent",
                action="record_observation",
                payload=_observation("challenge"),
                runtime=runtime,
            ).run
            with self.assertRaises(DiscoveryFailure) as provider_decision:
                submit_discovery_step_use_case(
                    run.id,
                    expected_revision=challenged.revision,
                    actor="provider",
                    action="select_candidate",
                    payload={
                        "candidate_id": "country-to-region",
                        "reason": "Provider decisions are forbidden.",
                    },
                    runtime=runtime,
                )
            selected = submit_discovery_step_use_case(
                run.id,
                expected_revision=challenged.revision,
                actor="coding_agent",
                action="select_candidate",
                payload={
                    "candidate_id": "country-to-region",
                    "reason": "Independent aggregate challenge found no contradictions.",
                },
                runtime=runtime,
            ).run
            completed = submit_discovery_step_use_case(
                run.id,
                expected_revision=selected.revision,
                actor="coding_agent",
                action="complete_run",
                payload={"reason": "The selected mapping is ready for human review."},
                runtime=runtime,
            ).run
            promoted = promote_discovery_candidates_use_case(
                completed.id,
                candidate_ids=("country-to-region",),
                reason="Offer the challenged mapping for human review.",
                runtime=runtime,
            )
            candidate = promoted.reference_mapping_candidates[0]
            exploratory = find_reference_mapping_candidates_use_case(
                "warehouse", runtime=runtime
            )
            confirmed_before = find_reference_mapping_candidates_use_case(
                "warehouse", mode="confirmed_only", runtime=runtime
            )
            reversed_direction = find_reference_mapping_candidates_use_case(
                "warehouse",
                source="main.regions.region_name",
                target="main.countries.country_code",
                mode="include_candidates",
                runtime=runtime,
            )
            stored_text = promoted.path.read_text(encoding="utf-8")
            stored_mode = promoted.path.stat().st_mode & 0o777
            reviewed = decide_reference_mapping_candidate_use_case(
                candidate.id,
                decision="approve",
                reason="Direction, manifest, support, and challenge were reviewed.",
                expected_revision=candidate.revision,
                runtime=runtime,
            ).candidate
            confirmed_after = find_reference_mapping_candidates_use_case(
                "warehouse", mode="confirmed_only", runtime=runtime
            )
            after_graph = runtime.graph_store().load("warehouse")

        self.assertEqual(run.contract_version, "tarel.discovery-run.v0.2.experimental")
        self.assertEqual(provider_manifest.exception.code, "discovery_action_not_allowed")
        self.assertEqual(provider_evidence.exception.code, "discovery_action_not_allowed")
        self.assertEqual(provider_decision.exception.code, "discovery_action_not_allowed")
        self.assertEqual(candidate.cardinality, "many_to_one")
        self.assertEqual(candidate.mapping_manifest_hash, "d" * 64)
        self.assertEqual(candidate.mapping_count, 12)
        self.assertEqual(candidate.provenance.producer, "provider")
        self.assertEqual(candidate.state, "candidate")
        self.assertEqual(exploratory[0].usage, "exploratory_only")
        self.assertTrue(exploratory[0].requires_runtime_validation)
        self.assertEqual(confirmed_before, ())
        self.assertEqual(reversed_direction, ())
        self.assertEqual(reviewed.state, "reviewed")
        self.assertEqual(reviewed.review.source, "human")
        self.assertEqual(confirmed_after[0].usage, "confirmed")
        self.assertFalse(confirmed_after[0].requires_runtime_validation)
        self.assertEqual(stored_mode, 0o600)
        self.assertEqual(graph_revision(after_graph), before_revision)
        self.assertEqual(after_graph.edges, before_edges)
        for forbidden in ("pairs", "samples", "query_text", "SELECT", "country_values"):
            self.assertNotIn(forbidden, stored_text)

    def test_manifest_and_independent_support_are_required_for_promotion(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            runtime = _runtime(temporary_directory)
            run = start_discovery_run_use_case(
                "reference_mapping",
                graph_name="warehouse",
                run_id="incomplete-map",
                runtime=runtime,
            ).run
            proposed = submit_discovery_step_use_case(
                run.id,
                expected_revision=run.revision,
                actor="coding_agent",
                action="propose_candidate",
                payload=_proposal(),
                runtime=runtime,
            ).run
            with self.assertRaises(DiscoveryFailure) as missing_manifest:
                submit_discovery_step_use_case(
                    run.id,
                    expected_revision=proposed.revision,
                    actor="coding_agent",
                    action="record_observation",
                    payload=_observation("challenge"),
                    runtime=runtime,
                )
            manifested = submit_discovery_step_use_case(
                run.id,
                expected_revision=proposed.revision,
                actor="coding_agent",
                action="register_mapping_manifest",
                payload=_manifest(),
                runtime=runtime,
            ).run
            challenged = submit_discovery_step_use_case(
                run.id,
                expected_revision=manifested.revision,
                actor="coding_agent",
                action="record_observation",
                payload=_observation("challenge"),
                runtime=runtime,
            ).run
            selected = submit_discovery_step_use_case(
                run.id,
                expected_revision=challenged.revision,
                actor="coding_agent",
                action="select_candidate",
                payload={
                    "candidate_id": "country-to-region",
                    "reason": "Challenge alone must remain insufficient for promotion.",
                },
                runtime=runtime,
            ).run
            completed = submit_discovery_step_use_case(
                run.id,
                expected_revision=selected.revision,
                actor="coding_agent",
                action="complete_run",
                payload={"reason": "Exercise the promotion guard."},
                runtime=runtime,
            ).run
            with self.assertRaises(DiscoveryFailure) as incomplete:
                promote_discovery_candidates_use_case(
                    completed.id,
                    candidate_ids=("country-to-region",),
                    reason="Must fail without support.",
                    runtime=runtime,
                )

        self.assertEqual(missing_manifest.exception.code, "discovery_action_not_allowed")
        self.assertEqual(
            incomplete.exception.code, "incomplete_reference_mapping_evidence"
        )

    def test_provider_advice_proposes_only_the_mapping_hypothesis(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            runtime = _runtime(temporary_directory)
            run = start_discovery_run_use_case(
                "reference_mapping",
                graph_name="warehouse",
                advisor_provider="mapping-advisor",
                run_id="advised-map",
                runtime=runtime,
            ).run
            provider = Mock()
            provider.name = "mapping-advisor"
            provider.default_model = "local-model"
            provider.generate_structured.return_value = {"proposals": [_proposal()]}
            with patch(
                "tarel.discovery.application.load_provider", return_value=provider
            ):
                advised = advise_discovery_run_use_case(
                    run.id,
                    expected_revision=run.revision,
                    count=1,
                    runtime=runtime,
                )
            request = provider.generate_structured.call_args.args[0]
            program_schema = request.schema["properties"]["proposals"]["items"][
                "properties"
            ]["program"]

        self.assertEqual(advised.run.steps[0].actor, "provider")
        self.assertEqual(
            program_schema["required"],
            ["cardinality", "kind", "source_field", "target_field"],
        )
        self.assertNotIn("mapping_manifest_hash", program_schema["properties"])
        self.assertNotIn("mapping_count", program_schema["properties"])
        self.assertIn("registers its hash and count separately", request.messages[0].content)

    def test_v01_join_artifacts_roundtrip_unchanged_and_mapping_payloads_are_strict(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            runtime = _runtime(temporary_directory)
            join = start_discovery_run_use_case(
                "join_discovery",
                graph_name="warehouse",
                run_id="legacy-join",
                runtime=runtime,
            ).run
            roundtrip = DiscoveryRun.from_dict(json.loads(json.dumps(join.to_dict())))
            polluted_legacy = join.to_dict()
            polluted_legacy["steps"] = [
                {
                    "action": "register_mapping_manifest",
                    "actor": "coding_agent",
                    "candidate_id": None,
                    "note": None,
                    "observation_id": None,
                    "sequence": 1,
                }
            ]
            polluted_legacy.pop("revision")
            with self.assertRaises(DiscoveryFailure) as mapping_step:
                DiscoveryRun.from_dict(polluted_legacy)
            mapping = start_discovery_run_use_case(
                "reference_mapping",
                graph_name="warehouse",
                run_id="strict-map",
                runtime=runtime,
            ).run
            same_field = _proposal()
            same_field["program"]["target_field"] = (
                "MAIN.COUNTRIES.COUNTRY_CODE"
            )
            with self.assertRaises(DiscoveryFailure) as same_field_error:
                submit_discovery_step_use_case(
                    mapping.id,
                    expected_revision=mapping.revision,
                    actor="provider",
                    action="propose_candidate",
                    payload=same_field,
                    runtime=runtime,
                )
            unsafe = _proposal()
            unsafe["program"]["pairs"] = [["AT", "Europe"]]
            with self.assertRaises(DiscoveryFailure) as unsafe_program:
                submit_discovery_step_use_case(
                    mapping.id,
                    expected_revision=mapping.revision,
                    actor="provider",
                    action="propose_candidate",
                    payload=unsafe,
                    runtime=runtime,
                )
            proposed = submit_discovery_step_use_case(
                mapping.id,
                expected_revision=mapping.revision,
                actor="provider",
                action="propose_candidate",
                payload=_proposal(),
                runtime=runtime,
            ).run
            unsafe_manifest = _manifest()
            unsafe_manifest["pairs"] = [["AT", "Europe"]]
            with self.assertRaises(DiscoveryFailure) as unsafe_manifest_error:
                submit_discovery_step_use_case(
                    mapping.id,
                    expected_revision=proposed.revision,
                    actor="coding_agent",
                    action="register_mapping_manifest",
                    payload=unsafe_manifest,
                    runtime=runtime,
                )

        self.assertEqual(join.contract_version, "tarel.discovery-run.v0.1.experimental")
        self.assertEqual(roundtrip, join)
        self.assertEqual(mapping_step.exception.code, "invalid_discovery")
        self.assertEqual(same_field_error.exception.code, "invalid_discovery")
        self.assertEqual(unsafe_program.exception.code, "invalid_discovery")
        self.assertEqual(unsafe_manifest_error.exception.code, "invalid_discovery")

    def test_review_contract_rejects_non_human_review_and_supports_rejection(self) -> None:
        candidate = _candidate_contract()
        rejected = review_reference_mapping_candidate(
            candidate,
            decision="reject",
            reason="The mapping collapses two distinct target domains.",
        )
        payload = candidate.to_dict()
        payload["state"] = "reviewed"
        payload["review"] = {
            "decision": "approve",
            "reason": "A provider cannot approve evidence.",
            "source": "provider",
        }
        payload.pop("revision")
        with self.assertRaises(ReferenceMappingFailure) as non_human:
            ReferenceMappingCandidate.from_dict(payload)
        unsafe_payload = candidate.to_dict()
        unsafe_payload["pairs"] = [["AT", "Europe"]]
        with self.assertRaises(ReferenceMappingFailure) as unsafe_candidate:
            ReferenceMappingCandidate.from_dict(unsafe_payload)

        self.assertEqual(rejected.state, "rejected")
        self.assertEqual(rejected.review.source, "human")
        self.assertEqual(non_human.exception.code, "invalid_reference_mapping")
        self.assertEqual(unsafe_candidate.exception.code, "invalid_reference_mapping")


def _runtime(root: str) -> TarelRuntime:
    runtime = TarelRuntime.local(Path(root) / ".tarel")
    runtime.graph_store().save(_graph())
    return runtime


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
                    name="countries",
                    kind="table",
                    primary_key=("country_code",),
                    fields=(
                        CatalogField("country_code", 1, "TEXT", False),
                        CatalogField("country_name", 2, "TEXT", False),
                    ),
                ),
                CatalogObject(
                    namespace="main",
                    name="regions",
                    kind="table",
                    primary_key=("region_name",),
                    fields=(CatalogField("region_name", 1, "TEXT", False),),
                ),
            ),
        ),
    )


def _proposal() -> dict[str, object]:
    return {
        "candidate_id": "country-to-region",
        "parent_ids": [],
        "program": {
            "cardinality": "many_to_one",
            "kind": "reference_mapping",
            "source_field": "main.countries.country_code",
            "target_field": "main.regions.region_name",
        },
        "variation_operator": "provider_semantic_hypothesis",
    }


def _manifest() -> dict[str, object]:
    return {
        "candidate_id": "country-to-region",
        "mapping_count": 12,
        "mapping_manifest_hash": "d" * 64,
    }


def _observation(phase: str) -> dict[str, object]:
    return {
        "candidate_id": "country-to-region",
        "observation": {
            "dialect": "sqlite",
            "duration_ms": 4,
            "error_category": None,
            "evidence_level": "population_tested",
            "execution": {
                "artifact_hash": "b" * 64,
                "blocking_strategy": "exact_value",
                "blocking_version": "v1",
                "executor_id": "test.mapping-harness",
                "executor_version": "v1",
            },
            "id": f"mapping-{phase}",
            "metrics": {
                "basis": "population",
                "collision_count": 0,
                "collision_rate": 0.0,
                "confidence": 0.8,
                "counterexample_count": 0,
                "coverage": 0.8,
                "distinct_source_count": 8,
                "distinct_target_count": 4,
                "evaluated_count": 10,
                "matched_count": 8,
            },
            "phase": phase,
            "query_hash": ("a" if phase == "support" else "c") * 64,
            "row_limit": 100,
            "status": "succeeded",
            "truncated": False,
        },
    }


def _candidate_contract() -> ReferenceMappingCandidate:
    evidence = _observation("support")["observation"]
    challenge = _observation("challenge")["observation"]
    return ReferenceMappingCandidate.from_dict(
        {
            "cardinality": "many_to_one",
            "challenge_evidence": {
                "execution": challenge["execution"],
                "level": challenge["evidence_level"],
                "metrics": challenge["metrics"],
                "observation_id": challenge["id"],
                "phase": challenge["phase"],
                "query_hash": challenge["query_hash"],
            },
            "contract_version": "tarel.reference-mapping-candidate.v0.1.experimental",
            "graph": {"name": "warehouse", "revision": "f" * 64},
            "id": "mapping-candidate",
            "mapping_count": 12,
            "mapping_manifest_hash": "d" * 64,
            "provenance": {
                "discovery_candidate_id": "country-to-region",
                "producer": "provider",
                "promotion_reason": "Offer for review.",
                "run_id": "country-region-map",
                "run_revision": "e" * 64,
                "source_names": [],
            },
            "review": None,
            "source_field_id": "country-field",
            "state": "candidate",
            "support_evidence": {
                "execution": evidence["execution"],
                "level": evidence["evidence_level"],
                "metrics": evidence["metrics"],
                "observation_id": evidence["id"],
                "phase": evidence["phase"],
                "query_hash": evidence["query_hash"],
            },
            "target_field_id": "region-field",
        }
    )
