"""Contracts, hard caps, error formatting, and instructions for ``tarel mcp serve``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.errors import TarelError

VALID_PROFILES: frozenset[str] = frozenset({"meta", "meta-write"})
VALID_TRANSPORTS: frozenset[str] = frozenset({"stdio", "streamable-http"})

# Hard caps protecting LLM context windows from unbounded metadata dumps.
DEFAULT_OBJECTS_LIMIT = 50
MAX_OBJECTS_LIMIT = 200
MAX_SLICE_OBJECTS = 50
DEFAULT_SEARCH_LIMIT = 15
MAX_SEARCH_LIMIT = 50
DEFAULT_CONTEXT_MAX_OBJECTS = 10
MAX_CONTEXT_MAX_OBJECTS = 50
DEFAULT_CONTEXT_MAX_CHARS = 16_000
MAX_CONTEXT_MAX_CHARS = 64_000
DEFAULT_GROUNDING_MAX_OBJECTS = 10
MAX_GROUNDING_MAX_OBJECTS = 30
DEFAULT_LINEAGE_MAX_HOPS = 12
MAX_LINEAGE_MAX_HOPS = 25
DEFAULT_LINEAGE_LIMIT = 50
MAX_LINEAGE_LIMIT = 200
DEFAULT_FOCUS_LIMIT = 100
MAX_FOCUS_LIMIT = 200

# Compact (< 2 KB) server instructions delivered during the MCP handshake.
MCP_SERVER_INSTRUCTIONS = """\
TAREL Metadata & Context Server (read-only metadata authority; NOT a data query engine).

Workflow:
1. Orientation: call `tarel_catalog_overview` first to list workspaces, graphs,
   focuses, and lineages.
2. Discovery: use `tarel_search` (lexical | bm25 | hybrid) to find candidate objects,
   or `tarel_context` for a budgeted semantic packet with joins and annotations.
3. Exact schema & keys: use `tarel_grounding` (with concrete `object_ids` or `question`)
   or `tarel_graph_inspect(mode='slice')` before writing SQL or analytics code.
4. Lineage & focuses: use `tarel_lineage_trace` (upstream | downstream | tables) and
   `tarel_focus` (list | show) to verify ETL origins and curated working sets.
5. Execution boundary: run SQL, DuckDB, Python, or BI queries in your separate
   data-execution MCP/tool, never through TAREL.

Parameter hygiene:
- In `tarel_lineage_trace`, pass ONLY catalog graph names in `graphs` and ONLY lineage
  document names in `lineages` (never mix them).
- Respect `truncated`, `total_count`, and `next_offset`; narrow queries or page
  explicitly instead of requesting full graphs.
- In `meta-write` profile, `tarel_annotate_draft` writes draft proposals only and
  never overwrites validated/human-reviewed annotations.
"""

_RETRYABLE_CODES: frozenset[str] = frozenset(
    {
        "lock_timeout",
        "transient_error",
    }
)


class McpFailure(TarelError):
    """Structured failure raised by the TAREL MCP layer."""


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """Validated configuration for a ``tarel mcp serve`` instance."""

    state_root: Path
    profile: str = "meta"
    workspace: str | None = None
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8770

    def __post_init__(self) -> None:
        if self.profile not in VALID_PROFILES:
            raise McpFailure(
                "invalid_profile",
                f"Unsupported MCP profile: {self.profile!r}.",
                hint=f"Choose one of: {', '.join(sorted(VALID_PROFILES))}.",
            )
        if self.transport not in VALID_TRANSPORTS:
            raise McpFailure(
                "invalid_transport",
                f"Unsupported MCP transport: {self.transport!r}.",
                hint=f"Choose one of: {', '.join(sorted(VALID_TRANSPORTS))}.",
            )
        if not 1 <= self.port <= 65535:
            raise McpFailure(
                "invalid_port",
                f"Invalid MCP port: {self.port}.",
                hint="Provide a port between 1 and 65535.",
            )


def clamp_int(value: int, *, minimum: int, maximum: int, field_name: str) -> tuple[int, bool]:
    """Validate and clamp an integer budget parameter; returns ``(clamped, was_clamped)``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise McpFailure(
            "invalid_argument",
            f"Parameter `{field_name}` must be an integer.",
            hint=f"Pass an integer between {minimum} and {maximum}.",
        )
    if value < minimum:
        raise McpFailure(
            "invalid_argument",
            f"Parameter `{field_name}` must be >= {minimum} (got {value}).",
            hint=f"Pass an integer between {minimum} and {maximum}.",
        )
    if value > maximum:
        return maximum, True
    return value, False


def format_mcp_error(exc: Exception) -> dict[str, Any]:
    """Convert any exception into a structured, traceback-free MCP error payload."""
    if isinstance(exc, McpFailure):
        payload: dict[str, Any] = {
            "status": "error",
            "code": exc.code,
            "message": str(exc),
            "hint": exc.hint,
            "retryable": exc.retryable,
        }
        if exc.details:
            payload["details"] = exc.details
        return payload
    if isinstance(exc, TarelError):
        return {
            "status": "error",
            "code": exc.code,
            "message": str(exc),
            "hint": exc.hint or _default_hint_for_code(exc.code),
            "retryable": exc.retryable or exc.code in _RETRYABLE_CODES,
            **({"details": exc.details} if exc.details else {}),
        }
    return {
        "status": "error",
        "code": "internal_error",
        "message": f"Unexpected TAREL MCP error ({type(exc).__name__}): {exc}",
        "hint": "Check arguments and state root integrity; inspect server logs if this persists.",
        "retryable": False,
    }


def _default_hint_for_code(code: str) -> str | None:
    hints = {
        "graph_not_found": "Call `tarel_catalog_overview` to list available graph names.",
        "workspace_not_found": "Call `tarel_catalog_overview` to list available workspace names.",
        "lineage_not_found": "Call `tarel_catalog_overview` to list available lineage documents.",
        "focus_not_found": "Call `tarel_focus(action='list')` to list available focuses.",
        "reviewed_annotation": (
            "Human-reviewed or validated annotations are protected and cannot be overwritten "
            "by draft proposals."
        ),
    }
    return hints.get(code)
