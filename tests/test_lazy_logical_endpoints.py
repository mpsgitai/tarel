from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.expansion import ExpansionInput, ExpansionTarget
from tarel.graph.contracts import GraphAnnotation, GraphDocument, GraphFailure, GraphNode
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.object_bindings import ObjectValueBinding
from tarel.object_families import FamilyAttribute, ObjectFamilyFailure
from tarel.sdk import Tarel
from tarel.topology import save_logical_topology_use_case
from tarel.topology.endpoint_contracts import LogicalEndpoint, LogicalEndpointFailure
from tarel.topology.endpoints import (
    resolve_logical_endpoint_for_graph_use_case,
    resolve_logical_endpoint_use_case,
)
from tests.test_logical_topology import _document as _derived_document
from tests.test_logical_topology import _graph as _derived_graph
from tests.test_object_families import _graph
from tests.test_object_families_ui import _family as _large_family
from tests.test_object_families_ui import _graph as _large_graph
from tests.test_reference_mapping import _candidate_contract as _mapping_candidate
from tests.test_reference_mapping import _graph as _mapping_graph


class LazyLogicalEndpointTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.family = self.sdk.families.propose(
            "commerce", "monthly", name="monthly_sales",
            members=("sales.sales_2024_01", "sales.sales_2024_02"),
            grain=("month", "sale_id"),
            attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
        )
        self.source = next(node for node in self.graph.nodes if node.type == "field")
        self.source_endpoint = LogicalEndpoint(
            "graph_field", self.source.metadata["object_id"], self.source.id,
            physical_graph_revision(self.graph),
        )
        self.family_endpoint = LogicalEndpoint(
            "family_attribute", self.family.id, "month", self.family.revision
        )

    @contextmanager
    def _warm_only(self, *, field_object: str | None = None):
        self.sdk.graph.header(self.graph.name)
        original_node = GraphNode.from_dict
        original_open = Path.open

        def node(data):
            if data["type"] == "field":
                self.assertIsNotNone(field_object, "Family fields must stay unloaded")
                self.assertEqual(data["metadata"]["object_id"], field_object)
            return original_node(data)

        def open_without_graph(path, *args, **kwargs):
            self.assertNotEqual(path.name, "graph.json", "Canonical source read on warm path")
            return original_open(path, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch.object(FileGraphStore, "load", side_effect=AssertionError(
                "Full GraphStore.load on a warm selective endpoint"
            )))
            stack.enter_context(patch.object(GraphDocument, "from_dict", side_effect=AssertionError(
                "Full GraphDocument hydration on a warm selective endpoint"
            )))
            stack.enter_context(patch.object(GraphNode, "from_dict", side_effect=node))
            stack.enter_context(patch.object(Path, "open", open_without_graph))
            yield

    def _resolve(self, endpoint, *, graph=None):
        if graph is not None:
            return resolve_logical_endpoint_for_graph_use_case(
                graph, endpoint, mode="include_candidates", runtime=self.sdk.runtime
            )
        return resolve_logical_endpoint_use_case(
            self.graph.name, endpoint, mode="include_candidates", runtime=self.sdk.runtime
        )

    def _binding(self):
        return self.sdk.bindings.import_document(ObjectValueBinding(
            "month-routing", "commerce", self.source_endpoint, self.family_endpoint,
            "coding_agent", "test-run",
        ))

    def test_physical_endpoint_hydrates_only_requested_object_with_full_result_parity(self):
        expected = self._resolve(self.source_endpoint, graph=self.graph)
        parent = self.graph.node_by_id()[self.source_endpoint.object_id]
        self.assertEqual(expected.label, f"{parent.label}.{self.source.label}")
        with self._warm_only(field_object=self.source_endpoint.object_id):
            self.assertEqual(self._resolve(self.source_endpoint), expected)
            for changed, code in (
                (replace(self.source_endpoint, object_id="missing"), "logical_endpoint_not_found"),
                (replace(self.source_endpoint, field_id="missing"), "logical_endpoint_not_found"),
                (replace(self.source_endpoint, revision="0" * 64), "stale_logical_endpoint"),
            ):
                with self.subTest(code=code), self.assertRaises(LogicalEndpointFailure) as raised:
                    self._resolve(changed)
                self.assertEqual(raised.exception.code, code)

    def test_mapping_label_qualifies_target_and_reuses_supplied_graph_without_extra_io(self):
        graph = _mapping_graph()
        source = next(node for node in graph.nodes if node.label == "country_code")
        target = next(node for node in graph.nodes if node.label == "region_name")
        candidate = replace(
            _mapping_candidate(), graph_name=graph.name,
            graph_revision=physical_graph_revision(graph),
            source_field_id=source.id, target_field_id=target.id,
        )
        self.sdk.runtime.graph_store().save(graph)
        self.sdk.runtime.reference_mapping_store().save(candidate)
        endpoint = LogicalEndpoint("reference_mapping", candidate.id, target.id, candidate.revision)
        expected = resolve_logical_endpoint_use_case(
            graph.name, endpoint, mode="include_candidates", runtime=self.sdk.runtime
        )
        parent = graph.node_by_id()[target.metadata["object_id"]]
        self.assertEqual(expected.label, f"{parent.label}.{target.label}")
        with patch.object(FileGraphStore, "load", side_effect=AssertionError("extra graph load")):
            self.assertEqual(self._resolve(endpoint, graph=graph), expected)

    def test_two_thousand_family_members_validate_without_hydrating_any_field(self):
        self.graph = _large_graph(2000)
        family = _large_family(self.graph)
        self.sdk.runtime.graph_store().save(self.graph)
        self.sdk.runtime.object_family_store().save(family)
        endpoints = (
            LogicalEndpoint("family_field", family.id, "id", family.revision),
            LogicalEndpoint("family_attribute", family.id, "partition", family.revision),
        )
        expected = tuple(self._resolve(item, graph=self.graph) for item in endpoints)
        with self._warm_only():
            actual = tuple(self._resolve(item) for item in endpoints)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual[0].physical_object_ids), 2000)
        self.assertNotIn("physical_object_ids", json.dumps(actual[0].to_dict()))

    def test_binding_resolution_is_selective_and_private_input_never_persists(self):
        binding = self._binding()
        kwargs = {
            "expected_revision": binding.revision,
            "values": ("2024_01", "PRIVATE_UNKNOWN_SENTINEL"),
            "mode": "include_candidates",
        }
        expected = self.sdk.bindings.resolve("commerce", binding.id, **kwargs)
        with self._warm_only(field_object=self.source_endpoint.object_id):
            result = self.sdk.bindings.resolve("commerce", binding.id, **kwargs)
            scoped = self.sdk.bindings.resolve(
                "commerce", binding.id, allowed_object_ids=frozenset(), **kwargs
            )
        self.assertEqual(result, expected)
        self.assertEqual((result.matched_member_count, result.unmatched_input_count), (1, 1))
        self.assertEqual((scoped.matched_member_count, scoped.unmatched_input_count), (0, 2))
        self.assertNotIn("PRIVATE_", json.dumps(result.to_dict()))
        self._assert_no_private_material()

    def test_binding_context_expansion_is_selective_and_does_not_echo_handles_or_values(self):
        binding = self._binding()
        base = self.sdk.context.graph("commerce", "sales")
        target = ExpansionTarget(
            "object_binding", "commerce", binding.id, binding.revision, handle="PRIVATE_HANDLE"
        )
        options = {
            "mode": "include_candidates",
            "inputs": {"PRIVATE_HANDLE": ExpansionInput(
                "a" * 64, values=("2024_01", "PRIVATE_UNKNOWN_SENTINEL")
            )},
        }
        with self._warm_only(field_object=self.source_endpoint.object_id):
            result = self.sdk.context.expand(base, (target,), **options)
        self.assertEqual(result.omissions, ())
        resolution = result.items[0].metadata["resolution"]
        self.assertEqual((resolution["matched_member_count"], resolution["unmatched_input_count"]),
                         (1, 1))
        self.assertFalse(any(row[2] for row in result.base_validation))
        self.assertNotIn("PRIVATE_", json.dumps(result.to_dict()))
        self._assert_no_private_material()

    def test_all_affixes_and_every_member_schema_are_checked_before_endpoint_use(self):
        cases = (
            (replace(self.family, attributes=(FamilyAttribute(
                "month", "object_name", prefix="sales_2024_01"
            ),)), "object_family_attribute_mismatch"),
            (replace(self.family, member_ids=(self.family.member_ids[0], "missing")),
             "object_family_member_not_found"),
            (replace(self.family, schema=tuple(replace(item, data_type="text")
                                              for item in self.family.schema)),
             "object_family_schema_mismatch"),
        )
        for family, code in cases:
            with self.subTest(code=code):
                self.sdk.runtime.object_family_store().save(family)
                endpoint = replace(self.family_endpoint, revision=family.revision)
                with self.assertRaises(ObjectFamilyFailure) as eager:
                    self._resolve(endpoint, graph=self.graph)
                with self._warm_only(), self.assertRaises(ObjectFamilyFailure) as lazy:
                    self._resolve(endpoint)
                self.assertEqual(lazy.exception.code, eager.exception.code)
                self.assertEqual(lazy.exception.code, code)

    def test_incomplete_observed_family_schema_keeps_visible_error_code(self):
        member = self.family.member_ids[-1]
        field = next(node for node in self.graph.nodes
                     if node.type == "field" and node.metadata["object_id"] == member)
        self.graph = replace(self.graph, nodes=tuple(
            replace(node, metadata={**node.metadata, "nullable": None}) if node.id == field.id
            else node for node in self.graph.nodes
        ))
        family = replace(self.family, graph_revision=physical_graph_revision(self.graph))
        self.sdk.runtime.graph_store().save(self.graph)
        self.sdk.runtime.object_family_store().save(family)
        endpoint = replace(self.family_endpoint, revision=family.revision)
        with self._warm_only(), self.assertRaises(ObjectFamilyFailure) as raised:
            self._resolve(endpoint)
        self.assertEqual(raised.exception.code, "object_family_schema_unavailable")

    def test_annotation_change_keeps_physical_endpoint_and_cache_corruption_is_visible(self):
        self.sdk.graph.header("commerce")
        self.graph = replace(self.graph, nodes=tuple(
            replace(node, annotation=GraphAnnotation(description="Reviewed label"))
            if node.id == self.source.id else node for node in self.graph.nodes
        ))
        self.sdk.runtime.graph_store().save(self.graph)
        with self._warm_only(field_object=self.source_endpoint.object_id):
            self.assertEqual(self._resolve(self.source_endpoint).usage, "confirmed")
        cache = next(self.sdk.root.rglob("graph.selective.sqlite"))
        with cache.open("ab") as handle:
            handle.write(b"invalid-cache")
        with self.assertRaises(GraphFailure) as raised:
            self._resolve(self.source_endpoint)
        self.assertEqual(raised.exception.code, "invalid_graph_cache")

    def test_derived_resolution_reuses_supplied_graph_and_still_validates_it(self):
        graph = _derived_graph()
        self.sdk.runtime.graph_store().save(graph)
        document = save_logical_topology_use_case(
            _derived_document(graph), runtime=self.sdk.runtime
        )
        endpoint = LogicalEndpoint("derived_field", "order-items", "product-id", document.revision)
        with patch.object(FileGraphStore, "load", side_effect=AssertionError("nested load")):
            result = self._resolve(endpoint, graph=graph)
            self.assertEqual(result.label, "order_items.product_id")
            from tarel.topology.contracts import LogicalTopologyFailure

            with self.assertRaises(LogicalTopologyFailure) as raised:
                self._resolve(endpoint, graph=replace(graph, connector="changed"))
            self.assertEqual(raised.exception.code, "logical_topology_graph_revision_mismatch")

    def _assert_no_private_material(self):
        for path in self.sdk.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE_", path.read_bytes())
