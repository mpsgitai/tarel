from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.request import Request, urlopen

from tarel.cli import main
from tarel.sdk import Tarel
from tarel.ui.server import TarelUIBackend, UIConfig, _Server
from tests.test_ui import _graph


class ExplicitUIRuntimeTests(TestCase):
    def test_sdk_ui_forwards_the_clients_explicit_runtime(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            sdk = Tarel(Path(temporary_directory) / "state")

            def ready(_url: str) -> None:
                pass

            with patch("tarel.ui.server.run_ui", return_value=0) as run:
                result = sdk.ui.serve(
                    "sales",
                    lineages=("sales-lineage",),
                    editable=True,
                    port=8765,
                    open_browser=False,
                    on_ready=ready,
                )

        self.assertEqual(result, 0)
        self.assertIs(run.call_args.kwargs["runtime"], sdk.runtime)
        self.assertEqual(run.call_args.kwargs["lineages"], ("sales-lineage",))
        self.assertTrue(run.call_args.kwargs["editable"])
        self.assertIs(run.call_args.kwargs["on_ready"], ready)

    def test_cli_ui_accepts_an_explicit_state_root(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            state_root = Path(temporary_directory) / "state"
            with patch("tarel.ui.server.run_ui", return_value=0) as run:
                result = main([
                    "ui", "sales", "--state-root", str(state_root), "--no-open",
                ])

        self.assertEqual(result, 0)
        self.assertEqual(run.call_args.kwargs["runtime"].root, state_root.resolve())

    def test_http_routes_read_and_edit_only_the_explicit_state_root(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_root = root / "external-state"
            unrelated_working_directory = root / "working-directory"
            unrelated_working_directory.mkdir()
            sdk = Tarel(state_root)
            sdk.runtime.graph_store().save(_graph())
            server = _Server(
                ("127.0.0.1", 0),
                TarelUIBackend(
                    UIConfig(graph="sales", editable=True, search_mode="bm25"),
                    runtime=sdk.runtime,
                ),
                "fixture-token",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                os.chdir(unrelated_working_directory)
                bootstrap = self._get(server, "/api/bootstrap")
                search = self._post(server, "/api/search", {"query": "sales amount"})
                edited = self._post(server, "/api/annotation/edit", {
                    "patch": {"description": "Reviewed through the explicit UI runtime."},
                    "reason": "Explicit runtime integration test.",
                    "reference": "mart.FactSales",
                    "revision": bootstrap["revision"],
                })
            finally:
                os.chdir(previous)
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

            self.assertEqual(bootstrap["graph"], "sales")
            self.assertTrue(search["results"]["hits"])
            self.assertNotEqual(edited["revision"], bootstrap["revision"])
            fact = next(
                node for node in sdk.graph.load("sales").nodes
                if node.label == "mart.FactSales"
            )
            self.assertEqual(
                fact.annotation.description,
                "Reviewed through the explicit UI runtime.",
            )
            self.assertFalse((unrelated_working_directory / ".tarel").exists())

    @staticmethod
    def _get(server: _Server, route: str) -> dict[str, object]:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}{route}", timeout=5,
        ) as response:
            return json.load(response)

    @staticmethod
    def _post(
        server: _Server, route: str, payload: dict[str, object],
    ) -> dict[str, object]:
        request = Request(
            f"http://127.0.0.1:{server.server_port}{route}",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Tarel-Token": "fixture-token",
            },
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)
