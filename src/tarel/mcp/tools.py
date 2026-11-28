"""Coarse-grained, budget-enforced TAREL MCP tool dispatcher over ``Tarel(state_root)``.

Every tool delegates directly to the TAREL SDK without duplicating domain logic, applies
explicit hard caps and truncation metadata, evaluates the configured :class:`PolicyHook`,
and returns structured errors instead of raw tracebacks.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from tarel.graph.contracts import GraphNode
from tarel.mcp.contracts import (
    DEFAULT_CONTEXT_MAX_CHARS,
    DEFAULT_CONTEXT_MAX_OBJECTS,
    DEFAULT_FOCUS_LIMIT,
    DEFAULT_GROUNDING_MAX_OBJECTS,
    DEFAULT_LINEAGE_LIMIT,
    DEFAULT_LINEAGE_MAX_HOPS,
    DEFAULT_OBJECTS_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_CONTEXT_MAX_CHARS,
    MAX_CONTEXT_MAX_OBJECTS,
    MAX_FOCUS_LIMIT,
    MAX_GROUNDING_MAX_OBJECTS,
    MAX_LINEAGE_LIMIT,
    MAX_LINEAGE_MAX_HOPS,
    MAX_OBJECTS_LIMIT,
    MAX_SEARCH_LIMIT,
    MAX_SLICE_OBJECTS,
    McpFailure,
    McpServerConfig,
    clamp_int,
    format_mcp_error,
)
from tarel.mcp.policy import NoOpPolicyHook, PolicyHook, ToolCallContext
from tarel.sdk import Tarel

_VALID_INSPECT_MODES = frozenset({"header", "objects", "slice"})
_VALID_SEARCH_MODES = frozenset({"lexical", "bm25", "hybrid"})
_VALID_LINEAGE_MODES = frozenset({"upstream", "downstream", "tables"})
_VALID_FOCUS_ACTIONS = frozenset({"list", "show"})

READ_ONLY_TOOL_NAMES: tuple[str, ...] = (
    "tarel_catalog_overview",
    "tarel_graph_inspect",
    "tarel_search",
    "tarel_context",
    "tarel_grounding",
    "tarel_lineage_trace",
    "tarel_focus",
)
WRITE_TOOL_NAMES: tuple[str, ...] = ("tarel_annotate_draft",)


class TarelMcpDispatcher:
    """Transport-agnostic dispatcher implementing the 8 TAREL MCP tools."""

    def __init__(
        self,
        config: McpServerConfig,
        *,
        policy_hook: PolicyHook | None = None,
    ) -> None:
        self.config = config
        self.policy_hook: PolicyHook = policy_hook if policy_hook is not None else NoOpPolicyHook()
        self._client = Tarel(config.state_root)

    @property
    def client(self) -> Tarel:
        """The underlying explicit-root ``Tarel`` SDK client."""
        return self._client

    @property
    def state_root(self) -> Path:
        return self._client.root

    def available_tools(self) -> tuple[str, ...]:
        """Return tool names enabled for the configured profile."""
        if self.config.profile == "meta-write":
            return READ_ONLY_TOOL_NAMES + WRITE_TOOL_NAMES
        return READ_ONLY_TOOL_NAMES

    def _execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        ctx = ToolCallContext(
            tool_name=tool_name,
            profile=self.config.profile,
            workspace=self.config.workspace,
            state_root=self.state_root,
            args=dict(args),
        )
        try:
            if tool_name in WRITE_TOOL_NAMES and self.config.profile != "meta-write":
                raise McpFailure(
                    "profile_read_only",
                    f"Tool `{tool_name}` is disabled in read-only profile `{self.config.profile}`.",
                    hint=(
                        "Start the server with `--profile meta-write` to enable "
                        "draft annotations."
                    ),
                )
            decision = self.policy_hook.before_tool_call(ctx)
            effective_args = dict(args)
            if decision is not None:
                if not decision.allowed:
                    raise McpFailure(
                        decision.code,
                        decision.reason or f"Policy denied tool `{tool_name}`.",
                        hint=decision.hint,
                    )
                if decision.override_args is not None:
                    effective_args = dict(decision.override_args)
            result = handler(effective_args)
            return self.policy_hook.after_tool_call(ctx, result)
        except Exception as exc:
            return format_mcp_error(exc)

    # ------------------------------------------------------------------
    # Tool 1: tarel_catalog_overview
    # ------------------------------------------------------------------
    def catalog_overview(self, *, workspace: str | None = None) -> dict[str, Any]:
        return self._execute(
            "tarel_catalog_overview",
            {"workspace": workspace},
            self._handle_catalog_overview,
        )

    def _handle_catalog_overview(self, args: dict[str, Any]) -> dict[str, Any]:
        selected_ws = args.get("workspace") or self.config.workspace
        workspace_names = self._client.workspace.list()
        workspaces_summary: list[dict[str, Any]] = []
        for ws_name in workspace_names:
            if selected_ws is not None and ws_name != selected_ws:
                continue
            ws_doc = self._client.workspace.load(ws_name)
            workspaces_summary.append(
                {
                    "name": ws_doc.name,
                    "description": ws_doc.description,
                    "system_count": len(ws_doc.systems),
                    "systems": [
                        {"name": sys_obj.name, "graphs": list(sys_obj.graphs)}
                        for sys_obj in ws_doc.systems
                    ],
                    "relationship_count": len(ws_doc.relationships),
                }
            )
        if selected_ws is not None and not workspaces_summary:
            raise McpFailure(
                "workspace_not_found",
                f"Workspace not found: {selected_ws}",
                hint=(
                    f"Available workspaces: {', '.join(workspace_names) or '(none)'}."
                ),
            )

        graphs_summary: list[dict[str, Any]] = []
        for graph_name in self._client.graph.list():
            header = self._client.graph.header(graph_name)
            graphs_summary.append(
                {
                    "name": header.name,
                    "catalog": header.catalog,
                    "connector": header.connector,
                    "dialect": header.dialect,
                    "object_count": header.object_count,
                    "node_count": header.node_count,
                    "edge_count": header.edge_count,
                    "revision": header.revision,
                }
            )

        focuses_summary: list[dict[str, Any]] = []
        for focus_name in self._client.focus.list():
            focus_doc = self._client.focus.load(focus_name)
            focuses_summary.append(
                {
                    "name": focus_doc.name,
                    "seed": focus_doc.seed,
                    "member_count": len(focus_doc.members),
                    "hop_count": len(focus_doc.hops),
                }
            )

        lineages_summary: list[dict[str, Any]] = []
        for lineage_name in self._client.lineage.list():
            status = self._client.lineage.status(lineage_name)
            tables = self._client.lineage.tables(lineage_name)
            lineages_summary.append(
                {
                    "name": lineage_name,
                    "table_count": len(tables),
                    "status": status.to_dict(),
                }
            )

        return {
            "status": "ok",
            "state_root": str(self.state_root),
            "profile": self.config.profile,
            "default_workspace": self.config.workspace,
            "counts": {
                "workspaces": len(workspaces_summary),
                "graphs": len(graphs_summary),
                "focuses": len(focuses_summary),
                "lineages": len(lineages_summary),
            },
            "workspaces": workspaces_summary,
            "graphs": graphs_summary,
            "focuses": focuses_summary,
            "lineages": lineages_summary,
        }

    # ------------------------------------------------------------------
    # Tool 2: tarel_graph_inspect
    # ------------------------------------------------------------------
    def graph_inspect(
        self,
        graph: str,
        *,
        mode: str = "header",
        namespace: str | None = None,
        offset: int = 0,
        limit: int = DEFAULT_OBJECTS_LIMIT,
        object_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_graph_inspect",
            {
                "graph": graph,
                "mode": mode,
                "namespace": namespace,
                "offset": offset,
                "limit": limit,
                "object_ids": list(object_ids) if object_ids is not None else None,
            },
            self._handle_graph_inspect,
        )

    def _handle_graph_inspect(self, args: dict[str, Any]) -> dict[str, Any]:
        graph_name = _require_non_empty_str(args.get("graph"), "graph")
        mode = str(args.get("mode") or "header").strip().lower()
        if mode not in _VALID_INSPECT_MODES:
            raise McpFailure(
                "invalid_mode",
                f"Unsupported inspect mode: {mode!r}.",
                hint=f"Use one of: {', '.join(sorted(_VALID_INSPECT_MODES))}.",
            )
        namespace = _optional_str(args.get("namespace"))

        if mode == "header":
            header = self._client.graph.header(graph_name)
            return {
                "status": "ok",
                "mode": "header",
                "header": header.to_dict(),
                "truncated": False,
            }

        if mode == "objects":
            offset_val, _ = clamp_int(
                args.get("offset", 0),
                minimum=0,
                maximum=1_000_000,
                field_name="offset",
            )
            limit_val, limit_clamped = clamp_int(
                args.get("limit", DEFAULT_OBJECTS_LIMIT),
                minimum=1,
                maximum=MAX_OBJECTS_LIMIT,
                field_name="limit",
            )
            page = self._client.graph.objects(
                graph_name,
                namespace=namespace,
                offset=offset_val,
                limit=limit_val,
            )
            truncated = page.next_offset is not None or limit_clamped
            return {
                "status": "ok",
                "mode": "objects",
                "graph": graph_name,
                "namespace": namespace,
                "offset": page.offset,
                "limit": page.limit,
                "total_count": page.total_objects,
                "next_offset": page.next_offset,
                "truncated": truncated,
                "objects": [_compact_object_node(node) for node in page.objects],
            }

        # mode == "slice"
        raw_ids = args.get("object_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise McpFailure(
                "missing_object_ids",
                "Parameter `object_ids` is required when `mode='slice'`.",
                hint=(
                    "Pass a non-empty list of object IDs from `tarel_search` or "
                    "`tarel_graph_inspect(mode='objects')`."
                ),
            )
        cleaned_ids = tuple(str(item).strip() for item in raw_ids if str(item).strip())
        if not cleaned_ids:
            raise McpFailure(
                "missing_object_ids",
                "Parameter `object_ids` must contain at least one non-empty object ID.",
            )
        truncated = len(cleaned_ids) > MAX_SLICE_OBJECTS
        bounded_ids = cleaned_ids[:MAX_SLICE_OBJECTS]
        graph_slice = self._client.graph.slice(
            graph_name,
            bounded_ids,
            namespace=namespace,
        )
        return {
            "status": "ok",
            "mode": "slice",
            "graph": graph_name,
            "requested_count": len(cleaned_ids),
            "returned_count": len(graph_slice.object_ids),
            "total_count": len(cleaned_ids),
            "truncated": truncated,
            "slice": graph_slice.to_dict(),
        }

    # ------------------------------------------------------------------
    # Tool 3: tarel_search
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        graph: str | None = None,
        workspace: str | None = None,
        mode: str = "lexical",
        limit: int = DEFAULT_SEARCH_LIMIT,
        namespace: str | None = None,
        validated_only: bool = False,
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_search",
            {
                "query": query,
                "graph": graph,
                "workspace": workspace,
                "mode": mode,
                "limit": limit,
                "namespace": namespace,
                "validated_only": validated_only,
            },
            self._handle_search,
        )

    def _handle_search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = _require_non_empty_str(args.get("query"), "query")
        mode = str(args.get("mode") or "lexical").strip().lower()
        if mode not in _VALID_SEARCH_MODES:
            raise McpFailure(
                "invalid_mode",
                f"Unsupported search mode: {mode!r}.",
                hint=f"Use one of: {', '.join(sorted(_VALID_SEARCH_MODES))}.",
            )
        limit_val, limit_clamped = clamp_int(
            args.get("limit", DEFAULT_SEARCH_LIMIT),
            minimum=1,
            maximum=MAX_SEARCH_LIMIT,
            field_name="limit",
        )
        graph_name, ws_name = self._resolve_scope(args.get("graph"), args.get("workspace"))
        namespace = _optional_str(args.get("namespace"))
        validated_only = bool(args.get("validated_only", False))

        # Request one extra hit when possible to detect truncation accurately without full scans.
        probe_limit = limit_val + 1 if limit_val < MAX_SEARCH_LIMIT else limit_val
        if graph_name is not None:
            results = self._client.search.graph(
                graph_name,
                query,
                limit=probe_limit,
                namespace=namespace,
                mode=mode,
                validated_only=validated_only,
            )
        else:
            assert ws_name is not None
            schemas = (namespace,) if namespace else ()
            results = self._client.search.workspace(
                ws_name,
                query,
                schemas=schemas,
                limit=probe_limit,
                mode=mode,
                validated_only=validated_only,
            )

        has_more = len(results.hits) > limit_val
        hits = results.hits[:limit_val]
        total_in_scope = (
            results.inventory.objects_after_filters
            if results.inventory is not None
            else len(results.hits)
        )
        truncated = has_more or limit_clamped
        compact_hits = [
            {
                "object_id": hit.id,
                "label": hit.label,
                "type": hit.type,
                "namespace": hit.namespace,
                "source_graph": hit.source_graph or results.graph,
                "score": hit.score,
                "summary": _truncate_text(hit.description, 200),
                "role": hit.role,
                "annotation_state": hit.annotation_state,
                "matched_fields": [f.label for f in hit.fields[:5]],
            }
            for hit in hits
        ]
        return {
            "status": "ok",
            "query": query,
            "mode": results.mode,
            "scope": {"graph": graph_name, "workspace": ws_name},
            "limit": limit_val,
            "returned_count": len(compact_hits),
            "total_count": total_in_scope,
            "truncated": truncated,
            "warnings": list(results.warnings),
            "hits": compact_hits,
        }

    # ------------------------------------------------------------------
    # Tool 4: tarel_context
    # ------------------------------------------------------------------
    def context(
        self,
        query: str,
        *,
        graph: str | None = None,
        workspace: str | None = None,
        max_objects: int = DEFAULT_CONTEXT_MAX_OBJECTS,
        max_characters: int = DEFAULT_CONTEXT_MAX_CHARS,
        mode: str = "lexical",
        namespace: str | None = None,
        validated_only: bool = False,
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_context",
            {
                "query": query,
                "graph": graph,
                "workspace": workspace,
                "max_objects": max_objects,
                "max_characters": max_characters,
                "mode": mode,
                "namespace": namespace,
                "validated_only": validated_only,
            },
            self._handle_context,
        )

    def _handle_context(self, args: dict[str, Any]) -> dict[str, Any]:
        query = _require_non_empty_str(args.get("query"), "query")
        mode = str(args.get("mode") or "lexical").strip().lower()
        if mode not in _VALID_SEARCH_MODES:
            raise McpFailure(
                "invalid_mode",
                f"Unsupported context search mode: {mode!r}.",
                hint=f"Use one of: {', '.join(sorted(_VALID_SEARCH_MODES))}.",
            )
        max_obj, obj_clamped = clamp_int(
            args.get("max_objects", DEFAULT_CONTEXT_MAX_OBJECTS),
            minimum=1,
            maximum=MAX_CONTEXT_MAX_OBJECTS,
            field_name="max_objects",
        )
        max_chars, chars_clamped = clamp_int(
            args.get("max_characters", DEFAULT_CONTEXT_MAX_CHARS),
            minimum=1_000,
            maximum=MAX_CONTEXT_MAX_CHARS,
            field_name="max_characters",
        )
        graph_name, ws_name = self._resolve_scope(args.get("graph"), args.get("workspace"))
        namespace = _optional_str(args.get("namespace"))
        validated_only = bool(args.get("validated_only", False))

        seed_limit = min(3, max_obj)
        if graph_name is not None:
            packet = self._client.context.graph(
                graph_name,
                query,
                namespace=namespace,
                seed_limit=seed_limit,
                max_objects=max_obj,
                max_characters=max_chars,
                mode=mode,
                validated_only=validated_only,
            )
        else:
            assert ws_name is not None
            schemas = (namespace,) if namespace else ()
            packet = self._client.context.workspace(
                ws_name,
                query,
                schemas=schemas,
                seed_limit=seed_limit,
                max_objects=max_obj,
                max_characters=max_chars,
                mode=mode,
                validated_only=validated_only,
            )

        packet_dict = packet.to_dict()
        omissions = packet.omissions
        truncated = bool(
            obj_clamped
            or chars_clamped
            or omissions.objects > 0
            or omissions.joins > 0
            or omissions.fields > 0
            or omissions.paths > 0
            or bool(omissions.reasons)
        )
        return {
            "status": "ok",
            "scope": {"graph": graph_name, "workspace": ws_name},
            "budget": {
                "max_objects": max_obj,
                "max_characters": max_chars,
            },
            "returned_objects": len(packet.objects),
            "total_count": len(packet.objects) + omissions.objects,
            "truncated": truncated,
            "context": packet_dict,
        }

    # ------------------------------------------------------------------
    # Tool 5: tarel_grounding
    # ------------------------------------------------------------------
    def grounding(
        self,
        *,
        question: str | None = None,
        graph: str | None = None,
        workspace: str | None = None,
        object_ids: Sequence[str] | None = None,
        source: str | None = None,
        lineages: Sequence[str] | None = None,
        max_objects: int = DEFAULT_GROUNDING_MAX_OBJECTS,
        max_characters: int = DEFAULT_CONTEXT_MAX_CHARS,
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_grounding",
            {
                "question": question,
                "graph": graph,
                "workspace": workspace,
                "object_ids": list(object_ids) if object_ids is not None else None,
                "source": source,
                "lineages": list(lineages) if lineages is not None else None,
                "max_objects": max_objects,
                "max_characters": max_characters,
            },
            self._handle_grounding,
        )

    def _handle_grounding(self, args: dict[str, Any]) -> dict[str, Any]:
        question = _optional_str(args.get("question"))
        raw_ids = args.get("object_ids")
        source = _optional_str(args.get("source"))
        lineage_names = _string_tuple_arg(args.get("lineages"), "lineages")

        if raw_ids is not None:
            if not isinstance(raw_ids, list) or not raw_ids:
                raise McpFailure(
                    "invalid_argument",
                    "Parameter `object_ids` must be a non-empty list of object IDs "
                    "or table references.",
                )
            graph_name = _optional_str(args.get("graph"))
            if graph_name is None:
                raise McpFailure(
                    "missing_graph",
                    "Grounding concrete `object_ids` requires `graph`.",
                    hint="Pass the catalog `graph` name owning the requested `object_ids`.",
                )
            cleaned_ids = tuple(str(item).strip() for item in raw_ids if str(item).strip())
            truncated = len(cleaned_ids) > MAX_GROUNDING_MAX_OBJECTS
            bounded_ids = cleaned_ids[:MAX_GROUNDING_MAX_OBJECTS]
            assets = [
                _compact_grounding_asset(
                    self._client.grounding.describe(graph_name, ref, source=source)
                )
                for ref in bounded_ids
            ]
            return {
                "status": "ok",
                "mode": "assets",
                "graph": graph_name,
                "returned_count": len(assets),
                "total_count": len(cleaned_ids),
                "truncated": truncated,
                "assets": assets,
            }

        if question is None:
            raise McpFailure(
                "missing_grounding_input",
                "Provide either `object_ids` (with `graph`) or `question` "
                "(with `graph` or `workspace`).",
                hint=(
                    "Use `object_ids` for exact table/column grounding or `question` "
                    "for a full grounding bundle."
                ),
            )

        max_obj, obj_clamped = clamp_int(
            args.get("max_objects", DEFAULT_GROUNDING_MAX_OBJECTS),
            minimum=1,
            maximum=MAX_GROUNDING_MAX_OBJECTS,
            field_name="max_objects",
        )
        max_chars, chars_clamped = clamp_int(
            args.get("max_characters", DEFAULT_CONTEXT_MAX_CHARS),
            minimum=1_000,
            maximum=MAX_CONTEXT_MAX_CHARS,
            field_name="max_characters",
        )
        graph_name, ws_name = self._resolve_scope(args.get("graph"), args.get("workspace"))
        bundle = self._client.grounding.context(
            question,
            graph=graph_name,
            workspace=ws_name,
            lineages=lineage_names,
            seed_limit=min(3, max_obj),
            max_objects=max_obj,
            max_characters=max_chars,
        )
        omissions = bundle.context.omissions
        truncated = bool(
            obj_clamped
            or chars_clamped
            or omissions.objects > 0
            or omissions.joins > 0
            or omissions.fields > 0
            or bool(omissions.reasons)
        )
        return {
            "status": "ok",
            "mode": "bundle",
            "scope": {"graph": graph_name, "workspace": ws_name},
            "returned_objects": len(bundle.context.objects),
            "total_count": len(bundle.context.objects) + omissions.objects,
            "truncated": truncated,
            "grounding": bundle.to_dict(),
        }

    # ------------------------------------------------------------------
    # Tool 6: tarel_lineage_trace
    # ------------------------------------------------------------------
    def lineage_trace(
        self,
        *,
        mode: str = "upstream",
        reference: str | None = None,
        lineage: str | None = None,
        lineages: Sequence[str] | None = None,
        graphs: Sequence[str] | None = None,
        workspace: str | None = None,
        max_hops: int = DEFAULT_LINEAGE_MAX_HOPS,
        limit: int = DEFAULT_LINEAGE_LIMIT,
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_lineage_trace",
            {
                "mode": mode,
                "reference": reference,
                "lineage": lineage,
                "lineages": list(lineages) if lineages is not None else None,
                "graphs": list(graphs) if graphs is not None else None,
                "workspace": workspace,
                "max_hops": max_hops,
                "limit": limit,
            },
            self._handle_lineage_trace,
        )

    def _handle_lineage_trace(self, args: dict[str, Any]) -> dict[str, Any]:
        mode = str(args.get("mode") or "upstream").strip().lower()
        if mode not in _VALID_LINEAGE_MODES:
            raise McpFailure(
                "invalid_mode",
                f"Unsupported lineage mode: {mode!r}.",
                hint=f"Use one of: {', '.join(sorted(_VALID_LINEAGE_MODES))}.",
            )
        graph_names = _string_tuple_arg(args.get("graphs"), "graphs")
        self._validate_catalog_graphs(graph_names)

        single_lineage = _optional_str(args.get("lineage"))
        lineage_names = _string_tuple_arg(args.get("lineages"), "lineages")
        if single_lineage and single_lineage not in lineage_names:
            lineage_names = (single_lineage, *lineage_names)

        if mode == "tables":
            target_lineage = single_lineage or (
                lineage_names[0] if len(lineage_names) == 1 else None
            )
            if target_lineage is None:
                raise McpFailure(
                    "missing_lineage",
                    "Mode `tables` requires exactly one lineage document name in `lineage`.",
                    hint="Call `tarel_catalog_overview` to list available lineage documents.",
                )
            limit_val, limit_clamped = clamp_int(
                args.get("limit", DEFAULT_LINEAGE_LIMIT),
                minimum=1,
                maximum=MAX_LINEAGE_LIMIT,
                field_name="limit",
            )
            all_tables = self._client.lineage.tables(target_lineage)
            sliced = all_tables[:limit_val]
            return {
                "status": "ok",
                "mode": "tables",
                "lineage": target_lineage,
                "returned_count": len(sliced),
                "total_count": len(all_tables),
                "truncated": len(all_tables) > limit_val or limit_clamped,
                "tables": [item.to_dict() for item in sliced],
            }

        reference = _require_non_empty_str(args.get("reference"), "reference")
        if not lineage_names:
            lineage_names = self._client.lineage.list()
            if not lineage_names:
                raise McpFailure(
                    "lineage_not_found",
                    "No lineage documents exist in this TAREL state root.",
                    hint="Build or import a lineage document before tracing.",
                )
        max_hops_val, _ = clamp_int(
            args.get("max_hops", DEFAULT_LINEAGE_MAX_HOPS),
            minimum=1,
            maximum=MAX_LINEAGE_MAX_HOPS,
            field_name="max_hops",
        )
        ws_name = _optional_str(args.get("workspace"))

        if mode == "upstream":
            if ws_name is not None and not graph_names:
                trace = self._client.lineage.upstream_workspace(
                    ws_name,
                    reference,
                    lineages=lineage_names,
                    max_hops=max_hops_val,
                )
            else:
                trace = self._client.lineage.upstream(
                    reference,
                    lineages=lineage_names,
                    graphs=graph_names,
                    max_hops=max_hops_val,
                )
            return {
                "status": "ok",
                "mode": "upstream",
                "lineages": list(lineage_names),
                "graphs": list(graph_names),
                "truncated": trace.truncated,
                "trace": trace.to_dict(),
            }

        # mode == "downstream": forward BFS over lineage table edges
        limit_val, limit_clamped = clamp_int(
            args.get("limit", DEFAULT_LINEAGE_LIMIT),
            minimum=1,
            maximum=MAX_LINEAGE_LIMIT,
            field_name="limit",
        )
        return self._trace_downstream(
            reference=reference,
            lineage_names=lineage_names,
            max_hops=max_hops_val,
            limit=limit_val,
            limit_clamped=limit_clamped,
        )

    def _validate_catalog_graphs(self, graph_names: tuple[str, ...]) -> None:
        if not graph_names:
            return
        known_graphs = set(self._client.graph.list())
        known_lineages = set(self._client.lineage.list())
        for name in graph_names:
            if name in known_graphs:
                continue
            if name in known_lineages:
                raise McpFailure(
                    "invalid_graph_argument",
                    f"`{name}` is a lineage document, not a catalog graph.",
                    hint=(
                        f"Move `{name}` from `graphs` to `lineages`. "
                        f"Available catalog graphs: {', '.join(sorted(known_graphs)) or '(none)'}."
                    ),
                    details={
                        "invalid_graph": name,
                        "available_graphs": sorted(known_graphs),
                        "available_lineages": sorted(known_lineages),
                    },
                )
            raise McpFailure(
                "graph_not_found",
                f"Unknown catalog graph in `graphs`: `{name}`.",
                hint=f"Available catalog graphs: {', '.join(sorted(known_graphs)) or '(none)'}.",
                details={"available_graphs": sorted(known_graphs)},
            )

    def _trace_downstream(
        self,
        *,
        reference: str,
        lineage_names: tuple[str, ...],
        max_hops: int,
        limit: int,
        limit_clamped: bool,
    ) -> dict[str, Any]:
        needle = reference.strip().casefold()
        adjacency: dict[str, list[dict[str, Any]]] = {}
        canonical_names: dict[str, str] = {}
        for lineage_name in lineage_names:
            for table_item in self._client.lineage.tables(lineage_name):
                src = table_item.source
                target = table_item.target
                src_key = src.casefold()
                target_key = target.casefold()
                canonical_names.setdefault(src_key, src)
                canonical_names.setdefault(target_key, target)
                adjacency.setdefault(src_key, []).append(
                    {
                        "lineage": lineage_name,
                        "source": src,
                        "target": target,
                        "role": table_item.role,
                        "via_definition": table_item.via_definition,
                        "state": table_item.state,
                        "via": list(table_item.via),
                    }
                )

        start_keys = [
            key
            for key in adjacency
            if key == needle or key.endswith(f".{needle}") or needle.endswith(f".{key}")
        ]
        if not start_keys:
            return {
                "status": "ok",
                "mode": "downstream",
                "reference": reference,
                "lineages": list(lineage_names),
                "hops": [],
                "terminals": [],
                "returned_count": 0,
                "total_count": 0,
                "truncated": False,
            }

        visited_nodes: set[str] = set(start_keys)
        visited_edges: set[tuple[str, str, str]] = set()
        queue: deque[tuple[str, int]] = deque((key, 0) for key in start_keys)
        hops: list[dict[str, Any]] = []
        terminals: set[str] = set()
        truncated = limit_clamped

        while queue:
            current_key, depth = queue.popleft()
            outgoing = adjacency.get(current_key, [])
            if not outgoing:
                terminals.add(canonical_names.get(current_key, current_key))
                continue
            if depth >= max_hops:
                truncated = True
                terminals.add(canonical_names.get(current_key, current_key))
                continue
            for edge in outgoing:
                edge_sig = (edge["lineage"], edge["source"].casefold(), edge["target"].casefold())
                if edge_sig in visited_edges:
                    continue
                visited_edges.add(edge_sig)
                if len(hops) >= limit:
                    truncated = True
                    continue
                hops.append({"depth": depth + 1, **edge})
                next_key = edge["target"].casefold()
                if next_key not in visited_nodes:
                    visited_nodes.add(next_key)
                    queue.append((next_key, depth + 1))

        return {
            "status": "ok",
            "mode": "downstream",
            "reference": reference,
            "lineages": list(lineage_names),
            "hops": hops,
            "terminals": sorted(terminals),
            "returned_count": len(hops),
            "total_count": len(hops),
            "truncated": truncated,
        }

    # ------------------------------------------------------------------
    # Tool 7: tarel_focus
    # ------------------------------------------------------------------
    def focus(
        self,
        *,
        action: str = "list",
        name: str | None = None,
        limit: int = DEFAULT_FOCUS_LIMIT,
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_focus",
            {"action": action, "name": name, "limit": limit},
            self._handle_focus,
        )

    def _handle_focus(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "list").strip().lower()
        if action not in _VALID_FOCUS_ACTIONS:
            raise McpFailure(
                "invalid_action",
                f"Unsupported focus action: {action!r}.",
                hint=f"Use one of: {', '.join(sorted(_VALID_FOCUS_ACTIONS))}.",
            )
        limit_val, limit_clamped = clamp_int(
            args.get("limit", DEFAULT_FOCUS_LIMIT),
            minimum=1,
            maximum=MAX_FOCUS_LIMIT,
            field_name="limit",
        )
        if action == "list":
            names = self._client.focus.list()
            sliced = names[:limit_val]
            items = []
            for focus_name in sliced:
                doc = self._client.focus.load(focus_name)
                items.append(
                    {
                        "name": doc.name,
                        "seed": doc.seed,
                        "member_count": len(doc.members),
                        "hop_count": len(doc.hops),
                    }
                )
            return {
                "status": "ok",
                "action": "list",
                "returned_count": len(items),
                "total_count": len(names),
                "truncated": len(names) > limit_val or limit_clamped,
                "focuses": items,
            }

        focus_name = _require_non_empty_str(args.get("name"), "name")
        doc = self._client.focus.load(focus_name)
        members = doc.members[:limit_val]
        hops = doc.hops[:limit_val]
        truncated = (
            doc.truncated
            or len(doc.members) > limit_val
            or len(doc.hops) > limit_val
            or limit_clamped
        )
        return {
            "status": "ok",
            "action": "show",
            "name": doc.name,
            "seed": doc.seed,
            "seed_id": doc.seed_id,
            "sources": [src.to_dict() for src in doc.sources],
            "total_members": len(doc.members),
            "total_hops": len(doc.hops),
            "total_count": len(doc.members),
            "truncated": truncated,
            "members": [member.to_dict() for member in members],
            "hops": [hop.to_dict() for hop in hops],
            "warnings": list(doc.warnings),
        }

    # ------------------------------------------------------------------
    # Tool 8: tarel_annotate_draft (meta-write profile only)
    # ------------------------------------------------------------------
    def annotate_draft(
        self,
        graph: str,
        proposal: dict[str, Any],
        *,
        source: str = "mcp-agent",
    ) -> dict[str, Any]:
        return self._execute(
            "tarel_annotate_draft",
            {"graph": graph, "proposal": proposal, "source": source},
            self._handle_annotate_draft,
        )

    def _handle_annotate_draft(self, args: dict[str, Any]) -> dict[str, Any]:
        graph_name = _require_non_empty_str(args.get("graph"), "graph")
        proposal = args.get("proposal")
        if not isinstance(proposal, dict):
            raise McpFailure(
                "invalid_proposal",
                "Parameter `proposal` must be a JSON object matching TAREL's "
                "annotation proposal contract.",
            )
        source = _optional_str(args.get("source")) or "mcp-agent"
        result = self._client.annotation.apply(graph_name, proposal, source=source)
        return {
            "status": "ok",
            "graph": graph_name,
            "target_id": result.target_id,
            "state": "draft",
            "provenance_source": source,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_scope(
        self,
        raw_graph: Any,
        raw_workspace: Any,
    ) -> tuple[str | None, str | None]:
        graph_name = _optional_str(raw_graph)
        ws_name = _optional_str(raw_workspace)
        if graph_name is not None and ws_name is not None:
            raise McpFailure(
                "ambiguous_scope",
                "Specify either `graph` or `workspace`, not both.",
                hint="Pass `graph` for a single graph or `workspace` for a multi-graph workspace.",
            )
        if graph_name is None and ws_name is None:
            if self.config.workspace is not None:
                ws_name = self.config.workspace
            else:
                graphs = self._client.graph.list()
                if len(graphs) == 1:
                    graph_name = graphs[0]
                else:
                    raise McpFailure(
                        "missing_scope",
                        "Provide `graph` or `workspace` (no default workspace configured).",
                        hint=(
                            "Call `tarel_catalog_overview` to inspect available graphs "
                            "and workspaces."
                        ),
                    )
        return graph_name, ws_name


def _require_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpFailure(
            "invalid_argument",
            f"Parameter `{field_name}` must be a non-empty string.",
        )
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value).strip() or None
    return value.strip() or None


def _string_tuple_arg(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    if not isinstance(value, (list, tuple)):
        raise McpFailure(
            "invalid_argument",
            f"Parameter `{field_name}` must be a list of strings.",
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise McpFailure(
                "invalid_argument",
                f"Every entry in `{field_name}` must be a non-empty string.",
            )
        result.append(item.strip())
    return tuple(result)


def _truncate_text(text: str | None, max_len: int) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 1].rstrip() + "…"


def _compact_object_node(node: GraphNode) -> dict[str, Any]:
    annotation = node.annotation
    return {
        "id": node.id,
        "label": node.label,
        "type": node.type,
        "namespace": node.metadata.get("namespace"),
        "primary_key": node.metadata.get("primary_key", []),
        "annotation_state": annotation.state if annotation else None,
        "role": annotation.role if annotation else None,
        "description": _truncate_text(annotation.description if annotation else None, 200),
    }


def _compact_grounding_asset(asset: Any) -> dict[str, Any]:
    node = asset.node
    annotation = node.annotation
    fields_payload = []
    for field_node in asset.fields:
        f_ann = field_node.annotation
        fields_payload.append(
            {
                "name": field_node.label,
                "data_type": field_node.metadata.get("data_type"),
                "nullable": field_node.metadata.get("nullable"),
                "is_primary_key": bool(field_node.metadata.get("is_primary_key", False)),
                "description": (
                    f_ann.description if f_ann else field_node.metadata.get("description")
                ),
                "annotation_state": f_ann.state if f_ann else None,
            }
        )
    return {
        "reference": asset.reference,
        "object_id": node.id,
        "label": node.label,
        "type": node.type,
        "namespace": node.metadata.get("namespace"),
        "primary_key": node.metadata.get("primary_key", []),
        "source": asset.source.to_dict(),
        "annotation": (
            {
                "state": annotation.state,
                "role": annotation.role,
                "description": annotation.description,
                "grain": node.metadata.get("grain"),
                "synonyms": list(annotation.synonyms),
                "warnings": list(annotation.warnings),
            }
            if annotation
            else None
        ),
        "fields": fields_payload,
    }
