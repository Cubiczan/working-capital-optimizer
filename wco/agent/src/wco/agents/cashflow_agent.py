"""Cash Flow consolidation & forecasting agent.

Synthesises outputs from AR, AP, and Inventory agents into a unified
cash position view.  Calculates the Cash Conversion Cycle and produces
a 13-week rolling cash forecast.
"""

from __future__ import annotations

from typing import Any

from wco.agents.base import AgentCapability, GeminiMeshAgent

# ── System Prompt ─────────────────────────────────────────────────────────

CASHFLOW_SYSTEM_PROMPT = """\
You are a cash flow specialist AI agent for a manufacturing CFO.
Produce accurate cash flow forecasts and identify liquidity risks.

Your analysis should cover:
1. **Cash Conversion Cycle (CCC)** — Compute CCC = DSO + DIO − DPO. \
   Explain what each component means and how it impacts cash flow.
2. **Opening Cash Position** — Start from the reported opening balance \
   and walk through expected inflows and outflows.
3. **13-Week Rolling Forecast** — Build a week-by-week cash forecast \
   incorporating:
   - Expected AR collections (weighted by aging probability)
   - Scheduled AP payments
   - Inventory procurement outflows
4. **Liquidity Risk Assessment** — Identify weeks where cash may dip \
   below critical thresholds and flag contingency actions.
5. **CCC Improvement Roadmap** — Translate the AR, AP, and Inventory \
   recommendations into a consolidated timeline showing projected CCC \
   reduction week over week.
6. **Sensitivity Analysis** — Show how a 10 % change in collections, \
   payments, or demand would shift the forecast.

Reference specific dollar amounts, week numbers, and confidence levels. \
This is the final agent — your output is what the CFO will see.
"""


class CashFlowAgent(GeminiMeshAgent):
    """Cash Flow consolidation & forecasting agent.

    Expected context keys (populated by the orchestrator from earlier
    agent results):
        opening_cash_balance: float
        ar_invoices: list[dict]
        ap_invoices: list[dict]
        skus: list[dict]
        monthly_revenue: float
        monthly_cogs: float
        ar_result: TurnResult from the AR agent
        ap_result: TurnResult from the AP agent
        inventory_result: TurnResult from the Inventory agent
    """

    def __init__(self) -> None:
        super().__init__(
            name="CashFlow Agent",
            capability=AgentCapability.CASHFLOW,
            system_prompt=CASHFLOW_SYSTEM_PROMPT,
        )

    def prepare_context(
        self,
        raw_data: dict[str, Any],
        ar_result: dict[str, Any] | None = None,
        ap_result: dict[str, Any] | None = None,
        inventory_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a cash-flow-specific context from raw data + prior agent results.

        Calculates the CCC and a basic 13-week projection skeleton that
        the LLM can refine.

        Args:
            raw_data: Original input payload.
            ar_result: Serialized TurnResult from AR agent.
            ap_result: Serialized TurnResult from AP agent.
            inventory_result: Serialized TurnResult from Inventory agent.

        Returns:
            Enriched context dict for ``self.run()``.
        """
        # ── Basic CCC calculation ────────────────────────────────────
        monthly_revenue = raw_data.get("monthly_revenue", 0)
        monthly_cogs = raw_data.get("monthly_cogs", 0)

        # DSO estimate
        ar_invoices = raw_data.get("ar_invoices", [])
        total_ar = sum(inv.get("amount", 0) for inv in ar_invoices)
        dso = round(total_ar / monthly_revenue * 30, 1) if monthly_revenue else 0

        # DPO estimate
        ap_invoices = raw_data.get("ap_invoices", [])
        total_ap = sum(inv.get("amount", 0) for inv in ap_invoices)
        dpo = round(total_ap / monthly_cogs * 30, 1) if monthly_cogs else 0

        # DIO estimate
        skus = raw_data.get("skus", [])
        total_inv_value = sum(
            s.get("quantity_on_hand", 0) * s.get("unit_cost", 0) for s in skus
        )
        dio = round(total_inv_value / monthly_cogs * 30, 1) if monthly_cogs else 0

        ccc = round(dso + dio - dpo, 1)

        # ── 13-week projection skeleton ──────────────────────────────
        weekly_collections = monthly_revenue / 4.33
        weekly_payments = monthly_cogs / 4.33
        opening_balance = raw_data.get("opening_cash_balance", 0)

        weekly_forecast: list[dict[str, float]] = []
        balance = opening_balance
        for week in range(1, 14):
            # Apply aging-weighted collection probability
            collection_factor = 0.92 if week <= 4 else (0.97 if week <= 8 else 1.0)
            expected_inflows = round(weekly_collections * collection_factor, 2)
            expected_outflows = round(weekly_payments * 1.02, 2)  # slight buffer
            net_change = round(expected_inflows - expected_outflows, 2)
            balance = round(balance + net_change, 2)
            weekly_forecast.append(
                {
                    "week": week,
                    "opening_balance": round(balance - net_change, 2),
                    "inflows": expected_inflows,
                    "outflows": expected_outflows,
                    "net_change": net_change,
                    "closing_balance": balance,
                }
            )

        # ── Liquidity risk flags ─────────────────────────────────────
        min_balance_threshold = raw_data.get("min_cash_threshold", 500_000)
        risk_weeks = [
            w for w in weekly_forecast if w["closing_balance"] < min_balance_threshold
        ]

        return {
            "opening_cash_balance": opening_balance,
            "monthly_revenue": monthly_revenue,
            "monthly_cogs": monthly_cogs,
            "dso": dso,
            "dpo": dpo,
            "dio": dio,
            "cash_conversion_cycle": ccc,
            "weekly_forecast": weekly_forecast,
            "min_cash_threshold": min_balance_threshold,
            "risk_weeks": risk_weeks,
            "ar_analysis_summary": self._summarise_agent_result(ar_result),
            "ap_analysis_summary": self._summarise_agent_result(ap_result),
            "inventory_analysis_summary": self._summarise_agent_result(inventory_result),
            "ar_invoices": ar_invoices,
            "ap_invoices": ap_invoices,
            "skus": skus,
        }

    @staticmethod
    def _summarise_agent_result(result: dict[str, Any] | None) -> dict[str, Any]:
        """Extract a lightweight summary from a serialised TurnResult."""
        if not result:
            return {"status": "not_available"}
        compressions = result.get("compression_steps", [])
        return {
            "agent_name": result.get("agent_name", "unknown"),
            "duration_ms": result.get("duration_ms", 0),
            "num_recommendations": len(compressions),
            "recommendations": [
                {
                    "insight": c.get("insight", ""),
                    "recommendation": c.get("recommendation", ""),
                    "expected_impact": c.get("expected_impact", ""),
                }
                for c in compressions
            ],
            "grounded": result.get("grounding_check", {}).get("is_grounded", False),
        }
