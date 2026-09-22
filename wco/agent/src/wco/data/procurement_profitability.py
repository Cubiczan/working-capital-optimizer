"""Deterministic adapter for the generic procurement-profitability data spine.

The adapter deliberately accepts only normalized records.  A payload has the
following shape::

    {
        "ar": [{"balance": 1000}],
        "ap": [{"balance": 700}],
        "inventory": [{"value": 500}],
        "cash": [{"week": 1, "opening_balance": 10000,
                  "inflows": 2000, "outflows": 1500,
                  "revenue": 3000, "cogs": 1800}]
    }

Cash rows are weekly by default; ``period_days`` can be supplied per row when
the source uses a different period.  No source-specific identifiers or
proprietary transformations belong here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

CONTRACT_VERSION = "procurement-profitability.v1"


def adapt_normalized_records(
    records: Mapping[str, Any],
    *,
    owner: str = "unassigned",
    status: str = "ready",
) -> dict[str, Any]:
    """Convert normalized spine records into metrics, cash inputs, and evidence.

    ``records`` is never mutated.  The returned ``run_metadata`` is stable for
    identical input and metadata arguments, which makes it safe to persist or
    compare across agent runs.
    """
    source_hash = _source_hash(records)
    assumptions: list[str] = [
        "DSO, DIO, and DPO use the supplied balance divided by average daily revenue or COGS.",
        "Cash rows without period_days represent seven days.",
    ]

    ar = _records(records, "ar")
    ap = _records(records, "ap")
    inventory = _records(records, "inventory")
    cash = _records(records, "cash")
    cash_by_week = _cash_by_week(cash)
    if len(cash_by_week) < 13:
        assumptions.append("Missing cash weeks are represented as zero inflows and outflows.")

    total_days = sum(_number(row, "period_days", 7) for row in cash)
    revenue = _sum_field(cash, "revenue")
    cogs = _sum_field(cash, "cogs")
    ar_balance = sum(_number(row, "balance") for row in ar)
    ap_balance = sum(_number(row, "balance") for row in ap)
    inventory_value = sum(_number(row, "value") for row in inventory)

    dso = _days(ar_balance, revenue, total_days, "revenue", assumptions)
    dio = _days(inventory_value, cogs, total_days, "cogs", assumptions)
    dpo = _days(ap_balance, cogs, total_days, "cogs", assumptions)
    ccc = _round((dso or 0) + (dio or 0) - (dpo or 0))

    cash_inputs = _build_cash_inputs(cash_by_week, assumptions)
    findings = [
        (
            f"DSO is {_display(dso)} days, DIO is {_display(dio)} days, "
            f"and DPO is {_display(dpo)} days."
        ),
        f"Cash Conversion Cycle is {ccc:.1f} days.",
        f"13-week net cash change is {_round(sum(row['net_change'] for row in cash_inputs)):.2f}.",
    ]

    return {
        "contract_version": CONTRACT_VERSION,
        "metrics": {
            "dso": dso,
            "dio": dio,
            "dpo": dpo,
            "ccc": ccc,
            "period_days": _round(total_days),
            "revenue": _round(revenue),
            "cogs": _round(cogs),
        },
        "cash_inputs": cash_inputs,
        "run_metadata": {
            "run_id": f"{CONTRACT_VERSION}:{source_hash[:16]}",
            "source_hash": source_hash,
            "findings": findings,
            "assumptions": assumptions,
            "owner": owner,
            "status": status,
        },
    }


def _records(records: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = records.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{key!r} must be a list of normalized records")
    if not all(isinstance(row, Mapping) for row in value):
        raise TypeError(f"{key!r} must contain mapping records")
    return list(value)


def _number(row: Mapping[str, Any], key: str, default: float | None = None) -> float:
    value = row.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{key!r} must be a finite number")
    return float(value)


def _sum_field(rows: list[Mapping[str, Any]], key: str) -> float:
    """Sum an optional driver, treating an omitted field as zero."""
    return sum(_number(row, key, 0) for row in rows)


def _days(
    balance: float,
    driver: float,
    period_days: float,
    driver_name: str,
    assumptions: list[str],
) -> float | None:
    if driver <= 0 or period_days <= 0:
        assumptions.append(
            f"{driver_name.upper()} is unavailable, so the related day metric is null."
        )
        return None
    return _round(balance / driver * period_days)


def _cash_by_week(cash: list[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for row in cash:
        week = _number(row, "week")
        if week != int(week) or not 1 <= week <= 13:
            raise ValueError("cash week must be an integer from 1 through 13")
        if int(week) in result:
            raise ValueError(f"duplicate cash week: {int(week)}")
        result[int(week)] = row
    return result


def _build_cash_inputs(
    cash_by_week: dict[int, Mapping[str, Any]], assumptions: list[str]
) -> list[dict[str, float | int]]:
    inputs: list[dict[str, float | int]] = []
    balance = 0.0
    for week in range(1, 14):
        row = cash_by_week.get(week)
        if row is None:
            opening = balance
            inflows = outflows = 0.0
        else:
            opening = _number(row, "opening_balance", balance)
            inflows = _number(row, "inflows", 0)
            outflows = _number(row, "outflows", 0)
        net_change = _round(inflows - outflows)
        balance = _round(opening + net_change)
        inputs.append(
            {
                "week": week,
                "opening_balance": _round(opening),
                "inflows": _round(inflows),
                "outflows": _round(outflows),
                "net_change": net_change,
                "closing_balance": balance,
            }
        )
    return inputs


def _source_hash(records: Mapping[str, Any]) -> str:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    return round(value, 2)


def _display(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.2f}"
