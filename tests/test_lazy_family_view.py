from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphDocument, GraphEdge, GraphNode
from tarel.graph.revision import graph_revision, physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.object_families.contracts import (
    FamilyAttribute,
    FamilyField,
    ObjectFamily,
    ObjectFamilyFailure,
    review_family,
)
from tarel.sdk import Tarel
from tarel.topology.contracts import LogicalTopologyDocument, LogicalTopologyFailure
from tarel.ui.lazy_family_view import try_lazy_family_graph_view_use_case
from tarel.ui.presentation import browser_graph, family_view_scope_revision
from tarel.ui.server import TarelUIBackend, UIConfig


class LazyFamilyViewTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = _graph(8)
        self.family = _family(self.graph, exclude_last=True)
        self.sdk.runtime.graph_store().save(self.graph)
        self.sdk.runtime.object_family_store().save(self.family)

    def test_lazy_payload_preserves_existing_projection_and_full_source_identity(self) -> None:
        """Only review counts are deferred; lazy loading must not claim an empty queue."""
        payload = self.sdk.view.graph("estate", family_mode="confirmed_only")
        storage = payload.pop("storage")
        expected = browser_graph(
            self.graph, family_mode="confirmed_only", object_families=(self.family,)
        )
        self.assertEqual(payload.pop("review_summary"), {
            "known": False, "total_objects": 8, "review_objects": None,
            "pending_tables": None, "pending_fields": None,
            "missing_tables": None, "missing_fields": None,
        })
        self.assertEqual(expected.pop("review_summary"), {
            "known": True, "total_objects": 8, "review_objects": 0,
            "pending_tables": 0, "pending_fields": 0,
            "missing_tables": 8, "missing_fields": 40,
        })
        self.assertEqual(payload, expected)
        self.assertTrue(storage["full_document_read"])
        self.assertEqual(payload["revision"], graph_revision(self.graph))
        self.assertEqual(
            payload["object_families"]["scope_revision"],
            family_view_scope_revision((self.graph,), ()),
        )
        tables = [item for item in payload["objects"] if item["type"] == "table"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]["fields"]), 5)

    def test_two_thousand_member_sdk_and_http_bootstrap_never_load_full_graph_warm(self) -> None:
        graph = _graph(2000)
        family = _family(graph)
        self.sdk.runtime.graph_store().save(graph)
        self.sdk.runtime.object_family_store().save(family)
        self.sdk.runtime.graph_store().header(graph.name)
        original = GraphNode.from_dict
        original_read = Path.read_text

        def only_metadata(data):
            self.assertNotEqual(data["type"], "field")
            return original(data)

        def no_source_read(path, *args, **kwargs):
            self.assertNotEqual(path.name, "graph.json")
            return original_read(path, *args, **kwargs)

        old = Path.cwd()
        try:
            os.chdir(self.project)
            with (
                patch.object(FileGraphStore, "load", side_effect=AssertionError("whole graph")),
                patch.object(GraphDocument, "from_dict", side_effect=AssertionError("whole parse")),
                patch.object(GraphNode, "from_dict", side_effect=only_metadata),
                patch.object(Path, "read_text", no_source_read),
            ):
                sdk_payload = self.sdk.view.graph(graph.name, family_mode="confirmed_only")
                backend = TarelUIBackend(UIConfig(graph=graph.name, family_mode="confirmed_only"))
                ui_payload = backend.bootstrap()
                page = backend.mutate(
                    "/api/families/members",
                    {
                        "graph": graph.name,
                        "family_id": family.id,
                        "revision": family.revision,
                        "mode": "confirmed_only",
                        "limit": 10,
                        "scope_revision": ui_payload["object_families"]["scope_revision"],
                    },
                )
        finally:
            os.chdir(old)
        for payload in (sdk_payload, ui_payload):
            self.assertEqual(len(payload["objects"]), 1)
            self.assertEqual(payload["object_families"]["collapsed_member_count"], 2000)
            self.assertFalse(payload["storage"]["full_document_read"])
            self.assertEqual(payload["storage"]["mode"], "selective_family_projection")
            self.assertLess(len(json.dumps(payload)), 13000)
            self.assertNotIn(family.member_ids[0], json.dumps(payload))
        self.assertEqual(len(page["members"]), 10)
        self.assertEqual(page["total_members"], 2000)

    def test_default_projection_does_not_touch_selective_store_or_add_storage_fields(self) -> None:
        with patch.object(FileGraphStore, "header", side_effect=AssertionError("opt-in only")):
            result = self.sdk.view.graph("estate")
        self.assertNotIn("storage", result)
        self.assertEqual(len(result["objects"]), 8)

    def test_actual_collapsed_relationship_counts_are_preserved_without_field_hydration(
        self,
    ) -> None:
        graph = replace(
            self.graph,
            edges=self.graph.edges
            + (
                GraphEdge(
                    "actual-join",
                    self.family.member_ids[0],
                    self.family.member_ids[1],
                    "foreign_key",
                ),
            ),
        )
        self.sdk.runtime.graph_store().save(graph)
        payload = self.sdk.view.graph("estate", family_mode="confirmed_only")
        family = next(item for item in payload["objects"] if item["type"] == "object_family")
        self.assertEqual(family["object_family"]["hidden_details"]["physical_relationships"], 1)
        self.assertEqual(payload["edges"], [])

    def test_rich_sidecars_fall_back_visibly_and_keep_validation_errors(self) -> None:
        path = self.sdk.runtime.logical_topology_store().path("estate")
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        attempt = try_lazy_family_graph_view_use_case(
            "estate", family_mode="confirmed_only", runtime=self.sdk.runtime
        )
        self.assertIsNone(attempt.payload)
        self.assertEqual(attempt.fallback_reason, "logical_topology_requires_full_projection")
        with self.assertRaises(LogicalTopologyFailure):
            self.sdk.view.graph("estate", family_mode="confirmed_only")

    def test_valid_rich_sidecars_report_full_projection_without_disappearing(self) -> None:
        self.sdk.runtime.logical_topology_store().save(
            LogicalTopologyDocument(
                graph_name="estate",
                graph_revision=physical_graph_revision(self.graph),
                derived_relations=(),
            )
        )
        payload = self.sdk.view.graph("estate", family_mode="confirmed_only")
        self.assertEqual(payload["storage"]["mode"], "full_projection")
        self.assertEqual(payload["storage"]["reason"], "logical_topology_requires_full_projection")
        self.assertTrue(payload["storage"]["full_document_read"])
        self.assertEqual(payload["objects"][0]["object_family"]["member_count"], 7)

    def test_focus_requests_select_the_explicit_full_projection_path(self) -> None:
        with patch.object(
            FileGraphStore, "load", side_effect=AssertionError("no eager work in selector")
        ):
            attempt = try_lazy_family_graph_view_use_case(
                "estate",
                family_mode="confirmed_only",
                has_focus=True,
                runtime=self.sdk.runtime,
            )
        self.assertIsNone(attempt.payload)
        self.assertEqual(attempt.fallback_reason, "focus_requires_full_projection")

    def test_stale_and_excluded_families_never_hide_physical_objects(self) -> None:
        self.sdk.runtime.object_family_store().save(
            replace(self.family, state="candidate", review=None)
        )
        payload = self.sdk.view.graph("estate", family_mode="confirmed_only")
        self.assertEqual(payload["storage"]["mode"], "full_projection")
        self.assertEqual(payload["storage"]["reason"], "no_eligible_families")
        self.assertEqual(len(payload["objects"]), 8)
        exploratory = self.sdk.view.graph("estate", family_mode="include_candidates")
        self.assertEqual(exploratory["objects"][0]["usage"], "exploratory_only")

    def test_corrupted_family_schema_or_affixes_are_not_trusted_from_cache(self) -> None:
        for altered in (
            replace(
                self.family,
                schema=(FamilyField("no_such_field", "int", False),),
                grain=("no_such_field",),
            ),
            replace(
                self.family,
                attributes=(FamilyAttribute("partition", "object_name", prefix="wrong_"),),
            ),
        ):
            with self.subTest(altered=altered):
                self.sdk.runtime.object_family_store().save(altered)
                with self.assertRaises(ObjectFamilyFailure):
                    self.sdk.view.graph("estate", family_mode="confirmed_only")


def _graph(count: int) -> GraphDocument:
    fields = tuple(
        CatalogField(
            name=f"value_{index}",
            data_type="int",
            nullable=False,
            position=index + 1,
            is_primary_key=False,
        )
        for index in range(5)
    )
    return build_graph_from_catalog(
        "estate",
        CatalogResult(
            connector="fixture",
            source_type="sql",
            catalog="prices",
            dialect="sqlite",
            objects=tuple(
                CatalogObject(
                    namespace="prices", name=f"prices_{index:05d}", kind="table", fields=fields
                )
                for index in range(count)
            ),
            relationships=(),
        ),
    )


def _family(graph: GraphDocument, *, exclude_last: bool = False) -> ObjectFamily:
    members = tuple(node.id for node in graph.nodes if node.type == "table")
    if exclude_last:
        members = members[:-1]
    family = ObjectFamily(
        graph_name=graph.name,
        graph_revision=physical_graph_revision(graph),
        id="prices",
        name="stock_prices",
        member_ids=members,
        schema=tuple(FamilyField(f"value_{index}", "int", False) for index in range(5)),
        grain=("value_0",),
        attributes=(),
        producer="fixture",
    )
    return review_family(family, decision="approve", reason="Reviewed synthetic schema.")
