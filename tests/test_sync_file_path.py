"""One site, one central state: first takeover, repetition, update and the history rules."""

from __future__ import annotations

import contextlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.annotations.review import decide_annotation
from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.errors import TarelError
from tarel.graph.build import build_graph_from_catalog, object_node_id
from tarel.graph.contracts import (
    AnnotationEvidence,
    AnnotationProvenance,
    GraphAnnotation,
    GraphDocument,
)
from tarel.graph.revision import graph_revision
from tarel.packages.application import verify_package
from tarel.sdk import Tarel
from tarel.sync import application
from tarel.sync.contracts import SyncFailure
from tarel.sync.envelope import PACKAGE_MEMBER, PUBLICATION_MEMBER
from tarel.sync.results import PublishResult

OBSERVED = "2030-01-01T12:00:00Z"
ORDERS = object_node_id("Shop", "dbo", "orders")
HUMAN = GraphAnnotation(
    "Central view of orders",
    state="validated",
    provenance=AnnotationProvenance(source="human"),
)


def _catalog(*tables: tuple[str, str], columns: tuple[str, ...] = ("id",)) -> GraphDocument:
    return build_graph_from_catalog(
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
                    fields=tuple(
                        CatalogField(
                            name=column,
                            data_type="INTEGER",
                            nullable=False,
                            position=position,
                            is_primary_key=False,
                            description="Free text from the source",
                        )
                        for position, column in enumerate(columns, start=1)
                    ),
                    description="Free text from the source",
                )
                for namespace, name in tables
            ),
        ),
    )


