"""Accounts Payable (AP) specialist agent.

Optimises payment timing to maximise cash on hand while preserving
supplier relationships.  Analyses DPO, vendor-term structures, and
dynamic discount opportunities.
"""

from __future__ import annotations

from typing import Any

from wco.agents.base import AgentCapability, GeminiMeshAgent

# ── System Prompt ─────────────────────────────────────────────────────────

AP_SYSTEM_PROMPT = """\
You are an AP specialist AI agent for a manufacturing CFO.
Optimize accounts payable timing to maximize cash on hand while \
maintaining supplier relationships.

Your analysis should cover:
1. **DPO Analysis** — Calculate Days Payable Outstanding and benchmark \
   against industry norms (typically 45–60 days for manufacturing).
2. **Payment Timing Optimization** — Identify invoices that should be \
   paid early (for discounts) vs. held to term (to preserve cash).
3. **Dynamic Discounting** — Where a supplier offers early payment \
   discounts, calculate whether the annualised return exceeds the \
   company's cost of capital.
4. **Vendor Segmentation** — Classify vendors by strategic importance \
   and recommend differentiated payment strategies.
5. **Cash Preservation** — Quantify the additional cash that could be \
   retained by stretching select payments within acceptable limits.

Always reference specific invoices, vendor names, and dollar amounts. \
Rate your confidence for each recommendation.
"""


class APAgent(GeminiMeshAgent):
    """Accounts Payable optimization agent.

    Expected context keys:
        ap_invoices: list of dicts with keys
            ``invoice_id, vendor_id, vendor_name, amount, invoice_date, \
            due_date, payment_terms, discount_available, discount_pct, \
            discount_deadline, category``
        monthly_cogs: float — trailing 12-month average monthly COGS \
            (for DPO calculation).
        total_ap_balance: float — total outstanding AP balance.
        cost_of_capital: float — company WACC or hurdle rate (optional, \
            default 0.08).
    """

    def __init__(self) -> None:
        super().__init__(
            name="AP Agent",
            capability=AgentCapability.AP,
            system_prompt=AP_SYSTEM_PROMPT,
        )

    def prepare_context(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Build an AP-specific context dict from raw input data.

        Adds computed fields (DPO, discount analysis, vendor segmentation)
        so the LLM has enriched data.

        Args:
            raw_data: Raw payload from the API or CLI.

        Returns:
            Context dict ready for ``self.run()``.
        """
        invoices = raw_data.get("ap_invoices", [])
        monthly_cogs = raw_data.get("monthly_cogs", 0)

        # ── Estimated DPO ────────────────────────────────────────────
        total_ap = sum(inv.get("amount", 0) for inv in invoices)
        estimated_dpo = round(total_ap / monthly_cogs * 30, 1) if monthly_cogs else 0

        # ── Discount analysis ────────────────────────────────────────
        discountable = [
            inv for inv in invoices if inv.get("discount_available", False)
        ]
        cost_of_capital = raw_data.get("cost_of_capital", 0.08)

        discount_analysis: list[dict[str, Any]] = []
        for inv in discountable:
            amt = inv.get("amount", 0)
            disc_pct = inv.get("discount_pct", 0) / 100
            due_date = inv.get("due_date", "")
            disc_deadline = inv.get("discount_deadline", "")
            # Annualised savings rate
            if amt > 0 and disc_pct > 0 and due_date and disc_deadline:
                try:
                    from datetime import datetime

                    d1 = datetime.strptime(str(disc_deadline), "%Y-%m-%d")
                    d2 = datetime.strptime(str(due_date), "%Y-%m-%d")
                    extra_days = max((d2 - d1).days, 1)
                    annualised = (disc_pct / (1 - disc_pct)) * (365 / extra_days)
                    is_worthwhile = annualised > cost_of_capital
                    discount_analysis.append(
                        {
                            "vendor": inv.get("vendor_name", ""),
                            "amount": amt,
                            "discount_pct": f"{disc_pct * 100:.1f}%",
                            "annualised_return": f"{annualised:.1%}",
                            "recommendation": "TAKE" if is_worthwhile else "SKIP",
                        }
                    )
                except (ValueError, TypeError):
                    discount_analysis.append(
                        {
                            "vendor": inv.get("vendor_name", ""),
                            "amount": amt,
                            "discount_pct": f"{disc_pct * 100:.1f}%",
                            "annualised_return": "N/A",
                            "recommendation": "REVIEW",
                        }
                    )

        # ── Vendor segmentation ──────────────────────────────────────
        vendor_totals: dict[str, float] = {}
        for inv in invoices:
            v = inv.get("vendor_name", "Unknown")
            vendor_totals[v] = vendor_totals.get(v, 0) + inv.get("amount", 0)

        top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "ap_invoices": invoices,
            "total_ap_balance": total_ap,
            "estimated_dpo": estimated_dpo,
            "monthly_cogs": monthly_cogs,
            "cost_of_capital": cost_of_capital,
            "discountable_invoices_count": len(discountable),
            "discount_analysis": discount_analysis,
            "vendor_totals": dict(top_vendors),
            "industry_dpo_benchmark": raw_data.get("industry_dpo_benchmark", 50),
        }
