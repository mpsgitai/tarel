from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.discovery.coverage import QueryLinkedEntityCoverage
from tarel.entity_resolution.contracts import EntityResolutionFailure
from tarel.graph.revision import physical_graph_revision
from tarel.sdk import Tarel
from tarel.semantics.contracts import SemanticExpression, SourceSnapshot
from tarel.semantics.ossie import read_ossie_import
from tarel.ui.optional_metadata import OptionalMetadataFailure, optional_object_metadata
from tests.test_discovery import (
    _complete_identity_inspection_run,
    _complete_selected_entity_run,
    _observation_payload,
    _query_linked_coverage,
    _self_entity_proposal,
)
from tests.test_discovery import _graph as discovery_graph
from tests.test_entity_resolution import _candidate, _graph
from tests.test_reference_mapping import _candidate_contract
from tests.test_semantic_imports import _graph as semantic_graph
from tests.test_semantic_imports import _source


class OptionalObjectMetadataTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.candidate = _candidate(self.graph)
        self.sdk.entity_resolution.import_candidate(self.candidate)
        self.objects = frozenset(node.id for node in self.graph.nodes if node.type == "table")
        self.selected = self.graph.node_by_id()[
            self.candidate.source_field_id
        ].metadata["object_id"]

    def metadata(self, kind="identity", **updates):
        options = {"allowed_object_ids": self.objects, "kind": kind, "runtime": self.sdk.runtime}
        options.update(updates)
        return optional_object_metadata(self.graph, self.selected, **options)

    def test_identity_edges_are_current_safe_and_do_not_mutate_graph(self):
        before = self.graph.to_dict()
        result = self.metadata()
        self.assertEqual(result["state"], "loaded")
        self.assertEqual(len(result["edges"]), 1)
        edge = result["edges"][0]
        self.assertEqual(edge["source"], f"music::{self.selected}")
        self.assertEqual(edge["metadata"]["usage"], "exploratory_only")
        self.assertTrue(edge["metadata"]["requires_runtime_validation"])
        self.assertEqual(result["artifact_revisions"], [
            {"id": self.candidate.id, "revision": self.candidate.revision},
        ])
        self.assertEqual(result["items"], [])
        self.assertEqual(self.sdk.runtime.graph_store().load(self.graph.name).to_dict(), before)

    def test_other_endpoint_outside_authorized_scope_is_not_disclosed(self):
        result = self.metadata(allowed_object_ids=frozenset({self.selected}))
        self.assertEqual(result["edges"], [])
        self.assertEqual(result["artifact_revisions"], [])
        for object_id in self.objects - {self.selected}:
            self.assertNotIn(json.dumps(object_id), json.dumps(result))
        with self.assertRaises(OptionalMetadataFailure) as raised:
            self.metadata(allowed_object_ids=self.objects - {self.selected})
        self.assertEqual(raised.exception.code, "optional_object_outside_scope")

    def test_reviewed_and_rejected_use_the_existing_retrieval_policy(self):
        reviewed = self.sdk.entity_resolution.decide(
            self.candidate.id, decision="approve", reason="Synthetic evidence review.",
        ).candidate
        result = self.metadata()
        self.assertEqual(result["edges"][0]["metadata"]["usage"], "confirmed")
        self.assertEqual(result["artifact_revisions"][0]["revision"], reviewed.revision)
        self.sdk.runtime.entity_resolution_store().save(self.candidate)
        self.sdk.entity_resolution.decide(self.candidate.id, decision="reject",
                                          reason="Synthetic rejection.")
        self.assertEqual(self.metadata()["edges"], [])

    def test_result_limit_is_deterministic_and_visible(self):
        for index in range(25):
            self.sdk.runtime.entity_resolution_store().save(replace(
                self.candidate, id=f"candidate-{index:02d}",
            ))
        result = self.metadata()
        self.assertEqual(len(result["edges"]), 20)
        self.assertEqual(len(result["artifact_revisions"]), 20)
        self.assertTrue(result["more_available"])
        self.assertIn({"code": "metadata_result_limit", "count": 6}, result["omissions"])
        self.assertEqual(result, self.metadata())
        for limit in (0, 21, True, "20"):
            with self.subTest(limit=limit), self.assertRaises(OptionalMetadataFailure):
                self.metadata(limit=limit)

    def test_corrupted_optional_candidate_fails_not_empty(self):
        self.sdk.runtime.entity_resolution_store().path(self.candidate.id).write_text("{bad")
        with self.assertRaises(EntityResolutionFailure) as raised:
            self.metadata()
        self.assertEqual(raised.exception.code, "invalid_entity_resolution")

    def test_mapping_edges_retain_policy_and_hide_private_manifest_details(self):
        mapping = replace(
            _candidate_contract(), graph_name=self.graph.name,
            graph_revision=physical_graph_revision(self.graph),
            source_field_id=self.candidate.source_field_id,
            target_field_id=self.candidate.target_field_id,
        )
        self.sdk.reference_mapping.import_candidate(mapping)
        result = self.metadata("mappings")
        self.assertEqual(len(result["edges"]), 1)
        metadata = result["edges"][0]["metadata"]
        self.assertEqual(metadata["usage"], "exploratory_only")
        self.assertEqual(metadata["mapping_count"], 12)
        self.assertEqual(metadata["revision"], mapping.revision)
        self.assertNotIn("mapping_manifest_hash", json.dumps(result))
        self.assertNotIn("query_hash", json.dumps(result))
        self.assertEqual(
            self.metadata("mappings", allowed_object_ids=frozenset({self.selected}))["edges"], [],
        )

    def test_full_entity_program_scope_checks_secondary_fields(self):
        graph = discovery_graph()
        self.sdk.runtime.graph_store().save(graph)
        run = _complete_selected_entity_run(self.sdk, run_id="program-scope", with_execution=True)
        candidate = self.sdk.discovery.promote(
            run.id, candidates=("entity-fuzzy-v1",), reason="Synthetic evidence.",
        ).entity_candidates[0]
        fields = {node.label: node.id for node in graph.nodes if node.type == "field"
                  and "orders" in node.id}
        selected = graph.node_by_id()[fields["order_id"]].metadata["object_id"]
        other = next(node.id for node in graph.nodes if node.type == "field"
                     and "customers" in node.id and node.label == "tenant_key")
        program = replace(candidate.program,
                          source_fields=(fields["customer_key"], other),
                          target_fields=(fields["order_id"], fields["tenant_key"]))
        candidate = replace(candidate, source_field_id=fields["customer_key"],
                            target_field_id=fields["order_id"], program=program)
        self.sdk.runtime.entity_resolution_store().save(candidate)
        narrow = optional_object_metadata(
            graph, selected, kind="identity", allowed_object_ids=frozenset({selected}),
            runtime=self.sdk.runtime,
        )
        self.assertEqual(narrow["edges"], [])
        self.assertNotIn(other, json.dumps(narrow))
        wide = optional_object_metadata(
            graph, selected, kind="identity", runtime=self.sdk.runtime,
            allowed_object_ids=frozenset(node.id for node in graph.nodes if node.type == "table"),
        )
        self.assertEqual(len(wide["edges"]), 1)

    def test_protected_alias_keys_rationale_and_sql_are_never_projected(self):
        graph = discovery_graph()
        self.sdk.runtime.graph_store().save(graph)
        self.sdk.source.configure("warehouse-source", connector="sqlite", graphs=(graph.name,),
                                  enrichment_permissions=("aggregates", "entity_aliases"))
        run = _complete_identity_inspection_run(self.sdk, run_id="identity-loop")
        candidate = self.sdk.discovery.promote(
            run.id, candidates=("same-customer-17",), reason="Synthetic evidence.",
        ).entity_candidates[0]
        group = replace(candidate.identity_group,
                        member_keys=("PRIVATE_KEY_A", "PRIVATE_KEY_B"),
                        rationale="SELECT PRIVATE_SQL_SENTINEL FROM private_table")
        candidate = replace(candidate, identity_group=group, provenance=replace(
            candidate.provenance, promotion_reason="PRIVATE_PROMOTION_REASON",
        ))
        self.sdk.runtime.entity_resolution_store().save(candidate)
        selected = candidate.self_match.object_id
        result = optional_object_metadata(
            graph, selected, kind="identity", allowed_object_ids=frozenset({selected}),
            runtime=self.sdk.runtime,
        )
        self.assertEqual(result["edges"][0]["metadata"]["identity_member_count"], 2)
        encoded = json.dumps(result)
        for forbidden in ("PRIVATE_KEY", "PRIVATE_SQL", "PRIVATE_PROMOTION", "member_keys",
                          "rationale", "mapping_groups"):
            self.assertNotIn(forbidden, encoded)

    def test_imports_expose_only_selected_bindings_without_source_or_sql(self):
        graph = semantic_graph()
        self.sdk.runtime.graph_store().save(graph)
        document = read_ossie_import("sales-model", graph=graph, content=_source(),
                                     media_type="application/json")
        model = document.models[0]
        dataset = model.datasets[0]
        field = replace(dataset.fields[0],
                        expressions=(SemanticExpression("ANSI_SQL", "PRIVATE_SQL_SENTINEL"),),
                        source_reference="/private/source/path")
        dataset = replace(dataset, fields=(field, *dataset.fields[1:]))
        other = replace(model.datasets[1], description="PRIVATE_OTHER_OBJECT")
        document = replace(document,
                           models=(replace(model, datasets=(dataset, other),
                                           description="PRIVATE_MODEL_DESCRIPTION"),),
                           snapshot=SourceSnapshot.from_content("PRIVATE_SNAPSHOT_ROWS",
                                                                 media_type="text/plain"))
        self.sdk.runtime.semantic_import_store().save(document)
        result = optional_object_metadata(
            graph, dataset.graph_node_id, kind="imports",
            allowed_object_ids=frozenset({dataset.graph_node_id}), runtime=self.sdk.runtime,
        )
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue(all(item["object_id"] == dataset.graph_node_id for item in result["items"]))
        self.assertEqual(result["artifact_revisions"][0]["id"], "sales-model")
        self.assertIn({"code": "model_wide_metadata_not_projected", "count": 1},
                      result["omissions"])
        for forbidden in ("PRIVATE_", "/private/", "original", "expressions", other.graph_node_id):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_oversized_semantic_description_is_omitted_as_a_whole(self):
        graph = semantic_graph()
        document = read_ossie_import("huge-model", graph=graph, content=_source(),
                                     media_type="application/json")
        model = document.models[0]
        dataset = replace(model.datasets[0], description="X" * (128 * 1024))
        document = replace(document, models=(replace(model, datasets=(dataset,)),))
        self.sdk.runtime.semantic_import_store().save(document)
        result = optional_object_metadata(
            graph, dataset.graph_node_id, kind="imports",
            allowed_object_ids=frozenset({dataset.graph_node_id}), runtime=self.sdk.runtime,
        )
        self.assertTrue(result["more_available"])
        self.assertIn({"code": "metadata_response_budget", "count": 1}, result["omissions"])
        self.assertLess(len(json.dumps(result).encode()), 128 * 1024)

    def test_query_coverage_requires_complete_single_object_candidate_attribution(self):
        graph = discovery_graph()
        self.sdk.runtime.graph_store().save(graph)
        run, candidate = _self_coverage_fixture(self.sdk)
        coverage = self.sdk.discovery.record_coverage(
            run.id, _coverage_payload(run, candidate),
        ).coverage
        selected = candidate.self_match.object_id
        result = optional_object_metadata(
            graph, selected, kind="coverage", allowed_object_ids=frozenset({selected}),
            runtime=self.sdk.runtime,
        )
        self.assertEqual(result["items"][0]["query_slice_coverage"], 1.0)
        self.assertLess(result["items"][0]["mapped_record_coverage"], 0.001)
        self.assertEqual(result["items"][0]["candidate_usage"], "exploratory_only")
        identity = optional_object_metadata(
            graph, selected, kind="identity", allowed_object_ids=frozenset({selected}),
            runtime=self.sdk.runtime,
        )
        self.assertNotIn("query_slice_coverage", json.dumps(identity))
        self.assertEqual(result["artifact_revisions"], [
            {"id": run.id, "revision": coverage.revision},
        ])
        other = next(node.id for node in graph.nodes
                     if node.type == "table" and node.id != selected)
        unrelated = optional_object_metadata(
            graph, other, kind="coverage", allowed_object_ids=frozenset({other}),
            runtime=self.sdk.runtime,
        )
        self.assertEqual(unrelated["items"], [])
        self.assertIn({"code": "coverage_object_scope_unverified", "count": 1},
                      unrelated["omissions"])
        self.assertNotIn(candidate.id, json.dumps(result))

    def test_cross_object_and_stale_query_coverage_are_explicit_omissions(self):
        graph = discovery_graph()
        self.sdk.runtime.graph_store().save(graph)
        run = _complete_selected_entity_run(self.sdk, run_id="cross-slice", with_execution=True,
                                            scope_mode="query_linked_slice")
        candidate = self.sdk.discovery.promote(
            run.id, candidates=("entity-fuzzy-v1",), reason="Synthetic support.",
        ).entity_candidates[0]
        coverage = self.sdk.discovery.record_coverage(
            run.id, _query_linked_coverage(run, candidate.id),
        ).coverage
        selected = graph.node_by_id()[candidate.source_field_id].metadata["object_id"]
        options = dict(kind="coverage", runtime=self.sdk.runtime,
                       allowed_object_ids=frozenset(node.id for node in graph.nodes
                                                   if node.type == "table"))
        result = optional_object_metadata(graph, selected, **options)
        self.assertEqual(result["items"], [])
        self.assertIn({"code": "coverage_object_scope_unverified", "count": 1}, result["omissions"])
        stale = replace(coverage, graph_revision="0" * 64)
        self.sdk.runtime.discovery_store().save_coverage(stale)
        result = optional_object_metadata(graph, selected, **options)
        self.assertIn({"code": "stale_query_linked_coverage", "count": 1}, result["omissions"])

    def test_discovery_only_coverage_refs_preserve_exploratory_usage(self):
        graph = discovery_graph()
        self.sdk.runtime.graph_store().save(graph)
        run, candidate = _self_coverage_fixture(self.sdk)
        coverage = self.sdk.discovery.record_coverage(
            run.id, _coverage_payload(run, candidate),
        ).coverage
        failed = replace(coverage.components[0], status="failed",
                         entity_candidate_refs=(), error_category="executor_error")
        self.sdk.runtime.discovery_store().save_coverage(replace(
            coverage, components=(failed,), completed_component_count=0,
            failed_component_count=1, query_slice_coverage=0.0,
        ))
        selected = candidate.self_match.object_id
        result = optional_object_metadata(
            graph, selected, kind="coverage", allowed_object_ids=frozenset({selected}),
            runtime=self.sdk.runtime,
        )
        self.assertEqual(result["items"][0]["candidate_usage"], "exploratory_only")
        self.assertEqual(result["items"][0]["query_slice_coverage"], 0.0)

    def test_invalid_kind_and_scope_types_fail_before_optional_reads(self):
        for updates in ({"kind": []}, {"kind": "unknown"},
                        {"allowed_object_ids": []}, {"allowed_object_ids": frozenset({1})}):
            with (
                self.subTest(updates=updates),
                self.assertRaises(OptionalMetadataFailure) as raised,
            ):
                self.metadata(**updates)
            self.assertEqual(raised.exception.code, "invalid_optional_metadata_request")

    def test_oversized_envelope_fails_without_echoing_long_identifiers(self):
        graph = replace(self.graph, name="PRIVATE_IDENTIFIER_" * 8192)
        with self.assertRaises(OptionalMetadataFailure) as raised:
            optional_object_metadata(
                graph, self.selected, kind="identity", allowed_object_ids=self.objects,
                runtime=self.sdk.runtime,
            )
        self.assertEqual(raised.exception.code, "optional_metadata_too_large")
        self.assertNotIn("PRIVATE_IDENTIFIER", str(raised.exception))


