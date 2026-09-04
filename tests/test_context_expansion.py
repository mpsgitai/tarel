from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from test_logical_topology import _document as derived_document
from test_logical_topology import _graph as derived_graph
from test_object_families import _graph
from test_reference_mapping import _candidate_contract as mapping_candidate
from test_reference_mapping import _graph as mapping_graph

from tarel.cli import main
from tarel.context import ContextFailure
from tarel.context_output import canonical_json
from tarel.expansion import ContextExpansionFailure, ExpansionInput, ExpansionTarget
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.object_bindings import ObjectValueBinding
from tarel.object_families import FamilyAttribute
from tarel.sdk import Tarel
from tarel.semantic_concepts import ConceptBinding, SemanticConcept, SemanticConceptDocument
from tarel.topology.endpoint_contracts import LogicalEndpoint
from tarel.workspaces.core import create_workspace, define_system


class ContextExpansionTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.family = self.sdk.families.propose(
            "commerce",
            "monthly",
            name="monthly_sales",
            members=("sales.sales_2024_01", "sales.sales_2024_02"),
            grain=("month", "sale_id"),
            attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
        )
        self.base = self.sdk.context.graph("commerce", "sales")
        self.source = next(node for node in self.graph.nodes if node.type == "field")

    def _target(self, **options) -> ExpansionTarget:
        return ExpansionTarget(
            "object_family", "commerce", self.family.id, self.family.revision, **options
        )

    def test_warm_object_and_family_expansion_never_load_full_graph(self) -> None:
        header = self.sdk.graph.header("commerce")
        target = ExpansionTarget("object", "commerce", self.family.member_ids[0], header.revision)
        before = self.base.canonical_json()
        with patch.object(FileGraphStore, "load", side_effect=AssertionError("Not a lazy path")):
            result = self.sdk.context.expand(
                self.base, (target, self._target(limit=1)), mode="include_candidates"
            )
        self.assertEqual(result.omissions, ())
        self.assertEqual(result.items[0].metadata["source_revision"], header.revision)
        self.assertEqual(result.items[0].metadata["objects"][0]["id"], target.id)
        self.assertEqual(result.items[1].metadata["next_offset"], 1)
        self.assertEqual(result.items[1].usage, "exploratory_only")
        self.assertEqual(self.base.canonical_json(), before)
        self.assertFalse(any(row[2] for row in result.base_validation))

    def test_private_filters_are_consumed_not_echoed_or_saved(self) -> None:
        target = self._target(handle="PRIVATE_HANDLE_SENTINEL")
        inputs = {
            target.handle: ExpansionInput("a" * 64, filters=(("month", "PRIVATE_VALUE_SENTINEL"),))
        }
        result = self.sdk.context.expand(
            self.base, (target,), inputs=inputs, mode="include_candidates"
        )
        self.assertEqual(result.items[0].metadata["matched_members"], 0)
        text = canonical_json(result.to_dict())
        self.assertNotIn("PRIVATE_", text)
        self.assertIsNone(result.items[0].target.handle)
        self.assertNotIn("PRIVATE_", repr(result))
        self.assertEqual(result.items[0].input_manifest_hash, "a" * 64)
        for path in self.sdk.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE_", path.read_bytes())
        missing = self.sdk.context.expand(self.base, (target,), mode="include_candidates")
        self.assertEqual(missing.omissions, ((0, "expansion_input_missing"),))

    def test_base_identity_currentness_and_scope_are_not_bypassed(self) -> None:
        packet = self.base.to_dict()
        packet["stable"]["graph"]["revision"] = "f" * 64
        with self.assertRaises(ContextFailure):
            self.sdk.context.expand(packet, (self._target(),))
        scoped = self.sdk.context.graph("commerce", "archive", namespace="archive")
        target = ExpansionTarget(
            "object",
            "commerce",
            self.family.member_ids[0],
            self.sdk.graph.header("commerce").revision,
        )
        self.assertEqual(
            self.sdk.context.expand(scoped, (target,)).omissions, ((0, "expansion_outside_scope"),)
        )
        with self.assertRaises(ContextExpansionFailure):
            self.sdk.context.expand(self.base, (self._target(),), max_characters=12)
        changed = replace(self.graph, connector="changed_metadata")
        self.sdk.runtime.graph_store().save(changed)
        with self.assertRaises(ContextExpansionFailure):
            self.sdk.context.expand(self.base, (self._target(),))

    def test_policy_stale_target_and_character_omissions_are_visible(self) -> None:
        self.assertTrue(self.sdk.context.expand(self.base, (self._target(),)).omissions)
        result = self.sdk.context.expand(
            self.base, (replace(self._target(), revision="f" * 64),), mode="include_candidates"
        )
        self.assertEqual(result.omissions[0][1], "stale_object_family")
        tight = self.sdk.context.expand(
            self.base, (self._target(),), mode="include_candidates", max_characters=1000
        )
        self.assertEqual(tight.omissions, ((0, "expansion_character_budget"),))
        self.assertLessEqual(len(canonical_json(tight.to_dict())), 1000)

    def test_workspace_scope_is_authoritatively_revalidated(self) -> None:
        workspace = define_system(
            create_workspace("estate"),
            "sales",
            graph_names=("commerce",),
            graphs={"commerce": self.graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        packet = self.sdk.context.workspace("estate", "sales", schemas=("commerce:archive",))
        result = self.sdk.context.expand(packet, (self._target(),), mode="include_candidates")
        self.assertEqual(result.items[0].metadata["family"]["member_count"], 0)
        self.assertEqual(result.items[0].metadata["members"], [])
        self.assertTrue(result.base_validation[0][2])
        outsider = replace(self._target(), graph="other")
        self.assertEqual(
            self.sdk.context.expand(packet, (outsider,)).omissions,
            ((0, "expansion_outside_scope"),),
        )

    def test_binding_input_resolves_only_object_metadata(self) -> None:
        source = LogicalEndpoint(
            "graph_field",
            self.source.metadata["object_id"],
            self.source.id,
            physical_graph_revision(self.graph),
        )
        binding = self.sdk.bindings.import_document(
            ObjectValueBinding(
                "monthly-routing",
                "commerce",
                source,
                LogicalEndpoint("family_attribute", self.family.id, "month", self.family.revision),
                "harness",
                "query-run",
            )
        )
        target = ExpansionTarget(
            "object_binding", "commerce", binding.id, binding.revision, handle="private"
        )
        result = self.sdk.context.expand(
            self.base,
            (target,),
            mode="include_candidates",
            inputs={"private": ExpansionInput("b" * 64, values=("2024_01", "not-present"))},
        )
        self.assertEqual(result.omissions, ())
        resolution = result.items[0].metadata["resolution"]
        self.assertEqual(resolution["matched_member_count"], 1)
        self.assertEqual(resolution["unmatched_input_count"], 1)
        self.assertNotIn("not-present", canonical_json(result.to_dict()))

    def test_semantic_concept_delta_remains_exploratory(self) -> None:
        endpoint = LogicalEndpoint(
            "graph_field",
            self.source.metadata["object_id"],
            self.source.id,
            physical_graph_revision(self.graph),
        )
        document = SemanticConceptDocument(
            "commerce",
            physical_graph_revision(self.graph),
            (
                SemanticConcept(
                    "sales", "Sales", "Sales identity", bindings=(ConceptBinding(endpoint, "code"),)
                ),
            ),
        )
        self.sdk.concepts.import_document(document)
        target = ExpansionTarget("semantic_concept", "commerce", "sales", document.revision)
        result = self.sdk.context.expand(self.base, (target,), mode="include_candidates")
        self.assertEqual(result.omissions, ())
        self.assertEqual(result.items[0].usage, "exploratory_only")
        self.assertEqual(result.items[0].metadata["bindings"][0]["representation"], "code")
        self.assertTrue(self.sdk.context.expand(self.base, (target,)).omissions)

    def test_derived_plan_and_reference_mapping_expand_without_private_rows(self) -> None:
        for graph, document, kind in (
            (derived_graph(), None, "derived_relation"),
            (mapping_graph(), mapping_candidate(), "reference_mapping"),
        ):
            with self.subTest(kind=kind), TemporaryDirectory() as temporary:
                sdk = Tarel(Path(temporary) / ".tarel")
                sdk.runtime.graph_store().save(graph)
                if kind == "derived_relation":
                    document = derived_document(graph)
                    sdk.topology.import_document(document)
                    target_id = document.derived_relations[0].id
                else:
                    document = replace(
                        document,
                        graph_revision=physical_graph_revision(graph),
                        source_field_id=next(
                            node.id for node in graph.nodes if node.label == "country_code"
                        ),
                        target_field_id=next(
                            node.id for node in graph.nodes if node.label == "region_name"
                        ),
                    )
                    sdk.reference_mapping.import_candidate(document)
                    target_id = document.id
                packet = sdk.context.prefix_graph(graph.name)
                target = ExpansionTarget(kind, graph.name, target_id, document.revision)
                result = sdk.context.expand(packet, (target,), mode="include_candidates")
                self.assertEqual(result.omissions, ())
                self.assertEqual(result.items[0].usage, "exploratory_only")
                self.assertNotIn("mapping_groups", canonical_json(result.to_dict()))

    def test_cli_identical_result_and_partial_exit_code(self) -> None:
        packet_path = self.project / "packet.json"
        packet_path.write_text(self.base.canonical_json())
        previous = Path.cwd()
        out, err = StringIO(), StringIO()
        try:
            os.chdir(self.project)
            with (
                redirect_stdout(out),
                redirect_stderr(err),
                patch("sys.stdin", StringIO(json.dumps([self._target().reference()]))),
            ):
                code = main(["context", "expand", "--packet", str(packet_path), "--requests", "-"])
        finally:
            os.chdir(previous)
        self.assertEqual((code, err.getvalue()), (1, ""))
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["base_packet_hash"], self.base.packet_hash)

    def test_request_contract_rejects_raw_rows_code_and_bad_handles(self) -> None:
        for change in (
            {"sql": "select secret"},
            {"values": ["secret"]},
            {"kind": "python"},
            {"revision": "wrong"},
            {"limit": True},
            {"offset": -1},
        ):
            with self.subTest(change=change), self.assertRaises(ContextExpansionFailure):
                ExpansionTarget.from_dict({**self._target().reference(), **change})
