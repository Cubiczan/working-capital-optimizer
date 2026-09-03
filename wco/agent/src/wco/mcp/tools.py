"""MCP tool catalog for Working Capital Optimizer *actions*.

This is not Phoenix. Phoenix MCP (`wco mcp` / @arizeai/phoenix-mcp) only
introspects traces. These tools run the Cubiczan WCO specialist mesh.
"""

from __future__ import annotations

from typing import Any

BRAND = "Cubiczan"
PRODUCT = "Working Capital Optimizer"

DATA_PROPERTIES: dict[str, Any] = {
    "ar_invoices": {
        "type": "array",
        "items": {"type": "object"},
        "description": "Accounts receivable invoice records",
    },
    "ap_invoices": {
        "type": "array",
        "items": {"type": "object"},
        "description": "Accounts payable invoice records",
    },
    "skus": {
        "type": "array",
        "items": {"type": "object"},
        "description": "Inventory SKU records",
    },
    "opening_cash_balance": {"type": "number"},
    "monthly_revenue": {"type": "number"},
    "monthly_cogs": {"type": "number"},
    "problem_description": {"type": "string"},
    "cost_of_capital": {"type": "number"},
    "carrying_cost_rate": {"type": "number"},
    "target_service_level": {"type": "number"},
    "min_cash_threshold": {"type": "number"},
    "industry_dso_benchmark": {"type": "number"},
    "industry_dpo_benchmark": {"type": "number"},
    "industry_dio_benchmark": {"type": "number"},
}

COMMON_PROPERTIES: dict[str, Any] = {
    "use_sample_data": {
        "type": "boolean",
        "default": True,
        "description": (
            "When true (default), merge Cubiczan demo manufacturing fixtures "
            "for any missing fields. Offline-safe."
        ),
    },
    "data": {
        "type": "object",
        "description": "Optional working-capital payload. Omitted keys fall back to sample data.",
        "properties": DATA_PROPERTIES,
        "additionalProperties": True,
    },
    "problem_description": {
        "type": "string",
        "description": "Optional CFO problem statement injected into the mesh context.",
    },
}


def tool_definitions() -> list[dict[str, Any]]:
    """Return MCP ``tools/list`` entries for the four specialists plus version."""
    return [
        {
            "name": "recommend_ar_actions",
            "description": (
                "Run the Cubiczan WCO accounts-receivable specialist (ARAgent) "
                "and return collection / DSO / credit-term actions. "
                "Uses demo fixtures when data is omitted. Not Phoenix traces."
            ),
            "inputSchema": {
                "type": "object",
                "properties": COMMON_PROPERTIES,
                "additionalProperties": False,
            },
        },
        {
            "name": "recommend_ap_actions",
            "description": (
                "Run the Cubiczan WCO accounts-payable specialist (APAgent) "
                "and return payment-timing / dynamic-discount / DPO actions. "
                "Uses demo fixtures when data is omitted. Not Phoenix traces."
            ),
            "inputSchema": {
                "type": "object",
                "properties": COMMON_PROPERTIES,
                "additionalProperties": False,
            },
        },
        {
            "name": "recommend_inventory_actions",
            "description": (
                "Run the Cubiczan WCO inventory specialist (InventoryAgent) "
                "and return DIO / safety-stock / ABC actions. "
                "Uses demo fixtures when data is omitted. Not Phoenix traces."
            ),
            "inputSchema": {
                "type": "object",
                "properties": COMMON_PROPERTIES,
                "additionalProperties": False,
            },
        },
        {
            "name": "recommend_cash_conversion_actions",
            "description": (
                "Run the Cubiczan WCO mesh (AR → AP → inventory → cash) and "
                "return cash-conversion-cycle actions plus CCC = DSO + DIO − DPO. "
                "Uses demo fixtures when data is omitted. Not Phoenix traces."
            ),
            "inputSchema": {
                "type": "object",
                "properties": COMMON_PROPERTIES,
                "additionalProperties": False,
            },
        },
        {
            "name": "wco_version",
            "description": (
                "Report Cubiczan WCO actions MCP + agent versions. "
                "Phoenix MCP is a different server (traces only)."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


TOOL_NAMES = {tool["name"] for tool in tool_definitions()}
