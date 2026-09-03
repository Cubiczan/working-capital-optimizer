use chrono::NaiveDate;
use regex::Regex;
use serde_json::{json, Map, Value};
use std::collections::HashMap;

fn num(value: &Value, key: &str) -> f64 {
    value.get(key).and_then(Value::as_f64).unwrap_or(0.0)
}

fn text(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

fn list<'a>(value: &'a Value, key: &str) -> &'a [Value] {
    value
        .get(key)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

fn round_to(value: f64, places: i32) -> f64 {
    let factor = 10_f64.powi(places);
    (value * factor).round() / factor
}

fn extract_first_number(text: &str, key: &str) -> Option<f64> {
    let pattern = format!(r"{}\s*(?:is|:|=|=~)?\s*(\d+\.?\d*)", regex::escape(key));
    let re = Regex::new(&pattern).ok()?;
    re.captures(text)
        .and_then(|caps| caps.get(1))
        .and_then(|m| m.as_str().parse::<f64>().ok())
}

fn parse_date(value: &Value) -> Option<NaiveDate> {
    value
        .as_str()
        .and_then(|s| NaiveDate::parse_from_str(s, "%Y-%m-%d").ok())
}

fn aging_bucket_key(bucket: &str) -> &'static str {
    let bucket = bucket.to_lowercase();
    if bucket.contains("current") {
        "current"
    } else if bucket.starts_with('1') || bucket.starts_with('0') {
        "1_30"
    } else if bucket.starts_with('3') {
        "31_60"
    } else if bucket.starts_with('6') {
        "61_90"
    } else {
        "90_plus"
    }
}

pub fn ar_context(raw: &Value) -> Value {
    let invoices = list(raw, "ar_invoices");
    let monthly_revenue = num(raw, "monthly_revenue");

    let mut aging_summary = Map::from_iter([
        ("current".to_string(), json!(0)),
        ("1_30".to_string(), json!(0)),
        ("31_60".to_string(), json!(0)),
        ("61_90".to_string(), json!(0)),
        ("90_plus".to_string(), json!(0)),
    ]);

    let mut total_ar = 0.0;
    for invoice in invoices {
        total_ar += num(invoice, "amount");
        let key = aging_bucket_key(&text(invoice, "aging_bucket"));
        let count = aging_summary.get(key).and_then(Value::as_i64).unwrap_or(0) + 1;
        aging_summary.insert(key.to_string(), json!(count));
    }

    let total_ar_balance = round_to(total_ar, 2);
    let estimated_dso = if monthly_revenue > 0.0 {
        round_to(total_ar / monthly_revenue * 30.0, 1)
    } else {
        0.0
    };

    let mut overdue_count = 0_i64;
    let mut overdue_amount = 0.0;
    for invoice in invoices {
        let days_outstanding = num(invoice, "days_outstanding");
        let payment_terms_days = num(invoice, "payment_terms_days");
        if days_outstanding > payment_terms_days {
            overdue_count += 1;
            overdue_amount += num(invoice, "amount");
        }
    }

    json!({
        "ar_invoices": invoices,
        "aging_summary": aging_summary,
        "total_ar_balance": total_ar_balance,
        "estimated_dso": estimated_dso,
        "monthly_revenue": monthly_revenue,
        "overdue_count": overdue_count,
        "overdue_amount": round_to(overdue_amount, 2),
        "industry_dso_benchmark": raw.get("industry_dso_benchmark").and_then(Value::as_f64).unwrap_or(45.0),
    })
}

