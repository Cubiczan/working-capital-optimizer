"""Newline-delimited JSON-RPC stdio transport for the WCO actions MCP.

MCP clients (Cursor, Claude Code) speak JSON-RPC 2.0 over stdin/stdout.
All logging goes to stderr so it cannot corrupt the protocol stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, TextIO

from wco import __version__
from wco.mcp.actions import dispatch_tool
from wco.mcp.tools import TOOL_NAMES, tool_definitions

logger = logging.getLogger("wco.mcp")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "wco-mcp"


def _json_content(data: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2, default=str)}]}


class ActionsMCPServer:
    """Minimal MCP server: initialize, tools/list, tools/call."""

    def __init__(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout

    def _write(self, message: dict[str, Any]) -> None:
        self._stdout.write(json.dumps(message, default=str) + "\n")
        self._stdout.flush()

    def _reply(self, req_id: Any, result: Any) -> None:
        self._write({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _error(self, req_id: Any, code: int, message: str) -> None:
        self._write(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        )

    async def _handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        req_id = message.get("id")
        params = message.get("params") or {}

        if method is None:
            return

        # Notifications have no id
        if req_id is None:
            if method == "notifications/initialized":
                logger.info("MCP client initialized")
            return

        if method == "initialize":
            self._reply(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": __version__},
                    "instructions": (
                        "Cubiczan Working Capital Optimizer actions MCP. "
                        "Use recommend_* tools for AR / AP / inventory / cash-conversion "
                        "recommendations from the WCO agent mesh. "
                        "Phoenix MCP is a different server and is traces-only."
                    ),
                },
            )
            return

        if method == "ping":
            self._reply(req_id, {})
            return

        if method == "tools/list":
            self._reply(req_id, {"tools": tool_definitions()})
            return

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOL_NAMES:
                self._reply(
                    req_id,
                    {
                        **_json_content({"error": f"Unknown tool: {name}"}),
                        "isError": True,
                    },
                )
                return
            try:
                result = await dispatch_tool(name, arguments)
                self._reply(req_id, _json_content(result))
            except Exception as exc:  # noqa: BLE001 — surface tool failures to the client
                logger.exception("Tool %s failed", name)
                self._reply(
                    req_id,
                    {**_json_content({"error": str(exc)}), "isError": True},
                )
            return

        self._error(req_id, -32601, f"Method not found: {method}")

    async def serve(self) -> None:
        """Read NDJSON JSON-RPC from stdin until EOF."""
        logger.info(
            "Cubiczan WCO actions MCP listening on stdio (Phoenix MCP is traces-only)"
        )
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, self._stdin.readline)
            if line == "":
                break
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid JSON on stdin: %s", exc)
                continue
            if not isinstance(message, dict):
                continue
            await self._handle(message)


async def serve_stdio() -> None:
    """Entry used by ``wco mcp-actions`` / ``python -m wco.mcp.actions_server``."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    await ActionsMCPServer().serve()
