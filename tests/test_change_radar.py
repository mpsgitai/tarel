import json
import os
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.annotations.review import decide_annotation
from tarel.application import context_packet_impact_use_case, refresh_graph_use_case
from tarel.cli import main
from tarel.connectors.contracts import (
    CatalogField,
    CatalogObject,
    CatalogRelationship,
    CatalogResult,
)
from tarel.context import compile_context
from tarel.context_packets import context_packet_from_dict, context_packet_impact
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.change_store import FileGraphChangeStore
from tarel.graph.contracts import GraphAnnotation, GraphFailure
from tarel.graph.refresh import refresh_graph
from tarel.graph.revision import graph_revision, technical_graph_fingerprint
from tarel.graph.store import FileGraphStore
from tarel.providers.contracts import ProviderFailure
from tarel.relationships.core import (
    add_manual_relationship,
    decide_relationship,
    relationship_pair,
)
from tarel.runtime import TarelRuntime
from tarel.workspaces.contracts import (
    Area,
    SchemaReference,
    WorkspaceDocument,
    WorkspaceSystem,
    Zone,
    ZoneMember,
)
from tarel.workspaces.impact import workspace_change_impacts


class ChangeRadarTests(TestCase):
    def test_technical_fingerprint_ignores_semantics_but_tracks_source_metadata(self) -> None:
        graph = build_graph_from_catalog("warehouse", _catalog(changed=False))
        annotated = replace(
            graph,
            nodes=tuple(
                replace(
                    node,
                    annotation=GraphAnnotation(
                        description="A local semantic description.",
                        state="draft",
                    ),
                )
                if node.type == "field"
                else node
                for node in graph.nodes
            ),
        )
        changed_description = replace(
            graph,
            nodes=tuple(
                replace(
                    node,
                    metadata={**node.metadata, "technical_description": "Source comment."},
                )
                if node.label == "Amount"
                else node
                for node in graph.nodes
            ),
        )
        without_declared_relationship = replace(
            graph,
            edges=tuple(edge for edge in graph.edges if edge.type != "foreign_key"),
        )

        self.assertEqual(
            technical_graph_fingerprint(graph),
            technical_graph_fingerprint(annotated),
        )
        self.assertNotEqual(
            technical_graph_fingerprint(graph),
            technical_graph_fingerprint(changed_description),
        )
        self.assertNotEqual(
            technical_graph_fingerprint(graph),
            technical_graph_fingerprint(without_declared_relationship),
        )

    def test_application_no_op_refresh_does_not_rewrite_graph(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            runtime = TarelRuntime.local(Path(temporary_directory) / ".tarel")
            graph = _annotated_graph()
            path = runtime.graph_store().save(graph)
            stable_time = 1_700_000_000_000_000_000
            os.utime(path, ns=(stable_time, stable_time))

            with patch(
                "tarel.application.discover_catalog_use_case",
                return_value=_catalog(changed=False),
            ):
                result = refresh_graph_use_case(graph.name, runtime=runtime)

            self.assertEqual(path.stat().st_mtime_ns, stable_time)
            self.assertEqual(result.status, "unchanged")
            self.assertFalse(result.changed)
            self.assertEqual(result.graph, graph)
            self.assertIsNone(result.change_report_path)
            self.assertEqual(result.workspace_impacts, ())

    def test_application_rejects_partial_or_empty_refresh_observations(self) -> None:
        graph = _annotated_graph()
        catalog = _catalog(changed=False)
        sales_catalog = replace(
            catalog,
            objects=tuple(item for item in catalog.objects if item.namespace == "sales"),
        )
        empty_catalog = replace(catalog, objects=(), relationships=())
        with TemporaryDirectory() as temporary_directory:
            runtime = TarelRuntime.local(Path(temporary_directory) / ".tarel")
            path = runtime.graph_store().save(graph)
            original = path.read_bytes()

            with patch(
                "tarel.application.discover_catalog_use_case",
                return_value=sales_catalog,
            ), self.assertRaises(GraphFailure) as partial:
                refresh_graph_use_case(graph.name, namespace="sales", runtime=runtime)
            with patch(
                "tarel.application.discover_catalog_use_case",
                return_value=empty_catalog,
            ), self.assertRaises(GraphFailure) as empty:
                refresh_graph_use_case(graph.name, runtime=runtime)

            self.assertEqual(path.read_bytes(), original)

        self.assertEqual(partial.exception.code, "partial_refresh_scope")
        self.assertEqual(empty.exception.code, "empty_refresh_observation")

    def test_namespace_scope_comparison_accepts_canonical_case(self) -> None:
        catalog = _catalog(changed=False)
        sales_catalog = replace(
            catalog,
            objects=tuple(item for item in catalog.objects if item.namespace == "sales"),
        )
        graph = build_graph_from_catalog("warehouse", sales_catalog)
        with TemporaryDirectory() as temporary_directory:
            runtime = TarelRuntime.local(Path(temporary_directory) / ".tarel")
            runtime.graph_store().save(graph)

            with patch(
                "tarel.application.discover_catalog_use_case",
                return_value=sales_catalog,
            ):
                result = refresh_graph_use_case(
                    graph.name,
                    namespace="SALES",
                    runtime=runtime,
                )

        self.assertEqual(result.status, "unchanged")

    def test_refresh_annotation_batch_touches_only_new_gaps(self) -> None:
        provider = _DeltaAnnotationProvider()
        before = _annotated_graph()
        packet = compile_context(
            before,
            "sales amount",
            seed_limit=1,
            max_objects=1,
            max_fields_per_object=10,
        )
        with TemporaryDirectory() as temporary_directory:
            runtime = TarelRuntime.local(Path(temporary_directory) / ".tarel")
            runtime.graph_store().save(before)

            with (
                patch(
                    "tarel.application.discover_catalog_use_case",
                    return_value=_catalog(changed=True),
                ),
                patch("tarel.application.load_provider", return_value=provider),
            ):
                result = refresh_graph_use_case(
                    "warehouse",
                    annotate_new_provider="fixture",
                    annotation_workers=2,
                    runtime=runtime,
                )

            fact = next(node for node in result.graph.nodes if node.label == "sales.FactSales")
            sales_key = next(
                node
                for node in result.graph.nodes
                if node.label == "SalesKey" and node.metadata.get("object_id") == fact.id
            )
            external_code = next(
                node
                for node in result.graph.nodes
                if node.label == "ExternalCode" and node.metadata.get("object_id") == fact.id
            )
            impact = context_packet_impact(
                context_packet_from_dict(packet.to_dict()),
                result.graph,
                result.report,
            )
            packet_path = Path(temporary_directory) / "before-context.json"
            packet_path.write_text(json.dumps(packet.to_dict()), encoding="utf-8")
            persisted_impact = context_packet_impact_use_case(
                packet_path,
                "warehouse",
                runtime=runtime,
            )
            report_exists = result.change_report_path.is_file()

        self.assertEqual(result.annotation_run.annotated, 1)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(fact.annotation.state, "review_required")
        self.assertIsNone(sales_key.annotation)
        self.assertEqual(external_code.annotation.state, "draft")
        self.assertEqual(result.report.after_revision, graph_revision(result.graph))
        self.assertTrue(report_exists)
        self.assertEqual(impact.status, "affected")
        self.assertTrue(impact.exact)
        self.assertEqual(persisted_impact.status, "affected")
        self.assertTrue(persisted_impact.exact)

    def test_unchanged_refresh_never_loads_delta_annotation_provider(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            runtime = TarelRuntime.local(Path(temporary_directory) / ".tarel")
            runtime.graph_store().save(_annotated_graph())

            with (
                patch(
                    "tarel.application.discover_catalog_use_case",
                    return_value=_catalog(changed=False),
                ),
                patch("tarel.application.load_provider") as load_provider,
            ):
                result = refresh_graph_use_case(
                    "warehouse",
                    annotate_new_provider="fixture",
                    runtime=runtime,
                )

        load_provider.assert_not_called()
        self.assertEqual(result.annotation_run.planned, 0)

    def test_provider_failure_keeps_successful_schema_refresh(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            runtime = TarelRuntime.local(Path(temporary_directory) / ".tarel")
            runtime.graph_store().save(_annotated_graph())

            with (
                patch(
                    "tarel.application.discover_catalog_use_case",
                    return_value=_catalog(changed=True),
                ),
                patch(
                    "tarel.application.load_provider",
                    side_effect=ProviderFailure("provider_unavailable", "offline"),
                ),
                self.assertRaises(ProviderFailure),
            ):
                refresh_graph_use_case(
                    "warehouse",
                    annotate_new_provider="fixture",
                    runtime=runtime,
                )
            saved = runtime.graph_store().load("warehouse")

        self.assertIn("ExternalCode", {node.label for node in saved.nodes})
        self.assertNotIn("LegacyCode", {node.label for node in saved.nodes})

    def test_refresh_classifies_changes_and_marks_only_affected_validated_claims(self) -> None:
        current = _annotated_graph()
        pair = relationship_pair(current, "sales.FactSales.Amount", "sales.DimAccount.AccountKey")
        current, candidate = add_manual_relationship(
            current,
            pair=pair,
            reason="Validated by the warehouse owner.",
            validated=True,
        )

        refreshed, report = refresh_graph(current, _changed_graph())

        kinds = {change.kind for change in report.changes}
        self.assertTrue(
            {
                "field_added",
                "field_removed",
                "field_type_changed",
                "field_key_status_changed",
                "possible_field_rename",
                "primary_key_changed",
                "relationship_removed",
            }.issubset(kinds)
        )
        nodes = refreshed.node_by_id()
        fact = next(node for node in refreshed.nodes if node.label == "sales.FactSales")
        amount = next(
            node
            for node in refreshed.nodes
            if node.type == "field"
            and node.label == "Amount"
            and node.metadata.get("object_id") == fact.id
        )
        account = next(node for node in refreshed.nodes if node.label == "sales.DimAccount")
        self.assertEqual(fact.annotation.state, "review_required")
        self.assertEqual(amount.annotation.state, "review_required")
        self.assertEqual(account.annotation.state, "validated")
        self.assertIn("primary_key_changed", fact.metadata["source_change"]["reasons"])
        self.assertIn("field_type_changed", amount.metadata["source_change"]["reasons"])
        self.assertNotIn("source_change", account.metadata)
        self.assertEqual(report.review_required_annotations, 2)

        refreshed_candidate = next(edge for edge in refreshed.edges if edge.id == candidate.id)
        self.assertEqual(refreshed_candidate.metadata["state"], "review_required")
        self.assertEqual(report.review_required_relationships, 1)
        removed_claim = next(
            claim for claim in report.stale_claims if claim.reference.endswith("LegacyCode")
        )
        self.assertFalse(removed_claim.present)
        self.assertEqual(removed_claim.previous_state, "validated")
        self.assertIn("annotation", removed_claim.claim)
        self.assertNotIn(
            next(node.id for node in current.nodes if node.label == "LegacyCode"),
            nodes,
        )

        reviewed, annotation_record = decide_annotation(
            refreshed,
            amount.id,
            state="validated",
            reason="The changed type preserves the approved business meaning.",
        )
        reviewed, relationship = decide_relationship(
            reviewed,
            edge_id=candidate.id,
            state="validated",
            reason="The join remains valid after the type migration.",
        )
        self.assertEqual(annotation_record.node.annotation.state, "validated")
        self.assertNotIn("change_review", annotation_record.node.metadata)
        self.assertNotIn("source_change", annotation_record.node.metadata)
        self.assertEqual(relationship.metadata["state"], "validated")
        self.assertNotIn("change_review", relationship.metadata)

    def test_draft_source_change_is_visible_in_context_without_forcing_review_state(self) -> None:
        current = _annotated_graph()
        current = replace(
            current,
            nodes=tuple(
                replace(node, annotation=replace(node.annotation, state="draft"))
                if node.label == "Amount" and node.annotation is not None
                else node
                for node in current.nodes
            ),
        )

        refreshed, _report = refresh_graph(current, _changed_graph())
        amount = next(node for node in refreshed.nodes if node.label == "Amount")
        packet = compile_context(
            refreshed,
            "sales amount",
            seed_limit=1,
            max_objects=1,
            max_fields_per_object=10,
        )
        fact = next(item for item in packet.objects if item.label == "sales.FactSales")
        context_amount = next(field for field in fact.fields if field.name == "Amount")

        self.assertEqual(amount.annotation.state, "draft")
        self.assertEqual(
            amount.metadata["source_change"]["reasons"],
            ["field_type_changed"],
        )
        self.assertEqual(
            context_amount.source_change["reasons"],
            ["field_type_changed"],
        )

    def test_change_report_round_trips_without_volatile_metadata(self) -> None:
        report = refresh_graph(_annotated_graph(), _changed_graph())[1]
        with TemporaryDirectory() as temporary_directory:
            store = FileGraphChangeStore(Path(temporary_directory))
            path = store.save("warehouse", report)
            self.assertEqual(store.save("warehouse", report), path)
            loaded = store.load("warehouse", report.before_revision, report.after_revision)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded.to_dict(), report.to_dict())
        self.assertNotIn("timestamp", json.dumps(payload).lower())
        self.assertEqual(
            path.name,
            f"{report.before_revision}--{report.after_revision}.json",
        )

    def test_unchanged_refresh_keeps_review_required_claims(self) -> None:
        first, first_report = refresh_graph(_annotated_graph(), _changed_graph())

        second, second_report = refresh_graph(first, _changed_graph())

        amount = next(node for node in second.nodes if node.label == "Amount")
        self.assertEqual(amount.annotation.state, "review_required")
        self.assertEqual(second_report.changes, ())
        self.assertEqual(second_report.stale_claims, ())
        self.assertEqual(second_report.before_revision, first_report.after_revision)
        self.assertEqual(second_report.after_revision, first_report.after_revision)

    def test_workspace_impact_finds_area_and_overlapping_zones(self) -> None:
        current = _annotated_graph()
        report = refresh_graph(current, _changed_graph())[1]
        fact = next(node for node in current.nodes if node.label == "sales.FactSales")
        workspace = WorkspaceDocument(
            name="enterprise",
            systems=(
                WorkspaceSystem(
                    name="commercial",
                    graphs=("warehouse",),
                    areas=(
                        Area(
                            name="sales",
                            schemas=(SchemaReference(graph="warehouse", namespace="sales"),),
                        ),
                    ),
                    zones=(
                        Zone(
                            name="finance",
                            members=(ZoneMember(graph="warehouse", object_id=fact.id),),
                        ),
                        Zone(
                            name="revenue",
                            members=(ZoneMember(graph="warehouse", object_id=fact.id),),
                        ),
                    ),
                ),
            ),
        )

        impacts = workspace_change_impacts(workspace, "warehouse", report)

        self.assertEqual(len(impacts), 1)
        self.assertEqual(impacts[0].areas, ("sales",))
        self.assertEqual(impacts[0].zones, ("finance", "revenue"))

    def test_context_impact_is_exact_for_one_refresh(self) -> None:
        current = _annotated_graph()
        packet = compile_context(current, "sales amount", seed_limit=1, max_objects=1)
        refreshed, report = refresh_graph(current, _changed_graph())

        impact = context_packet_impact(
            context_packet_from_dict(packet.to_dict()),
            refreshed,
            report,
        )

        self.assertEqual(impact.status, "affected")
        self.assertTrue(impact.affected)
        self.assertTrue(impact.exact)
        self.assertIn("field_type_changed", {change.kind for change in impact.matched_changes})

    def test_context_impact_distinguishes_unaffected_and_unknown_packets(self) -> None:
        current = _annotated_graph()
        packet = compile_context(
            current,
            "audit event log",
            seed_limit=1,
            max_objects=1,
            max_hops=0,
        )
        refreshed, report = refresh_graph(current, _changed_graph())
        snapshot = context_packet_from_dict(packet.to_dict())

        exact = context_packet_impact(snapshot, refreshed, report)
        unknown = context_packet_impact(snapshot, refreshed, None)

        self.assertEqual(exact.status, "unaffected")
        self.assertFalse(exact.affected)
        self.assertEqual(unknown.status, "unknown")
        self.assertIsNone(unknown.affected)

    def test_cli_reports_context_impact_from_persisted_change_report(self) -> None:
        current = _annotated_graph()
        packet = compile_context(current, "sales amount", seed_limit=1, max_objects=1)
        refreshed, report = refresh_graph(current, _changed_graph())
        with TemporaryDirectory() as temporary_directory:
            previous_directory = Path.cwd()
            os.chdir(temporary_directory)
            try:
                FileGraphStore().save(refreshed)
                FileGraphChangeStore().save(refreshed.name, report)
                packet_path = Path("packet.json")
                packet_path.write_text(json.dumps(packet.to_dict()), encoding="utf-8")
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "context",
                            "impact",
                            str(packet_path),
                            "--graph",
                            refreshed.name,
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous_directory)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "affected")


