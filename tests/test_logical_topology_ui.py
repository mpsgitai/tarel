from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.revision import physical_graph_revision
from tarel.reference_mapping.contracts import (
    ReferenceMappingCandidate,
    ReferenceMappingMatch,
    review_reference_mapping_candidate,
)
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
    new_logical_topology_document,
    review_derived_relation,
)
from tarel.ui.presentation import browser_graph, browser_workspace
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceSystem
from tarel.workspaces.scope import (
    ResolvedScope,
    ResolvedScopeObject,
    ScopeSelection,
)


class LogicalTopologyUIPresentationTests(TestCase):
    def test_workspace_scope_keeps_source_derivation_but_hides_partial_mapping(self) -> None:
        graph = _graph()
        orders = next(node for node in graph.nodes if node.label == "sales.orders")
        workspace = WorkspaceDocument(
            name="commerce-workspace",
            systems=(WorkspaceSystem(name="commerce", graphs=(graph.name,)),),
        )
        scope = ResolvedScope(
            workspace=workspace.name,
            selection=ScopeSelection(),
            graph_names=(graph.name,),
            objects=(
                ResolvedScopeObject(
                    graph=graph.name,
                    system="commerce",
                    area=None,
                    namespace="sales",
                    object_id=orders.id,
                    label=orders.label,
                    type=orders.type,
                    zones=(),
                ),
            ),
            scope_hash="0" * 64,
        )

        payload = browser_workspace(
            (graph,),
            scope,
            workspace=workspace,
            logical_topologies=(_reviewed_topology(graph),),
            reference_mapping_matches=(_reviewed_mapping(graph),),
        )

        self.assertEqual(
            [item["type"] for item in payload["objects"]],
            ["table", "derived_relation"],
        )
        self.assertEqual(
            [edge["type"] for edge in payload["edges"]],
            ["derives"],
        )

    def test_unreviewed_logical_objects_remain_exploratory(self) -> None:
        graph = _graph()
        reviewed_topology = _reviewed_topology(graph)
        candidate_topology = replace(
            reviewed_topology,
            derived_relations=(
                replace(
                    reviewed_topology.derived_relations[0],
                    state="candidate",
                    review=None,
                ),
            ),
        )
        reviewed_mapping = _reviewed_mapping(graph)
        candidate_mapping = replace(
            reviewed_mapping,
            candidate=replace(
                reviewed_mapping.candidate,
                state="candidate",
                review=None,
            ),
        )

        payload = browser_graph(
            graph,
            logical_topologies=(candidate_topology,),
            reference_mapping_matches=(candidate_mapping,),
        )

        derived = next(
            item for item in payload["objects"] if item["type"] == "derived_relation"
        )
        logical = derived["logical_topology"]
        mapping = next(
            edge for edge in payload["edges"] if edge["type"] == "reference_mapping"
        )["metadata"]
        self.assertEqual(logical["usage"], "exploratory_only")
        self.assertTrue(logical["requires_runtime_validation"])
        self.assertFalse(logical["usable"])
        self.assertEqual(mapping["usage"], "exploratory_only")
        self.assertTrue(mapping["requires_runtime_validation"])
        self.assertFalse(mapping["usable"])

    def test_projection_is_logical_safe_and_does_not_mutate_the_graph(self) -> None:
        graph = _graph()
        topology = _reviewed_topology(graph)
        mapping = _reviewed_mapping(graph)
        before = graph.to_dict()

        payload = browser_graph(
            graph,
            logical_topologies=(topology,),
            reference_mapping_matches=(mapping,),
        )

        self.assertEqual(graph.to_dict(), before)
        derived = next(
            item for item in payload["objects"] if item["type"] == "derived_relation"
        )
        self.assertEqual(derived["name"], "order_items")
        self.assertEqual(derived["state"], "reviewed")
        self.assertEqual(derived["usage"], "confirmed")
        self.assertEqual(derived["primary_key"], ["order_id", "product_id"])
        self.assertEqual(
            derived["logical_topology"]["step_kinds"], ["explode", "extract"]
        )
        self.assertEqual(
            [field["kind"] for field in derived["fields"]],
            ["passthrough", "derived"],
        )

        derivation = next(edge for edge in payload["edges"] if edge["type"] == "derives")
        self.assertEqual(derivation["target"], derived["id"])
        reference = next(
            edge for edge in payload["edges"] if edge["type"] == "reference_mapping"
        )
        self.assertEqual(reference["metadata"]["state"], "reviewed")
        self.assertEqual(reference["metadata"]["usage"], "confirmed")
        self.assertEqual(reference["metadata"]["mapping_count"], 12)
        self.assertEqual(reference["metadata"]["support"]["coverage"], 0.8)
        self.assertEqual(reference["metadata"]["challenge"]["counterexample_count"], 1)
        self.assertTrue(all(item["type"] in {"table", "view"} for item in payload["review"]))

        serialized = json.dumps(payload, sort_keys=True)
        for private_value in (
            "/private-array",
            "/PRIVATE_PRODUCT_KEY",
            "PRIVATE_TOPOLOGY_REVIEW",
            "PRIVATE_MAPPING_REVIEW",
            "PRIVATE_PROMOTION_REASON",
            "PRIVATE_SOURCE_NAME",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            "e" * 64,
            "f" * 64,
            "1" * 64,
            "2" * 64,
        ):
            self.assertNotIn(private_value, serialized)
        self.assertTrue(
            {
                "artifact_hash",
                "implementation_sha256",
                "input_manifest_sha256",
                "mapping_manifest_hash",
                "output_manifest_sha256",
                "pointer",
                "promotion_reason",
                "query_hash",
                "reason",
                "source_names",
            }.isdisjoint(_keys(payload))
        )

    def test_assets_present_logical_nodes_and_reference_mapping_evidence(self) -> None:
        static = Path(__file__).parents[1] / "src/tarel/ui/static"
        application = (static / "app.js").read_text(encoding="utf-8")
        styles = (static / "styles.css").read_text(encoding="utf-8")

        for marker in (
            "renderDerivedRelationInspector",
            "renderLogicalTopologyNotices",
            "referenceMappingCards",
            'node[type = "derived_relation"]',
            'edge[type = "reference_mapping"]',
            "mapping values remain private",
        ):
            self.assertIn(marker, application)
        for marker in (
            ".logical-step-chain",
            ".logical-field-card",
            ".reference-mapping-card",
            ".topology-notices",
        ):
            self.assertIn(marker, styles)