pub fn ap_context(raw: &Value) -> Value {
    let invoices = list(raw, "ap_invoices");
    let monthly_cogs = num(raw, "monthly_cogs");
    let cost_of_capital = num(raw, "cost_of_capital");

    let total_ap: f64 = invoices.iter().map(|invoice| num(invoice, "amount")).sum();
    let estimated_dpo = if monthly_cogs > 0.0 {
        round_to(total_ap / monthly_cogs * 30.0, 1)
    } else {
        0.0
    };

    let mut discount_analysis = Vec::new();
    let mut vendor_totals: HashMap<String, f64> = HashMap::new();

    for invoice in invoices {
        let vendor = text(invoice, "vendor_name");
        *vendor_totals.entry(vendor.clone()).or_insert(0.0) += num(invoice, "amount");

        if !invoice.get("discount_available").and_then(Value::as_bool).unwrap_or(false) {
            continue;
        }

        let amount = num(invoice, "amount");
        let discount_pct = num(invoice, "discount_pct") / 100.0;
        let due_date = invoice.get("due_date").and_then(parse_date);
        let deadline = invoice.get("discount_deadline").and_then(parse_date);

        let analysis = match (amount > 0.0, discount_pct > 0.0, due_date, deadline) {
            (true, true, Some(due_date), Some(deadline)) => {
                let extra_days = ((due_date - deadline).num_days()).max(1) as f64;
                let annualised = (discount_pct / (1.0 - discount_pct)) * (365.0 / extra_days);
                let recommendation = if annualised > cost_of_capital { "TAKE" } else { "SKIP" };
                json!({
                    "vendor": vendor,
                    "amount": amount,
                    "discount_pct": format!("{:.1}%", discount_pct * 100.0),
                    "annualised_return": format!("{:.1}%", annualised * 100.0),
                    "recommendation": recommendation,
                })
            }
            _ => json!({
                "vendor": vendor,
                "amount": amount,
                "discount_pct": format!("{:.1}%", discount_pct * 100.0),
                "annualised_return": "N/A",
                "recommendation": "REVIEW",
            }),
        };

        discount_analysis.push(analysis);
    }

    let mut vendor_totals_vec: Vec<(String, f64)> = vendor_totals.into_iter().collect();
    vendor_totals_vec.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let mut vendor_totals_top = Map::new();
    for (vendor, amount) in vendor_totals_vec.into_iter().take(10) {
        vendor_totals_top.insert(vendor, json!(round_to(amount, 2)));
    }

    json!({
        "ap_invoices": invoices,
        "total_ap_balance": round_to(total_ap, 2),
        "estimated_dpo": estimated_dpo,
        "monthly_cogs": monthly_cogs,
        "cost_of_capital": cost_of_capital,
        "discountable_invoices_count": discount_analysis.len(),
        "discount_analysis": discount_analysis,
        "vendor_totals": vendor_totals_top,
        "industry_dpo_benchmark": raw.get("industry_dpo_benchmark").and_then(Value::as_f64).unwrap_or(50.0),
    })
}