class _SyncCase(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.site = Tarel(self.root / "site")
        self.central = Tarel(self.root / "central")
        self.site.runtime.graph_store().save(_catalog(("dbo", "orders"), ("hr", "salaries")))
        self.publisher_id = self.site.sync.init_publisher()
        self.stream = self.site.sync.create_stream("erp-main", graph="erp", namespaces=("dbo",))
        self.central.sync.trust(
            publisher_id=self.publisher_id,
            stream_id=self.stream.stream_id,
            graph_id=self.stream.graph_id,
            local_graph="site-a.erp",
            workspace="group",
            system="site-a",
            namespaces=("dbo", "hr"),
            annotations=True,
        )
        self.counter = 0

    def publish(self, *, observed_at: str = OBSERVED, completeness: str = "complete") -> Path:
        self.counter += 1
        path = self.root / f"out-{self.counter}.tarelpub"
        result = self.site.sync.publish(
            "erp-main",
            output=path,
            observed_at=observed_at,
            completeness=completeness,
            unsigned_dev=True,
        )
        self.assertIsInstance(result, PublishResult)
        return path

    def apply(self, path: Path, **kwargs: object):
        return self.central.sync.apply(path, allow_unsigned_dev=True, **kwargs)

    def central_graph(self) -> GraphDocument:
        return self.central.runtime.graph_store().load("site-a.erp")

    def set_site_tables(self, *tables: tuple[str, str], **kwargs: tuple[str, ...]) -> None:
        self.site.runtime.graph_store().save(_catalog(*tables, **kwargs))

    def assert_rejected(self, code: str, path: Path, **kwargs: object) -> None:
        before = _active_files(self.central)
        with self.assertRaises(TarelError) as caught:
            self.apply(path, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(_active_files(self.central), before, "A rejection changed active state.")


def _active_files(client: Tarel) -> dict[str, bytes]:
    sync = client.root / "sync" / "streams"
    tracked = [*(client.root / "graphs").rglob("graph.json"), *sync.rglob("head.json")]
    return {str(path): path.read_bytes() for path in tracked if path.is_file()}


class FirstTakeoverTests(_SyncCase):
    def test_first_publication_becomes_a_local_graph_in_the_shared_workspace(self) -> None:
        result = self.apply(self.publish())

        self.assertTrue(result.applied)
        self.assertEqual(result.plan.action, "first_activation")
        self.assertEqual(result.plan.objects_added, ("dbo.orders",))
        self.assertIsNone(result.head.pending)
        graph = self.central_graph()
        self.assertEqual(graph.name, "site-a.erp")
        workspace = self.central.runtime.workspace_store().load("group")
        self.assertEqual(workspace.systems[0].graphs, ("site-a.erp",))

    def test_only_the_approved_scope_leaves_the_site(self) -> None:
        self.apply(self.publish())

        labels = {node.label for node in self.central_graph().nodes}
        self.assertIn("dbo.orders", labels)
        self.assertNotIn("hr.salaries", labels)
        self.assertNotIn("hr", labels)

    def test_free_text_stays_home_unless_the_stream_approves_it(self) -> None:
        self.apply(self.publish())

        for node in self.central_graph().nodes:
            self.assertNotIn("technical_description", node.metadata, node.id)

    def test_a_new_metadata_key_is_not_exported_by_accident(self) -> None:
        graph = self.site.runtime.graph_store().load("erp")
        nodes = tuple(
            replace(node, metadata={**node.metadata, "connection_string": "secret"})
            if node.id == ORDERS else node
            for node in graph.nodes
        )
        self.site.runtime.graph_store().save(replace(graph, nodes=nodes))

        self.apply(self.publish())

        self.assertNotIn("connection_string", self.central_graph().node_by_id()[ORDERS].metadata)

    def test_the_inner_package_stays_an_ordinary_verifiable_tarel_file(self) -> None:
        path = self.publish()
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(
                {item.filename for item in archive.infolist()},
                {PACKAGE_MEMBER, PUBLICATION_MEMBER},
            )
            inner = self.root / "inner.tarel"
            inner.write_bytes(archive.read(PACKAGE_MEMBER))
        self.assertTrue(verify_package(inner).verified)

    def test_an_existing_foreign_graph_is_not_overwritten(self) -> None:
        self.central.runtime.graph_store().save(replace(_catalog(), name="site-a.erp"))
        self.assert_rejected("local_graph_exists", self.publish())

    def test_plan_changes_nothing_and_its_id_is_stable(self) -> None:
        path = self.publish()
        before = _active_files(self.central)

        first = self.central.sync.plan(path, allow_unsigned_dev=True)
        second = self.central.sync.plan(path, allow_unsigned_dev=True)

        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(_active_files(self.central), before)
        self.assertEqual(self.central.sync.status()[0].active_sequence, None)


class RepetitionAndUpdateTests(_SyncCase):
    def test_same_publication_twice_is_a_no_op(self) -> None:
        path = self.publish()
        self.apply(path)
        before = _active_files(self.central)

        repeated = self.apply(path)

        self.assertFalse(repeated.applied)
        self.assertEqual(repeated.plan.action, "already_active")
        self.assertEqual(_active_files(self.central), before)

    def test_same_content_only_moves_freshness_and_writes_no_graph(self) -> None:
        self.apply(self.publish())
        graph_before = graph_revision(self.central_graph())
        changes = self.central.root / "graphs" / "site-a.erp" / "changes"

        result = self.apply(self.publish(observed_at="2030-01-02T12:00:00Z"))

        self.assertEqual(result.plan.action, "confirm_freshness")
        self.assertFalse(result.plan.content_changed)
        self.assertEqual(graph_revision(self.central_graph()), graph_before)
        self.assertFalse(changes.exists())
        status = self.central.sync.status()[0]
        self.assertEqual(status.active_sequence, 2)
        self.assertEqual(status.observed_at, "2030-01-02T12:00:00Z")

    def test_changed_content_updates_only_this_graph(self) -> None:
        self.central.runtime.graph_store().save(replace(_catalog(("x", "other")), name="other"))
        other = graph_revision(self.central.runtime.graph_store().load("other"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"), ("hr", "salaries"))

        result = self.apply(self.publish())

        self.assertEqual(result.plan.action, "update_content")
        self.assertEqual(result.plan.objects_added, ("dbo.customers",))
        self.assertIn("dbo.customers", {node.label for node in self.central_graph().nodes})
        self.assertEqual(graph_revision(self.central.runtime.graph_store().load("other")), other)

    def test_removal_from_a_complete_snapshot_removes_the_object(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"))

        result = self.apply(self.publish())

        self.assertEqual(result.plan.objects_deleted, ("dbo.customers",))
        self.assertNotIn("dbo.customers", {node.label for node in self.central_graph().nodes})


class HistoryTests(_SyncCase):
    def test_older_publication_does_not_roll_back(self) -> None:
        old = self.publish()
        self.apply(old)
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        new = self.publish()
        self.apply(new)

        self.assert_rejected("stale_publication", old)

    def test_missing_intermediate_snapshot_is_accepted_with_a_warning(self) -> None:
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.publish()
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"), ("dbo", "items"))

        result = self.apply(self.publish())

        self.assertEqual(result.plan.action, "update_content")
        self.assertIn("Skipped publications 2..2", result.plan.warnings[0])

    def test_same_sequence_with_other_content_is_a_conflict(self) -> None:
        self.apply(self.publish())
        store = self.site.runtime.sync_store()
        stream = store.publisher_stream("erp-main")
        store.save_publisher_stream(replace(stream, sequence=0, recent_publications=()))
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))

        self.assert_rejected("publication_conflict", self.publish())

    def test_a_copied_writer_that_forked_earlier_is_a_conflict(self) -> None:
        store = self.site.runtime.sync_store()
        self.publish()
        copied = store.publisher_stream("erp-main")
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())

        store.save_publisher_stream(copied)
        self.set_site_tables(("dbo", "orders"), ("dbo", "items"))
        self.publish()
        self.set_site_tables(("dbo", "orders"), ("dbo", "items"), ("dbo", "more"))

        self.assert_rejected("publication_conflict", self.publish())

    def test_a_restored_site_gets_back_only_by_an_explicit_decision(self) -> None:
        store = self.site.runtime.sync_store()
        backup = store.publisher_stream("erp-main")
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"), ("dbo", "items"))
        self.apply(self.publish())
        store.save_publisher_stream(backup)
        self.set_site_tables(("dbo", "orders"), ("dbo", "restored"))
        lower = self.publish()
        same = self.publish()
        higher = self.publish()

        self.assert_rejected("stale_publication", lower, accept_history_gap=True)
        self.assert_rejected("publication_conflict", same, accept_history_gap=True)
        self.assert_rejected("publication_conflict", higher)

        result = self.apply(higher, accept_history_gap=True)

        self.assertEqual(result.head.sequence, 3)
        self.assertIn("Accepted without history", result.plan.warnings[0])
        self.assertIn("dbo.restored", {node.label for node in self.central_graph().nodes})

    def test_history_beyond_the_window_needs_an_explicit_decision(self) -> None:
        self.apply(self.publish())
        store = self.site.runtime.sync_store()
        stream = store.publisher_stream("erp-main")
        store.save_publisher_stream(
            replace(stream, sequence=100, recent_publications=tuple(f"{n:064x}" for n in range(64)))
        )
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        path = self.publish()

        self.assert_rejected("history_gap", path)
        result = self.apply(path, accept_history_gap=True)
        self.assertEqual(result.head.sequence, 101)
        self.assertIn("Accepted without history", result.plan.warnings[0])

    def test_partial_publication_proves_nothing_and_stays_visible_as_a_failure(self) -> None:
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"))

        self.assert_rejected("incomplete_snapshot", self.publish(completeness="partial"))

        self.assertIn("dbo.customers", {node.label for node in self.central_graph().nodes})
        status = self.central.sync.status()[0]
        self.assertEqual(status.active_sequence, 1)
        self.assertEqual(status.last_received["sequence"], 2)
        self.assertEqual(status.last_failure["code"], "incomplete_snapshot")


class CentralKnowledgeTests(_SyncCase):
    def annotate_site(self, annotation: GraphAnnotation) -> None:
        graph = self.site.runtime.graph_store().load("erp")
        nodes = tuple(
            replace(node, annotation=annotation) if node.id == ORDERS else node
            for node in graph.nodes
        )
        self.site.runtime.graph_store().save(replace(graph, nodes=nodes))

    def annotate_central(self, annotation: GraphAnnotation) -> None:
        graph = self.central_graph()
        nodes = tuple(
            replace(node, annotation=annotation) if node.id == ORDERS else node
            for node in graph.nodes
        )
        self.central.runtime.graph_store().save(replace(graph, nodes=nodes))

    def use_annotated_stream(self) -> None:
        store = self.site.runtime.sync_store()
        stream = store.publisher_stream("erp-main")
        store.save_publisher_stream(
            replace(stream, scope=replace(stream.scope, annotations=True))
        )

    def test_central_annotation_survives_an_update(self) -> None:
        self.apply(self.publish())
        self.annotate_central(HUMAN)
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))

        self.apply(self.publish())

        self.assertEqual(self.central_graph().node_by_id()[ORDERS].annotation, HUMAN)

    def test_source_change_marks_a_validated_central_claim_for_review(self) -> None:
        field_id = "field:Shop/dbo/orders/id"
        self.apply(self.publish())
        graph = self.central_graph()
        self.central.runtime.graph_store().save(replace(graph, nodes=tuple(
            replace(node, annotation=HUMAN) if node.id == field_id else node
            for node in graph.nodes
        )))
        site = self.site.runtime.graph_store().load("erp")
        self.site.runtime.graph_store().save(replace(site, nodes=tuple(
            replace(node, metadata={**node.metadata, "nullable": True})
            if node.id == field_id else node
            for node in site.nodes
        )))

        result = self.apply(self.publish())

        node = self.central_graph().node_by_id()[field_id]
        self.assertEqual(node.annotation.description, HUMAN.description)
        self.assertEqual(node.annotation.state, "review_required")
        self.assertEqual(len(result.plan.affected_claims), 1)

    def test_published_claim_is_never_validated_by_import_and_keeps_its_origin(self) -> None:
        self.use_annotated_stream()
        self.annotate_site(
            GraphAnnotation(
                "Site view",
                state="validated",
                provenance=AnnotationProvenance(source="human"),
                evidence=(AnnotationEvidence("sample", "orders.id", value="4711"),),
            )
        )

        self.apply(self.publish())

        node = self.central_graph().node_by_id()[ORDERS]
        self.assertEqual(node.annotation.state, "draft")
        self.assertEqual(node.annotation.provenance.source, f"sync:{self.publisher_id}")
        published = node.metadata["published_annotation"]
        self.assertEqual(published["annotation"]["state"], "validated")
        self.assertEqual(published["origin"]["publisher_id"], self.publisher_id)
        self.assertIsNone(published["annotation"]["evidence"][0]["value"])

    def test_untouched_imported_claim_follows_the_site(self) -> None:
        self.use_annotated_stream()
        self.annotate_site(GraphAnnotation("First"))
        self.apply(self.publish())
        self.annotate_site(GraphAnnotation("Second"))

        self.apply(self.publish())

        self.assertEqual(self.central_graph().node_by_id()[ORDERS].annotation.description, "Second")

    def set_grain(self, store_owner: Tarel, graph_name: str, grain: str | None) -> None:
        store = store_owner.runtime.graph_store()
        graph = store.load(graph_name)
        nodes = []
        for node in graph.nodes:
            if node.id == ORDERS:
                metadata = {k: v for k, v in node.metadata.items() if k != "grain"}
                if grain is not None:
                    metadata["grain"] = grain
                node = replace(node, metadata=metadata)
            nodes.append(node)
        store.save(replace(graph, nodes=tuple(nodes)))

    def central_grain(self) -> str | None:
        return self.central_graph().node_by_id()[ORDERS].metadata.get("grain")

    def test_untouched_imported_grain_follows_the_site(self) -> None:
        self.use_annotated_stream()
        self.annotate_site(GraphAnnotation("Orders"))
        self.set_grain(self.site, "erp", "one row per order")
        self.apply(self.publish())
        self.set_grain(self.site, "erp", "one row per order line")

        self.apply(self.publish())

        self.assertEqual(self.central_grain(), "one row per order line")

    def test_withdrawn_annotation_export_takes_the_imported_grain_along(self) -> None:
        self.use_annotated_stream()
        self.annotate_site(GraphAnnotation("Orders"))
        self.set_grain(self.site, "erp", "one row per order")
        self.apply(self.publish())
        store = self.site.runtime.sync_store()
        stream = store.publisher_stream("erp-main")
        store.save_publisher_stream(replace(
            stream,
            scope=replace(stream.scope, annotations=False),
            profile_version=stream.profile_version + 1,
        ))

        self.apply(self.publish())

        self.assertIsNone(self.central_grain())

    def test_central_grain_survives_a_site_change(self) -> None:
        self.use_annotated_stream()
        self.annotate_site(GraphAnnotation("Orders"))
        self.set_grain(self.site, "erp", "one row per order")
        self.apply(self.publish())
        self.set_grain(self.central, "site-a.erp", "one row per order, checked here")
        self.set_grain(self.site, "erp", "one row per order line")

        self.apply(self.publish())

        self.assertEqual(self.central_grain(), "one row per order, checked here")

    def test_central_rejection_of_an_imported_claim_survives_and_both_stay_visible(self) -> None:
        self.use_annotated_stream()
        self.annotate_site(GraphAnnotation("Site view", state="draft"))
        self.apply(self.publish())
        rejected, _ = decide_annotation(
            self.central_graph(), "dbo.orders", state="rejected", reason="Wrong grain",
        )
        self.central.runtime.graph_store().save(rejected)
        self.annotate_site(GraphAnnotation("Site view, reworded", state="validated"))

        self.apply(self.publish())

        node = self.central_graph().node_by_id()[ORDERS]
        self.assertEqual(node.annotation.state, "rejected")
        self.assertEqual(
            node.metadata["published_annotation"]["annotation"]["description"],
            "Site view, reworded",
        )

    def test_central_change_after_planning_makes_the_plan_stale(self) -> None:
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        path = self.publish()
        plan = self.central.sync.plan(path, allow_unsigned_dev=True)
        self.annotate_central(HUMAN)

        self.assert_rejected("stale_plan", path, plan_id=plan.plan_id)

        self.assertEqual(self.apply(path).head.sequence, 2)
        self.assertEqual(self.central_graph().node_by_id()[ORDERS].annotation, HUMAN)


