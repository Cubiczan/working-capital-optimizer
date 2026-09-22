from wco.data.procurement_profitability import adapt_normalized_records


def _records() -> dict:
    return {
        "ar": [{"balance": 1000}],
        "ap": [{"balance": 600}],
        "inventory": [{"value": 2000}],
        "cash": [
            {
                "week": 1,
                "opening_balance": 10000,
                "inflows": 2000,
                "outflows": 1500,
                "revenue": 7000,
                "cogs": 3500,
                "period_days": 7,
            },
            {
                "week": 2,
                "opening_balance": 10500,
                "inflows": 2500,
                "outflows": 1000,
                "revenue": 7000,
                "cogs": 3500,
                "period_days": 7,
            },
        ],
    }


def test_adapter_computes_metrics_and_thirteen_week_inputs() -> None:
    result = adapt_normalized_records(_records(), owner="finance", status="review")

    assert result["metrics"] == {
        "dso": 1.0,
        "dio": 4.0,
        "dpo": 1.2,
        "ccc": 3.8,
        "period_days": 14.0,
        "revenue": 14000.0,
        "cogs": 7000.0,
    }
    assert len(result["cash_inputs"]) == 13
    assert result["cash_inputs"][0]["closing_balance"] == 10500.0
    assert result["cash_inputs"][1]["closing_balance"] == 12000.0
    assert result["cash_inputs"][2]["inflows"] == 0.0
    assert result["run_metadata"]["owner"] == "finance"
    assert result["run_metadata"]["status"] == "review"
    assert "Missing cash weeks" in result["run_metadata"]["assumptions"][-1]


def test_hash_and_run_id_are_deterministic_and_key_order_independent() -> None:
    first = adapt_normalized_records(_records(), owner="ops")
    reordered = {
        "cash": _records()["cash"],
        "inventory": _records()["inventory"],
        "ap": _records()["ap"],
        "ar": _records()["ar"],
    }
    second = adapt_normalized_records(reordered, owner="ops")

    assert first["run_metadata"] == second["run_metadata"]
    assert len(first["run_metadata"]["source_hash"]) == 64


def test_missing_driver_is_explicit_in_metrics_and_assumptions() -> None:
    records = _records()
    for row in records["cash"]:
        row.pop("cogs")

    result = adapt_normalized_records(records)

    assert result["metrics"]["dio"] is None
    assert result["metrics"]["dpo"] is None
    assert any("COGS is unavailable" in item for item in result["run_metadata"]["assumptions"])
