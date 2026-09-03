"""Stdio entry point for the Cubiczan WCO *actions* MCP server.

This is not Phoenix. Start with::

    wco mcp-actions
    python -m wco.mcp.actions_server
    wco-mcp
"""

from __future__ import annotations

import asyncio

from wco.mcp.stdio import serve_stdio


def main() -> None:
    """Run the actions MCP server on stdin/stdout."""
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
