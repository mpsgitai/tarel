# TAREL MCP Server (`tarel mcp serve`)

`tarel mcp serve` exposes the **TAREL SDK (`Tarel(state_root)`)** as a standardized, coarse-grained Model Context Protocol (MCP) server for coding and BI agents.

## Architectural Boundary: `tarel-meta` vs. `execution-mcp`

TAREL is strictly the **metadata, semantic, retrieval, grounding, and lineage authority** — never a business-data query engine.

- **`tarel-meta` (`tarel mcp serve`)**: Serves catalog overviews, paginated graph inspection, lexical/BM25/hybrid search, budgeted semantic context, exact table/column grounding, lineage tracing, and curated focus scopes.
- **`execution-mcp` (separate server)**: Runs authorized SQL, DuckDB, Python, or DAX queries against source systems or analytical frames (for example, `tarel-bi` in TAREL Harness).

Keeping these two MCP servers separate ensures agents ground themselves in reviewed metadata first, while business-data execution remains independently governed and auditable.

### Policy Seam for Tarel Wall

Every MCP tool invocation passes through `tarel.mcp.policy.PolicyHook` with an immutable `ToolCallContext(tool_name, profile, workspace, state_root, args)`:

- `before_tool_call(context) -> PolicyDecision | None`: Allow, deny (with structured error code/hint), or rewrite arguments.
- `after_tool_call(context, result) -> dict[str, Any]`: Audit or redact responses before serialization.

By default `NoOpPolicyHook` is attached. **Tarel Wall** can later enforce workspace allowlists, PII redaction, and audit logging directly at this boundary without modifying tool handlers.

---

## Installation & CLI Usage

Install the optional MCP extra:

```bash
pip install "tarel[mcp]"
```

Start the server with an **explicit** state root (no implicit CWD `.tarel` fallback):

```bash
# Default read-only metadata profile over stdio
tarel mcp serve --state-root /path/to/.tarel --workspace analytics

# Streamable HTTP on loopback
tarel mcp serve --state-root /path/to/.tarel \
  --transport streamable-http --host 127.0.0.1 --port 8770

# Opt-in draft-annotation profile (never overwrites validated/reviewed annotations)
tarel mcp serve --state-root /path/to/.tarel --profile meta-write
```

You may also supply the state root via `TAREL_STATE_ROOT=/path/to/.tarel`.

---

## Coarse-Grained Tool Surface

| Tool | Profile | Purpose |
| --- | --- | --- |
| `tarel_catalog_overview` | `meta`, `meta-write` | Compact counts & summaries of workspaces, graphs, focuses, and lineages. |
| `tarel_graph_inspect` | `meta`, `meta-write` | `mode="header"`, paginated `mode="objects"` (`offset`, `limit`, `namespace`), or `mode="slice"` (`object_ids`). |
| `tarel_search` | `meta`, `meta-write` | Unified search (`lexical` \| `bm25` \| `hybrid`) over a graph or workspace. |
| `tarel_context` | `meta`, `meta-write` | Budgeted semantic context packet (`max_objects`, `max_characters`). |
| `tarel_grounding` | `meta`, `meta-write` | Exact schema/key/annotation grounding for concrete `object_ids`, or a question grounding bundle. |
| `tarel_lineage_trace` | `meta`, `meta-write` | `upstream`, `downstream`, or `tables` lineage inspection; strictly validates catalog `graphs` vs. `lineages`. |
| `tarel_focus` | `meta`, `meta-write` | `action="list"` or `action="show"` for curated focus scopes. |
| `tarel_annotate_draft` | `meta-write` only | Applies draft proposals with provenance; rejects overwriting `validated` or human-reviewed annotations. |

Every tool enforces hard caps and returns explicit `truncated`, `total_count`, and (where paged) `next_offset` fields. Failures return structured JSON (`status: "error"`, `code`, `message`, `hint`, `retryable`) without raw tracebacks.

---

## Client Configuration Examples

### DeepSeek Harness (`cordis.tarel.patch.yml`)

```yaml
plugins:
  "@deepseek-ai/dsh-mcp-client":
    servers:
      tarel-meta:
        transport: stdio
        command: /path/to/.venv/bin/tarel
        args:
          - mcp
          - serve
          - --state-root
          - /path/to/.tarel
          - --workspace
          - analytics
```

### Claude Desktop / Claude Code (`mcpServers`)

```json
{
  "mcpServers": {
    "tarel-meta": {
      "command": "tarel",
      "args": [
        "mcp",
        "serve",
        "--state-root",
        "/path/to/.tarel",
        "--profile",
        "meta"
      ]
    }
  }
}
```

### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.tarel-meta]
command = "tarel"
args = ["mcp", "serve", "--state-root", "/path/to/.tarel", "--workspace", "analytics"]
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "tarel-meta": {
      "command": "tarel",
      "args": ["mcp", "serve", "--state-root", "/path/to/.tarel"]
    }
  }
}
```