def _self_coverage_fixture(sdk):
    run = sdk.discovery.start("entity_matching", graph="warehouse", run_id="self-slice",
                              scope_mode="query_linked_slice").run
    run = sdk.discovery.submit(run.id, expected_revision=run.revision, action="propose_candidate",
                               payload=_self_entity_proposal("self-customer-v1")).run
    for phase in ("support", "challenge"):
        run = sdk.discovery.submit(
            run.id, expected_revision=run.revision, action="record_observation",
            payload=_observation_payload("self-customer-v1", f"self-{phase}", phase=phase,
                                         with_execution=True, basis="pairs"),
        ).run
    run = sdk.discovery.submit(run.id, expected_revision=run.revision, action="select_candidate",
                               payload={"candidate_id": "self-customer-v1", "reason": "Test."}).run
    run = sdk.discovery.submit(run.id, expected_revision=run.revision, action="complete_run",
                               payload={"reason": "Test."}).run
    candidate = sdk.discovery.promote(run.id, candidates=("self-customer-v1",),
                                      reason="Test.").entity_candidates[0]
    return run, candidate


def _coverage_payload(run, candidate):
    payload = _query_linked_coverage(run, candidate.id)
    payload["components"][0]["discovery_candidate_refs"] = ["self-customer-v1"]
    payload["components"][0]["observation_refs"] = ["self-challenge", "self-support"]
    payload["candidate_refs"] = sorted(["self-customer-v1", candidate.id])
    payload["observation_refs"] = ["self-challenge", "self-support"]
    return QueryLinkedEntityCoverage.from_dict(payload).to_dict()
