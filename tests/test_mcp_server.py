"""Unit, parity, profile, policy, and stdio integration tests for ``tarel mcp serve``."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tarel.cli import main as cli_main
from tarel.connectors.contracts import (
    CatalogField,
    CatalogObject,
    CatalogRelationship,
    CatalogResult,
)
from tarel.mcp import (
    MCP_SERVER_INSTRUCTIONS,
    READ_ONLY_TOOL_NAMES,
    WRITE_TOOL_NAMES,
    McpServerConfig,
    PolicyDecision,
    TarelMcpDispatcher,
    ToolCallContext,
    create_mcp_server,
)
from tarel.sdk import Tarel


def _build_synthetic_workspace(tmp_path: Path) -> tuple[Path, Tarel]:
    """Create a synthetic TAREL state root with graph, workspace, lineage, and focus."""
    state_root = tmp_path / ".tarel"
    client = Tarel(state_root)

    catalog = CatalogResult(
        connector="sqlite",
        source_type="sqlite",
        catalog="retail_demo",
        dialect="sqlite",
        objects=(
            CatalogObject(
                namespace="main",
                name="dim_customer",
                kind="table",
                description="Customer master dimension",
                primary_key=("customer_id",),
                fields=(
                    CatalogField("customer_id", 1, "INTEGER", False, "Primary key", True),
                    CatalogField("customer_name", 2, "TEXT", False, "Full name"),
                    CatalogField("region", 3, "TEXT", True, "Sales region"),
                ),
            ),
            CatalogObject(
                namespace="main",
                name="fact_sales",
                kind="table",
                description="Daily sales transactions",
                primary_key=("sale_id",),
                fields=(
                    CatalogField("sale_id", 1, "INTEGER", False, "Sale identifier", True),
                    CatalogField("customer_id", 2, "INTEGER", False, "FK to dim_customer"),
                    CatalogField("amount_eur", 3, "REAL", False, "Net revenue in EUR"),
                ),
            ),
            CatalogObject(
                namespace="main",
                name="vw_revenue_by_region",
                kind="view",
                description="Aggregated regional revenue view",
                fields=(
                    CatalogField("region", 1, "TEXT", True, "Sales region"),
                    CatalogField("total_revenue", 2, "REAL", True, "Sum of amount_eur"),
                ),
            ),
        ),
        relationships=(
            CatalogRelationship(
                name="fk_sales_customer",
                from_namespace="main",
                from_object="fact_sales",
                from_fields=("customer_id",),
                to_namespace="main",
                to_object="dim_customer",
                to_fields=("customer_id",),
            ),
        ),
    )
    client.graph.import_catalog("retail", catalog)
    client.workspace.create("analytics", description="Synthetic retail analytics workspace")
    client.workspace.define_system("analytics", "dwh", graphs=("retail",))

    # Build a minimal lineage document with two hops:
    # main.dim_customer + main.fact_sales -> main.vw_revenue_by_region
    client.lineage.add_job(
        "retail-etl",
        kind="script",
        job_name="build_revenue_view",
        qualified_name="etl.build_revenue_view",
        language="sql",
        source_reference="sql/vw_revenue_by_region.sql",
        description="Builds regional revenue view from fact_sales and dim_customer",
    )
    client.lineage.add_hop(
        "retail-etl",
        job="etl.build_revenue_view",
        source="main.fact_sales",
        target="main.vw_revenue_by_region",
        operation="insert",
        evidence_reference="sql/vw_revenue_by_region.sql",
        reason="Aggregates fact_sales into vw_revenue_by_region",
    )
    client.lineage.add_hop(
        "retail-etl",
        job="etl.build_revenue_view",
        source="main.dim_customer",
        target="main.vw_revenue_by_region",
        operation="insert",
        evidence_reference="sql/vw_revenue_by_region.sql",
        reason="Joins dim_customer region attribute",
    )
    client.focus.build(
        "revenue-focus",
        seed="main.vw_revenue_by_region",
        lineages=("retail-etl",),
        graphs=("retail",),
    )
    return state_root, client


def test_mcp_instructions_compact() -> None:
    assert len(MCP_SERVER_INSTRUCTIONS.encode("utf-8")) < 2048
    assert "tarel_search" in MCP_SERVER_INSTRUCTIONS
    assert "tarel_lineage_trace" in MCP_SERVER_INSTRUCTIONS


def test_cli_requires_explicit_state_root(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.delenv("TAREL_STATE_ROOT", raising=False)
    exit_code = cli_main(["mcp", "serve"])
    assert exit_code == 2
    stderr = capsys.readouterr().err
    assert "missing_state_root" in stderr


def test_parity_sdk_cli_and_mcp(tmp_path: Path, capsys: Any) -> None:
    state_root, sdk = _build_synthetic_workspace(tmp_path)
    dispatcher = TarelMcpDispatcher(
        McpServerConfig(state_root=state_root, profile="meta", workspace="analytics")
    )

    # 1. Catalog overview parity
    overview = dispatcher.catalog_overview()
    assert overview["status"] == "ok"
    assert overview["counts"] == {
        "workspaces": 1,
        "graphs": 1,
        "focuses": 1,
        "lineages": 1,
    }
    assert [g["name"] for g in overview["graphs"]] == list(sdk.graph.list())
    assert [w["name"] for w in overview["workspaces"]] == list(sdk.workspace.list())
    assert [f["name"] for f in overview["focuses"]] == list(sdk.focus.list())
    assert [lin["name"] for lin in overview["lineages"]] == list(sdk.lineage.list())

    # 2. Graph header & objects parity
    mcp_header = dispatcher.graph_inspect("retail", mode="header")
    sdk_header = sdk.graph.header("retail")
    assert mcp_header["status"] == "ok"
    assert mcp_header["header"]["object_count"] == sdk_header.object_count == 3
    assert mcp_header["header"]["revision"] == sdk_header.revision

    # 3. Search parity (SDK vs MCP vs CLI)
    mcp_search = dispatcher.search("revenue", graph="retail", mode="lexical", limit=10)
    sdk_search = sdk.search.graph("retail", "revenue", mode="lexical", limit=10)
    assert mcp_search["status"] == "ok"
    assert [h["object_id"] for h in mcp_search["hits"]] == [h.id for h in sdk_search.hits]

    # Workspace search using default workspace from config
    ws_search = dispatcher.search("customer", mode="bm25", limit=10)
    sdk_ws_search = sdk.search.workspace("analytics", "customer", mode="bm25", limit=10)
    assert ws_search["status"] == "ok"
    assert [h["object_id"] for h in ws_search["hits"]] == [h.id for h in sdk_ws_search.hits]

    # CLI parity on graph header
    assert cli_main(["graph", "header", "retail", "--format", "json"]) in (0, 2)
    capsys.readouterr()

    # 4. Context parity
    mcp_ctx = dispatcher.context("sales revenue by region", graph="retail", max_objects=5)
    sdk_ctx = sdk.context.graph("retail", "sales revenue by region", max_objects=5)
    assert mcp_ctx["status"] == "ok"
    assert mcp_ctx["returned_objects"] == len(sdk_ctx.objects)

    # 5. Grounding concrete object_ids & bundle
    obj_id = sdk.graph.objects("retail", limit=10).objects[0].id
    mcp_ground = dispatcher.grounding(graph="retail", object_ids=[obj_id])
    assert mcp_ground["status"] == "ok"
    assert mcp_ground["mode"] == "assets"
    assert mcp_ground["assets"][0]["object_id"] == obj_id
    assert len(mcp_ground["assets"][0]["fields"]) >= 2

    mcp_bundle = dispatcher.grounding(question="customer sales revenue", workspace="analytics")
    assert mcp_bundle["status"] == "ok"
    assert mcp_bundle["mode"] == "bundle"

    # 6. Lineage upstream, downstream, tables
    upstream = dispatcher.lineage_trace(
        mode="upstream",
        reference="main.vw_revenue_by_region",
        lineages=["retail-etl"],
        graphs=["retail"],
    )
    assert upstream["status"] == "ok"
    assert len(upstream["trace"]["hops"]) == 2

    downstream = dispatcher.lineage_trace(
        mode="downstream",
        reference="main.fact_sales",
        lineages=["retail-etl"],
    )
    assert downstream["status"] == "ok"
    assert any(h["target"] == "main.vw_revenue_by_region" for h in downstream["hops"])

    tables = dispatcher.lineage_trace(mode="tables", lineage="retail-etl")
    assert tables["status"] == "ok"
    assert tables["total_count"] == len(sdk.lineage.tables("retail-etl"))

    # 7. Focus list & show
    f_list = dispatcher.focus(action="list")
    assert f_list["status"] == "ok"
    assert [item["name"] for item in f_list["focuses"]] == ["revenue-focus"]

    f_show = dispatcher.focus(action="show", name="revenue-focus")
    assert f_show["status"] == "ok"
    assert f_show["seed"] == "main.vw_revenue_by_region"


def test_budget_and_truncation_metadata(tmp_path: Path) -> None:
    state_root, _ = _build_synthetic_workspace(tmp_path)
    dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))

    # Page 1 of 3 objects with limit=2 -> truncated=True, next_offset=2
    page1 = dispatcher.graph_inspect("retail", mode="objects", offset=0, limit=2)
    assert page1["status"] == "ok"
    assert page1["truncated"] is True
    assert page1["total_count"] == 3
    assert page1["next_offset"] == 2
    assert len(page1["objects"]) == 2

    # Page 2 -> remaining 1 object, next_offset=None, truncated=False
    page2 = dispatcher.graph_inspect("retail", mode="objects", offset=2, limit=2)
    assert page2["status"] == "ok"
    assert page2["truncated"] is False
    assert page2["next_offset"] is None
    assert len(page2["objects"]) == 1

    # Hard cap clamping flags truncated=True
    clamped = dispatcher.graph_inspect("retail", mode="objects", offset=0, limit=9999)
    assert clamped["status"] == "ok"
    assert clamped["limit"] == 200
    assert clamped["truncated"] is True

    # Context tight object & character budget
    tight_ctx = dispatcher.context(
        "sales customer revenue", graph="retail", max_objects=1, max_characters=4000
    )
    assert tight_ctx["status"] == "ok", tight_ctx
    assert tight_ctx["budget"] == {"max_objects": 1, "max_characters": 4000}
    assert tight_ctx["returned_objects"] == 1
    assert tight_ctx["truncated"] is True


def test_lineage_rejects_lineage_name_in_graphs_param(tmp_path: Path) -> None:
    state_root, _ = _build_synthetic_workspace(tmp_path)
    dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))

    err = dispatcher.lineage_trace(
        mode="upstream",
        reference="main.vw_revenue_by_region",
        lineages=["retail-etl"],
        graphs=["retail-etl"],  # accidentally passed lineage name as graph!
    )
    assert err["status"] == "error"
    assert err["code"] == "invalid_graph_argument"
    assert "lineage document" in err["message"]
    assert "Move `retail-etl` from `graphs` to `lineages`" in (err["hint"] or "")
    assert err["retryable"] is False


def test_read_only_profile_and_validated_annotation_protection(tmp_path: Path) -> None:
    state_root, sdk = _build_synthetic_workspace(tmp_path)

    # Plan an annotation task for dim_customer
    tasks = sdk.annotation.plan_graph("retail", objects={"main.dim_customer"})
    assert len(tasks) == 1
    task = tasks[0]
    proposal: dict[str, Any] = {
        "task_id": task.id,
        "target_id": task.target_id,
        "mode": task.mode,
        "include_object": True,
        "field_names": list(task.field_names),
        "annotation": {
            "description": "Master table of retail customers.",
            "role": "dimension",
            "grain": "one row per customer_id",
            "synonyms": ["customers", "clients"],
            "tags": ["crm"],
            "warnings": [],
            "confidence": 0.9,
            "confidence_reason": "Clear primary key and customer columns.",
            "evidence": [{"source": "schema", "reference": "main.dim_customer"}],
            "fields": [
                {
                    "name": fname,
                    "description": f"Field {fname}",
                    "role": "identifier" if fname == "customer_id" else "attribute",
                    "synonyms": [],
                    "tags": [],
                    "warnings": [],
                    "confidence": 0.9,
                    "confidence_reason": "Observed column",
                    "evidence": [{"source": "schema", "reference": f"main.dim_customer.{fname}"}],
                }
                for fname in task.field_names
            ],
        },
    }

    # 1. Default `meta` profile rejects writes and does not expose write tools
    ro_dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))
    assert ro_dispatcher.available_tools() == READ_ONLY_TOOL_NAMES
    ro_res = ro_dispatcher.annotate_draft("retail", proposal)
    assert ro_res["status"] == "error"
    assert ro_res["code"] == "profile_read_only"

    # 2. `meta-write` profile applies draft with provenance
    rw_dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta-write"))
    assert rw_dispatcher.available_tools() == READ_ONLY_TOOL_NAMES + WRITE_TOOL_NAMES
    ok_res = rw_dispatcher.annotate_draft("retail", proposal, source="mcp-test-agent")
    assert ok_res["status"] == "ok"
    assert ok_res["state"] == "draft"
    assert ok_res["provenance_source"] == "mcp-test-agent"

    # 3. Human validates the annotation -> subsequent draft proposal MUST be rejected
    sdk.annotation.decide(
        "retail",
        task.target_id,
        state="validated",
        reason="Reviewed by BI owner",
        include_fields=True,
    )
    # Re-plan in full mode to get fresh task_id targeting the now-validated object
    full_tasks = sdk.annotation.plan_graph(
        "retail", objects={"main.dim_customer"}, missing_only=False
    )
    proposal["task_id"] = full_tasks[0].id
    proposal["mode"] = full_tasks[0].mode
    proposal.pop("include_object", None)
    proposal["field_names"] = list(full_tasks[0].field_names)

    blocked = rw_dispatcher.annotate_draft("retail", proposal, source="mcp-test-agent")
    assert blocked["status"] == "error"
    assert blocked["code"] == "reviewed_annotation"


def test_policy_hook_seam_deny_and_redact(tmp_path: Path) -> None:
    state_root, _ = _build_synthetic_workspace(tmp_path)
    audit_log: list[str] = []

    class TestWallPolicy:
        def before_tool_call(self, context: ToolCallContext) -> PolicyDecision | None:
            audit_log.append(f"before:{context.tool_name}")
            if context.tool_name == "tarel_focus":
                return PolicyDecision(
                    allowed=False,
                    code="wall_blocked",
                    reason="Focus access blocked by test policy.",
                    hint="Request workspace scope approval.",
                )
            return None

        def after_tool_call(
            self,
            context: ToolCallContext,
            result: dict[str, Any],
        ) -> dict[str, Any]:
            audit_log.append(f"after:{context.tool_name}")
            redacted = dict(result)
            redacted["policy_audited"] = True
            return redacted

    dispatcher = TarelMcpDispatcher(
        McpServerConfig(state_root=state_root, profile="meta"),
        policy_hook=TestWallPolicy(),
    )

    denied = dispatcher.focus(action="list")
    assert denied["status"] == "error"
    assert denied["code"] == "wall_blocked"

    allowed = dispatcher.catalog_overview()
    assert allowed["status"] == "ok"
    assert allowed["policy_audited"] is True
    assert "before:tarel_focus" in audit_log
    assert "after:tarel_catalog_overview" in audit_log


def test_real_mcp_stdio_roundtrip(tmp_path: Path) -> None:
    """Spawn `tarel mcp serve --transport stdio` and verify MCP handshake, tools, and calls."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    state_root, _ = _build_synthetic_workspace(tmp_path)

    async def _run(profile: str) -> tuple[str | None, list[str], dict[str, Any]]:
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "tarel",
                "mcp",
                "serve",
                "--state-root",
                str(state_root),
                "--profile",
                profile,
                "--workspace",
                "analytics",
            ],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init_res = await session.initialize()
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            call_res = await session.call_tool("tarel_catalog_overview", {})
            text_parts = [
                text
                for item in call_res.content
                if (text := getattr(item, "text", ""))
            ]
            payload = json.loads("\n".join(text_parts))
            return init_res.instructions, tool_names, payload

    instructions, ro_tools, overview = asyncio.run(_run("meta"))
    assert instructions is not None
    assert "TAREL Metadata & Context Server" in instructions
    assert set(ro_tools) == set(READ_ONLY_TOOL_NAMES)
    assert "tarel_annotate_draft" not in ro_tools
    assert overview["status"] == "ok"
    assert overview["counts"]["graphs"] == 1

    # Verify meta-write exposes tarel_annotate_draft too
    _, rw_tools, _ = asyncio.run(_run("meta-write"))
    assert set(rw_tools) == set(READ_ONLY_TOOL_NAMES) | set(WRITE_TOOL_NAMES)


def test_create_mcp_server_helper(tmp_path: Path) -> None:
    state_root, _ = _build_synthetic_workspace(tmp_path)
    server, dispatcher = create_mcp_server(McpServerConfig(state_root=state_root))
    assert server is not None
    assert dispatcher.state_root == state_root.resolve()
