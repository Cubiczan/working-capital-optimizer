"""WCO MCP surfaces.

Two different MCP servers live around this product. Do not conflate them.

1. **Phoenix MCP (traces only)** — ``wco mcp`` launches
   ``npx -y @arizeai/phoenix-mcp``. It introspects OpenInference spans,
   evaluations, and prompts. It does **not** recommend working-capital actions.
   Config: ``wco/mcp/mcp_config.json``.

2. **WCO actions MCP** — ``wco mcp-actions`` / ``wco-mcp`` /
   ``@cubiczan/wco-mcp``. Stdio tools wrap the existing Python mesh
   (``ARAgent``, ``APAgent``, ``InventoryAgent``, ``CashFlowAgent``) and
   return product-native recommendations. CHP is the lock; MCP is the pipe.

``PhoenixMCPClient`` below is a thin helper for the traces server. Action
clients should import :mod:`wco.mcp.actions` instead.
"""

from __future__ import annotations

from typing import Any

from wco.mcp.tools import tool_definitions

__all__ = ["PhoenixMCPClient", "tool_definitions"]


class PhoenixMCPClient:
    """Client notes for the Arize Phoenix MCP (trace introspection only).

    This is intentionally not an actions wrapper. Working-capital
    recommendations go through ``wco.mcp.actions.dispatch_tool``.
    """

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url or "https://app.phoenix.arize.com"

    def describe(self) -> dict[str, Any]:
        """Return a static description of the traces-only Phoenix MCP."""
        return {
            "server": "phoenix",
            "package": "@arizeai/phoenix-mcp",
            "purpose": "trace introspection only",
            "not": "working-capital AR/AP/inventory/cash recommendations",
            "actions_mcp": "@cubiczan/wco-mcp",
            "base_url": self.base_url,
        }