class VisibleFailureTests(_SyncCase):
    def test_a_refusal_from_another_domain_is_recorded_too(self) -> None:
        self.apply(self.publish())
        site = self.site.runtime.graph_store().load("erp")
        self.site.runtime.graph_store().save(replace(site, connector="moved"))

        self.assert_rejected("refresh_mismatch", self.publish())

        self.assertEqual(
            self.central.sync.status()[0].last_failure["code"], "refresh_mismatch",
        )


class TrustTests(_SyncCase):
    def test_unknown_publisher_writes_nothing_at_all(self) -> None:
        other = Tarel(self.root / "other-central")
        with self.assertRaises(SyncFailure) as caught:
            other.sync.apply(self.publish(), allow_unsigned_dev=True)
        self.assertEqual(caught.exception.code, "untrusted_publisher")
        self.assertFalse((other.root / "graphs").exists())
        self.assertFalse((other.root / "sync" / "streams").exists())

    def test_known_publisher_cannot_write_a_stream_it_was_not_granted(self) -> None:
        self.site.runtime.graph_store().save(
            replace(_catalog(("sales", "deals")), name="crm")
        )
        self.site.sync.create_stream("crm-main", graph="crm", namespaces=("sales",))
        path = self.root / "crm.tarelpub"
        self.site.sync.publish("crm-main", output=path, observed_at=OBSERVED, unsigned_dev=True)

        self.assert_rejected("unauthorized_scope", path)

    def test_unsigned_file_needs_the_development_flag(self) -> None:
        with self.assertRaises(SyncFailure) as caught:
            self.central.sync.apply(self.publish())
        self.assertEqual(caught.exception.code, "unsigned_publication")

    def test_a_signature_the_statement_never_named_is_never_ignored(self) -> None:
        path = self.publish()
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("publication.sig", b"signature")

        self.assert_rejected("invalid_signature", path)

    def test_two_streams_may_not_overlap_on_one_graph(self) -> None:
        with self.assertRaises(SyncFailure) as caught:
            self.site.sync.create_stream("again", graph="erp", namespaces=("dbo", "hr"))
        self.assertEqual(caught.exception.code, "overlapping_stream")