def _reviewed_topology(graph):
    orders = next(node for node in graph.nodes if node.label == "sales.orders")
    fields = {
        node.label: node
        for node in graph.nodes
        if node.type == "field" and node.metadata.get("object_id") == orders.id
    }
    relation = DerivedRelation(
        id="order-items",
        name="order_items",
        source=EndpointRef("graph_object", orders.id),
        steps=(
            ExplodeStep(
                id="explode-items",
                input=EndpointRef("graph_field", fields["items_json"].id),
                pointer="/private-array",
                output=StepOutput("item", "json", False),
            ),
            ExtractStep(
                id="extract-product-id",
                input=EndpointRef("step_output", "item"),
                pointer="/PRIVATE_PRODUCT_KEY",
                output=StepOutput("product-id-value", "string", False),
            ),
        ),
        output_schema=(
            OutputField(
                id="order-id",
                name="order_id",
                data_type="integer",
                nullable=False,
                kind="passthrough",
                source=EndpointRef("graph_field", fields["order_id"].id),
            ),
            OutputField(
                id="product-id",
                name="product_id",
                data_type="string",
                nullable=False,
                kind="derived",
                source=EndpointRef("step_output", "product-id-value"),
            ),
        ),
        grain=Grain(("order-id", "product-id")),
        evidence=(),
    )
    relation = replace(
        relation,
        evidence=(
            DerivationEvidence(
                id="bounded-run",
                level="sample_tested",
                plan_revision=relation.plan_revision,
                input_count=10,
                output_count=12,
                error_count=0,
                input_manifest_sha256="a" * 64,
                output_manifest_sha256="b" * 64,
                truncated=True,
                executor=ExecutorProvenance(
                    name="readonly-harness",
                    version="v1",
                    implementation_sha256="c" * 64,
                ),
            ),
        ),
    )
    relation = review_derived_relation(
        relation,
        decision="approve",
        reason="PRIVATE_TOPOLOGY_REVIEW",
    )
    return new_logical_topology_document(graph, (relation,))


