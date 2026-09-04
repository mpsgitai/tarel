from __future__ import annotations

import json
import shutil
import subprocess
import threading
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphEdge
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.object_families.contracts import (
    FamilyAttribute,
    FamilyField,
    ObjectFamily,
    ObjectFamilyFailure,
    review_family,
)
from tarel.object_families.store import FileObjectFamilyStore
from tarel.ui.presentation import browser_graph, browser_workspace
from tarel.ui.server import TarelUIBackend, UIConfig, UIFailure, _Server
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceSystem, Zone, ZoneMember
from tarel.workspaces.scope import ResolvedScope, ResolvedScopeObject, ScopeSelection


class ObjectFamilyPresentationTests(TestCase):
    @skipUnless(shutil.which("node"), "Node is needed for the bundled Cytoscape focus test")
    def test_selected_family_remains_visible_inside_compound_parents(self) -> None:
        static = Path(__file__).resolve().parents[1] / "src/tarel/ui/static"
        result = subprocess.run(
            ["node", "-e", r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const cytoscape = require(process.argv[1] + '/cytoscape.min.js');
const source = fs.readFileSync(process.argv[1] + '/app.js', 'utf8');
const cy = cytoscape({headless: true, styleEnabled: true,
  elements: [{data:{id:'parent'}}, {data:{id:'family',parent:'parent'}}],
  style: [{selector:'.hidden',style:{display:'none'}}]});
try {
  const code = source.slice(source.indexOf('function focusSelected()'),
    source.indexOf('function selectedObject()'));
  vm.runInNewContext(code + '\nfocusSelected();', {
    state: {cy,selectedId:'family'}, selectedObject: () => ({name:'Family'}), $: () => ({})});
  assert.equal(cy.$id('family').visible(), true);
  assert.equal(cy.$id('parent').visible(), true);
} finally {cy.destroy();}
""", str(static)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_thousand_members_are_not_serialized_before_on_demand_resolution(self) -> None:
        graph = _graph(1_000)
        family = _family(graph)
        before = graph.to_dict()
        payload = browser_graph(graph, family_mode="confirmed_only", object_families=(family,))

        self.assertEqual(len(payload["objects"]), 1)
        self.assertEqual(payload["objects"][0]["type"], "object_family")
        self.assertEqual(payload["objects"][0]["primary_key"], [])
        self.assertEqual(payload["objects"][0]["object_family"]["member_count"], 1_000)
        self.assertEqual(payload["object_families"]["collapsed_member_count"], 1_000)
        self.assertEqual(payload["review"], [])
        encoded = json.dumps(payload)
        self.assertLess(len(encoded), 12_000)
        self.assertNotIn('"member_ids"', encoded)
        self.assertNotIn("sales_00000", encoded)
        self.assertNotIn(family.member_ids[0], encoded)
        self.assertEqual(graph.to_dict(), before)

    def test_off_is_exactly_the_existing_projection(self) -> None:
        graph = _graph()
        baseline = browser_graph(graph)
        self.assertEqual(browser_graph(graph, object_families=(_family(graph),)), baseline)
        self.assertNotIn("object_families", baseline)

    def test_review_policies_rejected_and_stale_do_not_hide_physical_objects(self) -> None:
        graph = _graph()
        reviewed = _family(graph)
        candidate = replace(reviewed, state="candidate", review=None)
        rejected = review_family(candidate, decision="reject", reason="not one family")
        stale = replace(reviewed, graph_revision="0" * 64)
        for family in (candidate, rejected, stale):
            with self.subTest(state=family.state, revision=family.graph_revision):
                payload = browser_graph(
                    graph, family_mode="confirmed_only", object_families=(family,)
                )
                self.assertEqual([item["type"] for item in payload["objects"]], ["table"] * 3)
        exploratory = browser_graph(
            graph, family_mode="include_candidates", object_families=(candidate,)
        )["objects"][0]
        self.assertEqual(exploratory["usage"], "exploratory_only")
        self.assertEqual(exploratory["object_family"]["evidence"]["level"], "schema_only")

    def test_invalid_schema_and_overlapping_families_fail_visibly(self) -> None:
        graph = _graph()
        family = _family(graph)
        invalid = replace(family, schema=(FamilyField("id", "text", False),))
        with self.assertRaises(ObjectFamilyFailure):
            browser_graph(graph, family_mode="confirmed_only", object_families=(invalid,))
        with self.assertRaises(ObjectFamilyFailure) as raised:
            browser_graph(
                graph, family_mode="confirmed_only",
                object_families=(family, replace(family, id="other", name="other")),
            )
        self.assertEqual(raised.exception.code, "object_family_overlap")

    def test_member_edges_are_counted_but_not_promoted_to_family_edges(self) -> None:
        graph = _graph()
        objects = [node for node in graph.nodes if node.type == "table"]
        graph = replace(graph, edges=graph.edges + (
            GraphEdge("example-join", objects[0].id, objects[1].id, "foreign_key", {}),
        ))
        payload = browser_graph(
            graph, family_mode="confirmed_only", object_families=(_family(graph),)
        )
        self.assertEqual(payload["edges"], [])
        self.assertEqual(
            payload["objects"][0]["object_family"]["hidden_details"]["physical_relationships"], 1
        )
        self.assertIn("Disable families", payload["object_families"]["notice"])

    def test_workspace_counts_and_metadata_do_not_leak_members_outside_scope(self) -> None:
        graph = _graph(8, namespaces=True)
        family = _family(graph)
        allowed = family.member_ids[:2]
        workspace, scope = _workspace(graph, allowed)
        # Workspace metadata itself may name members excluded by this scope.
        system = workspace.systems[0]
        workspace = replace(workspace, systems=(replace(system, zones=(Zone(
            name="selected", members=tuple(
                ZoneMember(graph.name, member_id) for member_id in family.member_ids
            ),
        ),)),))
        payload = browser_workspace(
            (graph,), scope, workspace=workspace,
            family_mode="confirmed_only", object_families=(family,),
        )
        self.assertEqual(len(payload["objects"]), 1)
        item = payload["objects"][0]
        self.assertEqual(item["namespace"], "Logical families")
        self.assertEqual(item["object_family"]["member_count"], 2)
        self.assertEqual(payload["scope"]["object_count"], 2)
        self.assertNotIn("objects", payload["scope"])
        zone = payload["workspaces"][0]["systems"][0]["zones"][0]
        self.assertEqual(zone["members"], [])
        self.assertEqual(zone["collapsed_member_count"], 2)
        serialized = json.dumps(payload)
        for member_id in family.member_ids:
            self.assertNotIn(member_id, serialized)

    def test_assets_offer_explicit_modes_and_bounded_lazy_members(self) -> None:
        assets = Path(__file__).parents[1] / "src/tarel/ui/static"
        html = (assets / "index.html").read_text()
        script = (assets / "app.js").read_text()
        for marker in ('id="family-mode"', 'value="confirmed_only"', 'value="include_candidates"'):
            self.assertIn(marker, html)
        for marker in (
            '"/api/families/members"', "limit: 50", "renderFamilyInspector", "exploratory_only",
            "Disable object families before editing zones", 'node[type = "object_family"]',
        ):
            self.assertIn(marker, script)

    @skipUnless(shutil.which("node"), "Node.js is only needed for optional renderer smoke")
    def test_family_inspector_renders_actual_projection_without_browser_dependencies(self) -> None:
        graph = _graph()
        fixture = browser_graph(
            graph, family_mode="confirmed_only", object_families=(_family(graph),)
        )["objects"][0]
        script = Path(__file__).parents[1] / "src/tarel/ui/static/app.js"
        renderer = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
class Element {
  constructor(){this.children=[];this.innerHTML='';this.textContent='';this.dataset={};}
  append(...items){this.children.push(...items);}
  after(...items){this.afterNodes=items;}
  addEventListener(){}
}
const context = vm.createContext({
  document: {
    createElement(){return new Element();},
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll() { return []; },
  },
  fixture: JSON.parse(fs.readFileSync(0, 'utf8')),
});
const script = fs.readFileSync(process.argv[1], 'utf8');
vm.runInContext(fs.readFileSync(require('node:path').join(
  require('node:path').dirname(process.argv[1]), 'logical_metadata.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(require('node:path').join(
  require('node:path').dirname(process.argv[1]), 'optional_details.js'), 'utf8'), context);
vm.runInContext(script.slice(0, script.indexOf('$("#object-search").addEventListener')), context);
vm.runInContext('state.familyMode = "confirmed_only"; renderFamilyInspector(fixture);', context);
process.stdout.write(elements.get('#inspector').innerHTML);
process.stdout.write(JSON.stringify(elements.get('#inspector').children));
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", renderer, str(script)],
            input=json.dumps(fixture), capture_output=True, text=True, check=True, timeout=10,
        )
        self.assertIn("Scope members", result.stdout)
        self.assertIn("Load members", result.stdout)
        self.assertIn("Load logical metadata", result.stdout)
        self.assertIn("optional-details logical-metadata-details", result.stdout)
        self.assertIn("Not loaded", result.stdout)
        self.assertIn("Schema compatibility only", result.stdout)
        self.assertNotIn("undefined", result.stdout)


class ObjectFamilyBackendTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.stack = ExitStack()
        self.graph = _graph(120)
        self.family = _family(self.graph)
        self.graph_store = FileGraphStore(Path(self.temporary.name) / "graphs")
        self.family_store = FileObjectFamilyStore(Path(self.temporary.name) / "families")
        self.graph_store.save(self.graph)
        self.family_store.save(self.family)
        for target, value in (
            ("tarel.object_families.application.FileObjectFamilyStore", self.family_store),
            ("tarel.object_families.application.FileGraphStore", self.graph_store),
            ("tarel.application.FileGraphStore", self.graph_store),
        ):
            self.stack.enter_context(patch(target, return_value=value))
        self.backend = TarelUIBackend(UIConfig(graph=self.graph.name))

    def tearDown(self) -> None:
        self.stack.close()
        self.temporary.cleanup()

    def _request(self, **updates):
        return {
            "graph": self.graph.name, "family_id": self.family.id,
            "revision": self.family.revision, "mode": "confirmed_only", **updates,
        }

    def test_default_does_not_touch_family_store_and_modes_do_not_mutate_backend(self) -> None:
        with patch.object(self.family_store, "list", side_effect=AssertionError("opt-in only")):
            default = self.backend.bootstrap()
        compact = self.backend.mutate("/api/families/view", {"mode": "confirmed_only"})
        self.assertEqual(len(default["objects"]), 120)
        self.assertEqual(len(compact["objects"]), 1)
        self.assertFalse(compact["editable"])
        self.assertEqual(self.backend.bootstrap(), default)

    def test_read_only_member_pages_are_bounded_and_revision_pinned(self) -> None:
        first = self.backend.mutate("/api/families/members", self._request())
        second = self.backend.mutate(
            "/api/families/members", self._request(offset=first["next_offset"])
        )
        self.assertEqual(len(first["members"]), 50)
        self.assertEqual(first["total_members"], 120)
        self.assertEqual(first["next_offset"], 50)
        self.assertFalse(
            {item["object_id"] for item in first["members"]}
            & {item["object_id"] for item in second["members"]}
        )
        self.assertEqual(first["members"][0]["attributes"].keys(), {"partition"})
        for update in ({"revision": "0" * 64}, {"limit": 101}, {"offset": -1}):
            with self.subTest(update=update), self.assertRaises((ObjectFamilyFailure, UIFailure)):
                self.backend.mutate("/api/families/members", self._request(**update))

    def test_member_request_cannot_override_server_workspace_scope(self) -> None:
        allowed = self.family.member_ids[:2]
        _workspace_document, scope = _workspace(self.graph, allowed)
        backend = TarelUIBackend(UIConfig(workspace="estate"))
        with patch.object(backend, "_scope", return_value=scope):
            page = backend.mutate(
                "/api/families/members",
                self._request(allowed_object_ids=list(self.family.member_ids)),
            )
            self.assertEqual(page["total_members"], 2)
            self.assertEqual({item["object_id"] for item in page["members"]}, set(allowed))
            with self.assertRaises(UIFailure) as raised:
                backend.mutate("/api/families/members", self._request(graph="outside"))
            self.assertEqual(raised.exception.code, "graph_outside_scope")

    def test_changed_review_or_graph_invalidates_pending_member_page(self) -> None:
        changed = replace(self.family, state="candidate", review=None)
        self.family_store.save(changed)
        with self.assertRaises(ObjectFamilyFailure) as raised:
            self.backend.mutate("/api/families/members", self._request())
        self.assertEqual(raised.exception.code, "stale_object_family")
        self.family_store.save(self.family)
        self.graph_store.save(_graph(121))
        with self.assertRaises(ObjectFamilyFailure) as raised:
            self.backend.mutate("/api/families/members", self._request())
        self.assertEqual(raised.exception.code, "object_family_graph_revision_mismatch")

    def test_member_http_is_read_only_but_requires_session_token(self) -> None:
        server = _Server(("127.0.0.1", 0), self.backend, "session-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/api/families/members"
        try:
            for token in (None, "session-token"):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["X-Tarel-Token"] = token
                request = Request(url, json.dumps(self._request(limit=2)).encode(), headers)
                if token:
                    with urlopen(request, timeout=3) as response:
                        self.assertEqual(len(json.load(response)["members"]), 2)
                else:
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(request, timeout=3)
                    self.assertEqual(raised.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def _graph(count=3, *, namespaces=False):
    return build_graph_from_catalog("estate", CatalogResult(
        connector="test", source_type="database", catalog="Demo", dialect="sqlite",
        objects=tuple(
            CatalogObject(
                namespace=f"tenant_{index % 2}" if namespaces else "sales",
                name=f"sales_{index:05d}", kind="table",
                fields=(CatalogField("id", 1, "integer", False),), primary_key=("id",),
            ) for index in range(count)
        ),
    ))


def _family(graph):
    candidate = ObjectFamily(
        graph_name=graph.name, graph_revision=physical_graph_revision(graph),
        id="sales-family", name="sales", member_ids=tuple(
            node.id for node in graph.nodes if node.type == "table"
        ), schema=(FamilyField("id", "integer", False),), grain=("id", "partition"),
        attributes=(FamilyAttribute("partition", "object_name", "sales_"),),
        producer="test_harness",
    )
    return review_family(candidate, decision="approve", reason="test-only metadata review")


def _workspace(graph, allowed):
    nodes = graph.node_by_id()
    workspace = WorkspaceDocument(name="estate", systems=(WorkspaceSystem(
        name="analytics", graphs=(graph.name,), zones=(Zone(
            name="selected",
            members=tuple(ZoneMember(graph.name, member_id) for member_id in allowed),
        ),),
    ),))
    scope = ResolvedScope(
        workspace=workspace.name, selection=ScopeSelection(), graph_names=(graph.name,),
        scope_hash="0" * 64, objects=tuple(
            ResolvedScopeObject(
                graph.name, "analytics", None, nodes[member_id].metadata["namespace"],
                member_id, nodes[member_id].label, nodes[member_id].type, ("analytics:selected",),
            ) for member_id in allowed
        ),
    )
    return workspace, scope
