"""Actions MCP tests — tools/list plus AR / cash recommendations on fixtures.

Runs fully offline (no Gemini key). Phoenix MCP is out of scope.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ["WCO_OFFLINE"] = "1"
os.environ.pop("GEMINI_API_KEY", None)

from wco.config import reset_settings  # noqa: E402

reset_settings()

from wco.mcp.actions import dispatch_tool  # noqa: E402
from wco.mcp.tools import TOOL_NAMES, tool_definitions  # noqa: E402

AGENT_SRC = Path(__file__).resolve().parents[1] / "src"


def test_tools_list_catalog() -> None:
    names = {tool["name"] for tool in tool_definitions()}
    assert names == {
        "recommend_ar_actions",
        "recommend_ap_actions",
        "recommend_inventory_actions",
        "recommend_cash_conversion_actions",
        "wco_version",
    }
    assert names == TOOL_NAMES
    for tool in tool_definitions():
        assert "Phoenix" not in tool["description"] or "Not Phoenix" in tool["description"] or "traces" in tool["description"]


def test_stdio_tools_list() -> None:
    """Drive the real stdio server with initialize + tools/list."""
    payload = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "wco-test", "version": "0"},
                },
            }
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
    )
    env = os.environ.copy()
    env["WCO_OFFLINE"] = "1"
    env["PYTHONPATH"] = str(AGENT_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "wco.mcp.actions_server"],
        input=payload,
        text=True,
        capture_output=True,
        cwd=str(AGENT_SRC.parent),
        env=env,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    messages = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert len(messages) >= 2
    listed = next(m for m in messages if m.get("id") == 2)
    names = {t["name"] for t in listed["result"]["tools"]}
    assert "recommend_ar_actions" in names
    assert "recommend_cash_conversion_actions" in names
    assert "recommend_ap_actions" in names
    assert "recommend_inventory_actions" in names


@pytest.mark.asyncio
async def test_recommend_ar_actions_sample_data() -> None:
    result = await dispatch_tool("recommend_ar_actions", {"use_sample_data": True})
    assert result["brand"] == "Cubiczan"
    assert result["agent"] == "AR Agent"
    assert result["capability"] == "accounts_receivable"
    assert result["mode"] == "offline"
    assert result["trace_id"]
    assert result["recommendations"], "AR agent must return at least one action"
    rec = result["recommendations"][0]
    assert rec["recommendation"]
    assert rec["insight"]
    assert rec["expected_impact"]
    assert result["metrics"]["overdue_amount"] > 0
    assert result["metrics"]["estimated_dso"] > 0
    assert result["grounding_check"]["is_grounded"] is True
    assert "traces-only" in result["phoenix_note"]


@pytest.mark.asyncio
async def test_recommend_cash_conversion_sample_data() -> None:
    result = await dispatch_tool(
        "recommend_cash_conversion_actions", {"use_sample_data": True}
    )
    assert result["brand"] == "Cubiczan"
    assert result["capability"] == "cashflow"
    assert result["mode"] == "offline"
    assert result["recommendations"]
    assert "AR Agent" in result["mesh_agents"]
    assert "CashFlow Agent" in result["mesh_agents"]
    ccc = result["cash_conversion_cycle"]
    assert "dso" in ccc or result["metrics"].get("dso")
    assert result["metrics"]["dso"] > 0
    assert result["metrics"]["dio"] > 0


@pytest.mark.asyncio
async def test_wco_version_mentions_phoenix_split() -> None:
    result = await dispatch_tool("wco_version", {})
    assert result["brand"] == "Cubiczan"
    assert "traces only" in result["phoenix"]