pub fn inventory_context(raw: &Value) -> Value {
    let skus = list(raw, "skus");
    let monthly_cogs = num(raw, "monthly_cogs");
    let carrying_cost_rate = raw.get("carrying_cost_rate").and_then(Value::as_f64).unwrap_or(0.25);
    let target_service_level = raw.get("target_service_level").and_then(Value::as_f64).unwrap_or(0.95);

    let total_inventory_value: f64 = skus
        .iter()
        .map(|sku| num(sku, "quantity_on_hand") * num(sku, "unit_cost"))
        .sum();
    let estimated_dio = if monthly_cogs > 0.0 {
        round_to(total_inventory_value / monthly_cogs * 30.0, 1)
    } else {
        0.0
    };
    let annual_carrying_cost = round_to(total_inventory_value * carrying_cost_rate, 2);

    let mut sku_revenue: Vec<(Value, f64)> = skus
        .iter()
        .map(|sku| {
            let revenue = sku
                .get("annual_revenue")
                .and_then(Value::as_f64)
                .filter(|v| *v > 0.0)
                .unwrap_or_else(|| num(sku, "avg_monthly_demand") * num(sku, "unit_cost") * 12.0);
            (sku.clone(), revenue)
        })
        .collect();
    sku_revenue.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    let total_revenue: f64 = sku_revenue.iter().map(|(_, revenue)| *revenue).sum::<f64>().max(1.0);
    let mut cumulative = 0.0;
    let mut abc_a = Vec::new();
    let mut abc_b = Vec::new();
    let mut abc_c = Vec::new();

    for (sku, revenue) in sku_revenue {
        cumulative += revenue;
        let pct = cumulative / total_revenue;
        let classification = if pct <= 0.80 {
            "A"
        } else if pct <= 0.95 {
            "B"
        } else {
            "C"
        };
        let entry = json!({
            "sku_id": text(&sku, "sku_id"),
            "name": text(&sku, "name"),
            "annual_revenue_contribution": round_to(revenue, 2),
            "classification": classification,
        });
        match classification {
            "A" => abc_a.push(entry),
            "B" => abc_b.push(entry),
            _ => abc_c.push(entry),
        }
    }

    let z_score = 1.645_f64;
    let mut sku_recommendations = Vec::new();
    for sku in skus {
        let lt = num(sku, "lead_time_days").max(30.0);
        let avg_demand = num(sku, "avg_monthly_demand");
        let std_demand = num(sku, "std_monthly_demand");
        let daily_demand = avg_demand / 30.0;
        let reorder_point = round_to(daily_demand * lt, 1);
        let safety_stock = round_to(z_score * std_demand * (lt / 30.0).sqrt(), 1);
        let on_hand = num(sku, "quantity_on_hand");

        let status = if on_hand < safety_stock {
            "CRITICAL — below safety stock"
        } else if on_hand < reorder_point {
            "low — approaching reorder point"
        } else {
            "adequate"
        };

        sku_recommendations.push(json!({
            "sku_id": text(sku, "sku_id"),
            "name": text(sku, "name"),
            "on_hand": on_hand,
            "reorder_point": reorder_point,
            "safety_stock": safety_stock,
            "status": status,
        }));
    }

    json!({
        "skus": skus,
        "total_inventory_value": round_to(total_inventory_value, 2),
        "estimated_dio": estimated_dio,
        "annual_carrying_cost": annual_carrying_cost,
        "carrying_cost_rate": carrying_cost_rate,
        "abc_classification": {
            "A": abc_a,
            "B": abc_b,
            "C": abc_c,
        },
        "sku_recommendations": sku_recommendations,
        "target_service_level": target_service_level,
        "industry_dio_benchmark": raw.get("industry_dio_benchmark").and_then(Value::as_f64).unwrap_or(75.0),
    })
}

fn summarise_agent_result(result: Option<&Value>) -> Value {
    let Some(result) = result else {
        return json!({"status": "not_available"});
    };

    let compressions = result
        .get("compression_steps")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let recommendations: Vec<Value> = compressions
        .iter()
        .map(|step| {
            json!({
                "insight": step.get("insight").and_then(Value::as_str).unwrap_or(""),
                "recommendation": step.get("recommendation").and_then(Value::as_str).unwrap_or(""),
                "expected_impact": step.get("expected_impact").and_then(Value::as_str).unwrap_or(""),
            })
        })
        .collect();

    json!({
        "agent_name": result.get("agent_name").and_then(Value::as_str).unwrap_or("unknown"),
        "duration_ms": result.get("duration_ms").and_then(Value::as_f64).unwrap_or(0.0),
        "num_recommendations": recommendations.len(),
        "recommendations": recommendations,
        "grounded": result
            .get("grounding_check")
            .and_then(Value::as_object)
            .and_then(|obj| obj.get("is_grounded"))
            .and_then(Value::as_bool)
            .unwrap_or(false),
    })
}

