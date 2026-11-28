"""Unit, parity, profile, policy, and stdio integration tests for ``tarel mcp serve``."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

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

_HAS_MCP = importlib.util.find_spec("mcp") is not None


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


class TestTarelMcpServer(unittest.TestCase):
    def test_mcp_instructions_compact(self) -> None:
        self.assertLess(len(MCP_SERVER_INSTRUCTIONS.encode("utf-8")), 2048)
        self.assertIn("tarel_search", MCP_SERVER_INSTRUCTIONS)
        self.assertIn("tarel_lineage_trace", MCP_SERVER_INSTRUCTIONS)

    def test_cli_requires_explicit_state_root(self) -> None:
        buf = io.StringIO()
        cleaned_env = {k: v for k, v in os.environ.items() if k != "TAREL_STATE_ROOT"}
        with patch.dict(os.environ, cleaned_env, clear=True), contextlib.redirect_stderr(buf):
            exit_code = cli_main(["mcp", "serve"])
        self.assertEqual(exit_code, 2)
        self.assertIn("missing_state_root", buf.getvalue())

    def test_parity_sdk_cli_and_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, sdk = _build_synthetic_workspace(Path(tmp))
            dispatcher = TarelMcpDispatcher(
                McpServerConfig(state_root=state_root, profile="meta", workspace="analytics")
            )

            overview = dispatcher.catalog_overview()
            self.assertEqual(overview["status"], "ok")
            self.assertEqual(
                overview["counts"],
                {"workspaces": 1, "graphs": 1, "focuses": 1, "lineages": 1},
            )
            self.assertEqual([g["name"] for g in overview["graphs"]], list(sdk.graph.list()))
            self.assertEqual(
                [w["name"] for w in overview["workspaces"]], list(sdk.workspace.list())
            )
            self.assertEqual([f["name"] for f in overview["focuses"]], list(sdk.focus.list()))
            self.assertEqual(
                [lin["name"] for lin in overview["lineages"]], list(sdk.lineage.list())
            )

            mcp_header = dispatcher.graph_inspect("retail", mode="header")
            sdk_header = sdk.graph.header("retail")
            self.assertEqual(mcp_header["status"], "ok")
            self.assertEqual(mcp_header["header"]["object_count"], 3)
            self.assertEqual(mcp_header["header"]["revision"], sdk_header.revision)

            mcp_search = dispatcher.search("revenue", graph="retail", mode="lexical", limit=10)
            sdk_search = sdk.search.graph("retail", "revenue", mode="lexical", limit=10)
            self.assertEqual(mcp_search["status"], "ok")
            self.assertEqual(
                [h["object_id"] for h in mcp_search["hits"]],
                [h.id for h in sdk_search.hits],
            )

            ws_search = dispatcher.search("customer", mode="bm25", limit=10)
            sdk_ws_search = sdk.search.workspace("analytics", "customer", mode="bm25", limit=10)
            self.assertEqual(ws_search["status"], "ok")
            self.assertEqual(
                [h["object_id"] for h in ws_search["hits"]],
                [h.id for h in sdk_ws_search.hits],
            )

            mcp_ctx = dispatcher.context("sales revenue by region", graph="retail", max_objects=5)
            sdk_ctx = sdk.context.graph("retail", "sales revenue by region", max_objects=5)
            self.assertEqual(mcp_ctx["status"], "ok")
            self.assertEqual(mcp_ctx["returned_objects"], len(sdk_ctx.objects))

            obj_id = sdk.graph.objects("retail", limit=10).objects[0].id
            mcp_ground = dispatcher.grounding(graph="retail", object_ids=[obj_id])
            self.assertEqual(mcp_ground["status"], "ok")
            self.assertEqual(mcp_ground["mode"], "assets")
            self.assertEqual(mcp_ground["assets"][0]["object_id"], obj_id)
            self.assertGreaterEqual(len(mcp_ground["assets"][0]["fields"]), 2)

            mcp_bundle = dispatcher.grounding(
                question="customer sales revenue", workspace="analytics"
            )
            self.assertEqual(mcp_bundle["status"], "ok")
            self.assertEqual(mcp_bundle["mode"], "bundle")

            upstream = dispatcher.lineage_trace(
                mode="upstream",
                reference="main.vw_revenue_by_region",
                lineages=["retail-etl"],
                graphs=["retail"],
            )
            self.assertEqual(upstream["status"], "ok")
            self.assertEqual(len(upstream["trace"]["hops"]), 2)

            downstream = dispatcher.lineage_trace(
                mode="downstream",
                reference="main.fact_sales",
                lineages=["retail-etl"],
            )
            self.assertEqual(downstream["status"], "ok")
            self.assertTrue(
                any(h["target"] == "main.vw_revenue_by_region" for h in downstream["hops"])
            )

            tables = dispatcher.lineage_trace(mode="tables", lineage="retail-etl")
            self.assertEqual(tables["status"], "ok")
            self.assertEqual(tables["total_count"], len(sdk.lineage.tables("retail-etl")))

            f_list = dispatcher.focus(action="list")
            self.assertEqual(f_list["status"], "ok")
            self.assertEqual([item["name"] for item in f_list["focuses"]], ["revenue-focus"])

            f_show = dispatcher.focus(action="show", name="revenue-focus")
            self.assertEqual(f_show["status"], "ok")
            self.assertEqual(f_show["seed"], "main.vw_revenue_by_region")

    def test_budget_and_truncation_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, _ = _build_synthetic_workspace(Path(tmp))
            dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))

            page1 = dispatcher.graph_inspect("retail", mode="objects", offset=0, limit=2)
            self.assertEqual(page1["status"], "ok")
            self.assertTrue(page1["truncated"])
            self.assertEqual(page1["total_count"], 3)
            self.assertEqual(page1["next_offset"], 2)
            self.assertEqual(len(page1["objects"]), 2)

            page2 = dispatcher.graph_inspect("retail", mode="objects", offset=2, limit=2)
            self.assertEqual(page2["status"], "ok")
            self.assertFalse(page2["truncated"])
            self.assertIsNone(page2["next_offset"])
            self.assertEqual(len(page2["objects"]), 1)

            clamped = dispatcher.graph_inspect("retail", mode="objects", offset=0, limit=9999)
            self.assertEqual(clamped["status"], "ok")
            self.assertEqual(clamped["limit"], 200)
            self.assertTrue(clamped["truncated"])

            tight_ctx = dispatcher.context(
                "sales customer revenue", graph="retail", max_objects=1, max_characters=4000
            )
            self.assertEqual(tight_ctx["status"], "ok")
            self.assertEqual(tight_ctx["budget"], {"max_objects": 1, "max_characters": 4000})
            self.assertEqual(tight_ctx["returned_objects"], 1)
            self.assertTrue(tight_ctx["truncated"])

    def test_lineage_rejects_lineage_name_in_graphs_param(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, _ = _build_synthetic_workspace(Path(tmp))
            dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))

            err = dispatcher.lineage_trace(
                mode="upstream",
                reference="main.vw_revenue_by_region",
                lineages=["retail-etl"],
                graphs=["retail-etl"],
            )
            self.assertEqual(err["status"], "error")
            self.assertEqual(err["code"], "invalid_graph_argument")
            self.assertIn("lineage document", err["message"])
            self.assertIn("Move `retail-etl` from `graphs` to `lineages`", err["hint"] or "")
            self.assertFalse(err["retryable"])

    def test_read_only_profile_and_validated_annotation_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, sdk = _build_synthetic_workspace(Path(tmp))
            tasks = sdk.annotation.plan_graph("retail", objects={"main.dim_customer"})
            self.assertEqual(len(tasks), 1)
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
                            "evidence": [
                                {"source": "schema", "reference": f"main.dim_customer.{fname}"}
                            ],
                        }
                        for fname in task.field_names
                    ],
                },
            }

            ro_dispatcher = TarelMcpDispatcher(
                McpServerConfig(state_root=state_root, profile="meta")
            )
            self.assertEqual(ro_dispatcher.available_tools(), READ_ONLY_TOOL_NAMES)
            ro_res = ro_dispatcher.annotate_draft("retail", proposal)
            self.assertEqual(ro_res["status"], "error")
            self.assertEqual(ro_res["code"], "profile_read_only")

            rw_dispatcher = TarelMcpDispatcher(
                McpServerConfig(state_root=state_root, profile="meta-write")
            )
            self.assertEqual(
                rw_dispatcher.available_tools(), READ_ONLY_TOOL_NAMES + WRITE_TOOL_NAMES
            )
            # Plan via MCP directly (no external SDK call required)
            planned = rw_dispatcher.annotate_draft(
                "retail",
                action="plan",
                objects=["main.dim_customer"],
            )
            self.assertEqual(planned["status"], "ok")
            self.assertEqual(planned["action"], "plan")
            self.assertEqual(len(planned["tasks"]), 1)
            self.assertEqual(planned["tasks"][0]["task_id"], task.id)

            ok_res = rw_dispatcher.annotate_draft("retail", proposal, source="mcp-test-agent")
            self.assertEqual(ok_res["status"], "ok")
            self.assertEqual(ok_res["state"], "draft")
            self.assertEqual(ok_res["provenance_source"], "mcp-test-agent")

            sdk.annotation.decide(
                "retail",
                task.target_id,
                state="validated",
                reason="Reviewed by BI owner",
                include_fields=True,
            )
            full_tasks = sdk.annotation.plan_graph(
                "retail", objects={"main.dim_customer"}, missing_only=False
            )
            proposal["task_id"] = full_tasks[0].id
            proposal["mode"] = full_tasks[0].mode
            proposal.pop("include_object", None)
            proposal["field_names"] = list(full_tasks[0].field_names)

            blocked = rw_dispatcher.annotate_draft("retail", proposal, source="mcp-test-agent")
            self.assertEqual(blocked["status"], "error")
            self.assertEqual(blocked["code"], "reviewed_annotation")

    def test_grounding_budgets_and_direct_field_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, _ = _build_synthetic_workspace(Path(tmp))
            dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))

            # Enforce max_objects budget on concrete object_ids
            capped = dispatcher.grounding(
                graph="retail",
                object_ids=["main.dim_customer", "main.fact_sales"],
                max_objects=1,
            )
            self.assertEqual(capped["status"], "ok")
            self.assertEqual(capped["returned_count"], 1)
            self.assertEqual(capped["omitted_objects"], 1)
            self.assertTrue(capped["truncated"])

            # Direct field grounding retains column data_type, nullable, is_primary_key
            field_ground = dispatcher.grounding(
                graph="retail",
                object_ids=["main.dim_customer.customer_id"],
            )
            self.assertEqual(field_ground["status"], "ok")
            asset = field_ground["assets"][0]
            self.assertEqual(asset["type"], "field")
            self.assertEqual(asset["field"]["data_type"], "INTEGER")
            self.assertFalse(asset["field"]["nullable"])
            self.assertTrue(asset["field"]["is_primary_key"])

    def test_downstream_preserves_temporary_table_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, sdk = _build_synthetic_workspace(Path(tmp))
            sdk.lineage.add_job(
                "doc-one",
                kind="script",
                job_name="job_one",
                qualified_name="etl.job_one",
                language="sql",
                source_reference="sql/one.sql",
                description="Writes #tmp in doc-one",
            )
            sdk.lineage.add_hop(
                "doc-one",
                job="etl.job_one",
                source="main.fact_sales",
                target="#tmp",
                operation="insert",
                evidence_reference="sql/one.sql",
                reason="Stages into #tmp",
            )
            sdk.lineage.add_job(
                "doc-two",
                kind="script",
                job_name="job_two",
                qualified_name="etl.job_two",
                language="sql",
                source_reference="sql/two.sql",
                description="Reads unrelated #tmp in doc-two",
            )
            sdk.lineage.add_hop(
                "doc-two",
                job="etl.job_two",
                source="#tmp",
                target="main.vw_revenue_by_region",
                operation="insert",
                evidence_reference="sql/two.sql",
                reason="Reads own #tmp",
            )

            dispatcher = TarelMcpDispatcher(McpServerConfig(state_root=state_root, profile="meta"))
            res = dispatcher.lineage_trace(
                mode="downstream",
                reference="main.fact_sales",
                lineages=["doc-one", "doc-two"],
            )
            self.assertEqual(res["status"], "ok")
            targets = [hop["target"] for hop in res["hops"]]
            self.assertEqual(targets, ["#tmp"])
            self.assertNotIn("main.vw_revenue_by_region", targets)

    def test_policy_hook_seam_deny_and_redact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, _ = _build_synthetic_workspace(Path(tmp))
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
            self.assertEqual(denied["status"], "error")
            self.assertEqual(denied["code"], "wall_blocked")
            # after_tool_call runs on structured error responses too (for audit/redaction)
            self.assertTrue(denied["policy_audited"])
            self.assertIn("after:tarel_focus", audit_log)

            # Upstream limit enforcement
            capped_up = dispatcher.lineage_trace(
                mode="upstream",
                reference="main.vw_revenue_by_region",
                lineages=["retail-etl"],
                graphs=["retail"],
                limit=1,
            )
            self.assertEqual(capped_up["status"], "ok")
            self.assertEqual(capped_up["returned_hops"], 1)
            self.assertEqual(capped_up["total_hops"], 2)
            self.assertEqual(capped_up["omitted_hops"], 1)
            self.assertTrue(capped_up["truncated"])

            allowed = dispatcher.catalog_overview()
            self.assertEqual(allowed["status"], "ok")
            self.assertTrue(allowed["policy_audited"])
            self.assertIn("before:tarel_focus", audit_log)
            self.assertIn("after:tarel_catalog_overview", audit_log)

    @unittest.skipUnless(_HAS_MCP, "optional mcp extra not installed")
    def test_real_mcp_stdio_roundtrip(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as tmp:
            state_root, _ = _build_synthetic_workspace(Path(tmp))

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
                async with (
                    stdio_client(params) as (read, write),
                    ClientSession(read, write) as session,
                ):
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
            self.assertIsNotNone(instructions)
            self.assertIn("TAREL Metadata & Context Server", instructions or "")
            self.assertEqual(set(ro_tools), set(READ_ONLY_TOOL_NAMES))
            self.assertNotIn("tarel_annotate_draft", ro_tools)
            self.assertEqual(overview["status"], "ok")
            self.assertEqual(overview["counts"]["graphs"], 1)

            _, rw_tools, _ = asyncio.run(_run("meta-write"))
            self.assertEqual(set(rw_tools), set(READ_ONLY_TOOL_NAMES) | set(WRITE_TOOL_NAMES))

    @unittest.skipUnless(_HAS_MCP, "optional mcp extra not installed")
    def test_create_mcp_server_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root, _ = _build_synthetic_workspace(Path(tmp))
            server, dispatcher = create_mcp_server(McpServerConfig(state_root=state_root))
            self.assertIsNotNone(server)
            self.assertEqual(dispatcher.state_root, state_root.resolve())


if __name__ == "__main__":
    unittest.main()