def _reviewed_mapping(graph) -> ReferenceMappingMatch:
    source = next(node for node in graph.nodes if node.label == "status_code")
    target = next(
        node
        for node in graph.nodes
        if node.label == "code"
        and graph.node_by_id()[str(node.metadata["object_id"])].label
        == "reference.statuses"
    )
    metrics = {
        "basis": "population",
        "collision_count": 0,
        "collision_rate": 0.0,
        "confidence": 0.9,
        "counterexample_count": 0,
        "coverage": 0.8,
        "distinct_source_count": 8,
        "distinct_target_count": 4,
        "evaluated_count": 10,
        "matched_count": 8,
    }
    candidate = ReferenceMappingCandidate.from_dict(
        {
            "cardinality": "many_to_one",
            "challenge_evidence": _mapping_evidence(
                "challenge", metrics | {"counterexample_count": 1}, "f", "2"
            ),
            "contract_version": "tarel.reference-mapping-candidate.v0.1.experimental",
            "graph": {"name": graph.name, "revision": physical_graph_revision(graph)},
            "id": "status-reference-map",
            "mapping_count": 12,
            "mapping_manifest_hash": "d" * 64,
            "provenance": {
                "discovery_candidate_id": "status-reference-map",
                "producer": "provider",
                "promotion_reason": "PRIVATE_PROMOTION_REASON",
                "run_id": "mapping-run",
                "run_revision": "3" * 64,
                "source_names": ["PRIVATE_SOURCE_NAME"],
            },
            "review": None,
            "source_field_id": source.id,
            "state": "candidate",
            "support_evidence": _mapping_evidence("support", metrics, "e", "1"),
            "target_field_id": target.id,
        }
    )
    candidate = review_reference_mapping_candidate(
        candidate,
        decision="approve",
        reason="PRIVATE_MAPPING_REVIEW",
    )
    return ReferenceMappingMatch(
        candidate=candidate,
        source_reference="sales.orders.status_code",
        target_reference="reference.statuses.code",
    )


def _mapping_evidence(
    phase: str,
    metrics: dict[str, object],
    query_hash_character: str,
    artifact_hash_character: str,
) -> dict[str, object]:
    return {
        "execution": {
            "artifact_hash": artifact_hash_character * 64,
            "blocking_strategy": "exact_value",
            "blocking_version": "v1",
            "executor_id": "mapping-harness",
            "executor_version": "v1",
        },
        "level": "population_tested",
        "metrics": metrics,
        "observation_id": f"{phase}-observation",
        "phase": phase,
        "query_hash": query_hash_character * 64,
    }


def _graph():
    return build_graph_from_catalog(
        "commerce",
        CatalogResult(
            connector="test",
            source_type="database",
            catalog="Commerce",
            dialect="sqlite",
            objects=(
                CatalogObject(
                    namespace="sales",
                    name="orders",
                    kind="table",
                    fields=(
                        CatalogField("order_id", 1, "integer", False),
                        CatalogField("items_json", 2, "json", False),
                        CatalogField("status_code", 3, "string", False),
                    ),
                    primary_key=("order_id",),
                ),
                CatalogObject(
                    namespace="reference",
                    name="statuses",
                    kind="table",
                    fields=(
                        CatalogField("code", 1, "string", False),
                        CatalogField("label", 2, "string", False),
                    ),
                    primary_key=("code",),
                ),
            ),
        ),
    )


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for item in value.values()
            for key in _keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()