pub fn cashflow_context(raw: &Value) -> Value {
    let monthly_revenue = num(raw, "monthly_revenue");
    let monthly_cogs = num(raw, "monthly_cogs");

    let ar_invoices = list(raw, "ar_invoices");
    let ap_invoices = list(raw, "ap_invoices");
    let skus = list(raw, "skus");

    let total_ar: f64 = ar_invoices.iter().map(|inv| num(inv, "amount")).sum();
    let dso = if monthly_revenue > 0.0 {
        round_to(total_ar / monthly_revenue * 30.0, 1)
    } else {
        0.0
    };

    let total_ap: f64 = ap_invoices.iter().map(|inv| num(inv, "amount")).sum();
    let dpo = if monthly_cogs > 0.0 {
        round_to(total_ap / monthly_cogs * 30.0, 1)
    } else {
        0.0
    };

    let total_inv_value: f64 = skus
        .iter()
        .map(|sku| num(sku, "quantity_on_hand") * num(sku, "unit_cost"))
        .sum();
    let dio = if monthly_cogs > 0.0 {
        round_to(total_inv_value / monthly_cogs * 30.0, 1)
    } else {
        0.0
    };

    let ccc = round_to(dso + dio - dpo, 1);
    let weekly_collections = monthly_revenue / 4.33;
    let weekly_payments = monthly_cogs / 4.33;
    let opening_balance = num(raw, "opening_cash_balance");
    let min_cash_threshold = raw
        .get("min_cash_threshold")
        .and_then(Value::as_f64)
        .unwrap_or(500_000.0);

    let mut weekly_forecast = Vec::new();
    let mut balance = opening_balance;
    for week in 1..=13 {
        let collection_factor = if week <= 4 {
            0.92
        } else if week <= 8 {
            0.97
        } else {
            1.0
        };
        let expected_inflows = round_to(weekly_collections * collection_factor, 2);
        let expected_outflows = round_to(weekly_payments * 1.02, 2);
        let net_change = round_to(expected_inflows - expected_outflows, 2);
        let opening = balance;
        balance = round_to(balance + net_change, 2);
        weekly_forecast.push(json!({
            "week": week,
            "opening_balance": opening,
            "inflows": expected_inflows,
            "outflows": expected_outflows,
            "net_change": net_change,
            "closing_balance": balance,
        }));
    }

    let risk_weeks: Vec<Value> = weekly_forecast
        .iter()
        .filter(|week| week.get("closing_balance").and_then(Value::as_f64).unwrap_or(0.0) < min_cash_threshold)
        .cloned()
        .collect();

    json!({
        "opening_cash_balance": opening_balance,
        "monthly_revenue": monthly_revenue,
        "monthly_cogs": monthly_cogs,
        "dso": dso,
        "dpo": dpo,
        "dio": dio,
        "cash_conversion_cycle": ccc,
        "weekly_forecast": weekly_forecast,
        "min_cash_threshold": min_cash_threshold,
        "risk_weeks": risk_weeks,
        "ar_analysis_summary": summarise_agent_result(raw.get("ar_result")),
        "ap_analysis_summary": summarise_agent_result(raw.get("ap_result")),
        "inventory_analysis_summary": summarise_agent_result(raw.get("inventory_result")),
        "ar_invoices": ar_invoices,
        "ap_invoices": ap_invoices,
        "skus": skus,
    })
}

pub fn evaluate_overall(raw: &Value) -> Value {
    let scores = raw
        .get("scores")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);

    let mut weighted_sum = 0.0;
    let mut total_weight = 0.0;

    for score in scores {
        let dimension = score.get("dimension").and_then(Value::as_str).unwrap_or("");
        let weight = match dimension {
            "relevance" => 0.25,
            "actionability" => 0.30,
            "financial_impact" => 0.25,
            "risk_awareness" => 0.20,
            _ => 0.25,
        };
        let value = score.get("score").and_then(Value::as_f64).unwrap_or(0.0);
        weighted_sum += value * weight;
        total_weight += weight;
    }

    json!({
        "overall_score": if total_weight > 0.0 { round_to(weighted_sum / total_weight, 2) } else { 0.0 }
    })
}

