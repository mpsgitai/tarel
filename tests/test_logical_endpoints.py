from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.graph.revision import physical_graph_revision
from tarel.reference_mapping.contracts import review_reference_mapping_candidate
from tarel.runtime import TarelRuntime
from tarel.topology import decide_derived_relation_use_case, save_logical_topology_use_case
from tarel.topology.endpoint_contracts import LogicalEndpoint, LogicalEndpointFailure
from tarel.topology.endpoints import resolve_logical_endpoint_use_case
from tests.test_logical_topology import _document, _graph
from tests.test_object_families_ui import _family
from tests.test_object_families_ui import _graph as _family_graph
from tests.test_reference_mapping import _candidate_contract
from tests.test_reference_mapping import _graph as _mapping_graph


class LogicalEndpointTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = TarelRuntime.local(Path(self.temporary.name) / ".tarel")
        self.graph = _graph()
        self.runtime.graph_store().save(self.graph)

    def test_pure_contract_does_not_activate_application_or_runtime_on_import(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from tarel.topology.endpoint_contracts import LogicalEndpoint; "
                "assert 'tarel.runtime' not in sys.modules; "
                "assert 'tarel.topology.application' not in sys.modules",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_strict_roundtrip_rejects_code_values_and_unpinned_references(self):
        endpoint = LogicalEndpoint("derived_field", "items", "product", "a" * 64)
        self.assertEqual(LogicalEndpoint.from_dict(endpoint.to_dict()), endpoint)
        for change in (
            {"sql": "select *"},
            {"revision": None},
            {"kind": "python"},
            {"object_id": "bad\nref"},
            {"field_id": ""},
        ):
            with self.subTest(change=change), self.assertRaises(LogicalEndpointFailure):
                LogicalEndpoint.from_dict({**endpoint.to_dict(), **change})

    def test_physical_endpoint_validates_parent_and_preserves_observed_schema(self):
        field = next(node for node in self.graph.nodes if node.label == "order_id")
        endpoint = LogicalEndpoint(
            "graph_field",
            field.metadata["object_id"],
            field.id,
            physical_graph_revision(self.graph),
        )
        result = resolve_logical_endpoint_use_case(self.graph.name, endpoint, runtime=self.runtime)
        self.assertEqual(result.usage, "confirmed")
        self.assertEqual(result.data_type, "integer")
        self.assertEqual(result.physical_object_ids, (endpoint.object_id,))
        for changed in (replace(endpoint, object_id="wrong"), replace(endpoint, revision="0" * 64)):
            with self.assertRaises(LogicalEndpointFailure):
                resolve_logical_endpoint_use_case(self.graph.name, changed, runtime=self.runtime)

    def test_derived_endpoint_requires_current_artifact_and_explicit_exploratory_policy(self):
        document = save_logical_topology_use_case(_document(self.graph), runtime=self.runtime)
        endpoint = LogicalEndpoint("derived_field", "order-items", "product-id", document.revision)
        with self.assertRaises(LogicalEndpointFailure):
            resolve_logical_endpoint_use_case(self.graph.name, endpoint, runtime=self.runtime)
        result = resolve_logical_endpoint_use_case(
            self.graph.name,
            endpoint,
            mode="include_candidates",
            runtime=self.runtime,
        )
        self.assertEqual(result.usage, "exploratory_only")
        self.assertEqual(result.label, "order_items.product_id")
        reviewed = decide_derived_relation_use_case(
            self.graph.name,
            "order-items",
            decision="approve",
            reason="Metadata reviewed",
            expected_revision=document.revision,
            runtime=self.runtime,
        )
        with self.assertRaises(LogicalEndpointFailure) as raised:
            resolve_logical_endpoint_use_case(self.graph.name, endpoint, runtime=self.runtime)
        self.assertEqual(raised.exception.code, "stale_logical_endpoint")
        current = resolve_logical_endpoint_use_case(
            self.graph.name,
            replace(endpoint, revision=reviewed.revision),
            runtime=self.runtime,
        )
        self.assertEqual(current.usage, "confirmed")

    def test_family_fields_and_attributes_do_not_serialize_member_lists(self):
        graph = _family_graph(1000)
        family = _family(graph)
        self.runtime.graph_store().save(graph)
        self.runtime.object_family_store().save(family)
        for kind, name, data_type in (
            ("family_field", "id", "integer"),
            ("family_attribute", "partition", "string"),
        ):
            with self.subTest(kind=kind):
                endpoint = LogicalEndpoint(kind, family.id, name, family.revision)
                result = resolve_logical_endpoint_use_case(
                    graph.name, endpoint, runtime=self.runtime
                )
                self.assertEqual(result.data_type, data_type)
                self.assertEqual(len(result.physical_object_ids), 1000)
                serialized = json.dumps(result.to_dict())
                self.assertLess(len(serialized), 500)
                self.assertNotIn("physical_object_ids", serialized)
                self.assertNotIn(family.member_ids[0], serialized)
                self.assertNotIn(family.member_ids[0], repr(result))

    def test_rejected_family_is_never_an_eligible_endpoint(self):
        graph = _family_graph()
        family = _family(graph)
        from tarel.object_families.contracts import FamilyReview

        rejected = replace(family, state="rejected", review=FamilyReview("reject", "not related"))
        self.runtime.graph_store().save(graph)
        self.runtime.object_family_store().save(rejected)
        endpoint = LogicalEndpoint("family_field", family.id, "id", rejected.revision)
        for mode in ("confirmed_only", "include_candidates", "confirmed_then_candidates"):
            with self.subTest(mode=mode), self.assertRaises(LogicalEndpointFailure):
                resolve_logical_endpoint_use_case(
                    graph.name, endpoint, mode=mode, runtime=self.runtime
                )

    def test_mapping_endpoint_pins_target_graph_revision_and_review(self):
        graph = _mapping_graph()
        source = next(node for node in graph.nodes if node.label == "country_code")
        target = next(node for node in graph.nodes if node.label == "region_name")
        candidate = replace(
            _candidate_contract(),
            graph_name=graph.name,
            graph_revision=physical_graph_revision(graph),
            source_field_id=source.id,
            target_field_id=target.id,
        )
        self.runtime.graph_store().save(graph)
        self.runtime.reference_mapping_store().save(candidate)
        endpoint = LogicalEndpoint("reference_mapping", candidate.id, target.id, candidate.revision)
        with self.assertRaises(LogicalEndpointFailure):
            resolve_logical_endpoint_use_case(graph.name, endpoint, runtime=self.runtime)
        result = resolve_logical_endpoint_use_case(
            graph.name,
            endpoint,
            mode="include_candidates",
            runtime=self.runtime,
        )
        self.assertEqual(result.usage, "exploratory_only")
        self.assertEqual(
            set(result.physical_object_ids),
            {source.metadata["object_id"], target.metadata["object_id"]},
        )
        reviewed = review_reference_mapping_candidate(
            candidate, decision="approve", reason="Reviewed"
        )
        self.runtime.reference_mapping_store().save(reviewed)
        confirmed = resolve_logical_endpoint_use_case(
            graph.name,
            replace(endpoint, revision=reviewed.revision),
            runtime=self.runtime,
        )
        self.assertEqual(confirmed.usage, "confirmed")
        with self.assertRaises(LogicalEndpointFailure):
            resolve_logical_endpoint_use_case(
                graph.name,
                replace(endpoint, field_id=source.id, revision=reviewed.revision),
                runtime=self.runtime,
            )
