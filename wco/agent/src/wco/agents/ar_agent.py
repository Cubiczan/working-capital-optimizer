"""Accounts Receivable (AR) specialist agent.

Analyzes AR aging buckets, DSO trends, and collection patterns to recommend
actions that accelerate cash inflows — including early-payment discount
structuring, targeted collection pushes, and credit-term adjustments.
"""

from __future__ import annotations

from typing import Any

from wco.agents.base import AgentCapability, GeminiMeshAgent

# ── System Prompt ─────────────────────────────────────────────────────────

AR_SYSTEM_PROMPT = """\
You are an AR specialist AI agent for a manufacturing CFO.
Analyze accounts receivable data and provide actionable recommendations \
to optimize DSO and accelerate collections.

Your analysis should cover:
1. **Aging Analysis** — Break down receivables by aging bucket \
   (Current, 1-30, 31-60, 61-90, 90+ days). Flag concentrations in \
   overdue buckets.
2. **DSO Calculation** — Compute Days Sales Outstanding from the \
   receivables and revenue data provided.
3. **Collection Pattern** — Identify customers with chronic late \
   payments and quantify the cash impact.
4. **Discount Analysis** — Evaluate whether early-payment discounts \
   (e.g. 2/10 Net 30) would be cost-effective.
5. **Credit Policy** — Recommend credit-term tightening or loosening \
   based on risk profiles.

Always ground recommendations in specific invoice-level data.  Include \
dollar amounts wherever possible.  Rate your confidence for each insight.
"""


class ARAgent(GeminiMeshAgent):
    """Accounts Receivable analysis agent.

    Expected context keys:
        ar_invoices: list of dicts with keys
            ``invoice_id, customer_id, customer_name, amount, issue_date, \
            due_date, days_outstanding, aging_bucket, payment_status``
        monthly_revenue: float — trailing 12-month average monthly revenue \
            (for DSO calculation).
        total_ar_balance: float — total outstanding AR balance.
        industry_dso_benchmark: float — median DSO for the manufacturing \
            sector (optional).
    """

    def __init__(self) -> None:
        super().__init__(
            name="AR Agent",
            capability=AgentCapability.AR,
            system_prompt=AR_SYSTEM_PROMPT,
        )

    def prepare_context(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Build an AR-specific context dict from raw input data.

        Adds computed fields (aging summaries, DSO estimates) so the LLM
        has enriched data to reason over.

        Args:
            raw_data: Raw payload from the API or CLI.

        Returns:
            Context dict ready for ``self.run()``.
        """
        invoices = raw_data.get("ar_invoices", [])
        monthly_revenue = raw_data.get("monthly_revenue", 0)

        # ── Aging summary ────────────────────────────────────────────
        aging_summary: dict[str, int] = {
            "current": 0,
            "1_30": 0,
            "31_60": 0,
            "61_90": 0,
            "90_plus": 0,
        }
        for inv in invoices:
            bucket = str(inv.get("aging_bucket", "")).lower().replace(" ", "_")
            if "current" in bucket:
                aging_summary["current"] += 1
            elif bucket.startswith("1") or bucket.startswith("0"):
                aging_summary["1_30"] += 1
            elif bucket.startswith("3"):
                aging_summary["31_60"] += 1
            elif bucket.startswith("6"):
                aging_summary["61_90"] += 1
            elif bucket.startswith("9") or "90" in bucket:
                aging_summary["90_plus"] += 1

        # ── Estimated DSO ────────────────────────────────────────────
        total_ar = sum(inv.get("amount", 0) for inv in invoices)
        estimated_dso = round(total_ar / monthly_revenue * 30, 1) if monthly_revenue else 0

        # ── Overdue analysis ─────────────────────────────────────────
        overdue_invoices = [
            inv
            for inv in invoices
            if inv.get("days_outstanding", 0) > (inv.get("payment_terms_days", 30) or 30)
        ]
        overdue_amount = sum(inv.get("amount", 0) for inv in overdue_invoices)

        return {
            "ar_invoices": invoices,
            "aging_summary": aging_summary,
            "total_ar_balance": total_ar,
            "estimated_dso": estimated_dso,
            "monthly_revenue": monthly_revenue,
            "overdue_count": len(overdue_invoices),
            "overdue_amount": overdue_amount,
            "industry_dso_benchmark": raw_data.get("industry_dso_benchmark", 45),
        }
