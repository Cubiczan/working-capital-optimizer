use serde_json::Value;
use std::env;
use std::io::{self, Read};

use wco_core::{
    ap_context, ar_context, cashflow_context, evaluate_overall, health, inventory_context,
    orchestration_summary, select_context,
};

fn read_input() -> Result<Value, String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|err| format!("failed to read stdin: {err}"))?;
    if input.trim().is_empty() {
        return Ok(Value::Object(Default::default()));
    }
    serde_json::from_str(&input).map_err(|err| format!("invalid JSON input: {err}"))
}

fn main() {
    let mut args = env::args().skip(1);
    let command = match args.next() {
        Some(value) => value,
        None => {
            eprintln!("missing command");
            std::process::exit(2);
        }
    };

    let input = match read_input() {
        Ok(value) => value,
        Err(err) => {
            eprintln!("{err}");
            std::process::exit(2);
        }
    };

    let output = match command.as_str() {
        "ar-context" => ar_context(&input),
        "ap-context" => ap_context(&input),
        "inventory-context" => inventory_context(&input),
        "cashflow-context" => cashflow_context(&input),
        "evaluate-overall" => evaluate_overall(&input),
        "summarize-orchestration" => orchestration_summary(&input),
        "select-context" => select_context(&input),
        "health" => health(),
        other => {
            eprintln!("unknown command: {other}");
            std::process::exit(2);
        }
    };

    if let Err(err) = serde_json::to_writer(io::stdout(), &output) {
        eprintln!("failed to write JSON output: {err}");
        std::process::exit(1);
    }
}
