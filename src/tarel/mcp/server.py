"""MCP transport adapter for ``tarel mcp serve``.

Imports the optional ``mcp`` package lazily so ``import tarel`` remains zero-dependency.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

from tarel.mcp.contracts import (
    DEFAULT_CONTEXT_MAX_CHARS,
    DEFAULT_CONTEXT_MAX_OBJECTS,
    DEFAULT_FOCUS_LIMIT,
    DEFAULT_GROUNDING_MAX_OBJECTS,
    DEFAULT_LINEAGE_LIMIT,
    DEFAULT_LINEAGE_MAX_HOPS,
    DEFAULT_OBJECTS_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MCP_SERVER_INSTRUCTIONS,
    McpFailure,
    McpServerConfig,
)
from tarel.mcp.policy import PolicyHook
from tarel.mcp.tools import TarelMcpDispatcher


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)


def _import_mcp_server_class() -> type[Any]:
    for module_name, attr_name in (
        ("mcp.server.mcpserver", "MCPServer"),
        ("mcp.server.fastmcp", "FastMCP"),
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        server_cls = getattr(module, attr_name, None)
        if isinstance(server_cls, type):
            return server_cls
    raise McpFailure(
        "missing_dependency",
        "The optional `mcp` package is required to run `tarel mcp serve`.",
        hint="Install with `pip install 'tarel[mcp]'` (or `uv pip install mcp`).",
    )


def create_mcp_server(
    config: McpServerConfig,
    *,
    policy_hook: PolicyHook | None = None,
) -> tuple[Any, TarelMcpDispatcher]:
    """Build a configured MCP server instance and its underlying dispatcher."""
    server_cls = _import_mcp_server_class()
    dispatcher = TarelMcpDispatcher(config, policy_hook=policy_hook)

    init_kwargs: dict[str, Any] = {"instructions": MCP_SERVER_INSTRUCTIONS}
    server = server_cls("tarel-meta", **init_kwargs)

    @server.tool()
    def tarel_catalog_overview(workspace: str | None = None) -> str:
        """List TAREL workspaces, graphs, focuses, and lineages with compact counts."""
        return _dump(dispatcher.catalog_overview(workspace=workspace))

    @server.tool()
    def tarel_graph_inspect(
        graph: str,
        mode: str = "header",
        namespace: str | None = None,
        offset: int = 0,
        limit: int = DEFAULT_OBJECTS_LIMIT,
        object_ids: list[str] | None = None,
    ) -> str:
        """Inspect a TAREL graph: mode='header', paginated mode='objects', or mode='slice'."""
        return _dump(
            dispatcher.graph_inspect(
                graph,
                mode=mode,
                namespace=namespace,
                offset=offset,
                limit=limit,
                object_ids=object_ids,
            )
        )

    @server.tool()
    def tarel_search(
        query: str,
        graph: str | None = None,
        workspace: str | None = None,
        mode: str = "lexical",
        limit: int = DEFAULT_SEARCH_LIMIT,
        namespace: str | None = None,
        validated_only: bool = False,
    ) -> str:
        """Search TAREL objects in a graph or workspace (mode: lexical | bm25 | hybrid)."""
        return _dump(
            dispatcher.search(
                query,
                graph=graph,
                workspace=workspace,
                mode=mode,
                limit=limit,
                namespace=namespace,
                validated_only=validated_only,
            )
        )

    @server.tool()
    def tarel_context(
        query: str,
        graph: str | None = None,
        workspace: str | None = None,
        max_objects: int = DEFAULT_CONTEXT_MAX_OBJECTS,
        max_characters: int = DEFAULT_CONTEXT_MAX_CHARS,
        mode: str = "lexical",
        namespace: str | None = None,
        validated_only: bool = False,
    ) -> str:
        """Compile a budgeted semantic context packet for a graph or workspace."""
        return _dump(
            dispatcher.context(
                query,
                graph=graph,
                workspace=workspace,
                max_objects=max_objects,
                max_characters=max_characters,
                mode=mode,
                namespace=namespace,
                validated_only=validated_only,
            )
        )

    @server.tool()
    def tarel_grounding(
        question: str | None = None,
        graph: str | None = None,
        workspace: str | None = None,
        object_ids: list[str] | None = None,
        source: str | None = None,
        lineages: list[str] | None = None,
        max_objects: int = DEFAULT_GROUNDING_MAX_OBJECTS,
        max_characters: int = DEFAULT_CONTEXT_MAX_CHARS,
    ) -> str:
        """Ground concrete object_ids (columns, types, keys, annotations) or a question bundle."""
        return _dump(
            dispatcher.grounding(
                question=question,
                graph=graph,
                workspace=workspace,
                object_ids=object_ids,
                source=source,
                lineages=lineages,
                max_objects=max_objects,
                max_characters=max_characters,
            )
        )

    @server.tool()
    def tarel_lineage_trace(
        mode: str = "upstream",
        reference: str | None = None,
        lineage: str | None = None,
        lineages: list[str] | None = None,
        graphs: list[str] | None = None,
        workspace: str | None = None,
        max_hops: int = DEFAULT_LINEAGE_MAX_HOPS,
        limit: int = DEFAULT_LINEAGE_LIMIT,
    ) -> str:
        """Trace upstream/downstream lineage or tables. Pass only catalog graphs in `graphs`."""
        return _dump(
            dispatcher.lineage_trace(
                mode=mode,
                reference=reference,
                lineage=lineage,
                lineages=lineages,
                graphs=graphs,
                workspace=workspace,
                max_hops=max_hops,
                limit=limit,
            )
        )

    @server.tool()
    def tarel_focus(
        action: str = "list",
        name: str | None = None,
        limit: int = DEFAULT_FOCUS_LIMIT,
    ) -> str:
        """List curated focus scopes (action='list') or inspect one focus (action='show')."""
        return _dump(dispatcher.focus(action=action, name=name, limit=limit))

    if config.profile == "meta-write":

        @server.tool()
        def tarel_annotate_draft(
            graph: str,
            proposal: dict[str, Any],
            source: str = "mcp-agent",
        ) -> str:
            """Apply a draft annotation proposal with provenance (never overwrites reviewed)."""
            return _dump(dispatcher.annotate_draft(graph, proposal, source=source))

    return server, dispatcher


def serve_mcp(
    config: McpServerConfig,
    *,
    policy_hook: PolicyHook | None = None,
) -> int:
    """Start the TAREL MCP server over stdio or streamable-http."""
    server, _ = create_mcp_server(config, policy_hook=policy_hook)
    if config.transport == "stdio":
        server.run(transport="stdio")
        return 0

    # Streamable HTTP: pass host/port through settings or run kwargs depending on mcp version.
    settings = getattr(server, "settings", None)
    if settings is not None:
        if hasattr(settings, "host"):
            settings.host = config.host
        if hasattr(settings, "port"):
            settings.port = config.port
        server.run(transport="streamable-http")
    else:
        server.run(transport="streamable-http", host=config.host, port=config.port)
    return 0
