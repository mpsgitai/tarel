from __future__ import annotations

import copy
import json
import tempfile
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tarel.cli import main
from tarel.ui.architecture_store import (
    FORMAT,
    ArchitectureFailure,
    ArchitectureStore,
    endpoint_members,
    validate_document,
)
from tarel.ui.server import TarelUIBackend, UIConfig, UIFailure, _Server
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceSystem


def fixture():
    return dict(
        format=FORMAT,
        workspace="demo",
        layers=[dict(id="source", label="Source", color="#abcdef")],
        nodes=[
            dict(
                id=f"asset::{graph}::source",
                label=graph,
                graph=graph,
                area="source",
                system=system,
                layer="source",
                source_type="sqlite",
                method="fixture",
                objects=count,
                namespaces=["main"],
            )
            for graph, system, count in (("a", "one", 2), ("b", "two", 3), ("empty", "two", 0))
        ],
        collections=[
            dict(
                id="all",
                label="All",
                description="Test collection",
                members=["system::one", "system::two"],
            )
        ],
        connections=[],
        positions={},
    )


def connection():
    return dict(
        id="test",
        source="graph::a",
        target="graph::b",
        label="Test planned flow",
        state="planned",
        kind="data_flow",
        reason="Intent only",
        evidence="test plan",
    )


class ArchitectureTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "architecture.json"
        self.path.write_text(json.dumps(fixture()))
        self.store = ArchitectureStore(self.path, workspace="demo", editable=True)

    def mutate(self, action, **payload):
        return self.store.mutate(action, {"revision": self.store.snapshot()["revision"], **payload})

    def test_create_update_delete_backup_and_restart(self):
        original = self.path.read_bytes()
        first = self.mutate("connection", item=connection())
        self.assertEqual(len(first["document"]["connections"]), 1)
        edge = connection() | {"label": "Edited", "state": "documented"}
        self.mutate("connection", item=edge)
        fresh = ArchitectureStore(self.path, workspace="demo").snapshot()
        self.assertEqual(fresh["document"]["connections"][0]["label"], "Edited")
        self.mutate("connection-delete", id="test")
        self.assertEqual(self.store.snapshot()["document"]["connections"], [])
        previous = json.loads(self.path.with_suffix(".previous.json").read_text())
        self.assertEqual(previous["connections"][0]["label"], "Edited")
        self.assertEqual(json.loads(original)["nodes"], fresh["document"]["nodes"])

    def test_read_only_is_independent_and_stale_writes_are_rejected(self):
        stale = self.store.snapshot()["revision"]
        read_only = ArchitectureStore(self.path, workspace="demo")
        with self.assertRaises(ArchitectureFailure) as caught:
            read_only.mutate("connection", {"revision": stale, "item": connection()})
        self.assertEqual(caught.exception.status, 403)
        self.mutate("connection", item=connection())
        with self.assertRaises(ArchitectureFailure) as caught:
            self.store.mutate("connection-delete", {"revision": stale, "id": "test"})
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(len(self.store.snapshot()["document"]["connections"]), 1)

    def test_layout_bounds_no_hidden_node_loss_and_collection_overlap(self):
        self.mutate("layout", positions={"graph::a": dict(x=20, y=40)})
        self.mutate("layout", positions={"graph::b": dict(x=-20, y=70)})
        self.assertEqual(len(self.store.snapshot()["document"]["positions"]), 2)
        self.mutate(
            "collection",
            item=dict(
                id="second",
                label="Overlap",
                description="Intentional",
                members=["system::one", "graph::b"],
            ),
        )
        self.assertEqual(len(self.store.snapshot()["document"]["collections"]), 2)
        for position in (dict(x=float("nan"), y=2), dict(x=1e9, y=0), dict(x=True, y=0)):
            with self.assertRaises(ArchitectureFailure):
                self.mutate("layout", positions={"graph::a": position})
        self.mutate("collection-delete", id="second")
        self.assertEqual(len(self.store.snapshot()["document"]["nodes"]), 3)

    def test_invalid_endpoints_overlap_duplicate_and_unknown_fields(self):
        for update in (
            {"source": "graph::unknown"},
            {"source": "graph::b"},
            {"source": "system::two"},
            {"source": []},
            {"state": "verified"},
            {"path": "/tmp/not-allowed"},
        ):
            with self.subTest(update=update), self.assertRaises(ArchitectureFailure):
                self.mutate("connection", item=connection() | update)
        self.mutate("connection", item=connection())
        with self.assertRaises(ArchitectureFailure):
            self.mutate("connection", item=connection() | {"id": "duplicate"})
        self.assertFalse(self.path.with_suffix(".lock").exists())

    def test_empty_catalogs_and_system_membership_are_kept(self):
        document = fixture()
        validate_document(document)
        self.assertIn("asset::empty::source", endpoint_members(document)["system::two"])
        wrong = copy.deepcopy(document)
        wrong["nodes"][0]["layer"] = "no-layer"
        with self.assertRaises(ArchitectureFailure):
            validate_document(wrong)
        with self.assertRaises(ArchitectureFailure):
            ArchitectureStore(self.path, workspace="other").snapshot()

    def test_backend_rejects_filtered_architecture_and_edit_without_sidecar(self):
        for options in ({"systems": ("one",)}, {"zones": ("sales",)}, {"focuses": ("report",)}):
            with self.assertRaises(UIFailure):
                TarelUIBackend(UIConfig(workspace="demo", architecture_file=self.path, **options))
        with self.assertRaises(UIFailure):
            TarelUIBackend(UIConfig(workspace="demo", architecture_edit=True))

    def test_cli_forwards_architecture_without_enabling_graph_edits(self):
        with patch("tarel.ui.server.run_ui", return_value=0) as run:
            result = main([
                "ui", "--workspace", "demo", "--architecture-file", str(self.path),
                "--architecture-edit", "--no-open",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(run.call_args.kwargs["architecture_file"], self.path)
        self.assertTrue(run.call_args.kwargs["architecture_edit"])
        self.assertFalse(run.call_args.kwargs["editable"])
        self.assertFalse(run.call_args.kwargs["open_browser"])

    def test_cli_ordinary_browser_does_not_enable_architecture(self):
        with patch("tarel.ui.server.run_ui", return_value=0) as run:
            self.assertEqual(main(["ui", "--workspace", "demo"]), 0)
        self.assertIsNone(run.call_args.kwargs["architecture_file"])
        self.assertFalse(run.call_args.kwargs["architecture_edit"])

    def test_backend_rejects_stale_or_outside_workspace_inventory(self):
        backend = TarelUIBackend(UIConfig(workspace="demo", architecture_file=self.path))
        with (
            patch.object(backend, "_bootstrap", return_value={"graphs": [{"name": "a"}]}),
            patch("tarel.ui.server.load_workspace_use_case", return_value=WorkspaceDocument(
                name="demo", systems=(WorkspaceSystem(name="one", graphs=("a",)),),
            )),
            self.assertRaises(ArchitectureFailure) as caught,
        ):
            backend.bootstrap()
        self.assertEqual(caught.exception.status, 409)
        with (
            patch.object(backend, "_bootstrap", return_value={
                "graphs": [{"name": name} for name in ("a", "b")],
            }),
            patch("tarel.ui.server.load_workspace_use_case", return_value=WorkspaceDocument(
                name="demo", systems=(
                    WorkspaceSystem(name="one", graphs=("a",)),
                    WorkspaceSystem(name="two", graphs=("b", "empty")),
                ),
            )),
        ):
            self.assertEqual(len(backend.bootstrap()["architecture"]["document"]["nodes"]), 3)

    def test_http_session_gate_assets_and_graph_read_only(self):
        backend = TarelUIBackend(
            UIConfig(
                workspace="demo",
                architecture_file=self.path,
                architecture_edit=True,
                editable=False,
            )
        )
        server = _Server(("127.0.0.1", 0), backend, "test-session")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        for asset in ("architecture.js", "architecture_actions.js", "architecture.css"):
            with urlopen(f"{base}/{asset}") as response:
                self.assertEqual(response.status, 200)
        payload = json.dumps(
            dict(revision=self.store.snapshot()["revision"], item=connection())
        ).encode()
        with self.assertRaises(HTTPError) as caught:
            urlopen(
                Request(
                    f"{base}/api/architecture/connection",
                    payload,
                    {"Content-Type": "application/json"},
                )
            )
        self.assertEqual(caught.exception.code, 403)
        with urlopen(
            Request(
                f"{base}/api/architecture/connection",
                payload,
                {"Content-Type": "application/json", "X-Tarel-Token": "test-session"},
            )
        ) as response:
            self.assertEqual(len(json.load(response)["document"]["connections"]), 1)
        with self.assertRaises(UIFailure) as caught:
            backend.mutate("/api/manual/job", {})
        self.assertEqual(caught.exception.status, 403)
