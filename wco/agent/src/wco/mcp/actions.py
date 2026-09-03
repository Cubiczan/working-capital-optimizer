"""Run existing WCO specialists and shape their output for MCP tools."""

from __future__ import annotations

from typing import Any

from wco import __version__
from wco.agents import APAgent, ARAgent, CashFlowAgent, InventoryAgent
from wco.agents.base import AgentCapability, GeminiMeshAgent, TurnResult
from wco.config import get_settings
from wco.data.sample_data import get_sample_data
from wco.mcp.tools import BRAND, PRODUCT
from wco.orchestration import WorkingCapitalOrchestrator
from wco.orchestration.orchestrator import OrchestrationReport

_SINGLE_AGENTS: dict[str, type[GeminiMeshAgent]] = {
    "recommend_ar_actions": ARAgent,
    "recommend_ap_actions": APAgent,
    "recommend_inventory_actions": InventoryAgent,
}


def merge_payload(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Build the mesh payload from tool arguments + demo fixtures."""
    args = dict(arguments or {})
    use_sample = args.get("use_sample_data", True)
    data = dict(args.get("data") or {})
    problem = args.get("problem_description")
    if problem:
        data["problem_description"] = problem

    if use_sample:
        sample = get_sample_data()
        for key, value in sample.items():
            if key not in data:
                data[key] = value
    elif not data:
        data = get_sample_data()
    return data


def _metrics_for(capability: AgentCapability, context: dict[str, Any]) -> dict[str, Any]:
    """Keep a compact, CFO-useful slice of prepare_context (not the full book)."""
    skip = {
        "ar_invoices",
        "ap_invoices",
        "skus",
        "weekly_forecast",
        "ar_analysis_summary",
        "ap_analysis_summary",
        "inventory_analysis_summary",
        "sku_recommendations",
        "abc_classification",
        "discount_analysis",
        "vendor_totals",
    }
    metrics = {k: v for k, v in context.items() if k not in skip}
    if capability == AgentCapability.AR:
        metrics["invoice_count"] = len(context.get("ar_invoices") or [])
    elif capability == AgentCapability.AP:
        metrics["invoice_count"] = len(context.get("ap_invoices") or [])
        metrics["discountable_take"] = [
            row
            for row in (context.get("discount_analysis") or [])
            if row.get("recommendation") == "TAKE"
        ]
    elif capability == AgentCapability.INVENTORY:
        metrics["sku_count"] = len(context.get("skus") or [])
        recs = context.get("sku_recommendations") or []
        metrics["critical_skus"] = [s for s in recs if "CRITICAL" in str(s.get("status", ""))]
    elif capability == AgentCapability.CASHFLOW:
        metrics["risk_week_count"] = len(context.get("risk_weeks") or [])
        forecast = context.get("weekly_forecast") or []
        if forecast:
            metrics["week_13_closing_balance"] = forecast[-1].get("closing_balance")
    return metrics


def _serialise_turn(turn: TurnResult, context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    recs = [
        {
            "insight": step.insight,
            "recommendation": step.recommendation,
            "expected_impact": step.expected_impact,
            "confidence": step.confidence.value,
        }
        for step in turn.compression_steps
    ]
    payload: dict[str, Any] = {
        "brand": BRAND,
        "product": PRODUCT,
        "mode": "offline" if settings.offline_mode else "gemini",
        "agent": turn.agent_name,
        "capability": turn.capability.value,
        "trace_id": turn.trace_id,
        "duration_ms": turn.duration_ms,
        "metrics": _metrics_for(turn.capability, context),
        "recommendations": recs,
        "grounding_check": (
            {
                "data_points_referenced": turn.grounding_check.data_points_referenced,
                "calculation_trace": turn.grounding_check.calculation_trace,
                "is_grounded": turn.grounding_check.is_grounded,
            }
            if turn.grounding_check
            else None
        ),
        "reasoning_trace": (
            {
                "steps": turn.reasoning_trace.steps,
                "assumptions": turn.reasoning_trace.assumptions,
                "data_gaps": turn.reasoning_trace.data_gaps,
            }
            if turn.reasoning_trace
            else None
        ),
        "source": f"wco.agents.{turn.agent_name.replace(' ', '')}",
        "phoenix_note": (
            "This payload is a working-capital action from the WCO mesh. "
            "Phoenix MCP (`wco mcp` / @arizeai/phoenix-mcp) is traces-only."
        ),
    }
    return payload


def _serialise_report(report: OrchestrationReport, context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    cash_turn = next(
        (t for t in report.turns if t.capability == AgentCapability.CASHFLOW),
        report.turns[-1] if report.turns else None,
    )
    body = (
        _serialise_turn(cash_turn, context)
        if cash_turn
        else {
            "brand": BRAND,
            "product": PRODUCT,
            "recommendations": report.recommendations,
        }
    )
    metrics = dict(body.get("metrics") or {})
    extracted = report.cash_conversion_cycle or {}
    ccc = {
        "dso": metrics.get("dso") or extracted.get("dso") or 0,
        "dio": metrics.get("dio") or extracted.get("dio") or 0,
        "dpo": metrics.get("dpo") or extracted.get("dpo") or 0,
        "ccc": (
            metrics.get("cash_conversion_cycle")
            or metrics.get("ccc")
            or extracted.get("ccc")
            or 0
        ),
    }
    body["cash_conversion_cycle"] = ccc
    body["metrics"] = {**metrics, **ccc}
    body["mesh_agents"] = [t.agent_name for t in report.turns]
    body["mesh_recommendations"] = report.recommendations
    body["problem"] = report.problem
    body["mode"] = "offline" if settings.offline_mode else "gemini"
    return body


async def run_single_agent(tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Run one specialist (AR / AP / inventory) against the merged payload."""
    agent_cls = _SINGLE_AGENTS[tool_name]
    data = merge_payload(arguments)
    agent = agent_cls()
    context = agent.prepare_context(data) if hasattr(agent, "prepare_context") else data
    turn = await agent.run(context)
    return _serialise_turn(turn, context)


async def run_cash_conversion(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Run the full mesh so cash-conversion sees AR / AP / inventory first."""
    data = merge_payload(arguments)
    agents = [ARAgent(), APAgent(), InventoryAgent(), CashFlowAgent()]
    orchestrator = WorkingCapitalOrchestrator(agents, auto_improve=False)
    report = await orchestrator.run(data)
    cash_context: dict[str, Any] = {}
    cash_agent = next(a for a in agents if a.capability == AgentCapability.CASHFLOW)
    prior = {
        t.capability.value: WorkingCapitalOrchestrator._serialise_turn(t) for t in report.turns
    }
    cash_context = cash_agent.prepare_context(
        data,
        ar_result=prior.get("accounts_receivable"),
        ap_result=prior.get("accounts_payable"),
        inventory_result=prior.get("inventory"),
    )
    return _serialise_report(report, cash_context)


def version_payload() -> dict[str, Any]:
    settings = get_settings()
    return {
        "brand": BRAND,
        "product": PRODUCT,
        "mcp": f"@cubiczan/wco-mcp (wco-agent {__version__})",
        "wco_agent": __version__,
        "mode": "offline" if settings.offline_mode else "gemini",
        "phoenix": (
            "Separate server: `wco mcp` or `npx -y @arizeai/phoenix-mcp` — traces only, "
            "not working-capital actions."
        ),
        "engine": "wco.agents (ARAgent, APAgent, InventoryAgent, CashFlowAgent)",
    }


async def dispatch_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Execute a named actions-MCP tool."""
    if name == "wco_version":
        return version_payload()
    if name in _SINGLE_AGENTS:
        return await run_single_agent(name, arguments)
    if name == "recommend_cash_conversion_actions":
        return await run_cash_conversion(arguments)
    raise ValueError(f"Unknown WCO actions tool: {name}")
