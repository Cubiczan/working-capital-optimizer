"""Offline / fixture recommendations for the WCO specialist agents.

Each function consumes the same ``prepare_context()`` dict the live Gemini
path sees and emits product-native ``ExpansionStep`` / ``CompressionStep``
objects. Used when ``WCO_OFFLINE=1`` or no Gemini key is configured.
"""

from __future__ import annotations

from typing import Any

from wco.agents.base import (
    AgentCapability,
    CompressionStep,
    ConfidenceLevel,
    ExpansionStep,
    GroundingCheck,
    ReasoningTrace,
)


def _money(value: float) -> str:
    return f"${value:,.0f}"


def recommend_from_context(
    capability: AgentCapability,
    context: dict[str, Any],
) -> tuple[list[ExpansionStep], list[CompressionStep], GroundingCheck, ReasoningTrace]:
    """Dispatch offline recommendations for one specialist capability."""
    if capability == AgentCapability.AR:
        return _ar(context)
    if capability == AgentCapability.AP:
        return _ap(context)
    if capability == AgentCapability.INVENTORY:
        return _inventory(context)
    if capability == AgentCapability.CASHFLOW:
        return _cash(context)
    raise ValueError(f"Unsupported capability for offline recommendations: {capability}")


def _ar(
    context: dict[str, Any],
) -> tuple[list[ExpansionStep], list[CompressionStep], GroundingCheck, ReasoningTrace]:
    invoices = context.get("ar_invoices") or []
    dso = float(context.get("estimated_dso") or 0)
    bench = float(context.get("industry_dso_benchmark") or 45)
    overdue_amount = float(context.get("overdue_amount") or 0)
    overdue_count = int(context.get("overdue_count") or 0)
    total_ar = float(context.get("total_ar_balance") or 0)
    aging = context.get("aging_summary") or {}

    overdue = [
        inv
        for inv in invoices
        if inv.get("days_outstanding", 0) > (inv.get("payment_terms_days", 30) or 30)
    ]
    overdue.sort(key=lambda inv: inv.get("amount", 0), reverse=True)
    top = overdue[:3]
    top_names = ", ".join(
        f"{inv.get('customer_name', 'customer')} ({_money(inv.get('amount', 0))}, "
        f"{inv.get('days_outstanding', 0)} dso)"
        for inv in top
    ) or "no named overdue accounts"

    expansions = [
        ExpansionStep(
            step_number=1,
            description="Age the AR book and isolate overdue buckets",
            domain="accounts_receivable",
            data_required=["ar_invoices", "aging_summary"],
            expected_output="Aging concentrations and overdue dollars",
        ),
        ExpansionStep(
            step_number=2,
            description="Compute DSO versus the manufacturing benchmark",
            domain="accounts_receivable",
            data_required=["total_ar_balance", "monthly_revenue", "industry_dso_benchmark"],
            expected_output="Estimated DSO gap",
        ),
        ExpansionStep(
            step_number=3,
            description="Rank chronic late payers for a collection push",
            domain="accounts_receivable",
            data_required=["ar_invoices"],
            expected_output="Named customers and cash at risk",
        ),
    ]

    gap = round(dso - bench, 1)
    compressions = [
        CompressionStep(
            insight=(
                f"Estimated DSO is {dso:.1f} days versus a {bench:.0f}-day manufacturing "
                f"benchmark ({'+' if gap > 0 else ''}{gap:.1f} days). "
                f"Book is {_money(total_ar)} across {len(invoices)} invoices; "
                f"{overdue_count} invoices / {_money(overdue_amount)} are past terms."
            ),
            recommendation=(
                "Stand up a daily collection huddle on 61+ day invoices and offer "
                "2/10 Net 30 only on current Tier-1 balances where the annualised "
                "discount beats cost of capital."
            ),
            expected_impact=(
                f"Clearing the {_money(overdue_amount)} overdue book trims DSO toward "
                f"{bench:.0f} days and pulls cash forward this quarter."
            ),
            confidence=ConfidenceLevel.HIGH if overdue_amount else ConfidenceLevel.MEDIUM,
        ),
        CompressionStep(
            insight=f"Highest-cash overdue names: {top_names}.",
            recommendation=(
                "Assign collector + sales-owner pairs to the top overdue accounts, "
                "escalate 90+ day balances to formal collections, and freeze new "
                "credit until a payment plan is signed."
            ),
            expected_impact=(
                f"Targeted recovery of the top overdue invoices "
                f"({_money(sum(inv.get('amount', 0) for inv in top))})."
            ),
            confidence=ConfidenceLevel.HIGH if top else ConfidenceLevel.LOW,
        ),
    ]

    data_points = len(invoices) + len(aging)
    grounding = GroundingCheck(
        data_points_referenced=data_points,
        calculation_trace=(
            f"DSO = total_ar / monthly_revenue * 30; overdue = days_outstanding > terms; "
            f"aging buckets={aging}"
        ),
        is_grounded=True,
    )
    reasoning = ReasoningTrace(
        steps=[
            "Used ARAgent.prepare_context aging, DSO, and overdue totals",
            "Ranked overdue invoices by amount for named collection actions",
        ],
        assumptions=["Payment-terms default to 30 days when missing"],
        data_gaps=["No historical on-time payment rate by customer"],
    )
    return expansions, compressions, grounding, reasoning


