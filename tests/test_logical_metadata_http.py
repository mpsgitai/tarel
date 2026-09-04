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

from tarel.graph.revision import physical_graph_revision
from tarel.runtime import TarelRuntime
from tarel.semantic_concepts import ConceptBinding, SemanticConcept, SemanticConceptDocument
from tarel.semantic_concepts.application import save_semantic_concepts_use_case
from tarel.semantic_concepts.store import FileSemanticConceptStore
from tarel.topology.endpoint_contracts import LogicalEndpoint
from tarel.ui.server import TarelUIBackend, UIConfig, _Server
from tarel.workspaces.contracts import Area, SchemaReference, Zone, ZoneMember
from tests.test_family_focus import _focus
from tests.test_object_families_ui import _family, _graph, _workspace


class LogicalMetadataHTTPTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.previous = Path.cwd()
        self.addCleanup(os.chdir, self.previous)
        self.project = Path(self.temporary.name)
        os.chdir(self.project)
        self.runtime = TarelRuntime.local(self.project / ".tarel")
        self.graph = _graph(6, namespaces=True)
        self.runtime.graph_store().save(self.graph)
        self.family = _family(self.graph)
        self.runtime.object_family_store().save(self.family)
        self.ids = self.family.member_ids
        fields = {
            node.metadata["object_id"]: node for node in self.graph.nodes if node.type == "field"
        }
        self.concepts = save_semantic_concepts_use_case(
            SemanticConceptDocument(
                self.graph.name,
                physical_graph_revision(self.graph),
                tuple(
                    SemanticConcept(
                        f"concept-{index}",
                        f"Partition concept {index}",
                        "Scoped metadata only.",
                        bindings=(
                            ConceptBinding(
                                LogicalEndpoint(
                                    "graph_field",
                                    object_id,
                                    fields[object_id].id,
                                    physical_graph_revision(self.graph),
                                ),
                                "code",
                            ),
                        ),
                    )
                    for index, object_id in enumerate(self.ids)
                ),
            ),
            runtime=self.runtime,
        )
        self.focus = _focus(self.graph, "report", self.ids[:3])
        self.cube = _focus(self.graph, "cube", self.ids[2:5])
        self.runtime.focus_store().save(self.focus)
        self.runtime.focus_store().save(self.cube)
        self.backend = TarelUIBackend(UIConfig(graph=self.graph.name))
        self.server = _Server(("127.0.0.1", 0), self.backend, "metadata-test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def _configure(self, config: UIConfig) -> None:
        self.backend = TarelUIBackend(config)
        self.server.backend = self.backend

    def _post(
        self,
        payload=None,
        *,
        route="/api/logical/metadata",
        token="metadata-test-token",
        content_type="application/json",
        origin=None,
    ):
        headers = {"Content-Type": content_type}
        if token is not None:
            headers["X-Tarel-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        request = Request(
            self.base_url + route, json.dumps(payload or {}).encode(), headers, method="POST"
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def _request(self, **changes):
        return {"graph": self.graph.name, "object_ids": [self.ids[0]], **changes}

    def _workspace(self, members):
        workspace, _ = _workspace(self.graph, members)
        area = Area(
            "all-schemas",
            (
                SchemaReference(self.graph.name, "tenant_0"),
                SchemaReference(self.graph.name, "tenant_1"),
            ),
        )
        return replace(workspace, systems=(replace(workspace.systems[0], areas=(area,)),))

    def test_default_readonly_returns_metadata_but_does_not_enable_mutations(self) -> None:
        graph_before = self.runtime.graph_store().path(self.graph.name).read_bytes()
        concepts_before = self.concepts.to_dict()
        status, payload, headers = self._post(self._request())
        self.assertEqual(status, 200)
        self.assertFalse(self.backend.config.editable)
        self.assertEqual(payload["concepts"][0]["artifact"]["id"], "concept-0")
        self.assertEqual(payload["concepts"][0]["usage"], "exploratory_only")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))
        status, denied, _ = self._post({}, route="/api/annotation/edit")
        self.assertEqual((status, denied["error"]["code"]), (403, "read_only"))
        self.assertEqual(
            self.runtime.graph_store().path(self.graph.name).read_bytes(), graph_before
        )
        self.assertEqual(
            FileSemanticConceptStore(self.runtime.root / "semantic-concepts")
            .load(
                self.graph.name,
            )
            .to_dict(),
            concepts_before,
        )

    def test_csrf_missing_or_wrong_session_and_wrong_content_type_are_rejected(self) -> None:
        for token in (None, "wrong-token"):
            with self.subTest(token=token):
                status, payload, _ = self._post(
                    self._request(),
                    token=token,
                    origin="https://attacker.invalid",
                )
                self.assertEqual((status, payload["error"]["code"]), (403, "invalid_session"))
                self.assertNotIn("concepts", payload)
        status, payload, _ = self._post(self._request(), content_type="text/plain")
        self.assertEqual((status, payload["error"]["code"]), (400, "invalid_content_type"))
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.base_url + "/api/logical/metadata", timeout=5)
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()

    def test_graph_scope_is_authoritative_even_for_an_existing_other_graph(self) -> None:
        outside = replace(self.graph, name="outside")
        self.runtime.graph_store().save(outside)
        status, payload, _ = self._post(self._request(graph=outside.name))
        self.assertEqual((status, payload["error"]["code"]), (400, "graph_outside_scope"))
        self.assertNotIn("concepts", payload)

    def test_focus_scope_controls_payload_and_rejects_client_allowlist_expansion(self) -> None:
        status, payload, _ = self._post(self._request(focuses=[self.focus.name]))
        self.assertEqual(status, 200)
        self.assertEqual([item["artifact"]["id"] for item in payload["concepts"]], ["concept-0"])
        status, denied, _ = self._post(
            self._request(
                object_ids=[self.ids[4]],
                focuses=[self.focus.name],
                allowed_object_ids=list(self.ids),
            )
        )
        self.assertEqual(
            (status, denied["error"]["code"]), (400, "logical_metadata_object_outside_scope")
        )
        for names, code in (
            (["unknown"], "focus_outside_scope"),
            ([self.focus.name] * 2, "duplicate_focus"),
        ):
            status, denied, _ = self._post(self._request(focuses=names))
            self.assertEqual((status, denied["error"]["code"]), (400, code))

    def test_multiple_focus_union_is_intersected_with_real_workspace_scope(self) -> None:
        workspace = self._workspace(self.ids[1:4])
        self.runtime.workspace_store().save(workspace)
        self._configure(UIConfig(workspace=workspace.name, zones=("analytics:selected",)))
        status, payload, _ = self._post(
            self._request(
                object_ids=[f"object_family:{self.family.id}"],
                focuses=[self.focus.name, self.cube.name],
                allowed_object_ids=list(self.ids),
            )
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            {item["artifact"]["id"] for item in payload["concepts"]},
            {"concept-1", "concept-2", "concept-3"},
        )
        serialized = json.dumps(payload)
        for excluded in (self.ids[0], self.ids[4], self.ids[5]):
            self.assertNotIn(excluded, serialized)
        self.assertNotIn("member_ids", serialized)
        status, denied, _ = self._post(self._request(focuses=[self.focus.name]))
        self.assertEqual(
            (status, denied["error"]["code"]), (400, "logical_metadata_object_outside_scope")
        )

    def test_configured_focus_is_used_without_request_override(self) -> None:
        self._configure(UIConfig(graph=self.graph.name, focuses=(self.focus.name,)))
        status, payload, _ = self._post(self._request())
        self.assertEqual(status, 200)
        status, denied, _ = self._post(self._request(object_ids=[self.ids[4]]))
        self.assertEqual(
            (status, denied["error"]["code"]), (400, "logical_metadata_object_outside_scope")
        )

    def test_changed_focus_or_scope_revision_returns_conflict_without_metadata(self) -> None:
        status, view, _ = self._post(
            {"mode": "confirmed_only", "focuses": [self.focus.name]},
            route="/api/families/view",
        )
        self.assertEqual(status, 200)
        revision = view["object_families"]["scope_revision"]
        status, payload, _ = self._post(
            self._request(focuses=[self.focus.name], scope_revision=revision)
        )
        self.assertEqual(status, 200)
        status, denied, _ = self._post(
            self._request(
                object_ids=[self.ids[2]],
                focuses=[self.cube.name],
                scope_revision=revision,
            )
        )
        self.assertEqual((status, denied["error"]["code"]), (409, "stale_logical_metadata_scope"))
        self.assertNotIn("concepts", denied)
        self.runtime.focus_store().save(_focus(self.graph, self.focus.name, self.ids[:2]))
        status, denied, _ = self._post(
            self._request(focuses=[self.focus.name], scope_revision=revision)
        )
        self.assertEqual((status, denied["error"]["code"]), (409, "stale_logical_metadata_scope"))

    def test_changed_workspace_and_stale_focus_source_fail_with_conflict(self) -> None:
        workspace = self._workspace(self.ids[:3])
        self.runtime.workspace_store().save(workspace)
        self._configure(UIConfig(workspace=workspace.name, zones=("analytics:selected",)))
        status, view, _ = self._post({"mode": "confirmed_only"}, route="/api/families/view")
        self.assertEqual(status, 200)
        revision = view["object_families"]["scope_revision"]
        system = workspace.systems[0]
        changed = replace(
            workspace,
            systems=(
                replace(
                    system,
                    zones=(
                        Zone(
                            name="selected",
                            members=tuple(
                                ZoneMember(self.graph.name, item) for item in self.ids[:2]
                            ),
                        ),
                    ),
                ),
            ),
        )
        self.runtime.workspace_store().save(changed)
        status, denied, _ = self._post(self._request(scope_revision=revision))
        self.assertEqual((status, denied["error"]["code"]), (409, "stale_logical_metadata_scope"))
        self._configure(UIConfig(graph=self.graph.name))
        self.runtime.graph_store().save(_graph(7, namespaces=True))
        status, denied, _ = self._post(self._request(focuses=[self.focus.name]))
        self.assertEqual((status, denied["error"]["code"]), (409, "focus_stale"))

    def test_script_is_served_with_csp_and_index_references_it(self) -> None:
        with urlopen(self.base_url + "/", timeout=5) as response:
            self.assertIn("logical_metadata.js", response.read().decode())
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        with urlopen(self.base_url + "/logical_metadata.js", timeout=5) as response:
            self.assertIn("renderLogicalMetadata", response.read().decode())
            self.assertEqual(response.headers["Content-Type"], "text/javascript; charset=utf-8")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
