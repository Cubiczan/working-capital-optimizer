"""LLM-as-a-Judge evaluation for WCO agent recommendations.

Uses Gemini to score recommendations on four dimensions:
- **Relevance** (1–10) — Does the recommendation address the stated problem?
- **Actionability** (1–10) — Can a CFO actually execute this?
- **Financial Impact** (1–10) — Is there a clear, quantified financial benefit?
- **Risk Awareness** (1–10) — Does it acknowledge risks and trade-offs?

Evaluation results are persisted to CockroachDB (when available) and
returned as a structured ``EvalResult``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from google import genai  # type: ignore[import-untyped]
from google.genai import types  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from wco.config import get_settings

logger = logging.getLogger(__name__)


# ── Data models ───────────────────────────────────────────────────────────


class EvalScore(BaseModel):
    """A single evaluation dimension score.

    Attributes:
        dimension: Name of the dimension (relevance, actionability, …).
        score: Integer score 1–10.
        justification: LLM's explanation for the score.
    """

    dimension: str
    score: int = Field(ge=1, le=10)
    justification: str


class EvalResult(BaseModel):
    """Complete evaluation result for one recommendation.

    Attributes:
        id: Unique evaluation identifier.
        recommendation_id: ID of the evaluated recommendation (if available).
        agent_name: Name of the agent that produced the recommendation.
        recommendation_text: The full recommendation text.
        context_summary: Summary of the context provided.
        scores: List of dimension scores.
        overall_score: Weighted average of dimension scores.
        created_at: ISO-8601 timestamp.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    recommendation_id: str | None = None
    agent_name: str = ""
    recommendation_text: str = ""
    context_summary: str = ""
    scores: list[EvalScore] = Field(default_factory=list)
    overall_score: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return self.model_dump()


# ── Evaluator ─────────────────────────────────────────────────────────────


# Weights for each dimension in the overall score
_DIMENSION_WEIGHTS: dict[str, float] = {
    "relevance": 0.25,
    "actionability": 0.30,
    "financial_impact": 0.25,
    "risk_awareness": 0.20,
}

_JUDGE_SYSTEM_PROMPT = """\
You are an expert financial evaluator acting as an impartial judge. \
Your job is to score AI-generated recommendations for a manufacturing \
CFO's working capital optimization.

For each dimension, provide:
1. A score from 1 to 10 (integer only)
2. A brief justification (1–2 sentences)

Scoring rubric:

**Relevance (1–10)**
- 9–10: Directly and precisely addresses the stated problem with deep domain understanding.
- 7–8: Addresses the problem with minor gaps in specificity.
- 4–6: Partially relevant; some connection to the problem but misses key aspects.
- 1–3: Mostly irrelevant or tangential.

**Actionability (1–10)**
- 9–10: Crystal-clear steps that a CFO could implement tomorrow.
- 7–8: Actionable with minor ambiguity in execution details.
- 4–6: Vague or requires significant additional planning.
- 1–3: Abstract or impossible to execute.

**Financial Impact (1–10)**
- 9–10: Quantified dollar impact with sound methodology.
- 7–8: Reasonable estimate with clear assumptions.
- 4–6: Directional impact mentioned but not quantified.
- 1–3: No financial impact discussion.

**Risk Awareness (1–10)**
- 9–10: Thorough risk analysis with mitigation strategies.
- 7–8: Acknowledges key risks with partial mitigation.
- 4–6: Mentions risks superficially.
- 1–3: No risk discussion.

Respond ONLY with valid JSON in this format:
```json
{{
  "scores": [
    {{
      "dimension": "relevance",
      "score": <int>,
      "justification": "<explanation>"
    }},
    {{
      "dimension": "actionability",
      "score": <int>,
      "justification": "<explanation>"
    }},
    {{
      "dimension": "financial_impact",
      "score": <int>,
      "justification": "<explanation>"
    }},
    {{
      "dimension": "risk_awareness",
      "score": <int>,
      "justification": "<explanation>"
    }}
  ]
}}
```"""


