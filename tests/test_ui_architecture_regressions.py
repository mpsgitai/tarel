from __future__ import annotations

import json
import threading
from contextlib import redirect_stderr
from http.client import HTTPConnection
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.ui.architecture_store import ArchitectureFailure, ArchitectureStore, validate_document
from tarel.ui.server import TarelUIBackend, UIConfig, _Server
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceSystem
from tests.test_ui_architecture import fixture


class ArchitectureReviewTests(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "landscape.json"
        self.path.write_text(json.dumps(fixture()), encoding="utf-8")
        self.store = ArchitectureStore(self.path, workspace="demo", editable=True)

    def backend(self) -> TarelUIBackend:
        return TarelUIBackend(UIConfig(
            workspace="demo", architecture_file=self.path, architecture_edit=True,
        ))

    def assert_cli_read_failure(self) -> None:
        error = StringIO()
        with (
            patch.object(TarelUIBackend, "_bootstrap", return_value={}),
            redirect_stderr(error),
        ):
            result = main([
                "ui", "--workspace", "demo", "--architecture-file", str(self.path), "--no-open",
            ])
        self.assertEqual(result, 2)
        self.assertIn("error [invalid_architecture]", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        self.assertNotIn("private-sentinel", error.getvalue())

    def test_missing_sidecar_is_a_structured_cli_error(self) -> None:
        self.path = self.path.with_name("missing.json")
        self.assert_cli_read_failure()

    def test_unreadable_sidecar_is_a_structured_cli_error(self) -> None:
        for operation in ("stat", "read_text"):
            with self.subTest(operation=operation), patch.object(
                Path, operation, side_effect=PermissionError("private-sentinel"),
            ):
                self.assert_cli_read_failure()

    def test_malformed_or_non_utf8_sidecar_is_a_structured_cli_error(self) -> None:
        for content in (b'{"private-sentinel":', b'\xffprivate-sentinel'):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                self.assert_cli_read_failure()

    def test_backend_checks_graph_system_pairs_not_just_graph_names(self) -> None:
        workspace = WorkspaceDocument(name="demo", systems=(
            WorkspaceSystem(name="one", graphs=("a",)),
            WorkspaceSystem(name="two", graphs=("b", "empty")),
        ))
        for system in ("typo", "two"):
            document = fixture()
            document["collections"] = []
            document["nodes"][0]["system"] = system
            validate_document(document)
            self.path.write_text(json.dumps(document), encoding="utf-8")
            backend = self.backend()
            with (
                self.subTest(system=system),
                patch.object(backend, "_bootstrap", return_value={}),
                patch("tarel.ui.server.load_workspace_use_case", return_value=workspace),
            ):
                with self.assertRaises(ArchitectureFailure) as caught:
                    backend.bootstrap()
                self.assertEqual(caught.exception.status, 409)

    def serve(self) -> _Server:
        server = _Server(("127.0.0.1", 0), self.backend(), "synthetic-session")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def post(
        self, server: _Server, route: str, body: bytes, *,
        length: int | None = None, token: str = "synthetic-session",
    ) -> tuple[int, dict]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request("POST", route, body, {
                "Content-Type": "application/json", "X-Tarel-Token": token,
                "Content-Length": str(len(body) if length is None else length),
            })
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_large_valid_layout_saves_atomically_over_http(self) -> None:
        document = fixture()
        template = document["nodes"][0]
        document["collections"] = []
        document["nodes"] = [
            template | {"id": f"asset::{index:04d}::" + "x" * 220, "graph": f"g{index}"}
            for index in range(1200)
        ]
        self.path.write_text(json.dumps(document), encoding="utf-8")
        positions = {node["id"]: {"x": index, "y": -index}
                     for index, node in enumerate(document["nodes"])}
        original = self.store.snapshot()
        payload = json.dumps({"revision": original["revision"], "positions": positions}).encode()
        self.assertGreater(len(payload), 256 * 1024)
        server = self.serve()
        status, result = self.post(server, "/api/architecture/layout", payload)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["document"]["positions"], positions)
        self.assertEqual(self.store.snapshot()["document"]["positions"], positions)
        self.assertEqual(result["document"]["nodes"], document["nodes"])
        previous = json.loads(self.path.with_suffix(".previous.json").read_text())
        self.assertEqual(previous, original["document"])
        status, _ = self.post(server, "/api/architecture/layout", payload)
        self.assertEqual(status, 409)

    def test_request_limits_and_session_gate_remain_bounded(self) -> None:
        server = self.serve()
        original = self.path.read_bytes()
        for route in ("/api/architecture/connection", "/api/manual/job", "/api/search"):
            status, _ = self.post(server, route, b"{}", length=256 * 1024 + 1)
            self.assertEqual(status, 413, route)
        status, _ = self.post(server, "/api/architecture/layout", b"{}", length=5 * 1024 * 1024)
        self.assertEqual(status, 413)
        status, _ = self.post(
            server, "/api/architecture/layout", b"{}", length=300 * 1024, token="wrong",
        )
        self.assertEqual(status, 403)
        self.assertEqual(self.path.read_bytes(), original)
