"""CockroachDB connection management and schema definitions.

Provides:
- ``get_cockroachdb_connection()`` — async context manager yielding a
  SQLAlchemy async session backed by CockroachDB.
- ``init_db()`` — create tables if they don't exist.
- Pydantic models mirroring the DB rows.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, Field

from wco.config import get_settings

logger = logging.getLogger(__name__)


# ── Pydantic models for DB rows ───────────────────────────────────────────


class RecommendationRow(BaseModel):
    """Represents a stored recommendation record.

    Attributes:
        id: Primary key (UUID hex).
        agent_name: Name of the producing agent.
        capability: Agent capability domain.
        problem_description: The original problem statement.
        recommendation_text: The full recommendation text.
        expected_impact: Expected financial impact.
        confidence: Agent confidence level.
        ccc_at_time: Cash Conversion Cycle when recommendation was made.
        raw_result: Full serialised TurnResult JSON.
        created_at: ISO-8601 timestamp.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    agent_name: str = ""
    capability: str = ""
    problem_description: str = ""
    recommendation_text: str = ""
    expected_impact: str = ""
    confidence: str = "medium"
    ccc_at_time: float = 0.0
    raw_result: str = "{}"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EvaluationRow(BaseModel):
    """Represents a stored evaluation record.

    Attributes:
        id: Primary key (UUID hex).
        recommendation_id: FK to the evaluated recommendation.
        agent_name: Agent that produced the recommendation.
        recommendation_text: Text that was evaluated.
        context_summary: Truncated context used for evaluation.
        scores: JSON string of EvalScore objects.
        overall_score: Weighted average score (1–10).
        created_at: ISO-8601 timestamp.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    recommendation_id: str | None = None
    agent_name: str = ""
    recommendation_text: str = ""
    context_summary: str = ""
    scores: str = "[]"
    overall_score: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class TraceRow(BaseModel):
    """Represents a stored trace span record.

    Attributes:
        id: Primary key (UUID hex).
        trace_id: Phoenix / OpenTelemetry trace ID.
        agent_name: Agent that produced the span.
        span_name: Operation name (expand / compress).
        attributes: JSON string of span attributes.
        duration_ms: Span duration.
        status: "ok" or "error".
        created_at: ISO-8601 timestamp.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str = ""
    agent_name: str = ""
    span_name: str = ""
    attributes: str = "{}"
    duration_ms: float = 0.0
    status: str = "ok"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── DDL ────────────────────────────────────────────────────────────────────

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS recommendations (
    id STRING PRIMARY KEY,
    agent_name STRING NOT NULL,
    capability STRING NOT NULL,
    problem_description STRING,
    recommendation_text STRING,
    expected_impact STRING,
    confidence STRING DEFAULT 'medium',
    ccc_at_time FLOAT8 DEFAULT 0,
    raw_result JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evaluations (
    id STRING PRIMARY KEY,
    recommendation_id STRING REFERENCES recommendations(id),
    agent_name STRING NOT NULL,
    recommendation_text STRING,
    context_summary STRING,
    scores JSONB DEFAULT '[]',
    overall_score FLOAT8 DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS traces (
    id STRING PRIMARY KEY,
    trace_id STRING NOT NULL,
    agent_name STRING NOT NULL,
    span_name STRING NOT NULL,
    attributes JSONB DEFAULT '{}',
    duration_ms FLOAT8 DEFAULT 0,
    status STRING DEFAULT 'ok',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_capability ON recommendations(capability);
CREATE INDEX IF NOT EXISTS idx_recommendations_created ON recommendations(created_at);
CREATE INDEX IF NOT EXISTS idx_evaluations_recommendation ON evaluations(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_overall ON evaluations(overall_score);
CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_agent ON traces(agent_name);
"""


# ── Connection management ─────────────────────────────────────────────────


@asynccontextmanager
async def get_cockroachdb_connection() -> AsyncGenerator[Any, None]:
    """Yield an async database connection to CockroachDB.

    This is a lightweight context manager that wraps ``asyncpg`` directly
    (avoids heavy SQLAlchemy async engine overhead for simple queries).

    Usage::

        async with get_cockroachdb_connection() as conn:
            rows = await conn.fetch("SELECT * FROM recommendations")

    Yields:
        An ``asyncpg.Connection`` instance.

    Raises:
        RuntimeError: If CockroachDB connection string is not configured.
    """
    settings = get_settings()

    try:
        import asyncpg
    except ImportError:
        logger.warning("asyncpg not installed — CockroachDB operations unavailable")
        raise

    conn_str = settings.cockroachdb_connection_string
    conn = None
    try:
        conn = await asyncpg.connect(conn_str)
        yield conn
    finally:
        if conn is not None:
            await conn.close()


async def init_db() -> bool:
    """Create database tables if they don't exist.

    Returns:
        ``True`` if tables were created successfully, ``False`` on error.
    """
    settings = get_settings()
    if not settings.cockroachdb_password:
        logger.info("No CockroachDB password set — skipping DB initialisation")
        return False

    try:
        async with get_cockroachdb_connection() as conn:
            await conn.execute(_CREATE_TABLES_SQL)
            logger.info("CockroachDB tables initialised successfully")
            return True
    except Exception as exc:
        logger.warning("CockroachDB init failed (non-fatal): %s", exc)
        return False


async def store_recommendation(row: RecommendationRow) -> str | None:
    """Insert a recommendation record and return its ID.

    Returns ``None`` if the database is not available.
    """
    try:
        async with get_cockroachdb_connection() as conn:
            await conn.execute(
                """
                INSERT INTO recommendations (
                    id, agent_name, capability, problem_description,
                    recommendation_text, expected_impact, confidence,
                    ccc_at_time, raw_result, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO NOTHING
                """,
                row.id,
                row.agent_name,
                row.capability,
                row.problem_description,
                row.recommendation_text,
                row.expected_impact,
                row.confidence,
                row.ccc_at_time,
                row.raw_result,
                row.created_at,
            )
            return row.id
    except Exception as exc:
        logger.warning("Failed to store recommendation: %s", exc)
        return None


async def list_recommendations(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent recommendations from the database.

    Args:
        limit: Maximum number of records to return.

    Returns:
        List of dicts (empty if DB is unavailable).
    """
    try:
        async with get_cockroachdb_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, agent_name, capability, problem_description,
                       recommendation_text, expected_impact, confidence,
                       ccc_at_time, created_at
                FROM recommendations
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("Failed to list recommendations: %s", exc)
        return []


async def list_evaluations(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent evaluations from the database.

    Args:
        limit: Maximum number of records to return.

    Returns:
        List of dicts (empty if DB is unavailable).
    """
    try:
        async with get_cockroachdb_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, recommendation_id, agent_name, recommendation_text,
                       context_summary, scores, overall_score, created_at
                FROM evaluations
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("Failed to list evaluations: %s", exc)
        return []