class RecommendationEvaluator:
    """LLM-as-a-Judge evaluator for WCO agent recommendations.

    Uses Gemini to score recommendations on four quality dimensions
    and optionally persists results to CockroachDB.

    Parameters:
        model_id: Gemini model to use for judging (default: ``gemini-2.5-flash``).
    """

    def __init__(self, model_id: str = "gemini-2.5-flash") -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model_id = model_id

    # ── Public API ───────────────────────────────────────────────────────

    async def run_evaluation(
        self,
        recommendation: str,
        context: str,
        *,
        agent_name: str = "",
        recommendation_id: str | None = None,
        store: bool = True,
    ) -> EvalResult:
        """Evaluate a single recommendation.

        Args:
            recommendation: The recommendation text to evaluate.
            context: The context / problem description the recommendation
                was generated for.
            agent_name: Name of the producing agent (for storage).
            recommendation_id: Optional ID linking to the source
                recommendation record.
            store: Whether to persist the result to CockroachDB.

        Returns:
            An ``EvalResult`` with dimension scores and overall score.
        """
        prompt = self._build_judge_prompt(recommendation, context)
        response = await self._call_judge(prompt)
        raw = response.text if response.text else ""

        scores = self._parse_scores(raw)
        overall = self._compute_overall(scores)

        result = EvalResult(
            recommendation_id=recommendation_id,
            agent_name=agent_name,
            recommendation_text=recommendation,
            context_summary=context[:1000],
            scores=scores,
            overall_score=round(overall, 2),
        )

        logger.info(
            "Evaluation complete: overall=%.1f/10 (%s)",
            overall,
            ", ".join(f"{s.dimension}={s.score}" for s in scores),
        )

        # Persist to DB if configured
        if store:
            try:
                await self._store_result(result)
            except Exception as exc:
                logger.warning("Failed to store evaluation result: %s", exc)

        return result

    async def run_batch_evaluation(
        self,
        recommendations: list[dict[str, str]],
        context: str,
    ) -> list[EvalResult]:
        """Evaluate multiple recommendations in sequence.

        Args:
            recommendations: List of dicts with ``text`` and optionally
                ``agent_name`` and ``id`` keys.
            context: Shared context / problem description.

        Returns:
            List of ``EvalResult`` in the same order.
        """
        results: list[EvalResult] = []
        for rec in recommendations:
            result = await self.run_evaluation(
                recommendation=rec["text"],
                context=context,
                agent_name=rec.get("agent_name", ""),
                recommendation_id=rec.get("id"),
                store=False,  # Store after batch
            )
            results.append(result)

        # Batch store
        try:
            for r in results:
                await self._store_result(r)
        except Exception as exc:
            logger.warning("Failed to batch-store evaluation results: %s", exc)

        return results

    # ── Internals ────────────────────────────────────────────────────────

    async def _call_judge(self, prompt: str) -> types.GenerateContentResponse:
        """Send the evaluation prompt to Gemini."""
        return await self._client.aio.models.generate_content(
            model=self._model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_JUDGE_SYSTEM_PROMPT,
                temperature=0.1,  # Low temperature for consistent judging
                max_output_tokens=2048,
            ),
        )

    @staticmethod
    def _build_judge_prompt(recommendation: str, context: str) -> str:
        """Construct the evaluation prompt."""
        return f"""## Context / Problem Description
{context[:3000]}

## Recommendation to Evaluate
{recommendation[:2000]}

Evaluate this recommendation on all four dimensions. Be rigorous and fair."""

    @staticmethod
    def _parse_scores(raw: str) -> list[EvalScore]:
        """Parse the JSON scores from the judge response."""
        import json
        import re

        try:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
            json_str = match.group(1).strip() if match else raw
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start != -1 and end != -1:
                json_str = json_str[start : end + 1]
            data = json.loads(json_str)
            return [
                EvalScore(
                    dimension=s["dimension"],
                    score=max(1, min(10, int(s["score"]))),
                    justification=s.get("justification", ""),
                )
                for s in data.get("scores", [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse judge scores: %s — raw: %s", exc, raw[:200])
            return []

    @staticmethod
    def _compute_overall(scores: list[EvalScore]) -> float:
        """Compute the weighted overall score."""
        if not scores:
            return 0.0
        total_weight = 0.0
        weighted_sum = 0.0
        for s in scores:
            w = _DIMENSION_WEIGHTS.get(s.dimension, 0.25)
            weighted_sum += s.score * w
            total_weight += w
        return weighted_sum / total_weight if total_weight else 0.0

    @staticmethod
    async def _store_result(result: EvalResult) -> None:
        """Persist evaluation result to CockroachDB.

        Silently ignores errors if the database is not available.
        """
        try:
            from wco.db.connection import get_cockroachdb_connection

            async with get_cockroachdb_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO evaluations (
                        id, recommendation_id, agent_name, recommendation_text,
                        context_summary, scores, overall_score, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (id) DO UPDATE SET
                        overall_score = EXCLUDED.overall_score,
                        scores = EXCLUDED.scores
                    """,
                    result.id,
                    result.recommendation_id,
                    result.agent_name,
                    result.recommendation_text,
                    result.context_summary,
                    result.model_dump_json(include={"scores"}),
                    result.overall_score,
                    result.created_at,
                )
                logger.info("Evaluation result %s stored to CockroachDB", result.id)
        except Exception:
            # DB is optional — do not fail the evaluation
            pass
