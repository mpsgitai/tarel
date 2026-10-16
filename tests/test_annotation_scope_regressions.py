"""Regression boundaries from a mixed-field review failure."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.annotations.contracts import AnnotationFailure
from tarel.annotations.review import decide_annotation_scope
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphAnnotation
from tarel.graph.revision import graph_revision
from tarel.sdk import Tarel
from tarel.ui.server import TarelUIBackend, UIConfig, UIFailure


def mixed_graph():
    graph = build_graph_from_catalog(
        "mixed_review",
        CatalogResult(
            connector="test",
            source_type="database",
            catalog="SyntheticAudit",
            dialect="ansi",
            objects=tuple(
                CatalogObject(
                    namespace="audit",
                    name=name,
                    kind="table",
                    fields=(
                        CatalogField("Proposed", 1, "integer", False),
                        CatalogField("Missing", 2, "integer", True),
                    ),
                )
                for name in ("Sales", "Other")
            ),
        ),
    )
    return replace(
        graph,
        nodes=tuple(
            replace(node, annotation=GraphAnnotation(description="Synthetic proposal."))
            if node.type == "table" or (node.type == "field" and node.label == "Proposed")
            else node
            for node in graph.nodes
        ),
    )


class MixedFieldDecisionTests(TestCase):
    def test_approve_reject_and_defer_preserve_missing_fields_and_other_tables(self):
        for state, action in [
            ("validated", "validate"),
            ("rejected", "reject"),
            ("deferred", "defer"),
        ]:
            with self.subTest(state=state):
                graph = mixed_graph()
                before = graph.to_dict()
                table = next(n for n in graph.nodes if n.label == "audit.Sales")
                proposal = next(
                    n
                    for n in graph.nodes
                    if n.type == "field" and n.metadata["object_id"] == table.id and n.annotation
                )
                decided, records = decide_annotation_scope(
                    graph,
                    table.id,
                    state=state,
                    reason="Reviewed in regression test.",
                    include_fields=True,
                )
                self.assertEqual([r.node.id for r in records], [table.id, proposal.id])
                for old, new in zip(graph.nodes, decided.nodes, strict=True):
                    if old.id in {table.id, proposal.id}:
                        self.assertEqual(new.annotation.state, state)
                        self.assertEqual(new.annotation.description, old.annotation.description)
                        self.assertEqual(new.annotation.provenance, old.annotation.provenance)
                        event = new.metadata["annotation_review"]["events"][-1]
                        self.assertEqual(event["action"], action)
                        self.assertEqual(event["reason"], "Reviewed in regression test.")
                    else:
                        self.assertEqual(
                            new, old, f"Unrelated or missing proposal changed: {old.id}"
                        )
                self.assertEqual(graph.to_dict(), before, "Input graph was mutated")

    def test_table_only_decision_leaves_existing_field_proposal_pending(self):
        graph = mixed_graph()
        decided, records = decide_annotation_scope(
            graph,
            "audit.Sales",
            state="validated",
            reason="Table only.",
            include_fields=False,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(
            [n for n in decided.nodes if n.type == "field"],
            [n for n in graph.nodes if n.type == "field"],
        )

    def test_no_field_proposals_still_allows_the_table_decision(self):
        graph = mixed_graph()
        graph = replace(
            graph,
            nodes=tuple(
                replace(n, annotation=None) if n.type == "field" else n for n in graph.nodes
            ),
        )
        decided, records = decide_annotation_scope(
            graph,
            "audit.Sales",
            state="validated",
            reason="No field proposals.",
            include_fields=True,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].node.annotation.state, "validated")
        self.assertTrue(all(n.annotation is None for n in decided.nodes if n.type == "field"))

    def test_missing_table_proposal_is_not_implicitly_created(self):
        graph = mixed_graph()
        graph = replace(
            graph,
            nodes=tuple(
                replace(n, annotation=None) if n.label == "audit.Sales" else n for n in graph.nodes
            ),
        )
        with self.assertRaises(AnnotationFailure) as raised:
            decide_annotation_scope(
                graph,
                "audit.Sales",
                state="validated",
                reason="Missing table proposal.",
                include_fields=True,
            )
        self.assertEqual(raised.exception.code, "annotation_not_found")

    def test_ui_decision_persists_then_rejects_stale_revision_without_extra_changes(self):
        with TemporaryDirectory() as directory:
            sdk = Tarel(Path(directory) / "state")
            graph = mixed_graph()
            sdk.runtime.graph_store().save(graph)
            backend = TarelUIBackend(UIConfig(graph=graph.name, editable=True), runtime=sdk.runtime)
            payload = dict(
                reference="audit.Sales",
                state="validated",
                reason="UI regression.",
                include_fields=True,
                revision=graph_revision(graph),
            )
            result = backend.mutate("/api/annotation/decision", payload)
            persisted = sdk.runtime.graph_store().load(graph.name)
            self.assertEqual(result["revision"], graph_revision(persisted))
            self.assertNotEqual(result["revision"], payload["revision"])
            self.assertEqual(len(result["records"]), 2)
            review = backend.mutate("/api/review/view", {})
            record = next(r for r in review["review"] if r["label"] == "audit.Sales")
            self.assertEqual(record["state"], "validated")
            self.assertEqual(record["pending_field_count"], 0)
            self.assertEqual(record["missing_field_count"], 1)
            with self.assertRaises(UIFailure) as raised:
                backend.mutate("/api/annotation/decision", {**payload, "state": "rejected"})
            self.assertEqual(raised.exception.code, "stale_graph")
            self.assertEqual(sdk.runtime.graph_store().load(graph.name), persisted)

    def test_readonly_ui_cannot_apply_the_new_scope_decision(self):
        with TemporaryDirectory() as directory:
            sdk = Tarel(Path(directory) / "state")
            graph = mixed_graph()
            sdk.runtime.graph_store().save(graph)
            backend = TarelUIBackend(
                UIConfig(graph=graph.name, editable=False), runtime=sdk.runtime
            )
            with self.assertRaises(UIFailure):
                backend.mutate(
                    "/api/annotation/decision",
                    dict(
                        reference="audit.Sales",
                        state="validated",
                        reason="Read-only.",
                        include_fields=True,
                        revision=graph_revision(graph),
                    ),
                )
            self.assertEqual(sdk.runtime.graph_store().load(graph.name), graph)
