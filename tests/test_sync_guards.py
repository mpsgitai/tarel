"""Scope changes, deletion versus withdrawal, dangling references and recorded observations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tarel.connectors.contracts import (
    CatalogField,
    CatalogObject,
    CatalogRelationship,
    CatalogResult,
)
from tarel.errors import TarelError
from tarel.graph.application import refresh_graph_use_case
from tarel.graph.build import build_graph_from_catalog, object_node_id
from tarel.graph.revision import graph_revision
from tarel.sync.contracts import SyncFailure
from tarel.workspaces.application import (
    load_workspace_scope,
    show_workspace_zone_use_case,
)
from tarel.workspaces.contracts import WorkspaceFailure
from tarel.workspaces.projection import project_workspace_scope
from tests.test_sync_file_path import HUMAN, OBSERVED, ORDERS, _catalog, _SyncCase

CUSTOMERS = object_node_id("Shop", "dbo", "customers")
SALARIES = object_node_id("Shop", "hr", "salaries")


class ScopeChangeTests(_SyncCase):
    def widen_stream(self) -> None:
        self.site.sync.update_stream("erp-main", namespaces=("dbo", "hr"))

    def test_shrinking_the_scope_withdraws_and_does_not_claim_deletion(self) -> None:
        self.widen_stream()
        self.apply(self.publish())
        self.assertIn(SALARIES, self.central_graph().node_by_id())

        self.site.sync.update_stream("erp-main", namespaces=("dbo",))
        result = self.apply(self.publish())

        self.assertEqual(result.plan.objects_withdrawn, ("hr.salaries",))
        self.assertEqual(result.plan.objects_deleted, ())
        self.assertEqual(result.plan.scope_change["namespaces_removed"], ["hr"])
        self.assertIn("prune", result.plan.warnings[-1])
        self.assertNotIn(SALARIES, self.central_graph().node_by_id())
        removal = self.central.sync.status()[0].removals[0]
        self.assertEqual((removal["object_id"], removal["reason"]), (SALARIES, "withdrawn"))

    def test_deletion_inside_an_unchanged_scope_is_a_source_deletion(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"))

        result = self.apply(self.publish())

        self.assertEqual(result.plan.objects_deleted, ("dbo.customers",))
        self.assertEqual(result.plan.objects_withdrawn, ())
        self.assertIsNone(result.plan.scope_change)
        self.assertEqual(self.central.sync.status()[0].removals[0]["reason"], "source_deleted")

    def test_widening_is_visible_in_the_plan(self) -> None:
        self.apply(self.publish())
        self.widen_stream()

        plan = self.central.sync.plan(self.publish(), allow_unsigned_dev=True)

        self.assertEqual(plan.scope_change["namespaces_added"], ["hr"])
        self.assertEqual(plan.scope_change["to_version"], 2)
        self.assertEqual(plan.objects_added, ("hr.salaries",))

    def test_scope_changed_without_a_new_version_is_refused(self) -> None:
        self.apply(self.publish())
        store = self.site.runtime.sync_store()
        stream = store.publisher_stream("erp-main")
        store.save_publisher_stream(
            replace(stream, scope=replace(stream.scope, namespaces=("dbo", "hr")))
        )

        self.assert_rejected("publication_conflict", self.publish())

    def test_older_profile_version_is_refused_even_with_a_higher_sequence(self) -> None:
        self.widen_stream()
        self.apply(self.publish())
        store = self.site.runtime.sync_store()
        stream = store.publisher_stream("erp-main")
        store.save_publisher_stream(replace(stream, profile_version=1))

        self.assert_rejected("publication_conflict", self.publish())

    def test_updating_to_the_same_scope_changes_nothing(self) -> None:
        stream = self.site.sync.update_stream("erp-main", namespaces=("dbo",))
        self.assertEqual(stream.profile_version, 1)

    def test_update_cannot_create_an_overlap(self) -> None:
        self.site.sync.create_stream("hr-only", graph="erp", namespaces=("hr",))
        with self.assertRaises(SyncFailure) as caught:
            self.widen_stream()
        self.assertEqual(caught.exception.code, "overlapping_stream")

    def test_an_approved_namespace_that_vanished_is_not_read_as_mass_deletion(self) -> None:
        self.apply(self.publish())
        self.set_site_tables(("hr", "salaries"))
        with self.assertRaises(SyncFailure) as caught:
            self.publish()
        self.assertEqual(caught.exception.code, "scope_namespace_missing")

    def test_foreign_keys_into_an_excluded_namespace_stay_home(self) -> None:
        graph = build_graph_from_catalog(
            "erp",
            CatalogResult(
                connector="shop",
                source_type="sqlite",
                catalog="Shop",
                dialect="sqlite",
                objects=tuple(
                    CatalogObject(
                        namespace=namespace,
                        name=name,
                        kind="table",
                        fields=(CatalogField("id", 1, "INTEGER", False),),
                    )
                    for namespace, name in (("dbo", "orders"), ("hr", "salaries"))
                ),
                relationships=(
                    CatalogRelationship(
                        name="fk",
                        from_namespace="dbo",
                        from_object="orders",
                        from_fields=("id",),
                        to_namespace="hr",
                        to_object="salaries",
                        to_fields=("id",),
                    ),
                ),
            ),
        )
        self.site.runtime.graph_store().save(graph)

        self.apply(self.publish())

        self.assertEqual({edge.type for edge in self.central_graph().edges}, {"contains"})


class RemovedObjectTests(_SyncCase):
    def annotate_central(self, node_id: str, annotation=HUMAN) -> None:
        graph = self.central_graph()
        self.central.runtime.graph_store().save(replace(graph, nodes=tuple(
            replace(node, annotation=annotation) if node.id == node_id else node
            for node in graph.nodes
        )))

    def test_central_claim_on_a_removed_object_is_kept_with_its_reason(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.annotate_central(CUSTOMERS)
        self.set_site_tables(("dbo", "orders"))

        result = self.apply(self.publish())

        self.assertEqual(result.plan.affected_claims[0]["target_id"], CUSTOMERS)
        kept = self.central.sync.status()[0].retired_claims[0]
        self.assertEqual(kept["target_id"], CUSTOMERS)
        self.assertEqual(kept["reason"], "source_deleted")
        self.assertEqual(kept["claim"]["annotation"]["description"], HUMAN.description)

    def test_returning_object_gets_its_claim_back_for_review(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.annotate_central(CUSTOMERS)
        self.set_site_tables(("dbo", "orders"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))

        result = self.apply(self.publish())

        self.assertEqual(result.plan.restored_claims, (CUSTOMERS,))
        node = self.central_graph().node_by_id()[CUSTOMERS]
        self.assertEqual(node.annotation.description, HUMAN.description)
        self.assertEqual(node.annotation.state, "review_required")
        status = self.central.sync.status()[0]
        self.assertEqual(status.retired_claims, ())
        self.assertEqual(status.removals, ())

    def test_returning_object_keeps_a_rejection_as_a_rejection(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.annotate_central(CUSTOMERS, replace(HUMAN, state="rejected"))
        self.set_site_tables(("dbo", "orders"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))

        self.apply(self.publish())

        self.assertEqual(
            self.central_graph().node_by_id()[CUSTOMERS].annotation.state, "rejected",
        )

    def test_claims_survive_a_further_update_that_does_not_touch_them(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.annotate_central(CUSTOMERS)
        self.set_site_tables(("dbo", "orders"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "items"))

        self.apply(self.publish())

        self.assertEqual(self.central.sync.status()[0].retired_claims[0]["target_id"], CUSTOMERS)


class DanglingReferenceTests(_SyncCase):
    def setUp(self) -> None:
        super().setUp()
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.other = replace(_catalog(("dbo", "orders")), name="central.local")
        self.central.runtime.graph_store().save(self.other)
        self.central.workspace.define_system("group", "local", graphs=("central.local",))
        self.central.workspace.define_area(
            "group", "site-a", "main", schemas=("site-a.erp:dbo",),
        )
        self.central.workspace.define_zone(
            "group",
            "site-a",
            "core",
            objects=("site-a.erp:dbo.customers", "site-a.erp:dbo.orders"),
        )
        self.central.workspace.add_relationship(
            "group",
            source="site-a.erp:dbo.customers.id",
            target="central.local:dbo.orders.id",
            reason="Reviewed by hand",
            validated=True,
        )

    def remove_customers(self):
        self.set_site_tables(("dbo", "orders"))
        return self.apply(self.publish())

    def test_plan_names_what_would_be_left_without_a_target(self) -> None:
        self.set_site_tables(("dbo", "orders"))

        plan = self.central.sync.plan(self.publish(), allow_unsigned_dev=True)

        kinds = {(item["kind"], item["object_id"]) for item in plan.dangling_references}
        self.assertEqual(
            kinds, {("zone_member", CUSTOMERS), ("relationship_object", CUSTOMERS)},
        )

    def test_the_shared_view_keeps_working_after_the_object_is_gone(self) -> None:
        self.remove_customers()

        workspace, graphs, scope = load_workspace_scope(
            "group", runtime=self.central.runtime,
        )
        projection = project_workspace_scope(workspace, graphs, scope)

        self.assertEqual({item.object_id for item in scope.objects}, {ORDERS})
        self.assertFalse([e for e in projection.edges if e.type == "relationship_candidate"])
        zone = show_workspace_zone_use_case(
            "group", "site-a", "core", runtime=self.central.runtime,
        )
        self.assertEqual([item.object_id for item in zone.objects], [ORDERS])

    def test_the_human_decision_stays_in_the_workspace_and_is_reported(self) -> None:
        self.remove_customers()

        workspace = self.central.runtime.workspace_store().load("group")
        self.assertEqual(workspace.relationships[0].state, "validated")
        self.assertEqual(workspace.relationships[0].reason, "Reviewed by hand")
        dangling = self.central.sync.status()[0].dangling_references
        self.assertEqual({item["reason"] for item in dangling}, {"source_deleted"})
        self.assertEqual(len(dangling), 2)

    def test_the_relationship_works_again_when_the_object_returns(self) -> None:
        self.remove_customers()
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())

        workspace, graphs, scope = load_workspace_scope("group", runtime=self.central.runtime)
        projection = project_workspace_scope(workspace, graphs, scope)

        self.assertTrue([e for e in projection.edges if e.type == "relationship_candidate"])
        self.assertEqual(self.central.sync.status()[0].dangling_references, ())

    def test_a_lost_field_only_disables_the_relationship_that_needs_it(self) -> None:
        self.site.runtime.graph_store().save(
            _catalog(("dbo", "orders"), ("dbo", "customers"), columns=("other",))
        )
        self.apply(self.publish())

        workspace, graphs, scope = load_workspace_scope("group", runtime=self.central.runtime)
        projection = project_workspace_scope(workspace, graphs, scope)

        self.assertFalse([e for e in projection.edges if e.type == "relationship_candidate"])
        dangling = self.central.sync.status()[0].dangling_references
        self.assertEqual([item["kind"] for item in dangling], ["relationship_field"])

    def test_an_ordinary_local_graph_still_fails_loudly(self) -> None:
        self.central.workspace.define_area(
            "group", "local", "main", schemas=("central.local:dbo",),
        )
        self.central.workspace.define_zone(
            "group", "local", "here", objects=("central.local:dbo.orders",),
        )
        self.central.runtime.graph_store().save(
            replace(_catalog(("dbo", "other")), name="central.local")
        )

        with self.assertRaises(WorkspaceFailure) as caught:
            show_workspace_zone_use_case(
                "group", "local", "here", runtime=self.central.runtime,
            )
        self.assertEqual(caught.exception.code, "zone_member_not_found")


class ObservationTests(_SyncCase):
    def setUp(self) -> None:
        super().setUp()
        self.site.runtime.graph_store().save(_catalog(("dbo", "orders")))

    def publish_recorded(self, name: str = "recorded") -> Path:
        path = self.root / f"{name}.tarelpub"
        self.site.sync.publish("erp-main", output=path, unsigned_dev=True)
        return path

    def record(self, namespace: str | None = None) -> None:
        self.site.runtime.graph_store().record_observation("erp", namespace=namespace)

    def statement(self, path: Path):
        return self.site.sync.inspect(path).publication

    def test_without_any_record_a_site_cannot_claim_a_read(self) -> None:
        with self.assertRaises(SyncFailure) as caught:
            self.publish_recorded()
        self.assertEqual(caught.exception.code, "observation_missing")

    def test_recorded_read_supplies_time_and_completeness(self) -> None:
        self.record()

        publication = self.statement(self.publish_recorded())

        self.assertEqual(publication.observation_source, "recorded")
        self.assertEqual(publication.completeness, "complete")
        self.assertEqual(
            publication.observed_at,
            self.site.runtime.graph_store().observation("erp").observed_at,
        )

    def test_a_caller_statement_is_labelled_as_such(self) -> None:
        publication = self.statement(self.publish())
        self.assertEqual(publication.observation_source, "stated")

    def test_a_read_limited_to_another_namespace_is_partial_and_changes_nothing(self) -> None:
        self.apply(self.publish())
        before = graph_revision(self.central_graph())
        self.record(namespace="sales")

        path = self.publish_recorded()

        self.assertEqual(self.statement(path).completeness, "partial")
        self.assert_rejected("incomplete_snapshot", path)
        self.assertEqual(graph_revision(self.central_graph()), before)

    def test_a_failed_refresh_blocks_publishing_and_keeps_the_last_good_read(self) -> None:
        self.record()
        good = self.site.runtime.graph_store().observation("erp").observed_at
        failure = TarelError("connector_down", "Source unreachable.")

        with (
            patch("tarel.graph.application.discover_catalog_use_case", side_effect=failure),
            self.assertRaises(TarelError),
        ):
            refresh_graph_use_case("erp", runtime=self.site.runtime)

        observation = self.site.runtime.graph_store().observation("erp")
        self.assertEqual(observation.observed_at, good)
        self.assertEqual(observation.failure["code"], "connector_down")
        with self.assertRaises(SyncFailure) as caught:
            self.publish_recorded()
        self.assertEqual(caught.exception.code, "observation_failed")

    def test_a_successful_refresh_clears_the_failure_and_records_the_read(self) -> None:
        store = self.site.runtime.graph_store()
        store.record_failed_observation("erp", "connector_down", "Source unreachable.")
        catalog = CatalogResult(
            connector="shop",
            source_type="sqlite",
            catalog="Shop",
            dialect="sqlite",
            objects=(
                CatalogObject(
                    namespace="dbo",
                    name="orders",
                    kind="table",
                    fields=(CatalogField("id", 1, "INTEGER", False, "Free text from the source"),),
                    description="Free text from the source",
                ),
            ),
        )

        with patch("tarel.graph.application.discover_catalog_use_case", return_value=catalog):
            refresh_graph_use_case("erp", runtime=self.site.runtime)

        observation = store.observation("erp")
        self.assertIsNone(observation.failure)
        self.assertIsNotNone(observation.observed_at)
        self.assertEqual(observation.namespace, "dbo")

    def test_the_record_stays_out_of_the_graph_revision_and_the_package(self) -> None:
        before = graph_revision(self.site.runtime.graph_store().load("erp"))
        self.record()
        self.assertEqual(graph_revision(self.site.runtime.graph_store().load("erp")), before)

        self.assertEqual(self.statement(self.publish_recorded()).sequence, 1)
        self.assertEqual(self.site.sync.inspect(self.root / "recorded.tarelpub").objects, 1)


class FreshnessStatusTests(_SyncCase):
    def test_an_old_observation_is_marked_stale_even_if_just_received(self) -> None:
        self.apply(self.publish(observed_at="2020-01-01T00:00:00Z"))

        status = self.central.sync.status(max_age_hours=24)[0]

        self.assertTrue(status.stale)
        self.assertGreater(status.observation_age_seconds, 86400)
        self.assertIsNone(self.central.sync.status()[0].stale)

    def test_a_site_that_never_delivered_is_still_listed(self) -> None:
        status = self.central.sync.status(max_age_hours=24)[0]
        self.assertIsNone(status.active_sequence)
        self.assertIsNone(status.stale)

    def test_a_failure_does_not_look_like_a_successful_sync(self) -> None:
        self.apply(self.publish(observed_at=OBSERVED))
        self.assert_rejected("incomplete_snapshot", self.publish(completeness="partial"))

        status = self.central.sync.status()[0]

        self.assertEqual(status.active_sequence, 1)
        self.assertEqual(status.observed_at, OBSERVED)
        self.assertEqual(status.last_failure["code"], "incomplete_snapshot")


class PruneTests(_SyncCase):
    def test_prune_removes_old_bytes_and_leaves_the_active_view_alone(self) -> None:
        self.site.sync.update_stream("erp-main", namespaces=("dbo", "hr"))
        first = self.apply(self.publish())
        self.site.sync.update_stream("erp-main", namespaces=("dbo",))
        second = self.apply(self.publish())
        store = self.central.runtime.sync_store()
        old = store.artifact_path(self.stream.stream_id, first.plan.publication_id)
        self.assertTrue(old.is_file())
        before = graph_revision(self.central_graph())

        result = self.central.sync.prune(self.stream.stream_id)

        self.assertEqual(result.removed, (first.plan.publication_id,))
        self.assertIn(second.plan.publication_id, result.kept)
        self.assertFalse(old.exists())
        self.assertEqual(graph_revision(self.central_graph()), before)
        self.assertEqual(self.central.sync.status()[0].retained_revisions, 1)

    def test_prune_keeps_the_revision_a_freshness_publication_still_needs(self) -> None:
        first = self.apply(self.publish())
        self.apply(self.publish(observed_at="2030-01-02T12:00:00Z"))

        result = self.central.sync.prune(self.stream.stream_id)

        self.assertEqual(result.removed, ())
        self.assertIn(first.plan.publication_id, result.kept)
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.assertEqual(self.apply(self.publish()).plan.action, "update_content")
