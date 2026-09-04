from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from tarel.discovery.contracts import DiscoveryObservation
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.graph.revision import physical_graph_revision
from tarel.logical_joins.contracts import LogicalJoin
from tarel.logical_joins.store import FileLogicalJoinStore
from tarel.object_bindings import ObjectValueBinding
from tarel.object_bindings.application import save_object_binding_use_case
from tarel.runtime import TarelRuntime
from tarel.semantic_concepts import ConceptBinding, SemanticConcept, SemanticConceptDocument
from tarel.semantic_concepts.application import save_semantic_concepts_use_case
from tarel.topology.application import (
    decide_derived_relation_use_case,
    save_logical_topology_use_case,
)
from tarel.topology.endpoint_contracts import LogicalEndpoint
from tarel.ui.logical_metadata import LogicalMetadataFailure, logical_metadata_use_case
from tests.test_logical_joins import _observation
from tests.test_logical_topology import _document, _graph
from tests.test_object_families_ui import _family
from tests.test_object_families_ui import _graph as _family_graph


class LogicalMetadataUITests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = TarelRuntime.local(Path(self.temporary.name) / ".tarel")
        self.graph = _graph()
        self.runtime.graph_store().save(self.graph)
        self.document = save_logical_topology_use_case(_document(self.graph), runtime=self.runtime)
        self.orders = next(node.id for node in self.graph.nodes if node.label == "sales.orders")
        name = next(node for node in self.graph.nodes if node.label == "name")
        self.customers = name.metadata["object_id"]
        self.physical = LogicalEndpoint(
            "graph_field", self.customers, name.id, physical_graph_revision(self.graph)
        )
        self.derived = LogicalEndpoint(
            "derived_field", "order-items", "product-id", self.document.revision
        )
        concept = SemanticConcept(
            "item",
            "Item identifier",
            "Identifier representation metadata.",
            bindings=(ConceptBinding(self.derived, "code"),),
        )
        save_semantic_concepts_use_case(
            SemanticConceptDocument(
                self.graph.name,
                physical_graph_revision(self.graph),
                (concept,),
            ),
            runtime=self.runtime,
        )
        self.join = LogicalJoin(
            "items-to-names",
            self.graph.name,
            physical_graph_revision(self.graph),
            LogicalJoinProgram((self.derived,), (self.physical,)),
            tuple(
                DiscoveryObservation.from_dict(_observation(phase))
                for phase in ("support", "challenge")
            ),
            "fixture-run",
            "a" * 64,
            "fixture-candidate",
            "coding_agent",
            "PRIVATE_REASON_SENTINEL",
        )
        FileLogicalJoinStore(self.runtime.root / "logical-joins").save(self.join)

    def _metadata(self, object_ids=None, **kwargs):
        return logical_metadata_use_case(
            self.graph.name, object_ids or (self.orders,), runtime=self.runtime, **kwargs
        )

    def test_optional_metadata_contains_only_compact_current_scope_and_usage(self):
        before = self.graph.to_dict()
        result = self._metadata()
        self.assertEqual(len(result["concepts"]), 1)
        self.assertEqual(len(result["logical_joins"]), 1)
        self.assertEqual(result["concepts"][0]["usage"], "exploratory_only")
        self.assertEqual(result["logical_joins"][0]["usage"], "exploratory_only")
        self.assertEqual(result["logical_joins"][0]["evidence"][0]["metrics"]["coverage"], 1.0)
        serialized = json.dumps(result)
        for forbidden in (
            "PRIVATE_REASON_SENTINEL",
            "physical_object_ids",
            "query_hash",
            "pointer",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(self.runtime.graph_store().load(self.graph.name).to_dict(), before)
        confirmed = self._metadata(mode="confirmed_only")
        self.assertEqual(confirmed["concepts"], [])
        self.assertEqual(confirmed["logical_joins"], [])

    def test_complete_endpoint_scope_is_checked_not_just_selected_side(self):
        result = self._metadata(allowed_object_ids=frozenset({self.orders}))
        self.assertEqual(len(result["concepts"]), 1)
        self.assertEqual(result["logical_joins"], [])
        self.assertNotIn(self.customers, json.dumps(result))
        with self.assertRaises(LogicalMetadataFailure):
            self._metadata(allowed_object_ids=frozenset({self.customers}))

    def test_derived_inspector_identity_resolves_source_inside_server_scope(self):
        for prefix in ("logical_relation", "derived_relation"):
            result = self._metadata(
                (f"{prefix}:order-items",), allowed_object_ids=frozenset({self.orders})
            )
            self.assertEqual(len(result["concepts"]), 1)
            self.assertEqual(result["logical_joins"], [])
        with self.assertRaises(LogicalMetadataFailure):
            self._metadata(
                ("logical_relation:order-items",), allowed_object_ids=frozenset({self.customers})
            )

    def test_stale_dependencies_are_visible_omissions_without_stale_payloads(self):
        decide_derived_relation_use_case(
            self.graph.name,
            "order-items",
            decision="approve",
            reason="Metadata reviewed.",
            expected_revision=self.document.revision,
            runtime=self.runtime,
        )
        result = self._metadata()
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["logical_joins"], [])
        codes = {(item["kind"], item["code"]) for item in result["omissions"]}
        self.assertIn(("semantic_concepts", "stale_logical_endpoint"), codes)
        self.assertIn(("logical_joins", "stale_logical_endpoint"), codes)

    def test_family_and_binding_metadata_never_expand_member_lists_or_values(self):
        graph = _family_graph(1000)
        family = _family(graph)
        self.runtime.graph_store().save(graph)
        self.runtime.object_family_store().save(family)
        field = next(node for node in graph.nodes if node.type == "field")
        binding = ObjectValueBinding(
            "partition-binding",
            graph.name,
            LogicalEndpoint(
                "graph_field", field.metadata["object_id"], field.id, physical_graph_revision(graph)
            ),
            LogicalEndpoint("family_attribute", family.id, "partition", family.revision),
            "coding_agent",
            "metadata-fixture",
        )
        save_object_binding_use_case(binding, runtime=self.runtime)
        result = logical_metadata_use_case(
            graph.name, (f"object_family:{family.id}",), runtime=self.runtime
        )
        self.assertEqual(len(result["object_bindings"]), 1)
        self.assertEqual(result["object_bindings"][0]["provenance"]["run_id"], "metadata-fixture")
        serialized = json.dumps(result)
        self.assertNotIn("member_ids", serialized)
        self.assertNotIn(family.member_ids[-1], serialized)
        self.assertLess(len(serialized), 3000)
        narrow = logical_metadata_use_case(
            graph.name,
            (f"object_family:{family.id}",),
            allowed_object_ids=frozenset(family.member_ids[:1]),
            runtime=self.runtime,
        )
        self.assertEqual(narrow["object_bindings"], [])

    def test_selected_concepts_are_bounded_after_relevance_not_before(self):
        old = self.runtime.root / "semantic-concepts" / self.graph.name / "concepts.json"
        from tarel.semantic_concepts.store import FileSemanticConceptStore

        store = FileSemanticConceptStore(self.runtime.root / "semantic-concepts")
        self.assertTrue(old.is_file())
        existing = store.load(self.graph.name)
        unrelated = tuple(
            SemanticConcept(
                f"a-{index}",
                f"Other {index}",
                "Metadata on another physical object.",
                bindings=(ConceptBinding(self.physical, "label"),),
            )
            for index in range(150)
        )
        related = tuple(replace(existing.concepts[0], id=f"item-{index}") for index in range(30))
        save_semantic_concepts_use_case(
            replace(existing, concepts=unrelated + related),
            expected_revision=existing.revision,
            runtime=self.runtime,
        )
        result = self._metadata()
        self.assertEqual(len(result["concepts"]), 20)
        self.assertTrue(result["more_available"]["concepts"])
        self.assertTrue(
            all(item["artifact"]["id"].startswith("item-") for item in result["concepts"])
        )

    @skipUnless(shutil.which("node"), "Node.js is needed for the safe renderer smoke")
    def test_renderer_uses_text_nodes_and_late_responses_cannot_replace_new_inspector(self):
        script = Path(__file__).parents[1] / "src/tarel/ui/static/logical_metadata.js"
        payload = self._metadata()
        payload["concepts"][0]["name"] = "<script>private()</script>"
        result = subprocess.run(
            [
                shutil.which("node"),
                "-e",
                r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
class Element {
  constructor(){this.children=[];this.textContent='';this.isConnected=true;}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  set innerHTML(value){throw new Error('Unsafe HTML renderer');}
}
const container=new Element(); let resolve;
const pending=new Promise(done=>resolve=done);
const context={document:{createElement:()=>new Element(),createDocumentFragment:()=>new Element(),
  querySelector:()=>container},api:()=>pending,state:{selectedId:'old',focusSelection:null,data:{}}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
const payload=JSON.parse(fs.readFileSync(0,'utf8'));
context.renderLogicalMetadata(container,payload);
assert.ok(JSON.stringify(container).includes('<script>private()</script>'));
(async()=>{
  const task=context.loadLogicalMetadata({id:'old',object_id:'table-id',graph:'commerce'});
  container.isConnected=false;container.textContent='New object';context.state.selectedId='new';
  resolve(payload);await task;
  assert.equal(container.textContent,'New object');
})().catch(error=>{console.error(error);process.exitCode=1;});
""",
                str(script),
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
