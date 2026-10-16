"""Bound repeated reads without weakening workspace and focus validation."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.focus.contracts import FocusFailure
from tarel.graph.contracts import GraphDocument, GraphEdge
from tarel.graph.revision import graph_revision
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime
from tarel.ui.server import TarelUIBackend, UIConfig
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceFailure
from tarel.workspaces.core import validate_system_references
from tests.test_ui import _focus, _graph


class UILoadingTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runtime = TarelRuntime.local(Path(temporary.name))
        self.graph = _graph()
        self.copy = replace(self.graph, name="sales-copy")
        store = self.runtime.graph_store()
        store.save(self.graph)
        store.save(self.copy)
        self.runtime.focus_store().save(_focus("report", self.graph, include_dimension=True))
        objects = [node for node in self.graph.nodes if node.type == "table"]
        self.workspace = WorkspaceDocument.from_dict({
            "contract_version": "tarel.workspace.v0.1",
            "name": "enterprise", "description": None,
            "systems": [{
                "name": "analytics", "description": None,
                "graphs": [self.graph.name, self.copy.name],
                "areas": [{"name": "warehouse", "description": None, "schemas": [
                    {"graph": name, "namespace": "mart"}
                    for name in (self.graph.name, self.copy.name)
                ]}],
                "zones": [{
                    "name": f"zone-{i}", "description": None,
                    "members": [{"graph": self.graph.name, "object_id": node.id}
                                for node in objects],
                } for i in range(20)],
            }],
        })
        self.runtime.workspace_store().save(self.workspace)
        self.backend = TarelUIBackend(UIConfig(workspace="enterprise"), runtime=self.runtime)

    def test_zone_validation_work_is_bounded_by_graphs_not_memberships(self) -> None:
        with patch.object(
            GraphDocument, "node_by_id", autospec=True, side_effect=GraphDocument.node_by_id,
        ) as reads:
            validate_system_references(
                self.workspace.systems[0], {self.graph.name: self.graph, self.copy.name: self.copy},
            )
        self.assertEqual(reads.call_count, 1)

    def test_bootstrap_reads_each_graph_once_including_selected_focus_validation(self) -> None:
        backend = TarelUIBackend(
            replace(self.backend.config, focuses=("report",)), runtime=self.runtime,
        )
        with patch.object(
            FileGraphStore, "load", autospec=True, side_effect=FileGraphStore.load,
        ) as reads:
            payload = backend.bootstrap()
        self.assertEqual(Counter(call.args[1] for call in reads.call_args_list), {
            self.graph.name: 1, self.copy.name: 1,
        })
        self.assertEqual(len(payload["objects"]), 4)
        self.assertEqual(payload["revisions"][self.graph.name], graph_revision(self.graph))
        self.assertTrue(payload["focuses"][0]["current"])

    def test_reload_reads_changed_graph_and_marks_focus_stale(self) -> None:
        before = self.backend.bootstrap()
        changed = replace(self.graph, edges=(*self.graph.edges, GraphEdge(
            id="new-edge", source_id=self.graph.edges[0].source_id,
            target_id=self.graph.edges[0].target_id, type="foreign_key", metadata={},
        )))
        self.runtime.graph_store().save(changed)
        after = self.backend.bootstrap()
        self.assertNotEqual(before["revisions"], after["revisions"])
        self.assertFalse(after["focuses"][0]["current"])
        backend = TarelUIBackend(
            replace(self.backend.config, focuses=("report",)), runtime=self.runtime,
        )
        with self.assertRaises(FocusFailure) as raised:
            backend.bootstrap()
        self.assertEqual(raised.exception.code, "focus_stale")

    def test_reload_revalidates_changed_zone_memberships(self) -> None:
        self.backend.bootstrap()
        system = self.workspace.systems[0]
        zone = system.zones[0]
        bad_member = replace(zone.members[0], object_id="missing-object")
        changed = replace(self.workspace, systems=(replace(
            system, zones=(replace(zone, members=(bad_member,)),),
        ),))
        self.runtime.workspace_store().save(changed)
        with self.assertRaises(WorkspaceFailure) as raised:
            self.backend.bootstrap()
        self.assertEqual(raised.exception.code, "zone_member_not_found")

    def test_scoped_request_does_not_reuse_a_different_request_scope(self) -> None:
        all_objects = self.backend.bootstrap()
        narrowed = TarelUIBackend(
            replace(self.backend.config, graphs=(self.copy.name,)), runtime=self.runtime,
        ).bootstrap()
        self.assertEqual(len(all_objects["objects"]), 4)
        self.assertEqual({item["graph"] for item in narrowed["objects"]}, {self.copy.name})
        self.assertEqual(narrowed["focuses"], [])