class DamagedFileTests(_SyncCase):
    def test_truncated_file_is_rejected(self) -> None:
        path = self.publish()
        path.write_bytes(path.read_bytes()[:200])
        self.assert_rejected("invalid_package", path)

    def test_changed_statement_breaks_the_binding_to_the_package(self) -> None:
        path = self.publish()
        with zipfile.ZipFile(path) as archive:
            statement = json.loads(archive.read(PUBLICATION_MEMBER))
            package = archive.read(PACKAGE_MEMBER)
        statement["package_sha256"] = "0" * 64
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(PUBLICATION_MEMBER, json.dumps(statement))
            archive.writestr(PACKAGE_MEMBER, package)

        self.assert_rejected("invalid_package", path)

    def test_unknown_contract_version_is_named_as_such(self) -> None:
        path = self.publish()
        with zipfile.ZipFile(path) as archive:
            statement = json.loads(archive.read(PUBLICATION_MEMBER))
            package = archive.read(PACKAGE_MEMBER)
        statement["contract_version"] = "tarel.publication.v9"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(PUBLICATION_MEMBER, json.dumps(statement))
            archive.writestr(PACKAGE_MEMBER, package)

        self.assert_rejected("unsupported_contract", path)

    def test_ordinary_tarel_package_is_not_a_publication(self) -> None:
        with zipfile.ZipFile(self.publish()) as archive:
            plain = self.root / "plain.tarelpub"
            plain.write_bytes(archive.read(PACKAGE_MEMBER))

        self.assert_rejected("invalid_package", plain)

    def test_file_changed_between_plan_and_apply_is_refused(self) -> None:
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        path = self.publish()
        plan = self.central.sync.plan(path, allow_unsigned_dev=True)
        self.set_site_tables(("dbo", "orders"), ("dbo", "items"))
        path.write_bytes(self.publish().read_bytes())

        self.assert_rejected("stale_plan", path, plan_id=plan.plan_id)


