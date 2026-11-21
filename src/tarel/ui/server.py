"""The loopback HTTP adapter of the browser: static assets, session token and JSON API."""

from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from collections.abc import Callable, Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tarel.annotations.contracts import AnnotationFailure
from tarel.context.compiler import ContextFailure
from tarel.entity_resolution.contracts import EntityResolutionFailure
from tarel.expansion.contracts import ContextExpansionFailure
from tarel.focus.contracts import FocusFailure
from tarel.graph.contracts import GraphFailure
from tarel.knowledge.contracts import KnowledgeFailure
from tarel.lineage.contracts import LineageFailure
from tarel.logical_joins.contracts import LogicalJoinFailure
from tarel.object_bindings.contracts import ObjectBindingFailure
from tarel.object_families.contracts import ObjectFamilyFailure
from tarel.providers.contracts import ProviderFailure
from tarel.reference_mapping.contracts import ReferenceMappingFailure
from tarel.relationships.core import RelationshipFailure
from tarel.retrieval.contracts import RetrievalFailure
from tarel.runtime import TarelRuntime
from tarel.search import SearchFailure
from tarel.semantic_concepts.contracts import SemanticConceptFailure
from tarel.semantics.contracts import SemanticFailure
from tarel.topology.contracts import LogicalTopologyFailure
from tarel.topology.endpoint_contracts import LogicalEndpointFailure
from tarel.ui.architecture_store import MAX_SIDECAR_BYTES, ArchitectureFailure
from tarel.ui.backend import TarelUIBackend
from tarel.ui.contracts import UIConfig, UIFailure
from tarel.ui.logical_metadata import LogicalMetadataFailure
from tarel.ui.optional_metadata import OptionalMetadataFailure
from tarel.ui.query_tools import UIQueryFailure
from tarel.workspaces.contracts import WorkspaceFailure

_MAX_REQUEST_BYTES = 256 * 1024


# Context packets are bounded by 100,000 Unicode characters in the UI. Allow
# their UTF-8 representation plus the small preview or expansion envelope.
_MAX_CONTEXT_REQUEST_BYTES = 512 * 1024


# A full positions map fits within the sidecar cap, plus the JSON/revision envelope.
_MAX_LAYOUT_REQUEST_BYTES = MAX_SIDECAR_BYTES + 1024


_STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], backend: TarelUIBackend, token: str) -> None:
        super().__init__(address, _Handler)
        self.backend = backend
        self.token = token


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if not self._trusted_host():
            return
        if path.startswith("/api/"):
            if self._valid_token():
                self._api_read(path, parse_qs(urlparse(self.path).query))
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._trusted_host() or not self._valid_token():
            return
        if self.headers.get_content_type() != "application/json":
            self._json_error(UIFailure("invalid_content_type", "Expected application/json."))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if path == "/api/architecture/layout" and self.server.backend.architecture:
                limit = _MAX_LAYOUT_REQUEST_BYTES
            elif path in {"/api/context/preview", "/api/context/expand"}:
                limit = _MAX_CONTEXT_REQUEST_BYTES
            else:
                limit = _MAX_REQUEST_BYTES
            if length < 0 or length > limit:
                raise UIFailure("request_too_large", "UI request is too large.", status=413)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise UIFailure("invalid_request", "UI request root must be an object.")
            self._json(HTTPStatus.OK, self.server.backend.mutate(path, payload))
        except Exception as exc:  # boundary maps known domain failures to JSON
            self._json_error(_ui_failure(exc))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _trusted_host(self) -> bool:
        """Reject requests addressed to another host name (DNS rebinding) before any work."""
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if self.headers.get("Host", "") in allowed:
            return True
        self._json_error(UIFailure("untrusted_host", "Unexpected Host header.", status=403))
        return False

    def _valid_token(self) -> bool:
        """Every API request, read or write, carries the session token from index.html."""
        if secrets.compare_digest(self.headers.get("X-Tarel-Token", ""), self.server.token):
            return True
        self._json_error(UIFailure("invalid_session", "Invalid UI session token.", status=403))
        return False

    def _api_read(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            self._json(HTTPStatus.OK, self.server.backend.read(path, query))
        except Exception as exc:
            self._json_error(_ui_failure(exc))

    def _static(self, path: str) -> None:
        name = "index.html" if path in {"", "/"} else path.removeprefix("/")
        if name not in {
            "index.html", "app.js", "styles.css", "cytoscape.min.js", "logical_metadata.js",
            "retrieval_models.js",
            "query_tools.js",
            "optional_details.js",
            "estate_navigation.js",
            "architecture.js", "architecture_actions.js", "architecture.css",
            "atlas.css", "atlas.js", "lineage_flows.js",
        }:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        resource = files("tarel.ui").joinpath("static", name)
        try:
            body = resource.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if name == "index.html":
            body = body.replace(b"__TAREL_TOKEN__", self.server.token.encode("ascii"))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _STATIC_TYPES[Path(name).suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", _content_security_policy())
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, failure: UIFailure) -> None:
        self._json(failure.status, {"error": {"code": failure.code, "message": str(failure)}})

    def _json(self, status: int, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def run_ui(
    graph: str | None,
    *,
    workspace: str | None = None,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    lineages: tuple[str, ...] = (),
    focuses: tuple[str, ...] = (),
    editable: bool = False,
    family_mode: str | None = None,
    architecture_file: Path | None = None,
    architecture_edit: bool = False,
    port: int = 0,
    open_browser: bool = True,
    search_mode: str = "lexical",
    model_path: Path | None = None,
    n_threads: int | None = None,
    runtime: TarelRuntime | None = None,
    on_ready: Callable[[str], None] | None = None,
) -> int:
    if port < 0 or port > 65535:
        raise UIFailure("invalid_port", "Port must be between 0 and 65535.")
    if bool(graph) == bool(workspace):
        raise UIFailure(
            "ui_source_required",
            "Choose exactly one graph or one --workspace.",
        )
    backend = TarelUIBackend(
        UIConfig(
            graph=graph,
            workspace=workspace,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            lineages=lineages,
            focuses=focuses,
            editable=editable,
            family_mode=family_mode,
            architecture_file=architecture_file,
            architecture_edit=architecture_edit,
            search_mode=search_mode,
            model_path=model_path,
            n_threads=n_threads,
        ),
        runtime=runtime,
    )
    try:
        backend.bootstrap()
    except ArchitectureFailure as exc:
        raise _ui_failure(exc) from exc
    server = _Server(("127.0.0.1", port), backend, secrets.token_urlsafe(32))
    address = f"http://127.0.0.1:{server.server_port}/"
    if on_ready is None:
        mode = "edit" if editable else "read-only"
        print(f"TAREL UI ({mode}): {address}")
        print("Press Ctrl+C to stop.")
    else:
        on_ready(address)
    if open_browser:
        threading.Timer(0.15, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _ui_failure(exc: Exception) -> UIFailure:
    if isinstance(exc, ArchitectureFailure):
        return UIFailure(exc.code, str(exc), status=exc.status)
    if isinstance(exc, UIFailure):
        return exc
    if isinstance(exc, UIQueryFailure):
        return UIFailure(exc.code, str(exc), status=exc.status)
    if isinstance(
        exc,
        (
            AnnotationFailure,
            ContextFailure,
            ContextExpansionFailure,
            EntityResolutionFailure,
            FocusFailure,
            GraphFailure,
            KnowledgeFailure,
            LineageFailure,
            LogicalTopologyFailure,
            ObjectFamilyFailure,
            ObjectBindingFailure,
            LogicalJoinFailure,
            SemanticConceptFailure,
            LogicalEndpointFailure,
            LogicalMetadataFailure,
            OptionalMetadataFailure,
            ReferenceMappingFailure,
            RelationshipFailure,
            RetrievalFailure,
            ProviderFailure,
            SearchFailure,
            SemanticFailure,
            WorkspaceFailure,
        ),
    ):
        code = getattr(exc, "code", "ui_operation_failed")
        status = 409 if code in {
            "focus_stale",
            "stale_graph",
            "stale_lineage",
            "stale_semantic_import",
            "stale_workspace",
            "stale_logical_topology",
            "stale_reference_mapping_candidate",
            "logical_topology_graph_revision_mismatch",
            "logical_topology_graph_rebase_forbidden",
            "reference_mapping_graph_revision_mismatch",
            "reference_mapping_review_conflict",
            "object_family_graph_revision_mismatch",
            "stale_object_family",
            "stale_index",
            "index_policy_mismatch",
            "model_index_mismatch",
            "stale_expansion_base",
        } else 400
        if code.endswith("_not_found"):
            status = 404
        return UIFailure(code, str(exc), status=status)
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ValueError)):
        return UIFailure("invalid_request", "The UI request is invalid.")
    return UIFailure("ui_operation_failed", str(exc), status=500)


def _content_security_policy() -> str:
    return "; ".join((
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ))