pub fn orchestration_summary(raw: &Value) -> Value {
    let turns = list(raw, "turns");
    let mut recommendations = Vec::new();
    let mut ccc = Map::from_iter([
        ("dso".to_string(), json!(0.0)),
        ("dio".to_string(), json!(0.0)),
        ("dpo".to_string(), json!(0.0)),
        ("ccc".to_string(), json!(0.0)),
    ]);

    for turn in turns {
        let agent_name = text(turn, "agent_name");
        let capability = text(turn, "capability");
        let steps = list(turn, "compression_steps");

        if capability == "cashflow" {
            for step in steps {
                let text_blob = format!(
                    "{} {} {}",
                    step.get("insight").and_then(Value::as_str).unwrap_or(""),
                    step.get("recommendation").and_then(Value::as_str).unwrap_or(""),
                    step.get("expected_impact").and_then(Value::as_str).unwrap_or("")
                )
                .to_lowercase();

                for key in ["dso", "dio", "dpo", "ccc", "cash conversion cycle"] {
                    if let Some(value) = extract_first_number(&text_blob, key) {
                        ccc.insert(key.to_string(), json!(value));
                    }
                }
            }
        }

        for step in steps {
            recommendations.push(json!({
                "agent": agent_name,
                "capability": capability,
                "insight": step.get("insight").and_then(Value::as_str).unwrap_or(""),
                "recommendation": step.get("recommendation").and_then(Value::as_str).unwrap_or(""),
                "expected_impact": step.get("expected_impact").and_then(Value::as_str).unwrap_or(""),
                "confidence": step.get("confidence").and_then(Value::as_str).unwrap_or("medium"),
            }));
        }
    }

    json!({
        "cash_conversion_cycle": ccc,
        "recommendations": recommendations,
    })
}

pub fn select_context(raw: &Value) -> Value {
    let query = raw.get("query").and_then(Value::as_str).unwrap_or("");
    let top_k = raw.get("top_k").and_then(Value::as_u64).unwrap_or(10) as usize;
    let kind = raw.get("kind").and_then(Value::as_str).map(|s| s.to_lowercase());
    let source_agent = raw.get("source_agent").and_then(Value::as_str);
    let entries = list(raw, "entries");

    let query_terms = tokenize(query);
    let mut scored: Vec<(f64, usize, String)> = Vec::new();

    for (index, entry) in entries.iter().enumerate() {
        if let Some(kind_filter) = kind.as_deref() {
            if entry.get("kind").and_then(Value::as_str).map(|s| s.to_lowercase()).as_deref()
                != Some(kind_filter)
            {
                continue;
            }
        }
        if let Some(source_filter) = source_agent {
            if entry.get("source_agent").and_then(Value::as_str) != Some(source_filter) {
                continue;
            }
        }

        let mut doc = String::new();
        doc.push_str(entry.get("text").and_then(Value::as_str).unwrap_or(""));
        doc.push(' ');
        doc.push_str(entry.get("key").and_then(Value::as_str).unwrap_or(""));
        let score = overlap_score(&query_terms, &tokenize(&doc));
        scored.push((score, index, entry.get("entry_id").and_then(Value::as_str).unwrap_or("").to_string()));
    }

    scored.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.1.cmp(&b.1))
    });

    json!({
        "selected_entry_ids": scored
            .into_iter()
            .take(top_k)
            .map(|(_, _, id)| id)
            .collect::<Vec<_>>()
    })
}

fn tokenize(text: &str) -> std::collections::HashSet<String> {
    Regex::new(r"[a-z0-9_]+")
        .ok()
        .map(|re| {
            re.find_iter(&text.to_lowercase())
                .map(|m| m.as_str().to_string())
                .filter(|token| token.len() > 1)
                .collect()
        })
        .unwrap_or_default()
}

fn overlap_score(query: &std::collections::HashSet<String>, doc: &std::collections::HashSet<String>) -> f64 {
    if query.is_empty() {
        return 0.0;
    }
    let intersection = query.intersection(doc).count();
    intersection as f64 / query.len() as f64
}

pub fn health() -> Value {
    json!({
        "status": "ok",
        "version": "0.1.0",
        "agents_ready": true,
        "database_connected": false,
    })
}
