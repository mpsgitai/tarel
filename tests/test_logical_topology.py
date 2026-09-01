from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime
from tarel.sdk import Tarel
from tarel.topology import (
    DerivationEvidence,
    DerivedRelation,
    EndpointRef,
    ExecutorProvenance,
    ExplodeStep,
    ExtractStep,
    FileLogicalTopologyStore,
    Grain,
    LogicalTopologyDocument,
    LogicalTopologyFailure,
    OutputField,
    StepOutput,
    decide_derived_relation_use_case,
    load_logical_topology_use_case,
    new_logical_topology_document,
    save_logical_topology_use_case,
)

_MANIFEST_A = "a" * 64
_MANIFEST_B = "b" * 64
_EXECUTOR = ExecutorProvenance(
    name="test-harness",
    version="1.0",
    implementation_sha256="c" * 64,
)


class LogicalTopologyTests(TestCase):
    def test_cli_import_rejects_duplicate_json_fields(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = Tarel(project / ".tarel")
            document = _document()
            sdk.runtime.graph_store().save(_graph())
            source = project / "duplicate.json"
            encoded = json.dumps(document.to_dict())
            source.write_text(
                '{"contract_version":"shadow",' + encoded[1:],
                encoding="utf-8",
            )
            errors = StringIO()
            try:
                os.chdir(project)
                with redirect_stderr(errors):
                    exit_code = main(
                        ["topology", "import", "--source", str(source)]
                    )
            finally:
                os.chdir(previous)

        self.assertEqual(exit_code, 2)
        self.assertIn("invalid_logical_topology", errors.getvalue())

    def test_cli_and_sdk_share_import_review_and_view_application_paths(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory(dir=previous) as temporary_directory:
            project = Path(temporary_directory)
            sdk = Tarel(project / ".tarel")
            graph = _graph()
            sdk.runtime.graph_store().save(graph)
            source = project / "logical-topology.json"
            source.write_text(json.dumps(_document(graph).to_dict()), encoding="utf-8")
            imported_output = StringIO()
            shown_output = StringIO()
            try:
                os.chdir(project)
                with redirect_stdout(imported_output):
                    imported_exit = main(
                        [
                            "topology",
                            "import",
                            "--source",
                            str(source),
                            "--format",
                            "json",
                        ]
                    )
                current = sdk.topology.load("commerce")
                reviewed = sdk.topology.review(
                    "commerce",
                    "order-items",
                    decision="approve",
                    reason="Typed steps, bounded evidence, output schema, and grain reviewed.",
                    expected_revision=current.revision,
                )
                with redirect_stdout(shown_output):
                    shown_exit = main(
                        ["topology", "show", "commerce", "--format", "json"]
                    )
                view = sdk.view.graph("commerce")
                listed = sdk.topology.list()
            finally:
                os.chdir(previous)

        shown = json.loads(shown_output.getvalue())
        self.assertEqual((imported_exit, shown_exit), (0, 0))
        self.assertEqual(shown["revision"], reviewed.revision)
        self.assertEqual(shown["derived_relations"][0]["state"], "reviewed")
        logical = next(
            item for item in view["objects"] if item["type"] == "derived_relation"
        )
        self.assertEqual(logical["usage"], "confirmed")
        self.assertEqual(listed, (reviewed,))

    def test_contract_roundtrips_with_canonical_plan_and_document_revisions(self) -> None:
        document = _document()

        roundtrip = LogicalTopologyDocument.from_dict(document.to_dict())
        changed_payload = document.to_dict()
        changed_payload["derived_relations"][0]["output_schema"][1]["name"] = "sku"

        self.assertEqual(roundtrip, document)
        self.assertEqual(roundtrip.revision, document.revision)
        self.assertEqual(
            roundtrip.derived_relations[0].plan_revision,
            document.derived_relations[0].plan_revision,
        )
        with self.assertRaises(LogicalTopologyFailure) as stale_plan:
            LogicalTopologyDocument.from_dict(changed_payload)
        self.assertEqual(stale_plan.exception.code, "invalid_logical_topology")

    def test_contract_rejects_unknown_fields_free_parameters_and_unbound_evidence(self) -> None:
        unknown_document = _document().to_dict()
        unknown_document["sql"] = "select protected"
        free_parameters = _document().to_dict()
        free_parameters["derived_relations"][0]["steps"][0]["parameters"] = {
            "language": "python"
        }
        unbound_evidence = _document().to_dict()
        unbound_evidence["derived_relations"][0]["evidence"][0]["plan_revision"] = "d" * 64
        truncated_population = _document().to_dict()
        truncated_population["derived_relations"][0]["evidence"][0][
            "level"
        ] = "population_tested"

        for payload in (
            unknown_document,
            free_parameters,
            unbound_evidence,
            truncated_population,
        ):
            with self.assertRaises(LogicalTopologyFailure) as error:
                LogicalTopologyDocument.from_dict(payload)
            self.assertEqual(error.exception.code, "invalid_logical_topology")

    def test_store_is_atomic_private_and_rejects_duplicate_json_fields(self) -> None:
        document = _document()
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            store = FileLogicalTopologyStore(Path(temporary_directory) / "topology")
            path = store.save(document)
            stored = path.read_text(encoding="utf-8")
            loaded = store.load(document.graph_name)
            mode = path.stat().st_mode & 0o777
            path.write_text('{"contract_version":"x","contract_version":"y"}')
            with self.assertRaises(LogicalTopologyFailure) as duplicate:
                store.load(document.graph_name)

        self.assertEqual(loaded, document)
        self.assertEqual(mode, 0o600)
        self.assertNotIn('"parameters"', stored)
        self.assertNotIn('"sql"', stored)
        self.assertNotIn('"code"', stored)
        self.assertEqual(duplicate.exception.code, "invalid_logical_topology")

    def test_application_checks_graph_binding_expected_revision_and_stale_graph(self) -> None:
        graph = _graph()
        document = _document(graph)
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            root = Path(temporary_directory)
            graphs = FileGraphStore(root / "graphs")
            topologies = FileLogicalTopologyStore(root / "topology")
            graphs.save(graph)
            saved = save_logical_topology_use_case(
                document,
                graph_store=graphs,
                topology_store=topologies,
            )
            with self.assertRaises(LogicalTopologyFailure) as missing_revision:
                save_logical_topology_use_case(
                    document,
                    graph_store=graphs,
                    topology_store=topologies,
                )
            with self.assertRaises(LogicalTopologyFailure) as stale_revision:
                save_logical_topology_use_case(
                    document,
                    expected_revision="0" * 64,
                    graph_store=graphs,
                    topology_store=topologies,
                )
            reviewed = decide_derived_relation_use_case(
                graph.name,
                "order-items",
                decision="approve",
                reason="The typed output, grain, manifests, and bounded run were reviewed.",
                expected_revision=saved.revision,
                graph_store=graphs,
                topology_store=topologies,
            )
            loaded = load_logical_topology_use_case(
                graph.name,
                graph_store=graphs,
                topology_store=topologies,
            )
            annotated_nodes = tuple(
                replace(
                    node,
                    metadata={
                        **node.metadata,
                        "annotation_review": {"state": "validated"},
                    },
                )
                if node.type == "table"
                else node
                for node in graph.nodes
            )
            annotated = replace(graph, nodes=annotated_nodes)
            graphs.save(annotated)
            still_current = load_logical_topology_use_case(
                graph.name,
                graph_store=graphs,
                topology_store=topologies,
            )
            changed_graph = replace(annotated, catalog="ChangedCatalog")
            graphs.save(changed_graph)
            with self.assertRaises(LogicalTopologyFailure) as stale_graph:
                load_logical_topology_use_case(
                    graph.name,
                    graph_store=graphs,
                    topology_store=topologies,
                )
            rebound = replace(
                reviewed,
                graph_revision=physical_graph_revision(changed_graph),
            )
            with self.assertRaises(LogicalTopologyFailure) as forbidden_rebase:
                save_logical_topology_use_case(
                    rebound,
                    expected_revision=reviewed.revision,
                    graph_store=graphs,
                    topology_store=topologies,
                )

        self.assertEqual(
            missing_revision.exception.code,
            "expected_logical_topology_revision_required",
        )
        self.assertEqual(stale_revision.exception.code, "stale_logical_topology")
        self.assertEqual(reviewed.derived_relations[0].state, "reviewed")
        self.assertEqual(reviewed.derived_relations[0].review.source, "human")
        self.assertEqual(loaded, reviewed)
        self.assertEqual(still_current, reviewed)
        self.assertEqual(stale_graph.exception.code, "logical_topology_graph_revision_mismatch")
        self.assertEqual(
            forbidden_rebase.exception.code,
            "logical_topology_graph_rebase_forbidden",
        )

    def test_application_rejects_cross_object_and_mistyped_passthrough(self) -> None:
        graph = _graph()
        relation = _relation(graph)
        other_field = next(node for node in graph.nodes if node.label == "name")
        cross_object = replace(
            relation,
            output_schema=(
                replace(
                    relation.output_schema[0],
                    source=EndpointRef("graph_field", other_field.id),
                ),
                relation.output_schema[1],
            ),
        )
        mistyped = replace(
            relation,
            output_schema=(
                replace(relation.output_schema[0], data_type="string"),
                relation.output_schema[1],
            ),
        )

        for invalid in (cross_object, mistyped):
            invalid = _rebind_evidence(invalid)
            with self.assertRaises(LogicalTopologyFailure):
                new_logical_topology_document(graph, (invalid,))

    def test_whole_document_import_cannot_self_approve_or_remove_reviewed_history(self) -> None:
        graph = _graph()
        document = _document(graph)
        self_approved = replace(
            document,
            derived_relations=(
                replace(
                    document.derived_relations[0],
                    state="reviewed",
                    review=None,
                ),
            ),
        )
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            root = Path(temporary_directory)
            graphs = FileGraphStore(root / "graphs")
            topologies = FileLogicalTopologyStore(root / "topology")
            graphs.save(graph)
            with self.assertRaises(LogicalTopologyFailure):
                save_logical_topology_use_case(
                    self_approved,
                    graph_store=graphs,
                    topology_store=topologies,
                )
            save_logical_topology_use_case(
                document,
                graph_store=graphs,
                topology_store=topologies,
            )
            reviewed = decide_derived_relation_use_case(
                graph.name,
                "order-items",
                decision="approve",
                reason="Human-reviewed bounded evidence.",
                expected_revision=document.revision,
                graph_store=graphs,
                topology_store=topologies,
            )
            reset_relation = replace(
                reviewed.derived_relations[0],
                state="candidate",
                review=None,
            )
            reset_document = replace(reviewed, derived_relations=(reset_relation,))
            with self.assertRaises(LogicalTopologyFailure) as reset_review:
                save_logical_topology_use_case(
                    reset_document,
                    expected_revision=reviewed.revision,
                    graph_store=graphs,
                    topology_store=topologies,
                )
            emptied = replace(reviewed, derived_relations=())
            with self.assertRaises(LogicalTopologyFailure) as removed:
                save_logical_topology_use_case(
                    emptied,
                    expected_revision=reviewed.revision,
                    graph_store=graphs,
                    topology_store=topologies,
                )

        self.assertEqual(reset_review.exception.code, "immutable_derived_relation")
        self.assertEqual(removed.exception.code, "immutable_derived_relation")

    def test_application_supports_the_shared_runtime_boundary(self) -> None:
        graph = _graph()
        document = _document(graph)
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            runtime = TarelRuntime(Path(temporary_directory) / ".tarel")
            runtime.graph_store().save(graph)

            saved = save_logical_topology_use_case(document, runtime=runtime)
            loaded = load_logical_topology_use_case(graph.name, runtime=runtime)
            stored_path = runtime.root / "logical-topology" / graph.name / "topology.json"
            stored_exists = stored_path.is_file()
            stored_mode = stored_path.stat().st_mode & 0o777

        self.assertEqual(loaded, saved)
        self.assertTrue(stored_exists)
        self.assertEqual(stored_mode, 0o600)

    def test_stale_optional_sidecar_does_not_break_the_graph_view(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            sdk = Tarel(Path(temporary_directory) / ".tarel")
            graph = _graph()
            sdk.runtime.graph_store().save(graph)
            sdk.topology.import_document(_document(graph))
            sdk.runtime.graph_store().save(replace(graph, catalog="ChangedCatalog"))

            payload = sdk.view.graph(graph.name)
            with self.assertRaises(LogicalTopologyFailure) as strict_load:
                sdk.topology.load(graph.name)

        self.assertEqual(strict_load.exception.code, "logical_topology_graph_revision_mismatch")
        self.assertFalse(
            any(item["type"] == "derived_relation" for item in payload["objects"])
        )
        self.assertEqual(
            payload["logical_topology_notices"],
            [
                {
                    "code": "logical_topology_graph_revision_mismatch",
                    "graph": graph.name,
                    "message": (
                        "The physical graph changed; its stale logical-topology sidecar "
                        "was not projected."
                    ),
                }
            ],
        )


def _document(graph=None) -> LogicalTopologyDocument:
    graph = graph or _graph()
    return new_logical_topology_document(graph, (_relation(graph),))


def _relation(graph) -> DerivedRelation:
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
                pointer="",
                output=StepOutput("item", "json", False),
                ordinal_output=StepOutput("item-index", "integer", False),
            ),
            ExtractStep(
                id="extract-product-id",
                input=EndpointRef("step_output", "item"),
                pointer="/product_id",
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
    return _rebind_evidence(relation)


def _rebind_evidence(relation: DerivedRelation) -> DerivedRelation:
    return replace(
        relation,
        evidence=(
            DerivationEvidence(
                id="sample-1",
                level="sample_tested",
                plan_revision=relation.plan_revision,
                input_count=10,
                output_count=12,
                error_count=0,
                input_manifest_sha256=_MANIFEST_A,
                output_manifest_sha256=_MANIFEST_B,
                truncated=True,
                executor=_EXECUTOR,
            ),
        ),
    )


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
                    ),
                    primary_key=("order_id",),
                ),
                CatalogObject(
                    namespace="sales",
                    name="customers",
                    kind="table",
                    fields=(CatalogField("name", 1, "string", False),),
                ),
            ),
        ),
    )
