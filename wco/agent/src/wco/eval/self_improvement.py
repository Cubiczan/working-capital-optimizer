"""Self-improvement loop for WCO agent recommendations.

Reads evaluation history from CockroachDB, identifies systematic weaknesses
in agent recommendations, and generates targeted prompt amendments that
are applied on subsequent analysis runs.

The loop operates on a threshold basis:
- Prompt amendments are generated only when the rolling average score
  for a dimension drops below 6.0/10.
- Amendments are capped at one per agent per session to prevent
  feedback instability.
- Each amendment is recorded with the triggering evaluation context
  for full traceability.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from google import genai  # type: ignore[import-untyped]
from google.genai import types  # type: ignore[import-untyped]

from wco.config import get_settings

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────────

SCORE_THRESHOLD = 6.0  # Generate amendments when avg drops below this
MIN_EVALS_FOR_ANALYSIS = 3  # Need at least this many evals before amending
MAX_AMENDMENTS_PER_AGENT = 1  # Cap per agent per session

# ── Data models ─────────────────────────────────────────────────────────


@dataclass
class WeaknessPattern:
    """Identifies a systematic weakness in agent recommendations."""

    agent_name: str
    dimension: str
    avg_score: float
    eval_count: int
    top_issues: list[str] = field(default_factory=list)
    suggested_amendment: str = ""
    amendment_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class SelfImprovementReport:
    """Summary of one self-improvement cycle."""

    report_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    patterns_found: list[WeaknessPattern] = field(default_factory=list)
    amendments_applied: dict[str, str] = field(default_factory=dict)  # agent -> amendment
    amendments_skipped: list[str] = field(default_factory=list)


# ── Amendment templates ──────────────────────────────────────────────────

_DIMENSION_AMENDMENT_TEMPLATES: dict[str, str] = {
    "relevance": (
        "CRITICAL ADDENDUM — Relevance Improvement:\n"
        "Your recent recommendations have scored below the relevance threshold. "
        "You MUST directly reference specific data points from the provided context "
        "in every recommendation. Do not give generic advice — ground each insight "
        "in a specific invoice, vendor, SKU, or financial metric from the data. "
        "If you cannot find a specific data point to support your recommendation, "
        "explicitly state the data gap."
    ),
    "actionability": (
        "CRITICAL ADDENDUM — Actionability Improvement:\n"
        "Your recent recommendations have scored below the actionability threshold. "
        "Every recommendation MUST include:\n"
        "1. A specific person/team responsible for execution\n"
        "2. A concrete deadline or timeframe\n"
        "3. The exact steps needed to implement\n"
        "4. Any dependencies or prerequisites\n"
        "Avoid vague language like 'consider', 'explore', 'evaluate'. "
        "Use imperative verbs: 'Extend', 'Reduce', 'Implement', 'Negotiate'."
    ),
    "financial_impact": (
        "CRITICAL ADDENDUM — Financial Impact Improvement:\n"
        "Your recent recommendations have scored below the financial impact threshold. "
        "Every recommendation MUST include:\n"
        "1. A specific dollar amount (e.g., '$45,200 annual savings')\n"
        "2. The calculation methodology (e.g., '2% discount × $195K invoice')\n"
        "3. A timeframe for impact realization\n"
        "4. Confidence interval if applicable (e.g., 'conservative estimate')\n"
        "Do not use relative terms like 'significant savings' without a number."
    ),
    "risk_awareness": (
        "CRITICAL ADDENDUM — Risk Awareness Improvement:\n"
        "Your recent recommendations have scored below the risk awareness threshold. "
        "Every recommendation MUST acknowledge:\n"
        "1. At least one risk or downside of the proposed action\n"
        "2. A mitigation strategy for the identified risk\n"
        "3. Any assumptions that, if wrong, would invalidate the recommendation\n"
        "4. Potential unintended consequences\n"
        "Show that you understand trade-offs, not just benefits."
    ),
}


# ── Self-Improvement Engine ──────────────────────────────────────────────


class SelfImprovementEngine:
    """Analyzes evaluation history and generates prompt amendments.

    The engine reads past evaluation results from CockroachDB, groups
    them by agent and dimension, computes rolling averages, and identifies
    dimensions where the agent consistently underperforms.

    Parameters:
        model_id: Gemini model for amendment generation (default: gemini-2.5-flash).
    """

    def __init__(self, model_id: str = "gemini-2.5-flash") -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model_id = model_id
        self._applied_amendments: dict[str, int] = {}  # agent -> count

    async def run_improvement_cycle(self) -> SelfImprovementReport:
        """Execute one full self-improvement cycle.

        Returns:
            A ``SelfImprovementReport`` with identified weaknesses
            and any amendments generated.
        """
        report = SelfImprovementReport()

        try:
            evals = await self._fetch_recent_evals()
        except Exception as exc:
            logger.warning("Cannot fetch evaluations for self-improvement: %s", exc)
            return report

        if len(evals) < MIN_EVALS_FOR_ANALYSIS:
            logger.info(
                "Skipping self-improvement — only %d evals (need %d)",
                len(evals), MIN_EVALS_FOR_ANALYSIS,
            )
            return report

        # ── Identify weaknesses ─────────────────────────────────────────
        patterns = self._identify_weaknesses(evals)
        report.patterns_found = patterns

        # ── Generate amendments for each weakness ──────────────────────
        for pattern in patterns:
            agent = pattern.agent_name

            # Check cap
            if self._applied_amendments.get(agent, 0) >= MAX_AMENDMENTS_PER_AGENT:
                report.amendments_skipped.append(agent)
                logger.info("Skipping amendment for %s — cap reached", agent)
                continue

            # Generate or use template amendment
            amendment = await self._generate_amendment(pattern)
            pattern.suggested_amendment = amendment
            report.amendments_applied[agent] = amendment
            self._applied_amendments[agent] = self._applied_amendments.get(agent, 0) + 1

            logger.info(
                "Amendment generated for %s — dimension: %s (avg: %.1f)",
                agent, pattern.dimension, pattern.avg_score,
            )

        # ── Persist report ─────────────────────────────────────────────
        try:
            await self._store_report(report)
        except Exception as exc:
            logger.warning("Failed to store improvement report: %s", exc)

        return report

    # ── Internal methods ──────────────────────────────────────────────

    async def _fetch_recent_evals(self) -> list[dict[str, Any]]:
        """Fetch recent evaluation results from CockroachDB."""
        from wco.db.connection import get_cockroachdb_connection

        async with get_cockroachdb_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, agent_name, recommendation_text, scores, overall_score, created_at
                FROM evaluations
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
            return [dict(r) for r in rows]

    @staticmethod
    def _identify_weaknesses(evals: list[dict[str, Any]]) -> list[WeaknessPattern]:
        """Group evals by agent + dimension, find dimensions below threshold."""
        import json

        # Group: agent -> dimension -> scores
        agent_dim_scores: dict[str, dict[str, list[float]]] = {}
        agent_dim_issues: dict[str, dict[str, list[str]]] = {}

        for ev in evals:
            agent = ev.get("agent_name", "unknown")
            scores_raw = ev.get("scores", "[]")

            try:
                scores = json.loads(scores_raw) if isinstance(scores_raw, str) else scores_raw
            except (json.JSONDecodeError, TypeError):
                continue

            if agent not in agent_dim_scores:
                agent_dim_scores[agent] = {}
                agent_dim_issues[agent] = {}

            for s in scores:
                dim = s.get("dimension", "")
                score = s.get("score", 0)
                justification = s.get("justification", "")

                agent_dim_scores[agent].setdefault(dim, []).append(float(score))
                agent_dim_issues[agent].setdefault(dim, []).append(justification)

        # Find weaknesses
        patterns: list[WeaknessPattern] = []
        for agent, dims in agent_dim_scores.items():
            for dim, scores in dims.items():
                avg = sum(scores) / len(scores)
                if avg < SCORE_THRESHOLD and len(scores) >= MIN_EVALS_FOR_ANALYSIS:
                    issues = agent_dim_issues.get(agent, {}).get(dim, [])
                    # Extract top 3 most common issue keywords
                    top_issues = list(set(issues))[:3]

                    patterns.append(
                        WeaknessPattern(
                            agent_name=agent,
                            dimension=dim,
                            avg_score=round(avg, 2),
                            eval_count=len(scores),
                            top_issues=top_issues,
                        )
                    )

        # Sort by severity (lowest scores first)
        patterns.sort(key=lambda p: p.avg_score)
        return patterns

    async def _generate_amendment(self, pattern: WeaknessPattern) -> str:
        """Generate a prompt amendment for the identified weakness.

        Uses a template if available, otherwise asks Gemini to create one.
        """
        # Check for template
        template = _DIMENSION_AMENDMENT_TEMPLATES.get(pattern.dimension)
        if template:
            return template

        # Fallback: ask Gemini
        prompt = f"""You are improving an AI agent that gives financial recommendations.
