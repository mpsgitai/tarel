from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import redirect_stdout
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
    find_discovery_candidates_use_case,
    promote_discovery_candidates_use_case,
    start_discovery_run_use_case,
    submit_discovery_step_use_case,
)
from tarel.discovery.contracts import (
    DISCOVERY_CONTRACT_VERSION,
    DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION,
    DiscoveryFailure,
    DiscoveryObservation,
    DiscoveryRun,
)
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.revision import physical_graph_revision
from tarel.logical_joins.application import (
    find_logical_joins_use_case,
    load_logical_join_use_case,
    review_logical_join_use_case,
)
from tarel.logical_joins.contracts import LogicalJoin, LogicalJoinFailure
from tarel.object_families.application import (
    propose_object_family_use_case,
    review_object_family_use_case,
)
from tarel.object_families.contracts import FamilyAttribute
from tarel.reference_mapping.application import import_reference_mapping_candidate_use_case
from tarel.reference_mapping.contracts import (
    ReferenceMappingCandidate,
    ReferenceMappingEvidence,
    ReferenceMappingProvenance,
)
from tarel.runtime import TarelRuntime
from tarel.sdk import Tarel
from tarel.topology import (
    DerivationEvidence,
    DerivedRelation,
    EndpointRef,
    ExecutorProvenance,
    ExplodeStep,
    ExtractStep,
    Grain,
    OutputField,
    StepOutput,
    decide_derived_relation_use_case,
    new_logical_topology_document,
    save_logical_topology_use_case,
)
from tarel.topology.endpoint_contracts import LogicalEndpoint, LogicalEndpointFailure


class LogicalJoinTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.runtime = TarelRuntime.local(self.project / ".tarel")
        fields = (
            CatalogField("id", 1, "integer", False),
            CatalogField("amount", 2, "integer", False),
        )
        self.graph = build_graph_from_catalog(
            "commerce",
            CatalogResult(
                connector="test",
                source_type="database",
                catalog="Commerce",
                dialect="sqlite",
                objects=(
                    CatalogObject(
                        "sales",
                        "orders",
                        "table",
                        (
                            CatalogField("order_id", 1, "integer", False),
                            CatalogField("items_json", 2, "json", False),
                        ),
                    ),
                    CatalogObject("sales", "products", "table", fields),
                    CatalogObject("sales", "prices_01", "table", fields),
                    CatalogObject("sales", "prices_02", "table", fields),
                ),
            ),
        )
        self.runtime.graph_store().save(self.graph)
        self.family = propose_object_family_use_case(
            "commerce",
            "prices",
            name="prices",
            members=("sales.prices_01", "sales.prices_02"),
            grain=("id", "month"),
            attributes=(FamilyAttribute("month", "object_name", "prices_"),),
            runtime=self.runtime,
        )
        orders = self.object("sales.orders")
        item_field = self.field("sales.orders", "items_json")
        relation = DerivedRelation(
            id="items",
            name="order_items",
            source=EndpointRef("graph_object", orders.id),
            steps=(
                ExplodeStep(
                    "explode",
                    EndpointRef("graph_field", item_field.id),
                    "",
                    StepOutput("item", "json", False),
                ),
                ExtractStep(
                    "extract",
                    EndpointRef("step_output", "item"),
                    "/product_id",
                    StepOutput("product", "integer", False),
                ),
            ),
            output_schema=(
                OutputField(
                    "product",
                    "product_id",
                    "integer",
                    False,
                    "derived",
                    EndpointRef("step_output", "product"),
                ),
            ),
            grain=Grain(("product",)),
            evidence=(),
        )
        relation = replace(
            relation,
            evidence=(
                DerivationEvidence(
                    id="proposal",
                    level="proposed",
                    plan_revision=relation.plan_revision,
                    input_count=0,
                    output_count=0,
                    error_count=0,
                    input_manifest_sha256=None,
                    output_manifest_sha256=None,
                    truncated=False,
                    executor=ExecutorProvenance("fixture-author", "v1", "a" * 64),
                ),
            ),
        )
        self.topology = new_logical_topology_document(self.graph, (relation,))
        save_logical_topology_use_case(self.topology, runtime=self.runtime)

    def object(self, name):
        return next(item for item in self.graph.nodes if item.label == name)

    def field(self, object_name, field_name):
        return next(
            item
            for item in self.graph.nodes
            if item.type == "field"
            and item.metadata.get("object_id") == self.object(object_name).id
            and item.label == field_name
        )

    def physical(self, object_name="sales.products", field_name="id"):
        return LogicalEndpoint(
            "graph_field",
            self.object(object_name).id,
            self.field(object_name, field_name).id,
            physical_graph_revision(self.graph),
        )

    def derived(self):
        return LogicalEndpoint("derived_field", "items", "product", self.topology.revision)

    def program(self):
        return LogicalJoinProgram((self.derived(),), (self.physical(),))

    def step(self, run, action, payload, actor="coding_agent"):
        return submit_discovery_step_use_case(
            run.id,
            expected_revision=run.revision,
            actor=actor,
            action=action,
            payload=payload,
            runtime=self.runtime,
        ).run

    def selected(
        self,
        *,
        program=None,
        run_id="logical",
        with_execution=True,
        logical=True,
        observations=None,
    ):
        run = start_discovery_run_use_case(
            "join_discovery",
            graph_name="commerce",
            logical_endpoints=logical,
            run_id=run_id,
            runtime=self.runtime,
        ).run
        run = self.step(
            run,
            "propose_candidate",
            {
                "candidate_id": "join-v1",
                "parent_ids": [],
                "variation_operator": "initial",
                "program": (program or self.program()).to_dict(),
            },
        )
        for phase in ("support", "challenge"):
            observation = (
                observations[phase]
                if observations
                else _observation(phase, with_execution=with_execution)
            )
            run = self.step(
                run, "record_observation", {"candidate_id": "join-v1", "observation": observation}
            )
        run = self.step(
            run,
            "select_candidate",
            {"candidate_id": "join-v1", "reason": "Independent probes support this join."},
        )
        return self.step(run, "complete_run", {"reason": "Logical join ready for review."})

    def promote(self, run):
        return promote_discovery_candidates_use_case(
            run.id,
            candidate_ids=("join-v1",),
            reason="Read-only harness support and challenge.",
            runtime=self.runtime,
        )

    def approve_topology(self):
        self.topology = decide_derived_relation_use_case(
            "commerce",
            "items",
            decision="approve",
            reason="Declared schema reviewed.",
            expected_revision=self.topology.revision,
            runtime=self.runtime,
        )

    def test_logical_avo_roundtrip_promotion_does_not_create_a_physical_edge(self):
        baseline = self.runtime.graph_store().load("commerce").to_dict()
        run = self.selected()
        self.assertEqual(run.contract_version, DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION)
        self.assertEqual(DiscoveryRun.from_dict(run.to_dict()), run)
        result = self.promote(run)
        self.assertEqual(result.edges, ())
        self.assertEqual(len(result.logical_joins), 1)
        join = result.logical_joins[0]
        self.assertEqual(join.state, "candidate")
        self.assertEqual(join.observations, run.candidates[0].observations)
        self.assertEqual(self.runtime.graph_store().load("commerce").to_dict(), baseline)
        self.assertEqual(self.promote(run).logical_joins, result.logical_joins)
        self.assertEqual(load_logical_join_use_case(join.id, runtime=self.runtime), join)
        self.assertEqual(result.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(find_logical_joins_use_case("commerce", runtime=self.runtime), ())
        found = find_logical_joins_use_case(
            "commerce", mode="include_candidates", runtime=self.runtime
        )
        self.assertEqual(found[0].usage, "exploratory_only")
        self.assertNotIn("physical_object_ids", json.dumps(found[0].to_dict()))
        discovered = find_discovery_candidates_use_case(
            graph_name="commerce",
            query="items product",
            runtime=self.runtime,
        )
        self.assertEqual(discovered[0].candidate.id, "join-v1")
        self.assertIn("not a human-reviewed", discovered[0].to_dict()["warning"])

    def test_old_contract_and_non_join_runs_cannot_accept_logical_programs(self):
        with self.assertRaises(DiscoveryFailure) as failure:
            self.selected(logical=False)
        self.assertEqual(failure.exception.code, "unsupported_discovery")
        old = start_discovery_run_use_case(
            "join_discovery", graph_name="commerce", run_id="old", runtime=self.runtime
        ).run
        self.assertEqual(old.contract_version, DISCOVERY_CONTRACT_VERSION)
        self.assertNotIn("logical_endpoints", old.to_dict())
        self.assertEqual(DiscoveryRun.from_dict(old.to_dict()), old)
        with self.assertRaises(DiscoveryFailure):
            start_discovery_run_use_case(
                "entity_matching",
                graph_name="commerce",
                logical_endpoints=True,
                runtime=self.runtime,
            )

    def test_confirmed_requires_both_rule_review_and_reviewed_current_dependencies(self):
        join = self.promote(self.selected()).logical_joins[0]
        reviewed = review_logical_join_use_case(
            join.id,
            decision="approve",
            reason="Rule reviewed.",
            expected_revision=join.revision,
            runtime=self.runtime,
        )
        self.assertEqual(reviewed.state, "reviewed")
        self.assertEqual(find_logical_joins_use_case("commerce", runtime=self.runtime), ())
        found = find_logical_joins_use_case(
            "commerce", mode="include_candidates", runtime=self.runtime
        )
        self.assertEqual(found[0].usage, "exploratory_only")
        # Reviewing the dependency changes its revision; old pinned joins become stale.
        self.approve_topology()
        self.assertEqual(
            find_logical_joins_use_case(
                "commerce", mode="include_candidates", runtime=self.runtime
            ),
            (),
        )
        new = self.promote(self.selected(run_id="revalidated")).logical_joins[0]
        reviewed = review_logical_join_use_case(
            new.id,
            decision="approve",
            reason="New revision reviewed.",
            expected_revision=new.revision,
            runtime=self.runtime,
        )
        found = find_logical_joins_use_case("commerce", runtime=self.runtime)
        self.assertEqual(found[0].join, reviewed)
        self.assertEqual(found[0].usage, "confirmed")

    def test_exact_family_and_attribute_endpoints_support_composite_programs(self):
        family = self.family
        source = LogicalEndpoint("family_field", family.id, "id", family.revision)
        attribute = LogicalEndpoint("family_attribute", family.id, "month", family.revision)
        program = LogicalJoinProgram(
            (source, attribute), (self.physical(), self.physical(field_name="amount"))
        )
        run = self.selected(program=program)
        join = self.promote(run).logical_joins[0]
        self.assertEqual(len(join.program.source_endpoints), 2)
        found = find_logical_joins_use_case(
            "commerce", mode="include_candidates", endpoint=attribute, runtime=self.runtime
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0].endpoints[0].physical_object_ids), 2)
        review_object_family_use_case(
            "commerce",
            family.id,
            decision="approve",
            reason="Family reviewed.",
            expected_revision=family.revision,
            runtime=self.runtime,
        )
        self.assertEqual(
            find_logical_joins_use_case(
                "commerce", mode="include_candidates", runtime=self.runtime
            ),
            (),
        )

    def test_rejected_stale_and_malformed_logical_joins_fail_closed(self):
        join = self.promote(self.selected()).logical_joins[0]
        with self.assertRaises(LogicalJoinFailure):
            review_logical_join_use_case(
                join.id,
                decision="approve",
                reason="Review.",
                expected_revision="0" * 64,
                runtime=self.runtime,
            )
        rejected = review_logical_join_use_case(
            join.id,
            decision="reject",
            reason="Unsafe cardinality.",
            expected_revision=join.revision,
            runtime=self.runtime,
        )
        self.assertEqual(
            find_logical_joins_use_case(
                "commerce", mode="include_candidates", runtime=self.runtime
            ),
            (),
        )
        with self.assertRaises(LogicalJoinFailure):
            review_logical_join_use_case(
                join.id,
                decision="approve",
                reason="Change my mind.",
                expected_revision=rejected.revision,
                runtime=self.runtime,
            )
        for key, value in (
            ("raw_rows", ["PRIVATE"]),
            ("sql", "select private"),
            ("revision", "0" * 64),
        ):
            with self.subTest(key=key), self.assertRaises(LogicalJoinFailure):
                LogicalJoin.from_dict({**join.to_dict(), key: value})
        payload = join.to_dict()
        payload["review"] = {"source": "provider", "decision": "approve", "reason": "No."}
        payload["state"] = "reviewed"
        with self.assertRaises(LogicalJoinFailure):
            LogicalJoin.from_dict(payload)

    def test_logical_promotion_requires_execution_and_independent_challenge(self):
        run = self.selected(with_execution=False)
        with self.assertRaises(LogicalJoinFailure):
            self.promote(run)
        run = self.selected(run_id="valid")
        join = self.promote(run).logical_joins[0]
        payload = join.to_dict(include_revision=False)
        payload["observations"][1]["query_hash"] = payload["observations"][0]["query_hash"]
        with self.assertRaises(LogicalJoinFailure):
            LogicalJoin.from_dict(payload)

    def test_exact_lookup_preserves_confirmed_precedence_before_limit_and_filter(self):
        self.approve_topology()
        confirmed = self.promote(self.selected(run_id="reviewed")).logical_joins[0]
        confirmed = review_logical_join_use_case(
            confirmed.id,
            decision="approve",
            reason="Confirmed current dependencies.",
            expected_revision=confirmed.revision,
            runtime=self.runtime,
        )
        candidate = self.promote(self.selected(run_id="alternative")).logical_joins[0]
        self.assertEqual(
            find_logical_joins_use_case(
                "commerce",
                mode="confirmed_then_candidates",
                join_id=candidate.id,
                limit=1,
                runtime=self.runtime,
            ),
            (),
        )
        self.assertEqual(
            find_logical_joins_use_case(
                "commerce",
                mode="include_candidates",
                join_id=candidate.id,
                limit=1,
                runtime=self.runtime,
            )[0].join,
            candidate,
        )
        with self.assertRaises(LogicalJoinFailure) as failure:
            review_logical_join_use_case(
                candidate.id,
                decision="approve",
                reason="Would create conflicting reviews.",
                expected_revision=candidate.revision,
                runtime=self.runtime,
            )
        self.assertEqual(failure.exception.code, "logical_join_review_conflict")
        self.assertEqual(
            find_logical_joins_use_case(
                "commerce",
                join_id=confirmed.id,
                limit=1,
                runtime=self.runtime,
            )[0].join,
            confirmed,
        )

    def test_program_rejects_fuzzy_code_mixed_objects_and_unpinned_endpoints(self):
        original = self.program().to_dict()
        variants = (
            {**original, "comparison": "fuzzy"},
            {**original, "sql": "select private"},
            {**original, "source_endpoints": []},
            {**original, "source_endpoints": [self.derived().to_dict(), self.physical().to_dict()]},
        )
        for program in variants:
            with self.subTest(program=program), self.assertRaises(LogicalEndpointFailure):
                LogicalJoinProgram.from_dict(program)
        with self.assertRaises(LogicalEndpointFailure):
            LogicalJoinProgram((self.physical(),), (self.physical("sales.prices_01"),))
        stale = replace(self.derived(), revision="0" * 64)
        with self.assertRaises(LogicalEndpointFailure):
            self.selected(program=LogicalJoinProgram((stale,), (self.physical(),)))

    def test_reference_mapping_endpoint_preserves_mapping_identity_without_values(self):
        observations = [
            DiscoveryObservation.from_dict(_observation(phase))
            for phase in ("support", "challenge")
        ]
        evidence = [
            ReferenceMappingEvidence(
                item.phase,
                item.id,
                item.evidence_level,
                item.query_hash,
                item.metrics,
                item.execution,
            )
            for item in observations
        ]
        mapping = ReferenceMappingCandidate(
            id="reference-codes",
            graph_name="commerce",
            graph_revision=physical_graph_revision(self.graph),
            source_field_id=self.field("sales.products", "id").id,
            target_field_id=self.field("sales.prices_01", "id").id,
            cardinality="many_to_one",
            mapping_manifest_hash="f" * 64,
            mapping_count=2,
            support_evidence=evidence[0],
            challenge_evidence=evidence[1],
            provenance=ReferenceMappingProvenance(
                "mapping-run",
                "a" * 64,
                "mapping-candidate",
                "coding_agent",
                "Mapped privately.",
            ),
        )
        import_reference_mapping_candidate_use_case(mapping, runtime=self.runtime)
        endpoint = LogicalEndpoint(
            "reference_mapping", mapping.id, mapping.target_field_id, mapping.revision
        )
        program = LogicalJoinProgram((endpoint,), (self.physical("sales.prices_02"),))
        join = self.promote(self.selected(program=program)).logical_joins[0]
        found = find_logical_joins_use_case(
            "commerce", join_id=join.id, mode="include_candidates", runtime=self.runtime
        )
        self.assertEqual(found[0].usage, "exploratory_only")
        self.assertEqual(
            set(found[0].endpoints[0].physical_object_ids),
            {
                self.object("sales.products").id,
                self.object("sales.prices_01").id,
            },
        )
        self.assertNotIn("mapping_manifest_hash", json.dumps(join.to_dict()))
        self.assertNotIn("f" * 64, json.dumps(join.to_dict()))

    def test_provider_advisor_can_propose_logical_program_but_cannot_select_or_review_it(self):
        run = start_discovery_run_use_case(
            "join_discovery",
            graph_name="commerce",
            run_id="advisor",
            logical_endpoints=True,
            advisor_provider="local",
            runtime=self.runtime,
        ).run
        provider = Mock(name="Provider")
        provider.name, provider.default_model = "local", "test"
        provider.generate_structured.return_value = {
            "proposals": [
                {
                    "candidate_id": "advised",
                    "parent_ids": [],
                    "variation_operator": "initial",
                    "program": self.program().to_dict(),
                }
            ]
        }
        with patch("tarel.discovery.application.load_provider", return_value=provider):
            changed = advise_discovery_run_use_case(
                run.id, expected_revision=run.revision, count=1, runtime=self.runtime
            )
        self.assertEqual(changed.run.candidates[0].state, "proposed")
        schema = provider.generate_structured.call_args.args[0].schema
        self.assertIn("source_endpoints", json.dumps(schema))
        with self.assertRaises(DiscoveryFailure):
            self.step(
                changed.run,
                "select_candidate",
                {"candidate_id": "advised", "reason": "Trust me."},
                actor="provider",
            )

    def test_public_cli_sdk_workflow_and_real_sqlite_harness_use_only_aggregate_evidence(self):
        # The harness, not TAREL, privately executes the JSON explosion and join.
        with sqlite3.connect(":memory:") as database:
            database.executescript("""
                CREATE TABLE orders(id INTEGER, items_json TEXT);
                CREATE TABLE products(id INTEGER, private_label TEXT);
                INSERT INTO orders VALUES(1, '[{"product_id":10},{"product_id":20}]');
                INSERT INTO products VALUES(10,'PRIVATE-ALPHA'),(20,'PRIVATE-BETA');
                PRAGMA query_only=ON;
            """)
            support_sql = (
                "SELECT count(*) FROM orders,json_each(items_json) item JOIN products p "
                "ON p.id=json_extract(item.value,'$.product_id')"
            )
            challenge_sql = (
                "SELECT count(*) FROM orders,json_each(items_json) item LEFT JOIN products p "
                "ON p.id=json_extract(item.value,'$.product_id') WHERE p.id IS NULL"
            )
            matched = database.execute(support_sql).fetchone()[0]
            unmatched = database.execute(challenge_sql).fetchone()[0]
            self.assertEqual(matched, 2)
            self.assertEqual(unmatched, 0)
            observations = {}
            for phase, query in (("support", support_sql), ("challenge", challenge_sql)):
                observation = _observation(phase)
                observation["query_hash"] = hashlib.sha256(query.encode()).hexdigest()
                observation["metrics"].update(
                    {
                        "evaluated_count": matched + unmatched,
                        "matched_count": matched,
                        "coverage": matched / (matched + unmatched),
                        "counterexample_count": unmatched,
                    }
                )
                observation["execution"]["artifact_hash"] = hashlib.sha256(
                    json.dumps(
                        {"matched": matched, "unmatched": unmatched}, sort_keys=True
                    ).encode()
                ).hexdigest()
                observations[phase] = observation
        run = self.selected(observations=observations)
        result = self.promote(run)
        encoded = json.dumps(result.logical_joins[0].to_dict())
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("SELECT", encoded)
        self.assertNotIn("items_json", encoded)
        sdk = Tarel(self.runtime.root)
        self.assertEqual(
            sdk.logical_joins.load(result.logical_joins[0].id), result.logical_joins[0]
        )
        output = StringIO()
        previous = Path.cwd()
        try:
            os.chdir(self.project)
            with redirect_stdout(output):
                status = main(
                    [
                        "logical-join",
                        "find",
                        "commerce",
                        "--mode",
                        "include_candidates",
                        "--format",
                        "json",
                    ]
                )
        finally:
            os.chdir(previous)
        self.assertEqual(status, 0)
        self.assertEqual(
            json.loads(output.getvalue())["logical_joins"],
            [
                item.to_dict()
                for item in sdk.logical_joins.find("commerce", mode="include_candidates")
            ],
        )


def _observation(phase, *, with_execution=True):
    observation = {
        "id": phase,
        "phase": phase,
        "status": "succeeded",
        "evidence_level": "population_tested",
        "dialect": "sqlite",
        "query_hash": hashlib.sha256(phase.encode()).hexdigest(),
        "row_limit": 100,
        "truncated": False,
        "duration_ms": 2,
        "error_category": None,
        "metrics": {
            "basis": "source_distinct",
            "evaluated_count": 2,
            "matched_count": 2,
            "distinct_source_count": 2,
            "distinct_target_count": 2,
            "collision_count": 0,
            "counterexample_count": 0,
            "coverage": 1.0,
            "collision_rate": 0.0,
            "confidence": 0.9,
        },
    }
    if with_execution:
        observation["execution"] = {
            "executor_id": "private.sqlite-harness",
            "executor_version": "v1",
            "artifact_hash": hashlib.sha256((phase + "result").encode()).hexdigest(),
            "blocking_strategy": "full_scan_bounded",
            "blocking_version": "v1",
        }
    return observation
