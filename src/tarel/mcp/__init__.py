"""Standardized MCP server adapter over the TAREL SDK (``tarel mcp serve``)."""

from tarel.mcp.contracts import MCP_SERVER_INSTRUCTIONS, McpFailure, McpServerConfig
from tarel.mcp.policy import NoOpPolicyHook, PolicyDecision, PolicyHook, ToolCallContext
from tarel.mcp.server import create_mcp_server, serve_mcp
from tarel.mcp.tools import READ_ONLY_TOOL_NAMES, WRITE_TOOL_NAMES, TarelMcpDispatcher

__all__ = [
    "MCP_SERVER_INSTRUCTIONS",
    "READ_ONLY_TOOL_NAMES",
    "WRITE_TOOL_NAMES",
    "McpFailure",
    "McpServerConfig",
    "NoOpPolicyHook",
    "PolicyDecision",
    "PolicyHook",
    "TarelMcpDispatcher",
    "ToolCallContext",
    "create_mcp_server",
    "serve_mcp",
]
