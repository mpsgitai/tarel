from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from test_logical_topology import _relation
from test_reference_mapping import _candidate_contract

from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.context import ContextFailure
from tarel.context_output import ContextPacket, canonical_json
from tarel.context_packets import context_packet_from_dict, diff_context_packets
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.reference_mapping.contracts import ReferenceMappingCandidate, ReferenceMappingFailure
from tarel.runtime import TarelRuntime
from tarel.sdk import Tarel
from tarel.topology import LogicalTopologyFailure, new_logical_topology_document
from tarel.workspaces.core import create_workspace, define_system
from tarel.workspaces.projection import scoped_node_id


class LogicalContextHintTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project = Path(self.temporary_directory.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)

    def _save_hints(self, graph: GraphDocument | None = None) -> ReferenceMappingCandidate:
        graph = graph or self.graph
        self.sdk.runtime.logical_topology_store().save(
            new_logical_topology_document(graph, (_relation(graph),))
        )
        candidate = _mapping(graph)
        self.sdk.reference_mapping.import_candidate(candidate)
        return candidate

    def _workspace(self, *graphs: GraphDocument) -> None:
        graphs = graphs or (self.graph,)
        workspace = define_system(
            create_workspace("estate"),
            "commerce",
            graph_names=tuple(graph.name for graph in graphs),
            graphs={graph.name: graph for graph in graphs},
        )
        self.sdk.runtime.workspace_store().save(workspace)

    def _cli(self, args: list[str]) -> tuple[int, str, str]:
        previous = Path.cwd()
        output, errors = StringIO(), StringIO()
        try:
            os.chdir(self.project)
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(args)
        finally:
            os.chdir(previous)
        return status, output.getvalue(), errors.getvalue()

    def test_disabled_option_is_byte_identical_and_never_reads_sidecars(self) -> None:
        self._workspace()
        before = (
            self.sdk.context.graph("commerce", "orders"),
            self.sdk.context.prefix_graph("commerce"),
            self.sdk.context.workspace("estate", "orders"),
            self.sdk.context.prefix_workspace("estate"),
            self.sdk.grounding.context("orders", graph="commerce"),
        )
        self._save_hints()
        with (
            patch.object(TarelRuntime, "logical_topology_store", side_effect=AssertionError),
            patch.object(TarelRuntime, "reference_mapping_store", side_effect=AssertionError),
        ):
            after = (
                self.sdk.context.graph("commerce", "orders"),
                self.sdk.context.prefix_graph("commerce"),
                self.sdk.context.workspace("estate", "orders"),
                self.sdk.context.prefix_workspace("estate"),
                self.sdk.grounding.context("orders", graph="commerce"),
            )
        for original, current in zip(before, after, strict=True):
            self.assertEqual(original.to_dict(), current.to_dict())
            self.assertNotIn("logical_hints", json.dumps(current.to_dict()))
        self.assertEqual(before[0].canonical_json(), after[0].canonical_json())

    def test_selected_relation_has_schema_grain_and_safe_artifact_reference_only(self) -> None:
        self._save_hints()
        baseline = self.sdk.context.graph("commerce", "orders", seed_limit=1, max_objects=1)
        packet = self.sdk.context.graph(
            "commerce", "orders", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        hints = packet.stable_dict()["logical_hints"]["items"]

        self.assertEqual(packet.objects, baseline.objects)
        self.assertEqual(packet.joins, baseline.joins)
        self.assertEqual(len(hints), 1)
        hint = hints[0]
        self.assertEqual(hint["kind"], "derived_relation")
        self.assertEqual(hint["source_object_id"], packet.objects[0].id)
        self.assertEqual(hint["operations"], ["explode", "extract"])
        self.assertEqual(hint["grain"], ["order_id", "product_id"])
        self.assertEqual(
            hint["output_fields"],
            [
                {"name": "order_id", "data_type": "integer", "nullable": False},
                {"name": "product_id", "data_type": "string", "nullable": False},
            ],
        )
        document = self.sdk.topology.load("commerce")
        self.assertEqual(
            hint["artifact"],
            {"kind": "logical_topology", "graph": "commerce", "id": "order-items",
             "revision": document.revision},
        )
        self.assertEqual(hint["evidence"]["input_count"], 10)
        self.assertTrue(hint["evidence"]["truncated"])
        self.assertEqual(hint["usage"], "exploratory_only")
        self.assertTrue(hint["requires_runtime_validation"])

    def test_mapping_is_a_reference_not_a_join_or_implicit_table_expansion(self) -> None:
        candidate = self._save_hints()
        baseline = self.sdk.context.graph(
            "commerce", "countries", seed_limit=1, max_objects=1
        )
        packet = self.sdk.context.graph(
            "commerce", "countries", seed_limit=1, max_objects=1,
            logical_hints="confirmed_then_candidates",
        )
        hints = packet.stable_dict()["logical_hints"]["items"]

        self.assertEqual(packet.objects, baseline.objects)
        self.assertEqual(packet.joins, ())
        self.assertEqual(len(hints), 1)
        hint = hints[0]
        self.assertEqual(hint["kind"], "reference_mapping")
        self.assertEqual(hint["artifact"]["id"], candidate.id)
        self.assertEqual(hint["source"]["object_id"], packet.objects[0].id)
        self.assertNotEqual(hint["target"]["object_id"], packet.objects[0].id)
        self.assertEqual(hint["cardinality"], "many_to_one")
        self.assertEqual(hint["mapping_count"], 12)
        self.assertEqual(hint["support"]["metrics"]["coverage"], 0.8)
        self.assertEqual(hint["usage"], "exploratory_only")
        self.assertTrue(hint["requires_runtime_validation"])

    def test_unrelated_selected_object_gets_no_hints(self) -> None:
        self._save_hints()
        packet = self.sdk.context.graph(
            "commerce", "customers", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        self.assertEqual([item.label for item in packet.objects], ["sales.customers"])
        self.assertEqual(packet.stable_dict()["logical_hints"]["items"], [])

    def test_confirmed_policy_requires_review(self) -> None:
        candidate = self._save_hints()
        before = self.sdk.context.prefix_graph("commerce", logical_hints="confirmed_only")
        self.assertEqual(before.stable_dict()["logical_hints"]["items"], [])
        current = self.sdk.topology.load("commerce")
        self.sdk.topology.review(
            "commerce", "order-items", decision="approve", reason="Private review note.",
            expected_revision=current.revision,
        )
        self.sdk.reference_mapping.decide(
            candidate.id, decision="approve", reason="Private mapping review note.",
            expected_revision=candidate.revision,
        )
        after = self.sdk.context.prefix_graph("commerce", logical_hints="confirmed_only")
        hints = after.stable_dict()["logical_hints"]["items"]
        self.assertEqual(len(hints), 2)
        self.assertTrue(all(hint["usage"] == "confirmed" for hint in hints))
        self.assertTrue(all(not hint["requires_runtime_validation"] for hint in hints))

    def test_rejections_never_surface_under_any_policy(self) -> None:
        candidate = self._save_hints()
        current = self.sdk.topology.load("commerce")
        self.sdk.topology.review(
            "commerce", "order-items", decision="reject", reason="Counterexample.",
            expected_revision=current.revision,
        )
        self.sdk.reference_mapping.decide(
            candidate.id, decision="reject", reason="Counterexample.",
            expected_revision=candidate.revision,
        )
        for policy in ("confirmed_only", "confirmed_then_candidates", "include_candidates"):
            with self.subTest(policy=policy):
                rejected = self.sdk.context.prefix_graph("commerce", logical_hints=policy)
                self.assertEqual(rejected.stable_dict()["logical_hints"]["items"], [])
                self.assertEqual(
                    rejected.dynamic_dict()["logical_hints"]["omissions"]["rejected"], 2
                )

    def test_mapping_policy_reuses_reviewed_precedence_per_directed_pair(self) -> None:
        candidate = self._save_hints()
        alternative = replace(candidate, id="alternative-map", mapping_manifest_hash="9" * 64)
        self.sdk.reference_mapping.import_candidate(alternative)
        self.sdk.reference_mapping.decide(
            candidate.id, decision="approve", reason="This mapping was reviewed.",
            expected_revision=candidate.revision,
        )
        preferred = self.sdk.context.graph(
            "commerce", "countries", seed_limit=1, max_objects=1,
            logical_hints="confirmed_then_candidates",
        )
        all_active = self.sdk.context.graph(
            "commerce", "countries", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        self.assertEqual(
            [item["artifact"]["id"] for item in preferred.stable_dict()["logical_hints"]["items"]],
            [candidate.id],
        )
        self.assertEqual(
            {item["artifact"]["id"] for item in all_active.stable_dict()["logical_hints"]["items"]},
            {candidate.id, alternative.id},
        )

    def test_physical_drift_is_visible_but_annotation_changes_keep_hints_current(self) -> None:
        self._save_hints()
        annotated = replace(
            self.graph,
            nodes=tuple(
                replace(node, metadata={
                    **node.metadata, "annotation_review": {"state": "validated"},
                })
                if node.type == "table" else node
                for node in self.graph.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(annotated)
        current = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        self.assertEqual(len(current.stable_dict()["logical_hints"]["items"]), 2)
        drifted = replace(
            annotated,
            nodes=tuple(
                replace(node, metadata={**node.metadata, "data_type": "BIGINT"})
                if node.label == "order_id" else node
                for node in annotated.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(drifted)
        stale = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        self.assertEqual(stale.stable_dict()["logical_hints"]["items"], [])
        self.assertEqual(stale.dynamic_dict()["logical_hints"]["omissions"]["stale"], 2)
        self.assertTrue(stale.dynamic_dict()["logical_hints"]["warnings"])

    def test_namespace_does_not_leak_mapping_endpoints_outside_explicit_scope(self) -> None:
        graph = _graph(target_namespace="reference")
        self.sdk.runtime.graph_store().save(graph)
        self._save_hints(graph)
        packet = self.sdk.context.graph(
            "commerce", "countries", namespace="sales", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        self.assertEqual(packet.stable_dict()["logical_hints"]["items"], [])
        self.assertNotIn("reference.regions", packet.canonical_json())

    def test_namespace_filter_is_case_insensitive_for_mapping_hints(self) -> None:
        self._save_hints()
        lower = self.sdk.context.graph(
            "commerce", "countries", namespace="sales", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        upper = self.sdk.context.graph(
            "commerce", "countries", namespace="SALES", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        self.assertEqual(lower.objects, upper.objects)
        self.assertEqual(lower.stable_dict()["logical_hints"], upper.stable_dict()["logical_hints"])
        self.assertEqual(len(upper.stable_dict()["logical_hints"]["items"]), 1)

    def test_workspace_validates_original_graphs_and_scopes_every_endpoint_id(self) -> None:
        second = replace(self.graph, name="commerce-second")
        self.sdk.runtime.graph_store().save(second)
        self._save_hints()
        self._save_hints(second)
        self._workspace(self.graph, second)
        packet = self.sdk.context.prefix_workspace("estate", logical_hints="include_candidates")
        hints = packet.stable_dict()["logical_hints"]["items"]
        self.assertEqual(len(hints), 4)
        objects = {item.id for item in packet.objects}
        for hint in hints:
            graph_name = hint["artifact"]["graph"]
            self.assertIn(graph_name, {"commerce", "commerce-second"})
            if hint["kind"] == "derived_relation":
                original = next(
                    node.id for node in self.graph.nodes if node.label == "sales.orders"
                )
                self.assertEqual(hint["source_object_id"], scoped_node_id(graph_name, original))
                self.assertIn(hint["source_object_id"], objects)
            else:
                for endpoint in (hint["source"], hint["target"]):
                    self.assertTrue(endpoint["object_id"].startswith(f"scope::{graph_name}::"))
                    self.assertTrue(endpoint["field_id"].startswith(f"scope::{graph_name}::"))
                    self.assertIn(endpoint["object_id"], objects)
        selected = self.sdk.context.prefix_workspace(
            "estate", graphs=("commerce",), logical_hints="include_candidates"
        )
        self.assertEqual(len(selected.stable_dict()["logical_hints"]["items"]), 2)
        self.assertNotIn("commerce-second", json.dumps(selected.stable_dict()["logical_hints"]))

    def test_workspace_schema_scope_does_not_import_an_unselected_mapping_endpoint(self) -> None:
        graph = _graph(target_namespace="reference")
        self.sdk.runtime.graph_store().save(graph)
        self._save_hints(graph)
        self._workspace(graph)
        packet = self.sdk.context.workspace(
            "estate", "countries", schemas=("commerce:sales",),
            seed_limit=1, max_objects=1, logical_hints="include_candidates",
        )
        self.assertEqual(packet.stable_dict()["logical_hints"]["items"], [])
        self.assertNotIn("reference.regions", packet.canonical_json())

    def test_character_budget_removes_whole_hints_before_physical_fields(self) -> None:
        self._save_hints()
        full = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        budget = len(full.canonical_json()) - 50
        limited = self.sdk.context.prefix_graph(
            "commerce", logical_hints="include_candidates", max_characters=budget
        )
        hints = limited.stable_dict()["logical_hints"]["items"]
        self.assertLess(len(hints), 2)
        self.assertEqual(limited.objects, full.objects)
        self.assertEqual(limited.joins, full.joins)
        self.assertLessEqual(len(limited.canonical_json()), budget)
        self.assertEqual(
            limited.dynamic_dict()["logical_hints"]["omissions"]["character_budget"],
            2 - len(hints),
        )
        for item in hints:
            if item["kind"] == "derived_relation":
                self.assertEqual(len(item["output_fields"]), 2)
                self.assertEqual(len(item["grain"]), 2)

    def test_budget_retains_the_longest_complete_prefix_with_exact_counts(self) -> None:
        candidate = self._save_hints()
        for index in range(20):
            self.sdk.reference_mapping.import_candidate(
                replace(candidate, id=f"alternative-map-{index:02d}")
            )
        full = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        hints = full.logical_hints
        assert hints is not None
        total = len(hints.items)
        for budget in (5_000, 9_999, 10_000, 18_000, 24_000):
            with self.subTest(budget=budget):
                possible = []
                for count in range(total + 1):
                    omitted = total - count
                    oracle = _counted_packet(replace(
                        full, max_characters=budget,
                        logical_hints=replace(
                            hints, items=hints.items[:count],
                            omissions=(("character_budget", omitted),) if omitted else (),
                        ),
                    ))
                    if oracle.context_characters <= budget:
                        possible.append(oracle)
                self.assertTrue(possible, "Fixture should fit without dropping physical fields.")
                expected = possible[-1]
                actual = self.sdk.context.prefix_graph(
                    "commerce", logical_hints="include_candidates", max_characters=budget
                )
                self.assertEqual(actual.canonical_json(), expected.canonical_json())
                self.assertEqual(actual.context_characters, len(actual.canonical_json()))
                self.assertEqual(
                    actual.stable_characters, len(canonical_json(actual.stable_dict()))
                )
                self.assertEqual(actual.objects, full.objects)

    def test_bm25_graph_and_workspace_context_include_hints_without_new_index_entries(self) -> None:
        self._save_hints()
        self._workspace()
        index_path = self.sdk.runtime.retrieval_index().path("commerce")
        self.assertFalse(index_path.exists())
        for scoped, name in ((False, "commerce"), (True, "estate")):
            with self.subTest(workspace=scoped):
                compile_packet = self.sdk.context.workspace if scoped else self.sdk.context.graph
                baseline = compile_packet(name, "orders", mode="bm25")
                packet = compile_packet(
                    name, "orders", mode="bm25", logical_hints="include_candidates"
                )
                self.assertEqual(packet.objects, baseline.objects)
                self.assertEqual(packet.retrieval_mode, "bm25")
                self.assertEqual(len(packet.stable_dict()["logical_hints"]["items"]), 1)
                status, output, errors = self._cli(
                    ["context", name, "orders", "--mode", "bm25",
                     "--logical-hints", "include_candidates", "--format", "json"]
                    + (["--workspace"] if scoped else [])
                )
                self.assertEqual((status, errors), (0, ""))
                self.assertEqual(json.loads(output), packet.to_dict())
        self.assertFalse(index_path.exists())

    def test_hint_revision_changes_cache_and_roundtrips_without_false_current_claim(self) -> None:
        candidate = self._save_hints()
        before = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        self.sdk.reference_mapping.decide(
            candidate.id, decision="approve", reason="Checked by a human.",
            expected_revision=candidate.revision,
        )
        after = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        self.assertNotEqual(before.stable_hash, after.stable_hash)
        self.assertEqual(self.sdk.context.split(after).cache_key, after.stable_hash)
        self.assertIn('"logical_hints"', self.sdk.context.split(after).stable_json)
        left = self.project / "before.json"
        right = self.project / "after.json"
        left.write_text(before.canonical_json(), encoding="utf-8")
        right.write_text(after.canonical_json(), encoding="utf-8")
        self.assertFalse(self.sdk.context.diff(left, right).identical)
        self.assertTrue(self.sdk.context.diff(left, right).stable_changed)
        self.assertTrue(self.sdk.context.diff(left, right).logical_hints_changed)
        self.assertTrue(
            diff_context_packets(
                context_packet_from_dict(after.to_dict()), context_packet_from_dict(after.to_dict())
            ).identical
        )
        impact = self.sdk.context.impact(right, graph="commerce")
        self.assertEqual(impact.status, "unknown")
        self.assertFalse(impact.exact)
        payload = after.to_dict()
        payload["stable"]["logical_hints"]["items"][0]["state"] = "rejected"
        with self.assertRaisesRegex(ContextFailure, "identity hashes"):
            context_packet_from_dict(payload)

    def test_private_evidence_and_instructions_do_not_enter_hints_or_grounding(self) -> None:
        candidate = self._save_hints()
        self.sdk.reference_mapping.decide(
            candidate.id, decision="approve",
            reason="PRIVATE-REVIEW-NOTE SELECT secret FROM private_table",
            expected_revision=candidate.revision,
        )
        packet = self.sdk.context.prefix_graph("commerce", logical_hints="include_candidates")
        encoded = packet.canonical_json()
        hints = packet.stable_dict()["logical_hints"]
        forbidden = {
            "pointer", "steps", "mapping_manifest_hash", "query_hash", "executor",
            "execution", "promotion_reason", "review", "source_names", "rows", "values",
            "input_manifest_sha256", "output_manifest_sha256", "sql", "code",
        }
        self.assertTrue(forbidden.isdisjoint(_keys(hints)))
        for private in (
            "PRIVATE-REVIEW-NOTE", "SELECT secret", "/product_id", "test-harness",
            "test.mapping-harness", "a" * 64, "b" * 64, "c" * 64, "d" * 64,
        ):
            self.assertNotIn(private, encoded)
        grounding = self.sdk.grounding.context(
            "countries", graph="commerce", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        prompt = grounding.stable_prompt()
        self.assertIn("reference_mapping", prompt)
        self.assertNotIn("PRIVATE-REVIEW-NOTE", prompt)
        self.assertNotIn("test.mapping-harness", prompt)

    def test_invalid_policy_is_visible_even_without_selected_objects(self) -> None:
        for operation in (
            lambda: self.sdk.context.graph("commerce", "no_such_object", logical_hints="all"),
            lambda: self.sdk.context.prefix_graph("commerce", logical_hints="all"),
        ):
            with self.subTest(operation=operation), self.assertRaises(ContextFailure) as failure:
                operation()
            self.assertEqual(failure.exception.code, "invalid_logical_hint_mode")

    def test_corrupt_opted_in_topology_fails_visibly_not_as_empty_hints(self) -> None:
        path = self.sdk.runtime.logical_topology_store().save(
            new_logical_topology_document(self.graph, (_relation(self.graph),))
        )
        path.write_text('{"invalid": true}', encoding="utf-8")
        self.sdk.context.graph("commerce", "orders")
        with self.assertRaises(LogicalTopologyFailure):
            self.sdk.context.graph("commerce", "orders", logical_hints="include_candidates")
        status, _output, errors = self._cli(
            ["context", "commerce", "orders", "--logical-hints", "include_candidates"]
        )
        self.assertEqual(status, 2)
        self.assertIn("invalid_logical_topology", errors)

    def test_current_mapping_with_missing_endpoint_fails_but_stale_mapping_is_omitted(self) -> None:
        candidate = self._save_hints()
        broken = replace(candidate, id="broken-map", target_field_id="missing-field")
        store = self.sdk.runtime.reference_mapping_store()
        store.save(broken)
        with self.assertRaises(ReferenceMappingFailure) as failure:
            self.sdk.context.graph(
                "commerce", "countries", seed_limit=1, max_objects=1,
                logical_hints="include_candidates",
            )
        self.assertEqual(failure.exception.code, "reference_mapping_field_not_found")
        status, _output, errors = self._cli(
            ["context", "commerce", "countries", "--logical-hints", "include_candidates"]
        )
        self.assertEqual(status, 2)
        self.assertIn("reference_mapping_field_not_found", errors)
        store.save(replace(broken, graph_revision="f" * 64))
        stale = self.sdk.context.graph(
            "commerce", "countries", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        self.assertEqual(len(stale.stable_dict()["logical_hints"]["items"]), 1)
        self.assertEqual(stale.dynamic_dict()["logical_hints"]["omissions"]["stale"], 1)

    def test_cli_sdk_parity_for_graph_workspace_prefix_and_grounding(self) -> None:
        self._save_hints()
        self._workspace()
        calls = (
            (["context", "commerce", "orders"], self.sdk.context.graph("commerce", "orders",
                logical_hints="include_candidates")),
            (["context", "prefix", "commerce"], self.sdk.context.prefix_graph("commerce",
                logical_hints="include_candidates")),
            (["context", "estate", "orders", "--workspace"], self.sdk.context.workspace(
                "estate", "orders", logical_hints="include_candidates")),
            (["context", "prefix", "estate", "--workspace"], self.sdk.context.prefix_workspace(
                "estate", logical_hints="include_candidates")),
            (["grounding", "commerce", "orders"], self.sdk.grounding.context(
                "orders", graph="commerce", logical_hints="include_candidates")),
        )
        for args, expected in calls:
            with self.subTest(args=args):
                status, output, errors = self._cli(
                    args + ["--logical-hints", "include_candidates", "--format", "json"]
                )
                self.assertEqual((status, errors), (0, ""))
                self.assertEqual(json.loads(output), expected.to_dict())


def _graph(*, target_namespace: str = "sales") -> GraphDocument:
    return build_graph_from_catalog(
        "commerce",
        CatalogResult(
            connector="test", source_type="database", catalog="Commerce", dialect="sqlite",
            objects=(
                CatalogObject(
                    namespace="sales", name="orders", kind="table",
                    fields=(CatalogField("order_id", 1, "integer", False),
                            CatalogField("items_json", 2, "json", False)),
                    primary_key=("order_id",),
                ),
                CatalogObject(
                    namespace="sales", name="customers", kind="table",
                    fields=(CatalogField("name", 1, "string", False),),
                ),
                CatalogObject(
                    namespace="sales", name="countries", kind="table",
                    fields=(CatalogField("country_code", 1, "TEXT", False),
                            CatalogField("country_name", 2, "TEXT", False)),
                    primary_key=("country_code",),
                ),
                CatalogObject(
                    namespace=target_namespace, name="regions", kind="table",
                    fields=(CatalogField("region_name", 1, "TEXT", False),),
                    primary_key=("region_name",),
                ),
            ),
        ),
    )


def _mapping(graph: GraphDocument) -> ReferenceMappingCandidate:
    return replace(
        _candidate_contract(), id=f"{graph.name}-mapping", graph_name=graph.name,
        graph_revision=physical_graph_revision(graph),
        source_field_id=next(node.id for node in graph.nodes if node.label == "country_code"),
        target_field_id=next(node.id for node in graph.nodes if node.label == "region_name"),
    )


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def _counted_packet(packet: ContextPacket) -> ContextPacket:
    packet = replace(
        packet, stable_characters=len(canonical_json(packet.stable_dict())),
        context_characters=0,
    )
    for _ in range(10):
        count = len(packet.canonical_json())
        if count == packet.context_characters:
            return packet
        packet = replace(packet, context_characters=count)
    raise AssertionError("Fixture character counts did not converge.")
