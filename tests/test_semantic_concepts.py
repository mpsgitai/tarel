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
from tarel.graph.revision import physical_graph_revision
from tarel.object_families.contracts import review_family
from tarel.sdk import Tarel
from tarel.semantic_concepts import (
    ConceptBinding,
    ConceptReview,
    SemanticConcept,
    SemanticConceptDocument,
    SemanticConceptFailure,
)
from tarel.semantic_concepts.application import (
    find_semantic_concepts_use_case,
    load_semantic_concepts_use_case,
    review_semantic_concept_use_case,
    save_semantic_concepts_use_case,
)
from tarel.semantic_concepts.store import FileSemanticConceptStore
from tarel.topology.endpoint_contracts import LogicalEndpoint, LogicalEndpointFailure
from tests.test_logical_topology import _graph
from tests.test_object_families_ui import _family
from tests.test_object_families_ui import _graph as _family_graph


class SemanticConceptTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.runtime = self.sdk.runtime
        self.graph = _graph()
        self.runtime.graph_store().save(self.graph)
        field = next(node for node in self.graph.nodes if node.label == "order_id")
        self.endpoint = LogicalEndpoint(
            "graph_field",
            field.metadata["object_id"],
            field.id,
            physical_graph_revision(self.graph),
        )
        self.concept = SemanticConcept(
            "order",
            "Order",
            "Technical representation of a commercial order.",
            bindings=(ConceptBinding(self.endpoint, "code"),),
            evidence_hashes=("a" * 64,),
        )

    def _document(self, *concepts):
        return SemanticConceptDocument(
            self.graph.name,
            physical_graph_revision(self.graph),
            tuple(concepts) or (self.concept,),
        )

    def _save(self, document, **kwargs):
        return save_semantic_concepts_use_case(document, runtime=self.runtime, **kwargs)

    def _review(self, document, concept_id="order", decision="approve"):
        return review_semantic_concept_use_case(
            document.graph_name,
            concept_id,
            decision=decision,
            reason="Metadata reviewed.",
            expected_revision=document.revision,
            runtime=self.runtime,
        )

    def _find(self, **kwargs):
        return find_semantic_concepts_use_case(self.graph.name, runtime=self.runtime, **kwargs)

    def _cli(self, args, stdin=""):
        previous = Path.cwd()
        output, errors = StringIO(), StringIO()
        from unittest.mock import patch

        try:
            os.chdir(self.project)
            with (
                redirect_stdout(output),
                redirect_stderr(errors),
                patch("sys.stdin", StringIO(stdin)),
            ):
                status = main(args)
        finally:
            os.chdir(previous)
        return status, output.getvalue(), errors.getvalue()

    def test_roundtrip_is_revision_pinned_and_does_not_change_physical_behavior(self):
        before_graph = self.graph.to_dict()
        before_context = self.sdk.context.graph(self.graph.name, "orders").canonical_json()
        document = self._save(self._document())
        self.assertEqual(
            load_semantic_concepts_use_case(
                self.graph.name,
                runtime=self.runtime,
            ),
            document,
        )
        self.assertEqual(SemanticConceptDocument.from_dict(document.to_dict()), document)
        self.assertEqual(self.runtime.graph_store().load(self.graph.name).to_dict(), before_graph)
        self.assertEqual(
            self.sdk.context.graph(self.graph.name, "orders").canonical_json(), before_context
        )
        stored = FileSemanticConceptStore(self.runtime.root / "semantic-concepts").path(
            self.graph.name
        )
        self.assertEqual(stored.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self._find(), ())
        candidate = self._find(mode="include_candidates")[0].to_dict()
        self.assertEqual(candidate["usage"], "exploratory_only")
        self.assertNotIn("evidence_hashes", candidate)
        self.assertNotIn("review", candidate)
        reviewed = self._review(document)
        found = self._find(query="commercial", endpoint=self.endpoint)[0].to_dict()
        self.assertEqual(found["usage"], "confirmed")
        self.assertEqual(found["artifact"]["revision"], reviewed.revision)
        self.assertEqual(found["bindings"][0]["representation"], "code")
        self.assertIn("not equality", found["notice"])

    def test_multiple_parents_are_supported_without_implying_join_or_rollup(self):
        first = SemanticConcept("commercial", "Commercial", "Commercial information.")
        second = SemanticConcept("technical", "Technical", "Technical information.")
        child = replace(self.concept, parent_ids=(first.id, second.id))
        document = self._save(self._document(child, first, second))
        document = self._review(document, "order")
        self.assertEqual(self._find(query="order"), ())
        self.assertEqual(
            self._find(query="order", mode="include_candidates")[0].usage, "exploratory_only"
        )
        document = self._review(document, first.id)
        self.assertEqual(self._find(query="order"), ())
        self._review(document, second.id)
        found = self._find(query="order")[0].to_dict()
        self.assertEqual(found["parent_ids"], ["commercial", "technical"])
        self.assertEqual(found["usage"], "confirmed")
        self.assertNotIn("edges", found)
        self.assertNotIn("rollup", found["bindings"][0])

    def test_rejected_parent_excludes_descendants_even_with_exploratory_policy(self):
        parent = SemanticConcept("commercial", "Commercial", "Commercial information.")
        child = replace(self.concept, parent_ids=(parent.id,))
        document = self._save(self._document(parent, child))
        self._review(document, parent.id, "reject")
        self.assertEqual(self._find(mode="include_candidates"), ())

    def test_cycle_unknown_parent_self_reference_and_duplicate_bindings_fail(self):
        parent = SemanticConcept("parent", "Parent", "Parent concept.", parent_ids=("order",))
        with self.assertRaises(SemanticConceptFailure):
            self._document(parent, replace(self.concept, parent_ids=(parent.id,)))
        with self.assertRaises(SemanticConceptFailure):
            self._document(replace(self.concept, parent_ids=("missing",)))
        for change in (
            {"parent_ids": ("order",)},
            {"bindings": self.concept.bindings * 2},
            {"parent_ids": ("parent", "parent")},
        ):
            with self.subTest(change=change), self.assertRaises(SemanticConceptFailure):
                replace(self.concept, **change)

    def test_deep_hierarchy_uses_iterative_validation_and_review_closure(self):
        concepts = tuple(
            SemanticConcept(
                f"level-{index}",
                f"Level {index}",
                "Metadata level.",
                parent_ids=(f"level-{index - 1}",) if index else (),
            )
            for index in range(1100)
        )
        document = self._save(self._document(*concepts))
        self.assertEqual(len(document.concepts), 1100)
        found = self._find(query="level-1099", mode="include_candidates")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].usage, "exploratory_only")

    def test_new_import_cannot_forge_review_and_reviewed_records_are_immutable(self):
        forged = replace(self.concept, state="reviewed", review=ConceptReview("approve", "Forged"))
        with self.assertRaises(SemanticConceptFailure) as raised:
            self._save(self._document(forged))
        self.assertEqual(raised.exception.code, "invalid_semantic_concepts_import")
        document = self._save(self._document())
        reviewed = self._review(document)
        changed = replace(reviewed, concepts=(replace(reviewed.concepts[0], name="Changed"),))
        for incoming in (changed, replace(reviewed, concepts=())):
            with self.assertRaises(SemanticConceptFailure) as raised:
                self._save(incoming, expected_revision=reviewed.revision)
            self.assertEqual(raised.exception.code, "immutable_semantic_concept")

    def test_candidate_replacement_requires_revision_and_does_not_smuggle_review(self):
        document = self._save(self._document())
        with self.assertRaises(SemanticConceptFailure):
            self._review(document, {})
        changed = replace(document, concepts=(replace(self.concept, name="Order identity"),))
        for revision in (None, "0" * 64):
            with self.subTest(revision=revision), self.assertRaises(SemanticConceptFailure):
                self._save(changed, expected_revision=revision)
        saved = self._save(changed, expected_revision=document.revision)
        self.assertNotEqual(saved.revision, document.revision)
        with self.assertRaises(SemanticConceptFailure):
            self._review(document)

    def test_stale_physical_or_logical_endpoints_are_visible_errors_not_empty_results(self):
        bad = replace(self.endpoint, revision="0" * 64)
        with self.assertRaises(LogicalEndpointFailure):
            self._save(
                self._document(replace(self.concept, bindings=(ConceptBinding(bad, "code"),)))
            )
        self._save(self._document())
        changed = replace(
            self.graph,
            nodes=tuple(
                replace(node, metadata={**node.metadata, "data_type": "BIGINT"})
                if node.id == self.endpoint.field_id
                else node
                for node in self.graph.nodes
            ),
        )
        self.runtime.graph_store().save(changed)
        with self.assertRaises(SemanticConceptFailure) as raised:
            self._find(mode="include_candidates")
        self.assertEqual(raised.exception.code, "semantic_concepts_graph_revision_mismatch")

    def test_reviewed_concept_does_not_confirm_candidate_family_dependency(self):
        graph = _family_graph(1000)
        family = replace(_family(graph), state="candidate", review=None)
        self.runtime.graph_store().save(graph)
        self.runtime.object_family_store().save(family)
        endpoint = LogicalEndpoint("family_attribute", family.id, "partition", family.revision)
        concept = replace(self.concept, bindings=(ConceptBinding(endpoint, "code"),))
        document = self._save(
            SemanticConceptDocument(
                graph.name,
                physical_graph_revision(graph),
                (concept,),
            )
        )
        self._review(document)
        self.assertEqual(find_semantic_concepts_use_case(graph.name, runtime=self.runtime), ())
        found = find_semantic_concepts_use_case(
            graph.name,
            mode="include_candidates",
            runtime=self.runtime,
        )[0].to_dict()
        self.assertEqual(found["state"], "reviewed")
        self.assertEqual(found["usage"], "exploratory_only")
        self.assertNotIn("physical_object_ids", json.dumps(found))
        self.assertNotIn(family.member_ids[0], json.dumps(found))
        self.runtime.object_family_store().save(
            review_family(
                family,
                decision="approve",
                reason="Reviewed metadata.",
            )
        )
        with self.assertRaises(LogicalEndpointFailure) as raised:
            find_semantic_concepts_use_case(
                graph.name, mode="include_candidates", runtime=self.runtime
            )
        self.assertEqual(raised.exception.code, "stale_logical_endpoint")

    def test_unknown_fields_private_values_duplicate_json_and_tampered_revision_rejected(self):
        payload = self._document().to_dict()
        for change in (
            {"sql": "private query"},
            {"mapping_groups": [[1, 2]]},
            {"revision": "0" * 64},
        ):
            with self.subTest(change=change), self.assertRaises(SemanticConceptFailure):
                SemanticConceptDocument.from_dict({**payload, **change})
        status, _, errors = self._cli(
            ["concept", "import", "--source", "-"], '{"concepts":[],"concepts":[]}'
        )
        self.assertEqual(status, 2)
        self.assertIn("invalid_semantic_concepts", errors)
        self.assertFalse(
            FileSemanticConceptStore(self.runtime.root / "semantic-concepts").exists(
                self.graph.name,
            )
        )

    def test_cli_sdk_import_review_find_and_export_use_same_application_path(self):
        status, output, errors = self._cli(
            ["concept", "import", "--source", "-", "--format", "json"],
            json.dumps(self._document().to_dict()),
        )
        self.assertEqual(status, 0, errors)
        imported = json.loads(output)
        loaded = self.sdk.concepts.load(self.graph.name)
        self.assertEqual(loaded.revision, imported["revision"])
        self.sdk.concepts.review(
            self.graph.name,
            "order",
            decision="approve",
            reason="Metadata reviewed.",
            expected_revision=loaded.revision,
        )
        sdk = self.sdk.concepts.find(self.graph.name, query="order")
        status, output, errors = self._cli(
            [
                "concept",
                "find",
                self.graph.name,
                "order",
                "--format",
                "json",
            ]
        )
        self.assertEqual(status, 0, errors)
        self.assertEqual(json.loads(output)["matches"], [item.to_dict() for item in sdk])
        status, output, errors = self._cli(["concept", "show", self.graph.name, "--format", "json"])
        self.assertEqual(status, 0, errors)
        self.assertEqual(
            SemanticConceptDocument.from_dict(json.loads(output)),
            self.sdk.concepts.load(self.graph.name),
        )

    def test_bounded_search_absence_and_invalid_args_are_explicit(self):
        self.assertEqual(self._find(), ())
        self._save(self._document())
        for arguments in (
            {"limit": 0},
            {"limit": True},
            {"limit": 101},
            {"query": 123},
            {"mode": "magic"},
            {"endpoint": {}},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SemanticConceptFailure):
                self._find(**arguments)
        self.assertEqual(self._find(query="does-not-exist", mode="include_candidates"), ())

    def test_exact_concept_id_is_not_shadowed_by_many_substring_matches(self):
        concepts = tuple(replace(self.concept, id=f"order-{index}") for index in range(250))
        self._save(self._document(*concepts))
        found = self._find(concept_id="order-249", mode="include_candidates", limit=1)
        self.assertEqual([item.concept.id for item in found], ["order-249"])
        status, output, errors = self._cli(
            [
                "concept",
                "find",
                self.graph.name,
                "--concept-id",
                "order-249",
                "--mode",
                "include_candidates",
                "--format",
                "json",
            ]
        )
        self.assertEqual(status, 0, errors)
        self.assertEqual(json.loads(output)["matches"][0]["artifact"]["id"], "order-249")
        self.assertEqual(self._find(concept_id="missing", mode="include_candidates"), ())
        with self.assertRaises(SemanticConceptFailure):
            self._find(concept_id="../private")

    def test_scope_checks_complete_parent_endpoint_closure(self):
        outside_field = next(
            node
            for node in self.graph.nodes
            if node.type == "field" and node.metadata["object_id"] != self.endpoint.object_id
        )
        outside_endpoint = LogicalEndpoint(
            "graph_field",
            outside_field.metadata["object_id"],
            outside_field.id,
            physical_graph_revision(self.graph),
        )
        parent = SemanticConcept(
            "parent",
            "Parent",
            "A broader concept.",
            bindings=(ConceptBinding(outside_endpoint, "code"),),
        )
        child = replace(self.concept, parent_ids=(parent.id,))
        self._save(self._document(parent, child))
        allowed = frozenset({self.endpoint.object_id})
        self.assertEqual(
            self._find(concept_id="order", mode="include_candidates", allowed_object_ids=allowed),
            (),
        )
        visible = self._find(
            concept_id="order",
            mode="include_candidates",
            allowed_object_ids=allowed | {outside_endpoint.object_id},
        )
        self.assertEqual([item.concept.id for item in visible], ["order"])
        with self.assertRaises(SemanticConceptFailure):
            self._find(allowed_object_ids=list(allowed))
