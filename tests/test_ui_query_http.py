from __future__ import annotations

import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import Tarel
from tarel.ui.server import TarelUIBackend, UIConfig, _Server
from tests.test_ui import _graph


class QueryHTTPTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(temporary.name)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.server = _Server(
            ("127.0.0.1", 0), TarelUIBackend(UIConfig(graph="sales")), "fixture-token",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def _post(self, route, payload, *, token=True):
        request = Request(
            f"http://127.0.0.1:{self.server.server_port}{route}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **(
                {"X-Tarel-Token": "fixture-token"} if token else {}
            )},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_read_only_http_search_and_context_match_sdk(self) -> None:
        before = self.graph.to_dict()
        found = self._post("/api/search", {"query": "DateKey"})
        self.assertEqual(found["results"], self.sdk.search.graph("sales", "DateKey").to_dict())
        self.assertEqual(len(found["results"]["hits"]), 2)
        scope = self._post("/api/query/scope", {})
        preview = self._post("/api/context/preview", {
            "query": "DateKey", "expected_revisions": scope["revisions"],
            "expected_scope_identity": scope["scope_identity"],
        })
        self.assertEqual(preview["packet"], self.sdk.context.graph(
            "sales", "DateKey", validated_only=True,
        ).to_dict())
        self.assertEqual(before, self.sdk.graph.load("sales").to_dict())
        self.assertFalse((self.sdk.root / "sources").exists())
        self.assertFalse((self.sdk.root / "context").exists())

    def test_selected_context_can_expand_one_packet_object_over_http(self) -> None:
        scope = self._post("/api/query/scope", {})
        fact = next(node for node in self.graph.nodes if node.label == "mart.FactSales")
        preview = self._post("/api/context/preview", {
            "query": "sales amount", "kind": "selected", "object_ids": [fact.id],
            "max_objects": 1, "seed_limit": 1, "max_fields_per_object": 1,
            "expected_revisions": scope["revisions"],
            "expected_scope_identity": scope["scope_identity"],
        })

        expanded = self._post("/api/context/expand", {
            "packet": preview["packet"], "object_ids": [fact.id],
            "expected_revisions": scope["revisions"],
            "expected_scope_identity": scope["scope_identity"],
        })["expansion"]

        self.assertEqual(
            expanded["base_packet_hash"], preview["packet"]["identity"]["packet_hash"]
        )
        self.assertEqual(expanded["items"][0]["target"]["id"], fact.id)
        self.assertEqual(len(expanded["items"][0]["metadata"]["objects"][0]["fields"]), 2)

    def test_every_query_route_requires_the_session_token(self) -> None:
        for route, payload in (
            ("/api/query/scope", {}), ("/api/search", {"query": "DateKey"}),
            ("/api/context/preview", {"query": "DateKey"}),
            ("/api/context/expand", {}),
        ):
            with self.subTest(route=route), self.assertRaises(HTTPError) as raised:
                self._post(route, payload, token=False)
            self.assertEqual(raised.exception.code, 403)
            self.assertEqual(json.load(raised.exception)["error"]["code"], "invalid_session")

    def test_invalid_queries_are_visible_client_errors_without_echoing_unsafe_options(self):
        for route, payload, code in (
            ("/api/query/scope", {"graph": "PRIVATE_OVERRIDE"}, "invalid_query_request"),
            ("/api/search", {"query": "the"}, "empty_query"),
            ("/api/search", {"query": "DateKey", "model_path": "PRIVATE_OVERRIDE"},
             "invalid_query_request"),
            ("/api/context/preview", {"query": "DateKey", "max_objects": 0},
             "invalid_query_budget"),
        ):
            with self.subTest(route=route, code=code), self.assertRaises(HTTPError) as raised:
                self._post(route, payload)
            self.assertEqual(raised.exception.code, 400)
            response = json.load(raised.exception)
            self.assertEqual(response["error"]["code"], code)
            self.assertNotIn("PRIVATE_OVERRIDE", json.dumps(response))

    def test_stale_preview_returns_conflict_instead_of_a_new_scope_packet(self):
        scope = self._post("/api/query/scope", {})
        changed = replace(self.graph, nodes=tuple(
            replace(node, annotation=GraphAnnotation(description="New meaning", state="validated"))
            if node.type == "table" else node for node in self.graph.nodes
        ))
        self.sdk.runtime.graph_store().save(changed)
        with self.assertRaises(HTTPError) as raised:
            self._post("/api/context/preview", {
                "query": "DateKey", "expected_revisions": scope["revisions"],
                "expected_scope_identity": scope["scope_identity"],
            })
        self.assertEqual(raised.exception.code, 409)
        self.assertEqual(json.load(raised.exception)["error"]["code"], "stale_query_scope")

    def test_retrieval_configuration_failure_keeps_its_stable_http_error(self) -> None:
        server = _Server(
            ("127.0.0.1", 0),
            TarelUIBackend(UIConfig(
                graph="sales", search_mode="vector", model_path=Path("missing.gguf"),
            )),
            "vector-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/search",
                data=json.dumps({"query": "DateKey"}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Tarel-Token": "vector-token",
                },
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 404)
            self.assertEqual(json.load(raised.exception)["error"]["code"], "model_not_found")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_stale_expansion_base_returns_revision_conflict(self) -> None:
        scope = self._post("/api/query/scope", {})
        fact = next(node for node in self.graph.nodes if node.label == "mart.FactSales")
        preview = self._post("/api/context/preview", {
            "query": "sales amount", "kind": "selected", "object_ids": [fact.id],
            "expected_revisions": scope["revisions"],
            "expected_scope_identity": scope["scope_identity"],
        })
        changed = replace(
            self.graph,
            nodes=tuple(
                replace(node, annotation=GraphAnnotation(description="Changed meaning"))
                if node.id == fact.id else node
                for node in self.graph.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(changed)
        current = self._post("/api/query/scope", {})

        with self.assertRaises(HTTPError) as raised:
            self._post("/api/context/expand", {
                "packet": preview["packet"], "object_ids": [fact.id],
                "expected_revisions": current["revisions"],
                "expected_scope_identity": current["scope_identity"],
            })

        self.assertEqual(raised.exception.code, 409)
        self.assertEqual(
            json.load(raised.exception)["error"]["code"], "stale_expansion_base"
        )
