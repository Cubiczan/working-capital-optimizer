"""Minimal stdio MCP server for WCO."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from wco.data.sample_data import get_sample_data


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
ToolHandler = Callable[[dict[str, Any]], JsonValue]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class StdioServer:
    def __init__(self, name: str, version: str, tools: list[ToolSpec]) -> None:
        self.name = name
        self.version = version
        self.tools = {tool.name: tool for tool in tools}

    def serve(self) -> None:
        while True:
            message = _read_message()
            if message is None:
                return
            method = message.get("method")
            if method == "initialize":
                _respond(message, {
                    "protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "serverInfo": {"name": self.name, "version": self.version},
                    "capabilities": {"tools": {"listChanged": False}},
                })
                continue
            if method == "tools/list":
                _respond(message, {"tools": [self._tool_entry(tool) for tool in self.tools.values()]})
                continue
            if method == "tools/call":
                self._call_tool(message)
                continue
            if method in {"shutdown", "exit"}:
                if message.get("id") is not None:
                    _respond(message, {})
                return

    def _tool_entry(self, tool: ToolSpec) -> dict[str, Any]:
        return {"name": tool.name, "description": tool.description, "inputSchema": tool.input_schema}

    def _call_tool(self, message: dict[str, Any]) -> None:
        params = message.get("params", {})
        tool = self.tools.get(params.get("name"))
        if tool is None:
            _error(message, -32602, f"unknown tool: {params.get('name')}")
            return
        try:
            result = tool.handler(params.get("arguments") or {})
        except Exception as exc:  # pragma: no cover - surfaced to caller
            _error(message, -32000, str(exc))
            return
        _respond(message, {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]})


def serve() -> None:
    server = StdioServer(
        name="working-capital-optimizer",
        version="0.1.0",
        tools=[
            ToolSpec(
                name="analyze",
                description="Run the full working-capital analysis pipeline.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "data": {"type": "object"},
                        "data_file": {"type": "string"},
                    },
                },
                handler=_analyze_tool,
            ),
            ToolSpec(
                name="evaluate",
                description="Evaluate a recommendation with the WCO judge.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "recommendation_text": {"type": "string"},
                        "recommendation_id": {"type": "string"},
                        "context": {"type": "string"},
                        "agent_name": {"type": "string"},
                    },
                },
                handler=_evaluate_tool,
            ),
            ToolSpec(
                name="recommendations",
                description="List stored recommendations.",
                input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                handler=_recommendations_tool,
            ),
            ToolSpec(
                name="evaluations",
                description="List stored evaluations.",
                input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                handler=_evaluations_tool,
            ),
            ToolSpec(
                name="health",
                description="Check whether the DB can be initialized.",
                input_schema={"type": "object", "properties": {}},
                handler=lambda _args: asyncio.run(_health_tool()),
            ),
        ],
    )
    server.serve()


def _analyze_tool(args: dict[str, Any]) -> dict[str, Any]:
    data = _load_data(args)
    result = asyncio.run(_run_analysis(data))
    return result


async def _run_analysis(data: dict[str, Any]) -> dict[str, Any]:
    from wco.agents import ARAgent, APAgent, CashFlowAgent, InventoryAgent
    from wco.orchestration import WorkingCapitalOrchestrator

    orchestrator = WorkingCapitalOrchestrator([ARAgent(), APAgent(), InventoryAgent(), CashFlowAgent()])
    report = await orchestrator.run(data)
    return report.to_dict()


def _evaluate_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = asyncio.run(_run_evaluation(args))
    return result


async def _run_evaluation(args: dict[str, Any]) -> dict[str, Any]:
    from wco.eval.evaluator import RecommendationEvaluator
    from wco.db.connection import list_recommendations

    evaluator = RecommendationEvaluator()
    if args.get("recommendation_id"):
        recs = await list_recommendations(limit=50)
        recommendation = next((row for row in recs if row.get("id") == args["recommendation_id"]), None)
        if recommendation is None:
            raise ValueError(f"recommendation not found: {args['recommendation_id']}")
        recommendation_text = str(recommendation.get("recommendation_text", ""))
        context = str(args.get("context", recommendation.get("problem_description", "")))
        agent_name = str(args.get("agent_name", recommendation.get("agent_name", "unknown")))
        recommendation_id = args["recommendation_id"]
    else:
        recommendation_text = str(args.get("recommendation_text", ""))
        if not recommendation_text:
            raise ValueError("recommendation_text or recommendation_id is required")
        context = str(args.get("context", "Working capital optimization"))
        agent_name = str(args.get("agent_name", "unknown"))
        recommendation_id = None
    result = await evaluator.run_evaluation(
        recommendation=recommendation_text,
        context=context,
        agent_name=agent_name,
        recommendation_id=recommendation_id,
        store=True,
    )
    return result.to_dict()


def _recommendations_tool(args: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_list_recommendations(int(args.get("limit", 50))))


async def _list_recommendations(limit: int) -> dict[str, Any]:
    from wco.db.connection import list_recommendations

    rows = await list_recommendations(limit=limit)
    return {"count": len(rows), "recommendations": rows}


def _evaluations_tool(args: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_list_evaluations(int(args.get("limit", 50))))


async def _list_evaluations(limit: int) -> dict[str, Any]:
    from wco.db.connection import list_evaluations

    rows = await list_evaluations(limit=limit)
    return {"count": len(rows), "evaluations": rows}


async def _health_tool() -> dict[str, Any]:
    from wco.config import get_settings
    from wco.db.connection import init_db

    settings = get_settings()
    database_connected = await init_db()
    return {
        "status": "ok",
        "agents_ready": True,
        "database_connected": database_connected,
        "port": settings.port,
    }


def _load_data(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("data_file"):
        path = Path(str(args["data_file"]))
        if not path.exists():
            raise FileNotFoundError(f"data file not found: {path}")
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".csv":
            import csv

            rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
            payload: dict[str, Any] = {"problem_description": "Working capital optimization analysis"}
            name = path.stem.lower()
            if "ap" in name:
                payload["ap_invoices"] = rows
            elif "inv" in name or "sku" in name:
                payload["skus"] = rows
            else:
                payload["ar_invoices"] = rows
            return payload
        raise ValueError(f"unsupported file format: {path.suffix}")

    data = args.get("data")
    if isinstance(data, dict):
        return {**get_sample_data(), **data}
    return get_sample_data()


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.decode("utf-8", errors="replace").strip()
        if not stripped:
            break
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        headers[key.lower().strip()] = value.strip()
    length = int(headers.get("content-length", "0"))
    payload = sys.stdin.buffer.read(length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def _respond(message: dict[str, Any], result: dict[str, Any]) -> None:
    payload = json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": result}, default=str).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _error(message: dict[str, Any], code: int, detail: str) -> None:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": code, "message": detail}},
        default=str,
    ).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="wco mcp", description="Run the WCO MCP server.")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    serve()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