class InterruptedActivationTests(_SyncCase):
    def test_stop_after_the_commit_point_is_finished_by_the_next_run(self) -> None:
        self.apply(self.publish())
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        path = self.publish()

        with (
            patch.object(application, "_join_workspace", side_effect=RuntimeError("stop")),
            self.assertRaises(RuntimeError),
        ):
            self.apply(path)
        self.assertTrue(self.central.sync.status()[0].activation_pending)

        result = self.apply(path)

        self.assertEqual(result.plan.action, "already_active")
        self.assertFalse(self.central.sync.status()[0].activation_pending)
        self.assertIn("dbo.customers", {node.label for node in self.central_graph().nodes})

    def test_stop_before_the_commit_point_leaves_the_old_state_active(self) -> None:
        self.apply(self.publish())
        before = _active_files(self.central)
        self.set_site_tables(("dbo", "orders"), ("dbo", "customers"))
        path = self.publish()
        store_type = type(self.central.runtime.sync_store())

        with (
            patch.object(store_type, "save_activation", side_effect=RuntimeError("stop")),
            self.assertRaises(RuntimeError),
        ):
            self.apply(path)

        self.assertEqual(_active_files(self.central), before)
        self.assertEqual(self.apply(path).head.sequence, 2)


class CommandLineTests(_SyncCase):
    def run_cli(self, *arguments: str) -> dict[str, object]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main([*arguments, "--format", "json"])
        self.assertEqual(status, 0)
        return json.loads(output.getvalue())

    def test_cli_and_sdk_reach_the_same_plan_and_result(self) -> None:
        path = self.publish()
        state = str(self.central.root)
        sdk_plan = self.central.sync.plan(path, allow_unsigned_dev=True)

        cli_plan = self.run_cli("sync", "plan", str(path), "--state", state, "--allow-unsigned-dev")
        self.assertEqual(cli_plan, sdk_plan.to_dict())

        applied = self.run_cli(
            "sync", "apply", str(path), "--state", state, "--allow-unsigned-dev",
            "--plan-id", str(cli_plan["plan_id"]),
        )
        self.assertTrue(applied["applied"])
        status = self.run_cli("sync", "status", "--state", state)
        self.assertEqual(status["streams"][0], self.central.sync.status()[0].to_dict())

    def test_cli_reports_a_stable_error_code(self) -> None:
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = main(["sync", "apply", str(self.publish()), "--state", str(self.central.root)])
        self.assertEqual(status, 2)
        self.assertIn("unsigned_publication", errors.getvalue())

    def test_inspect_needs_no_state_and_grants_nothing(self) -> None:
        report = self.run_cli("sync", "inspect", str(self.publish()))
        self.assertEqual(report["objects"], 1)
        self.assertFalse(report["signed"])
        self.assertEqual(report["publication"]["sequence"], 1)
