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

from tarel.focus.contracts import FocusDocument, FocusFailure, FocusHop, FocusMember, FocusSource
from tarel.focus.core import focus_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.object_families.store import FileObjectFamilyStore
from tarel.ui.presentation import browser_graph, browser_workspace, family_view_scope_revision
from tarel.ui.server import TarelUIBackend, UIConfig, UIFailure, _Server
from tests.test_object_families_ui import _family, _graph, _workspace


def _focus(graph, name, member_ids):
    nodes = graph.node_by_id()
    members = tuple(FocusMember(
        id=f"graph:{graph.name}:{identifier}", reference=nodes[identifier].label,
        name=nodes[identifier].label, kind="table", source=f"graph:{graph.name}",
        depth=index, reasons=("seed",) if not index else ("upstream",), origin=True,
    ) for index, identifier in enumerate(member_ids))
    return FocusDocument(
        name=name, seed=members[0].reference, seed_id=members[0].id, max_hops=12,
        states=("validated",),
        sources=(FocusSource("graph", graph.name, focus_graph_revision(graph)),),
        members=members,
        hops=tuple(FocusHop(
            id=f"hop-{index}", depth=index, source_id=member.id,
            target_id=members[0].id, relation="reads_from", state="validated", lineage=None,
        ) for index, member in enumerate(members[1:], start=1)),
        warnings=(), truncated=False,
    )


class FamilyFocusProjectionTests(TestCase):
    def test_focus_is_applied_before_collapse_and_hops_are_not_rewritten(self):
        graph = _graph(1000)
        family = _family(graph)
        focus = _focus(graph, "report", family.member_ids[:3])
        payload = browser_graph(
            graph, family_mode="confirmed_only", object_families=(family,),
            focus_documents=(focus,),
        )
        self.assertEqual(len(payload["objects"]), 1)
        item = payload["objects"][0]
        self.assertEqual(item["object_family"]["member_count"], 3)
        self.assertEqual(payload["object_families"]["collapsed_member_count"], 3)
        selection = payload["focus_selection"]
        self.assertEqual(selection["object_ids"], [item["id"]])
        self.assertEqual(selection["hidden_member_count"], 3)
        self.assertEqual(selection["hidden_edge_count"], 2)
        self.assertEqual(selection["edges"], [])
        self.assertEqual(selection["origins"], [])
        self.assertEqual(payload["edges"], [])
        serialized = json.dumps(payload)
        self.assertLess(len(serialized), 12000)
        for member_id in family.member_ids:
            self.assertNotIn(member_id, serialized)
        self.assertNotIn("sales_00000", serialized)

    def test_multiple_focuses_are_union_then_intersected_with_workspace(self):
        graph = _graph(8)
        family = _family(graph)
        first = _focus(graph, "first-report", family.member_ids[:4])
        second = _focus(graph, "second-cube", family.member_ids[3:])
        workspace, scope = _workspace(graph, family.member_ids[2:5])
        payload = browser_workspace(
            (graph,), scope, workspace=workspace, family_mode="confirmed_only",
            object_families=(family,), focus_documents=(first, second),
        )
        self.assertEqual(payload["objects"][0]["object_family"]["member_count"], 3)
        self.assertEqual(payload["scope"]["object_count"], 3)
        self.assertEqual(payload["focus_selection"]["hidden_member_count"], 3)
        member = payload["focus_selection"]["members"][0]
        self.assertEqual(member["focuses"], ["first-report", "second-cube"])
        self.assertNotIn("member_ids", json.dumps(payload))

    def test_unrelated_focus_cannot_make_family_visible_in_workspace(self):
        graph = _graph(5)
        family = _family(graph)
        workspace, scope = _workspace(graph, family.member_ids[:2])
        payload = browser_workspace(
            (graph,), scope, workspace=workspace, family_mode="confirmed_only",
            object_families=(family,),
            focus_documents=(_focus(graph, "outside", family.member_ids[2:]),),
        )
        self.assertEqual(payload["objects"], [])
        self.assertEqual(payload["scope"]["object_count"], 0)
        self.assertEqual(payload["focus_selection"]["members"], [])
        self.assertEqual(payload["focus_selection"]["hidden_member_count"], 0)

    def test_policy_does_not_change_with_focus_and_default_remains_exact(self):
        graph = _graph(4)
        family = replace(_family(graph), state="candidate", review=None)
        focus = _focus(graph, "report", family.member_ids[:2])
        base = browser_graph(graph)
        self.assertEqual(base, browser_graph(graph, focus_documents=()))
        payload = browser_graph(
            graph, family_mode="confirmed_only", object_families=(family,),
            focus_documents=(focus,),
        )
        self.assertEqual([item["type"] for item in payload["objects"]], ["table", "table"])
        exploratory = browser_graph(
            graph, family_mode="include_candidates", object_families=(family,),
            focus_documents=(focus,),
        )
        self.assertEqual(exploratory["objects"][0]["usage"], "exploratory_only")

    def test_scope_revision_is_order_independent_and_pins_source_and_focus(self):
        graph = _graph(4)
        family = _family(graph)
        first = _focus(graph, "first", family.member_ids[:2])
        second = _focus(graph, "second", family.member_ids[2:])
        revision = family_view_scope_revision((graph,), (first, second))
        self.assertEqual(revision, family_view_scope_revision((graph,), (second, first)))
        self.assertNotEqual(revision, family_view_scope_revision((graph,), (first,)))
        self.assertNotEqual(revision, family_view_scope_revision((_graph(5),), (first, second)))


class FamilyFocusBackendTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.graph = _graph(12)
        self.family = _family(self.graph)
        self.focus = _focus(self.graph, "sales-report", self.family.member_ids[:4])
        self.other = _focus(self.graph, "sales-cube", self.family.member_ids[3:8])
        self.focuses = {self.focus.name: self.focus, self.other.name: self.other}
        self.graph_store = FileGraphStore(Path(self.temporary.name) / "graphs")
        family_store = FileObjectFamilyStore(Path(self.temporary.name) / "families")
        self.graph_store.save(self.graph)
        family_store.save(self.family)
        for target, value in (
            ("tarel.object_families.application.FileObjectFamilyStore", family_store),
            ("tarel.object_families.application.FileGraphStore", self.graph_store),
            ("tarel.application.FileGraphStore", self.graph_store),
        ):
            self.stack.enter_context(patch(target, return_value=value))
        self.stack.enter_context(patch(
            "tarel.ui.server.list_focuses_use_case", side_effect=lambda: tuple(self.focuses),
        ))
        self.stack.enter_context(patch(
            "tarel.ui.server.load_focus_use_case", side_effect=self.focuses.__getitem__,
        ))
        self.backend = TarelUIBackend(UIConfig(graph=self.graph.name))

    def _view(self, names=None):
        return self.backend.mutate("/api/families/view", {
            "mode": "confirmed_only", "focuses": names or [self.focus.name],
        })

    def _request(self, view, **updates):
        return {
            "graph": self.graph.name, "family_id": self.family.id,
            "revision": self.family.revision, "mode": "confirmed_only",
            "focuses": view["focus_selection"]["focuses"],
            "scope_revision": view["object_families"]["scope_revision"],
            **updates,
        }

    def test_bootstrap_accepts_configured_focus_and_pages_use_same_scope(self):
        self.backend = TarelUIBackend(UIConfig(
            graph=self.graph.name, family_mode="confirmed_only", focuses=(self.focus.name,),
        ))
        view = self.backend.bootstrap()
        self.assertEqual(view["objects"][0]["object_family"]["member_count"], 4)
        first = self.backend.mutate("/api/families/members", self._request(view, limit=2))
        second = self.backend.mutate("/api/families/members", self._request(view, offset=2))
        self.assertEqual(first["total_members"], 4)
        self.assertEqual(first["scope_revision"], view["object_families"]["scope_revision"])
        self.assertEqual(
            {item["object_id"] for item in first["members"] + second["members"]},
            set(self.family.member_ids[:4]),
        )

    def test_workspace_intersection_cannot_be_overridden_by_client_ids(self):
        workspace, scope = _workspace(self.graph, self.family.member_ids[2:6])
        self.backend = TarelUIBackend(UIConfig(workspace="estate"))
        with (
            patch.object(self.backend, "_scope", return_value=scope),
            patch("tarel.ui.server.load_workspace_use_case", return_value=workspace),
        ):
            view = self._view([self.focus.name, self.other.name])
            page = self.backend.mutate("/api/families/members", self._request(
                view, allowed_object_ids=list(self.family.member_ids),
            ))
        self.assertEqual(page["total_members"], 4)
        self.assertEqual({item["object_id"] for item in page["members"]}, set(scope_id.object_id
                         for scope_id in scope.objects))

    def test_pending_page_fails_when_focus_changed_or_revision_missing(self):
        view = self._view()
        for updates in (
            {"focuses": [self.other.name]}, {"scope_revision": None},
            {"scope_revision": "0" * 64},
        ):
            with self.subTest(updates=updates), self.assertRaises(UIFailure) as raised:
                self.backend.mutate("/api/families/members", self._request(view, **updates))
            self.assertEqual(raised.exception.code, "stale_object_family_scope")
            self.assertEqual(raised.exception.status, 409)

    def test_updated_focus_document_is_reloaded_not_cached(self):
        view = self._view()
        self.focuses[self.focus.name] = _focus(
            self.graph, self.focus.name, self.family.member_ids[1:4],
        )
        with self.assertRaises(UIFailure) as raised:
            self.backend.mutate("/api/families/members", self._request(view))
        self.assertEqual(raised.exception.code, "stale_object_family_scope")

    def test_unknown_duplicate_and_stale_focus_are_visible_errors(self):
        for names, code in ((["unknown"], "focus_outside_scope"),
                            ([self.focus.name] * 2, "duplicate_focus")):
            with self.subTest(names=names), self.assertRaises(UIFailure) as raised:
                self._view(names)
            self.assertEqual(raised.exception.code, code)
        self.graph_store.save(_graph(13))
        with self.assertRaises(FocusFailure) as raised:
            self._view()
        self.assertEqual(raised.exception.code, "focus_stale")

    def test_stale_page_http_returns_conflict_without_member_payload(self):
        view = self._view()
        server = _Server(("127.0.0.1", 0), self.backend, "session-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/families/members",
                json.dumps(self._request(view, focuses=[self.other.name])).encode(),
                {"Content-Type": "application/json", "X-Tarel-Token": "session-token"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 409)
            result = json.load(raised.exception)
            self.assertEqual(result["error"]["code"], "stale_object_family_scope")
            self.assertNotIn("members", result)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class FamilyFocusScriptTests(TestCase):
    @skipUnless(shutil.which("node"), "Node.js is needed for the UI state regression")
    def test_apply_focus_uses_backend_projection_and_clear_reloads(self):
        script = Path(__file__).parents[1] / "src/tarel/ui/static/app.js"
        result = subprocess.run([shutil.which("node"), "-e", r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const state = {familyMode:'confirmed_only',focusNames:new Set(['report','cube']),trace:{}};
const calls = [];
const context = {state,load:async (...args) => calls.push(args),setFooter:()=>{},toast:()=>{}};
vm.runInNewContext(source.slice(source.indexOf('async function applyFocuses()'),
  source.indexOf('function focusMembership(')), context);
(async () => {
  await context.applyFocuses();
  assert.equal(JSON.stringify(calls[0]), JSON.stringify(['confirmed_only',['cube','report']]));
  await context.clearFocuses();
  assert.equal(JSON.stringify(calls[1]), JSON.stringify(['confirmed_only',[]]));
  assert.equal(state.trace, null);
})().catch(error => {console.error(error); process.exitCode = 1;});
""", str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