def _ap(
    context: dict[str, Any],
) -> tuple[list[ExpansionStep], list[CompressionStep], GroundingCheck, ReasoningTrace]:
    invoices = context.get("ap_invoices") or []
    dpo = float(context.get("estimated_dpo") or 0)
    bench = float(context.get("industry_dpo_benchmark") or 50)
    total_ap = float(context.get("total_ap_balance") or 0)
    cost_of_capital = float(context.get("cost_of_capital") or 0.08)
    discounts = context.get("discount_analysis") or []
    take = [d for d in discounts if d.get("recommendation") == "TAKE"]
    skip = [d for d in discounts if d.get("recommendation") == "SKIP"]
    take_dollars = sum(float(d.get("amount") or 0) for d in take)

    take_names = ", ".join(
        f"{d.get('vendor', 'vendor')} {d.get('discount_pct', '')} "
        f"(ann. {d.get('annualised_return', 'n/a')})"
        for d in take[:4]
    ) or "no discounts that beat WACC"

    expansions = [
        ExpansionStep(
            step_number=1,
            description="Compute DPO and compare to sector norms",
            domain="accounts_payable",
            data_required=["ap_invoices", "monthly_cogs"],
            expected_output="Estimated DPO vs benchmark",
        ),
        ExpansionStep(
            step_number=2,
            description="Score early-pay discounts against cost of capital",
            domain="accounts_payable",
            data_required=["discount_analysis", "cost_of_capital"],
            expected_output="TAKE vs SKIP decisions",
        ),
    ]

    stretch_gap = bench - dpo
    compressions = [
        CompressionStep(
            insight=(
                f"AP book is {_money(total_ap)}; estimated DPO is {dpo:.1f} days vs "
                f"{bench:.0f}-day benchmark. Cost of capital {cost_of_capital:.1%}."
            ),
            recommendation=(
                "Pay strategic raw-material vendors to terms. Stretch non-critical "
                f"categories toward {bench:.0f} days where contracts allow, without "
                "missing discount windows that beat WACC."
            ),
            expected_impact=(
                f"{'Extending DPO by ~' + str(round(stretch_gap, 1)) + ' days frees cash. ' if stretch_gap > 0 else ''}"
                f"Preserve supplier scorecards on top vendors."
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        CompressionStep(
            insight=f"Dynamic-discount TAKE list: {take_names}. SKIP count={len(skip)}.",
            recommendation=(
                "Fund TAKE discounts this week from surplus cash; skip discounts "
                "whose annualised return is below WACC and hold those invoices to due date."
            ),
            expected_impact=(
                f"Capture discounts on {_money(take_dollars)} of payables where the "
                "annualised return exceeds cost of capital."
            ),
            confidence=ConfidenceLevel.HIGH if take else ConfidenceLevel.MEDIUM,
        ),
    ]

    grounding = GroundingCheck(
        data_points_referenced=len(invoices) + len(discounts),
        calculation_trace=(
            "DPO = total_ap / monthly_cogs * 30; annualised discount = "
            "(d/(1-d))*(365/extra_days); TAKE if annualised > WACC"
        ),
        is_grounded=True,
    )
    reasoning = ReasoningTrace(
        steps=["Used APAgent.prepare_context DPO and discount_analysis"],
        assumptions=["Invoice dates parse as YYYY-MM-DD"],
        data_gaps=["No vendor score / strategic-importance flags in the payload"],
    )
    return expansions, compressions, grounding, reasoning


def _inventory(
    context: dict[str, Any],
) -> tuple[list[ExpansionStep], list[CompressionStep], GroundingCheck, ReasoningTrace]:
    skus = context.get("skus") or []
    dio = float(context.get("estimated_dio") or 0)
    bench = float(context.get("industry_dio_benchmark") or 75)
    carrying = float(context.get("annual_carrying_cost") or 0)
    total_value = float(context.get("total_inventory_value") or 0)
    sku_recs = context.get("sku_recommendations") or []
    abc = context.get("abc_classification") or {}
    critical = [s for s in sku_recs if "CRITICAL" in str(s.get("status", ""))]
    low = [s for s in sku_recs if str(s.get("status", "")).startswith("low")]
    class_a = abc.get("A") or []

    crit_names = ", ".join(
        f"{s.get('name') or s.get('sku_id')} (on-hand {s.get('on_hand')}, "
        f"ROP {s.get('reorder_point')})"
        for s in critical[:4]
    ) or "no SKUs below safety stock"

    expansions = [
        ExpansionStep(
            step_number=1,
            description="Compute DIO and annual carrying cost",
            domain="inventory",
            data_required=["skus", "monthly_cogs", "carrying_cost_rate"],
            expected_output="Inventory dollars and DIO",
        ),
        ExpansionStep(
            step_number=2,
            description="Flag SKUs below safety stock or reorder point",
            domain="inventory",
            data_required=["sku_recommendations"],
            expected_output="Critical and low SKUs",
        ),
        ExpansionStep(
            step_number=3,
            description="Apply ABC policy to class-A movers",
            domain="inventory",
            data_required=["abc_classification"],
            expected_output="Differentiated inventory policy",
        ),
    ]

    compressions = [
        CompressionStep(
            insight=(
                f"Inventory value {_money(total_value)} implies DIO {dio:.1f} days "
                f"(benchmark {bench:.0f}) and {_money(carrying)} annual carrying cost."
            ),
            recommendation=(
                "Cut class-C safety stock and run a 30-day excess-reduction on slow "
                "movers; keep class-A service level at the configured target."
            ),
            expected_impact=(
                f"A 10% reduction in excess inventory frees ~{_money(total_value * 0.10)} "
                f"and trims carrying cost by ~{_money(carrying * 0.10)} / year."
            ),
            confidence=ConfidenceLevel.HIGH if skus else ConfidenceLevel.LOW,
        ),
        CompressionStep(
            insight=(
                f"{len(critical)} SKUs are below safety stock ({crit_names}); "
                f"{len(low)} approaching reorder; {len(class_a)} class-A SKUs."
            ),
            recommendation=(
                "Place replenishment POs for CRITICAL SKUs this week and raise "
                "reorder points on class-A items to the computed ROP + safety stock."
            ),
            expected_impact="Avoid stockouts on revenue-critical SKUs while DIO stays near benchmark.",
            confidence=ConfidenceLevel.HIGH if critical else ConfidenceLevel.MEDIUM,
        ),
    ]

    grounding = GroundingCheck(
        data_points_referenced=len(skus) + len(sku_recs),
        calculation_trace=(
            "DIO = inventory_value / monthly_cogs * 30; safety_stock = "
            "1.645 * std_demand * sqrt(lead_time/30)"
        ),
        is_grounded=True,
    )
    reasoning = ReasoningTrace(
        steps=["Used InventoryAgent.prepare_context DIO, ABC, and per-SKU ROP"],
        assumptions=["95% service level z-score ≈ 1.645"],
        data_gaps=["No supplier reliability or obsolescence write-off history"],
    )
    return expansions, compressions, grounding, reasoning


def _cash(
    context: dict[str, Any],
) -> tuple[list[ExpansionStep], list[CompressionStep], GroundingCheck, ReasoningTrace]:
    dso = float(context.get("dso") or 0)
    dio = float(context.get("dio") or 0)
    dpo = float(context.get("dpo") or 0)
    ccc = float(context.get("cash_conversion_cycle") or 0)
    opening = float(context.get("opening_cash_balance") or 0)
    threshold = float(context.get("min_cash_threshold") or 0)
    risk_weeks = context.get("risk_weeks") or []
    forecast = context.get("weekly_forecast") or []
    trough = min((w.get("closing_balance", opening) for w in forecast), default=opening)

    expansions = [
        ExpansionStep(
            step_number=1,
            description="Assemble CCC = DSO + DIO − DPO from domain metrics",
            domain="cashflow",
            data_required=["dso", "dio", "dpo"],
            expected_output="Cash conversion cycle in days",
        ),
        ExpansionStep(
            step_number=2,
            description="Walk the 13-week forecast against the cash floor",
            domain="cashflow",
            data_required=["weekly_forecast", "min_cash_threshold"],
            expected_output="Liquidity risk weeks",
        ),
        ExpansionStep(
            step_number=3,
            description="Translate AR / AP / inventory actions into CCC reduction",
            domain="cashflow",
            data_required=["ar_analysis_summary", "ap_analysis_summary", "inventory_analysis_summary"],
            expected_output="Consolidated working-capital roadmap",
        ),
    ]

    risk_label = (
        f"{len(risk_weeks)} week(s) close below {_money(threshold)}"
        if risk_weeks
        else f"no week closes below the {_money(threshold)} floor"
    )

    compressions = [
        CompressionStep(
            insight=(
                f"Cash conversion cycle is {ccc:.1f} days (DSO {dso:.1f} + DIO {dio:.1f} "
                f"− DPO {dpo:.1f}). Opening cash {_money(opening)}; 13-week trough "
                f"{_money(float(trough))}; {risk_label}."
            ),
            recommendation=(
                "Execute the AR collection push, TAKE-only AP discounts, and class-C "
                "inventory cut in the same two-week window so CCC compression shows "
                "up in the rolling forecast."
            ),
            expected_impact=(
                f"A 5-day CCC reduction on this book is roughly "
                f"{_money((context.get('monthly_cogs') or 0) / 30 * 5)} of cash unlocked, "
                "before any forecast mix shift."
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        CompressionStep(
            insight=(
                "Cash-flow agent is last in the mesh: AR inflows, AP timing, and "
                "inventory buys must be sequenced, not optimized in silos."
            ),
            recommendation=(
                "Lock a weekly CCC stand-up: collections forecast (AR), discount/"
                "stretch calendar (AP), and replenishment freezes (inventory) before "
                "treasury updates the 13-week model."
            ),
            expected_impact="Keeps the forecast grounded in the three specialist action lists.",
            confidence=ConfidenceLevel.HIGH,
        ),
    ]

    grounding = GroundingCheck(
        data_points_referenced=3 + len(forecast) + len(risk_weeks),
        calculation_trace="CCC = DSO + DIO − DPO; weekly skeleton from monthly revenue/COGS / 4.33",
        is_grounded=True,
    )
    reasoning = ReasoningTrace(
        steps=[
            "Used CashFlowAgent.prepare_context CCC and 13-week skeleton",
            "Folded prior AR/AP/inventory summaries when the orchestrator supplied them",
        ],
        assumptions=["Weekly collection factor 0.92 / 0.97 / 1.00 by horizon band"],
        data_gaps=["No committed revolver or tax-payment calendar"],
    )
    return expansions, compressions, grounding, reasoning
