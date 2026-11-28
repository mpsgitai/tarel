"""Policy seam for TAREL MCP tool calls (Tarel Wall integration boundary).

By default :class:`NoOpPolicyHook` allows every call permitted by the server profile and
returns results unchanged. Future policy engines (such as Tarel Wall) can plug in
allowlists, audit logging, argument inspection, or response redaction without changing
tool handlers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Immutable metadata describing one MCP tool invocation."""

    tool_name: str
    profile: str
    workspace: str | None
    state_root: Path
    args: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Outcome returned by a :class:`PolicyHook` before tool execution."""

    allowed: bool = True
    reason: str | None = None
    code: str = "policy_denied"
    hint: str | None = None
    override_args: Mapping[str, Any] | None = None


class PolicyHook(Protocol):
    """Pre- and post-execution hook evaluated around every TAREL MCP tool call."""

    def before_tool_call(self, context: ToolCallContext) -> PolicyDecision | None:
        """Return a :class:`PolicyDecision` or ``None`` to allow unchanged execution."""
        ...

    def after_tool_call(
        self,
        context: ToolCallContext,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Inspect, audit, or redact a tool result before serialization."""
        ...


class NoOpPolicyHook:
    """Default no-op policy hook used when no external policy engine is attached."""

    def before_tool_call(self, context: ToolCallContext) -> PolicyDecision | None:
        del context
        return None

    def after_tool_call(
        self,
        context: ToolCallContext,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        del context
        return result