def _annotated_graph():
    graph = build_graph_from_catalog("warehouse", _catalog(changed=False))
    return replace(
        graph,
        nodes=tuple(
            replace(
                node,
                annotation=GraphAnnotation(
                    description=f"Reviewed meaning for {node.label}.",
                    state="validated",
                ),
            )
            if node.label in {"sales.FactSales", "Amount", "LegacyCode", "sales.DimAccount"}
            else node
            for node in graph.nodes
        ),
    )


def _changed_graph():
    return build_graph_from_catalog("warehouse", _catalog(changed=True))


def _catalog(*, changed: bool) -> CatalogResult:
    fact_fields = (
        CatalogField("SalesKey", 1, "int", False, is_primary_key=not changed),
        CatalogField("Amount", 2, "decimal(18,2)" if changed else "money", False),
        CatalogField("ExternalCode" if changed else "LegacyCode", 3, "nvarchar(30)", True),
    )
    return CatalogResult(
        connector="test",
        source_type="database",
        catalog="Warehouse",
        dialect="ansi",
        objects=(
            CatalogObject(
                namespace="sales",
                name="FactSales",
                kind="table",
                fields=fact_fields,
                primary_key=() if changed else ("SalesKey",),
            ),
            CatalogObject(
                namespace="sales",
                name="DimAccount",
                kind="table",
                fields=(CatalogField("AccountKey", 1, "int", False, is_primary_key=True),),
                primary_key=("AccountKey",),
            ),
            CatalogObject(
                namespace="audit",
                name="EventLog",
                kind="table",
                fields=(CatalogField("EventId", 1, "bigint", False, is_primary_key=True),),
                primary_key=("EventId",),
            ),
        ),
        relationships=()
        if changed
        else (
            CatalogRelationship(
                name="FK_FactSales_Account",
                from_namespace="sales",
                from_object="FactSales",
                from_fields=("SalesKey",),
                to_namespace="sales",
                to_object="DimAccount",
                to_fields=("AccountKey",),
            ),
        ),
    )


class _DeltaAnnotationProvider:
    name = "delta-fixture"
    default_model = "fixture-model"

    def __init__(self) -> None:
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        evidence = {
            "reason": "The technical field name is direct evidence.",
            "reference": "ExternalCode",
            "source": "field_name",
            "value": None,
        }
        return {
            "confidence": 0.7,
            "confidence_reason": "Only technical metadata is available.",
            "description": "Existing sales fact object.",
            "evidence": [evidence],
            "fields": [
                {
                    "confidence": 0.7,
                    "confidence_reason": "The technical field name suggests an external code.",
                    "description": "External reference code.",
                    "evidence": [evidence],
                    "name": "ExternalCode",
                    "role": "key",
                    "semantic_type": "identifier",
                    "synonyms": [],
                    "warnings": ["Business meaning is not verified."],
                }
            ],
            "grain": None,
            "role": "fact",
            "synonyms": [],
            "warnings": ["Object annotation is context only."],
        }
