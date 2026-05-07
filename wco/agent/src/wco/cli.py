"""WCO CLI entry point.

Usage::

    # Run a full analysis from a JSON data file
    wco analyze --data-file ./data/company.json

    # Start the API server
    wco serve

    # Run evaluation on a stored recommendation
    wco evaluate --recommendation-id <id>

    # Print version
    wco --version
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("wco")


def _setup_logging(verbose: bool = False) -> None:
    """Configure root logger."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── Commands ──────────────────────────────────────────────────────────────


def cmd_analyze(args: argparse.Namespace) -> None:
    """Run a full working capital analysis from a data file.

    Loads JSON or CSV data, runs all four domain agents through the
    orchestrator, and prints the report to stdout.
    """
    import json

    data_file = Path(args.data_file)
    if not data_file.exists():
        logger.error("Data file not found: %s", data_file)
        sys.exit(1)

    # Load data
    if data_file.suffix == ".json":
        with open(data_file) as f:
            data = json.load(f)
    elif data_file.suffix == ".csv":
        # Basic CSV → JSON conversion (expects ar_invoices.csv etc.)
        import csv

        data = {"problem_description": "Working capital optimization analysis"}
        reader = csv.DictReader(open(data_file))
        rows = list(reader)
        fname = data_file.stem.lower()
        if "ar" in fname:
            data["ar_invoices"] = rows
        elif "ap" in fname:
            data["ap_invoices"] = rows
        elif "inv" in fname or "sku" in fname:
            data["skus"] = rows
        else:
            data["ar_invoices"] = rows
    else:
        logger.error("Unsupported file format: %s (use .json or .csv)", data_file.suffix)
        sys.exit(1)

    # Merge with sample data defaults if keys are missing
    from wco.data.sample_data import get_sample_data

    sample = get_sample_data()
    for key, value in sample.items():
        if key not in data:
            data[key] = value

    asyncio.run(_run_analysis(data, args.output, args.verbose))


async def _run_analysis(
    data: dict[str, Any],
    output_file: str | None,
    verbose: bool,
) -> None:
    """Execute the analysis pipeline and output results."""
    _setup_logging(verbose)

    from wco.agents import ARAgent, APAgent, CashFlowAgent, InventoryAgent
    from wco.orchestration import WorkingCapitalOrchestrator

    logger.info("Starting WCO analysis pipeline...")

    agents = [ARAgent(), APAgent(), InventoryAgent(), CashFlowAgent()]
    orchestrator = WorkingCapitalOrchestrator(agents)

    report = await orchestrator.run(data)
    result = report.to_dict()

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info("Report written to %s", out_path)
    else:
        print(json.dumps(result, indent=2, default=str))


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI server."""
    _setup_logging(args.verbose)

    import uvicorn

    from wco.config import get_settings

    settings = get_settings()

    logger.info("Starting WCO API server on port %d", settings.port)
    uvicorn.run(
        "wco.api.server:app",
        host="0.0.0.0",
        port=settings.port,
        reload=args.reload,
    )


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Run evaluation on a recommendation."""
    _setup_logging(args.verbose)

    if not args.recommendation_id and not args.recommendation_text:
        logger.error("Provide either --recommendation-id or --recommendation-text")
        sys.exit(1)

    asyncio.run(_run_evaluation(args))


async def _run_evaluation(args: argparse.Namespace) -> None:
    """Execute the evaluation and print results."""
    from wco.eval.evaluator import RecommendationEvaluator

    evaluator = RecommendationEvaluator()

    if args.recommendation_text:
        recommendation = args.recommendation_text
        context = args.context or "Working capital optimization"
        agent_name = args.agent_name or "unknown"
    else:
        # Load from DB
        from wco.db.connection import list_recommendations

        recs = await list_recommendations(limit=1)
        if not recs:
            logger.error("No recommendations found in database")
            sys.exit(1)
        recommendation = recs[0].get("recommendation_text", "")
        context = recs[0].get("problem_description", "")
        agent_name = recs[0].get("agent_name", "unknown")

    result = await evaluator.run_evaluation(
        recommendation=recommendation,
        context=context,
        agent_name=agent_name,
        store=True,
    )

    print(json.dumps(result.to_dict(), indent=2, default=str))


def cmd_improve(args: argparse.Namespace) -> None:
    """Run the self-improvement cycle."""
    _setup_logging(args.verbose)

    asyncio.run(_run_improvement())


async def _run_improvement() -> None:
    """Execute the self-improvement cycle and print results."""
    from wco.eval.self_improvement import SelfImprovementEngine

    logger.info("Starting self-improvement cycle...")
    engine = SelfImprovementEngine()

    report = await engine.run_improvement_cycle()

    result = {
        "report_id": report.report_id,
        "timestamp": report.timestamp,
        "patterns_found": [
            {
                "agent": p.agent_name,
                "dimension": p.dimension,
                "avg_score": p.avg_score,
                "eval_count": p.eval_count,
            }
            for p in report.patterns_found
        ],
        "amendments_applied": report.amendments_applied,
        "amendments_skipped": report.amendments_skipped,
    }

    print(json.dumps(result, indent=2, default=str))

    if not report.patterns_found:
        logger.info("No weakness patterns found — agents are performing well")
    else:
        logger.info(
            "Found %d patterns, applied %d amendments",
            len(report.patterns_found),
            len(report.amendments_applied),
        )


# ── Argument parser ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="wco",
        description="Working Capital Optimizer — AI agent mesh for CFO-level cash flow intelligence.",
    )
    parser.add_argument("--version", action="version", version="wco-agent 0.1.0")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Run full working capital analysis")
    p_analyze.add_argument(
        "--data-file",
        required=True,
        help="Path to JSON/CSV data file",
    )
    p_analyze.add_argument(
        "--output", "-o",
        help="Path to write the JSON report (default: stdout)",
    )
    p_analyze.add_argument("--verbose", "-v", action="store_true")
    p_analyze.set_defaults(func=cmd_analyze)

    # serve
    p_serve = sub.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload")
    p_serve.add_argument("--verbose", "-v", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate a recommendation")
    p_eval.add_argument(
        "--recommendation-id",
        help="ID of stored recommendation to evaluate",
    )
    p_eval.add_argument(
        "--recommendation-text",
        help="Inline recommendation text to evaluate",
    )
    p_eval.add_argument(
        "--context",
        default="Working capital optimization for a manufacturing company",
        help="Context description for evaluation",
    )
    p_eval.add_argument(
        "--agent-name",
        default="",
        help="Name of the agent that produced the recommendation",
    )
    p_eval.add_argument("--verbose", "-v", action="store_true")
    p_eval.set_defaults(func=cmd_evaluate)

    # improve
    p_improve = sub.add_parser("improve", help="Run self-improvement cycle")
    p_improve.add_argument("--verbose", "-v", action="store_true")
    p_improve.set_defaults(func=cmd_improve)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
