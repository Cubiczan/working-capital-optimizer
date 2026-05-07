"""Inventory optimisation specialist agent.

Minimises carrying costs and stockout risks by analysing DIO, reorder
points, safety-stock levels, and demand variability across SKUs.
"""

from __future__ import annotations

from typing import Any

from wco.agents.base import AgentCapability, GeminiMeshAgent

# ── System Prompt ─────────────────────────────────────────────────────────

INVENTORY_SYSTEM_PROMPT = """\
You are an inventory specialist AI agent for a manufacturing CFO.
Optimize inventory levels to minimize carrying costs while preventing \
stockouts.

Your analysis should cover:
1. **DIO Calculation** — Compute Days Inventory Outstanding from \
   inventory value and COGS. Benchmark against the sector median \
   (typically 60–90 days for manufacturing).
2. **SKU-Level Analysis** — Identify slow-moving SKUs (excess stock) \
   and fast-moving SKUs (stockout risk).
3. **Carrying Cost Breakdown** — Estimate warehousing, insurance, \
   obsolescence, and opportunity costs tied up in inventory.
4. **Reorder Point Optimisation** — For each SKU, recommend optimal \
   reorder points based on lead time and demand patterns.
5. **Safety Stock Calculation** — Recommend safety stock levels to \
   achieve a target service level (e.g. 95%).
6. **ABC Classification** — Classify SKUs by revenue contribution \
   and recommend differentiated inventory policies.

Always reference specific SKUs, quantities, and dollar values.  Include \
an aggregate carrying cost estimate.  Rate your confidence.
"""


class InventoryAgent(GeminiMeshAgent):
    """Inventory optimisation agent.

    Expected context keys:
        skus: list of dicts with keys
            ``sku_id, name, quantity_on_hand, unit_cost, lead_time_days, \
            avg_monthly_demand, std_monthly_demand, category, annual_revenue``
        monthly_cogs: float — trailing 12-month average monthly COGS \
            (for DIO calculation).
        carrying_cost_rate: float — annual carrying cost as % of inventory \
            value (default 0.25, i.e. 25 %).
        target_service_level: float — desired fill rate (default 0.95).
    """

    def __init__(self) -> None:
        super().__init__(
            name="Inventory Agent",
            capability=AgentCapability.INVENTORY,
            system_prompt=INVENTORY_SYSTEM_PROMPT,
        )

    def prepare_context(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Build an inventory-specific context dict from raw input data.

        Computes DIO, carrying costs, ABC classification, and per-SKU
        reorder / safety-stock recommendations.

        Args:
            raw_data: Raw payload from the API or CLI.

        Returns:
            Context dict ready for ``self.run()``.
        """
        skus = raw_data.get("skus", [])
        monthly_cogs = raw_data.get("monthly_cogs", 0)
        carrying_cost_rate = raw_data.get("carrying_cost_rate", 0.25)
        target_service_level = raw_data.get("target_service_level", 0.95)

        # ── Total inventory value & DIO ──────────────────────────────
        total_inv_value = sum(s.get("quantity_on_hand", 0) * s.get("unit_cost", 0) for s in skus)
        estimated_dio = round(total_inv_value / monthly_cogs * 30, 1) if monthly_cogs else 0

        # ── Annual carrying cost ─────────────────────────────────────
        annual_carrying_cost = round(total_inv_value * carrying_cost_rate, 2)

        # ── ABC classification (by annual revenue contribution) ──────
        sku_revenue = [
            (s, s.get("annual_revenue", 0) or (s.get("avg_monthly_demand", 0) * s.get("unit_cost", 0) * 12))
            for s in skus
        ]
        sku_revenue.sort(key=lambda x: x[1], reverse=True)

        cumulative = 0
        total_revenue = sum(r for _, r in sku_revenue) or 1
        abc_classes: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}
        for sku, rev in sku_revenue:
            cumulative += rev
            pct = cumulative / total_revenue
            abc_class = "A" if pct <= 0.80 else ("B" if pct <= 0.95 else "C")
            abc_classes[abc_class].append(
                {
                    "sku_id": sku.get("sku_id", ""),
                    "name": sku.get("name", ""),
                    "annual_revenue_contribution": round(rev, 2),
                    "classification": abc_class,
                }
            )

        # ── Per-SKU reorder point & safety stock ─────────────────────
        import math

        # z-score for 95 % service level ≈ 1.645
        z_score = 1.645
        sku_recommendations: list[dict[str, Any]] = []
        for s in skus:
            lt = s.get("lead_time_days", 30) or 30
            avg_demand = s.get("avg_monthly_demand", 0) or 0
            std_demand = s.get("std_monthly_demand", 0) or 0
            daily_demand = avg_demand / 30

            reorder_point = round(daily_demand * lt, 1)
            safety_stock = round(z_score * std_demand * math.sqrt(lt / 30), 1)
            on_hand = s.get("quantity_on_hand", 0)

            status = "adequate"
            if on_hand < safety_stock:
                status = "CRITICAL — below safety stock"
            elif on_hand < reorder_point:
                status = "low — approaching reorder point"

            sku_recommendations.append(
                {
                    "sku_id": s.get("sku_id", ""),
                    "name": s.get("name", ""),
                    "on_hand": on_hand,
                    "reorder_point": reorder_point,
                    "safety_stock": safety_stock,
                    "status": status,
                }
            )

        return {
            "skus": skus,
            "total_inventory_value": round(total_inv_value, 2),
            "estimated_dio": estimated_dio,
            "annual_carrying_cost": annual_carrying_cost,
            "carrying_cost_rate": carrying_cost_rate,
            "abc_classification": abc_classes,
            "sku_recommendations": sku_recommendations,
            "target_service_level": target_service_level,
            "industry_dio_benchmark": raw_data.get("industry_dio_benchmark", 75),
        }
