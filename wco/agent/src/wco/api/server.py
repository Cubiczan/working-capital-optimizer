"""FastAPI application for the WCO agent mesh.

Endpoints:
- ``POST /api/analyze`` — run full working capital analysis.
- ``POST /api/evaluate`` — evaluate a recommendation via LLM-as-a-Judge.
- ``GET /api/recommendations`` — list past recommendations.
- ``GET /api/evaluations`` — list past evaluations.
- ``GET /api/health`` — health check.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from wco.agents import ARAgent, APAgent, CashFlowAgent, InventoryAgent
from wco.orchestration import WorkingCapitalOrchestrator
from wco.eval.evaluator import RecommendationEvaluator

logger = logging.getLogger(__name__)

# ── App factory ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Working Capital Optimizer API",
    description="AI agent mesh for CFO-level working capital intelligence. "
    "Powered by Google Gemini and traced with Arize Phoenix.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open for hackathon dashboard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    """Payload for the ``/api/analyze`` endpoint.

    Attributes:
        ar_invoices: Accounts Receivable invoice records.
        ap_invoices: Accounts Payable invoice records.
        skus: Inventory SKU records.
        opening_cash_balance: Starting cash position.
        monthly_revenue: Average monthly revenue (trailing 12m).
        monthly_cogs: Average monthly COGS (trailing 12m).
        problem_description: Free-text description of the problem.
    """

    ar_invoices: list[dict[str, Any]] = Field(default_factory=list)
    ap_invoices: list[dict[str, Any]] = Field(default_factory=list)
    skus: list[dict[str, Any]] = Field(default_factory=list)
    opening_cash_balance: float = 2_500_000
    monthly_revenue: float = 1_200_000
    monthly_cogs: float = 720_000
    problem_description: str = "Optimize working capital for manufacturing operations"
    cost_of_capital: float = 0.08
    carrying_cost_rate: float = 0.25
    target_service_level: float = 0.95
    min_cash_threshold: float = 500_000


class EvaluateRequest(BaseModel):
    """Payload for the ``/api/evaluate`` endpoint.

    Attributes:
        recommendation: The recommendation text to evaluate.
        context: The problem / context the recommendation addresses.
        agent_name: Name of the producing agent (optional).
        recommendation_id: Link to stored recommendation (optional).
    """

    recommendation: str
    context: str = ""
    agent_name: str = ""
    recommendation_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    agents_ready: bool = True
    database_connected: bool = False


# ── Startup ───────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup() -> None:
    """Initialise tracing, DB, and agent instances on startup."""
    # Attempt DB initialisation
    try:
        from wco.db.connection import init_db

        db_ok = await init_db()
        app.state.db_connected = db_ok
    except Exception as exc:
        logger.warning("DB init failed (non-fatal): %s", exc)
        app.state.db_connected = False

    # Pre-build the agent mesh
    app.state.agents = [ARAgent(), APAgent(), InventoryAgent(), CashFlowAgent()]
    app.state.orchestrator = WorkingCapitalOrchestrator(app.state.agents)
    app.state.evaluator = RecommendationEvaluator()

    logger.info("WCO API started — %d agents ready", len(app.state.agents))


# ── Endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check — confirms the API and agents are operational."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        agents_ready=True,
        database_connected=app.state.db_connected,
    )


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    """Run the full working capital analysis pipeline.

    Executes all four domain agents (AR → AP → Inventory → CashFlow)
    through the orchestrator and returns the consolidated report.
    """
    t0 = time.perf_counter()
    logger.info("Starting full analysis — %d AR, %d AP, %d SKUs",
                len(request.ar_invoices), len(request.ap_invoices), len(request.skus))

    try:
        data = request.model_dump()
        report = await app.state.orchestrator.run(data)
        elapsed = (time.perf_counter() - t0) * 1000

        result = report.to_dict()
        result["total_duration_ms"] = round(elapsed, 2)
        result["status"] = "success"

        # Store recommendations to DB
        try:
            from wco.db.connection import RecommendationRow, store_recommendation
            import json

            for rec in report.recommendations:
                row = RecommendationRow(
                    agent_name=rec.get("agent", ""),
                    capability=rec.get("capability", ""),
                    problem_description=request.problem_description,
                    recommendation_text=rec.get("recommendation", ""),
                    expected_impact=rec.get("expected_impact", ""),
                    confidence=rec.get("confidence", "medium"),
                    ccc_at_time=report.cash_conversion_cycle.get("ccc", 0),
                    raw_result=json.dumps(rec),
                )
                await store_recommendation(row)
        except Exception as exc:
            logger.warning("Failed to store recommendations: %s", exc)

        return result

    except Exception as exc:
        logger.exception("Analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.post("/api/evaluate")
async def evaluate(request: EvaluateRequest) -> dict[str, Any]:
    """Evaluate a recommendation using LLM-as-a-Judge.

    Returns dimension scores (relevance, actionability, financial_impact,
    risk_awareness) and an overall weighted score.
    """
    logger.info("Evaluating recommendation from %s", request.agent_name)

    try:
        result = await app.state.evaluator.run_evaluation(
            recommendation=request.recommendation,
            context=request.context,
            agent_name=request.agent_name,
            recommendation_id=request.recommendation_id,
            store=True,
        )
        return result.to_dict()
    except Exception as exc:
        logger.exception("Evaluation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}") from exc


@app.get("/api/recommendations")
async def get_recommendations(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List past recommendations from the database."""
    try:
        from wco.db.connection import list_recommendations

        rows = await list_recommendations(limit=limit)
        return {"status": "ok", "count": len(rows), "recommendations": rows}
    except Exception as exc:
        logger.warning("Failed to list recommendations: %s", exc)
        return {"status": "ok", "count": 0, "recommendations": []}


@app.get("/api/evaluations")
async def get_evaluations(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List past evaluation results from the database."""
    try:
        from wco.db.connection import list_evaluations

        rows = await list_evaluations(limit=limit)
        return {"status": "ok", "count": len(rows), "evaluations": rows}
    except Exception as exc:
        logger.warning("Failed to list evaluations: %s", exc)
        return {"status": "ok", "count": 0, "evaluations": []}


# ── Run directly ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    from wco.config import get_settings

    settings = get_settings()
    uvicorn.run("wco.api.server:app", host="0.0.0.0", port=settings.port, reload=True)