The agent "{pattern.agent_name}" has been scoring poorly on the "{pattern.dimension}" dimension.
Average score: {pattern.avg_score}/10 over {pattern.eval_count} evaluations.

Recent issues from judge justifications:
{chr(10).join(f'- {issue}' for issue in pattern.top_issues)}

Write a concise addendum (3-5 sentences) to append to the agent's system prompt that
would fix this weakness. Be specific and actionable. Do NOT repeat the original prompt.
Respond ONLY with the addendum text, nothing else."""

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=512,
                ),
            )
            return response.text if response.text else template or ""
        except Exception as exc:
            logger.warning("Failed to generate amendment via Gemini: %s", exc)
            return f"Improve your {pattern.dimension} — recent average score is {pattern.avg_score}/10."

    @staticmethod
    async def _store_report(report: SelfImprovementReport) -> None:
        """Persist the self-improvement report to CockroachDB."""
        from wco.db.connection import get_cockroachdb_connection

        import json

        async with get_cockroachdb_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS self_improvement_reports (
                    id STRING PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    patterns_found JSONB DEFAULT '[]',
                    amendments_applied JSONB DEFAULT '{}',
                    amendments_skipped JSONB DEFAULT '[]'
                )
                """,
            )
            await conn.execute(
                """
                INSERT INTO self_improvement_reports (id, timestamp, patterns_found, amendments_applied, amendments_skipped)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO NOTHING
                """,
                report.report_id,
                report.timestamp,
                json.dumps([{"agent": p.agent_name, "dimension": p.dimension, "avg_score": p.avg_score} for p in report.patterns_found]),
                json.dumps(report.amendments_applied),
                json.dumps(report.amendments_skipped),
            )
            logger.info("Self-improvement report %s stored", report.report_id)

    # ── Public helper: apply amendments to system prompts ──────────────

    @staticmethod
    def apply_amendment(system_prompt: str, amendment: str) -> str:
        """Append a self-improvement amendment to an agent's system prompt.

        Args:
            system_prompt: The original system prompt.
            amendment: The amendment text to append.

        Returns:
            The augmented system prompt.
        """
        return f"{system_prompt}\n\n{amendment}"

    def get_applied_amendments(self) -> dict[str, int]:
        """Return a snapshot of amendment counts per agent."""
        return dict(self._applied_amendments)

    def reset(self) -> None:
        """Reset amendment counts (for new sessions)."""
        self._applied_amendments.clear()
