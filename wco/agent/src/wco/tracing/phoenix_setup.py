"""Arize Phoenix tracing setup for the WCO agent mesh.

Provides:
- ``setup_phoenix()`` — configure OpenInference instrumentation and
  return a ``TracerProvider``.
- ``log_traces_to_phoenix()`` — push stored trace spans to Phoenix Cloud
  via its REST API.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as OtelTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

logger = logging.getLogger(__name__)


def setup_phoenix() -> OtelTracerProvider:
    """Configure OpenInference instrumentation for Google Genai + Langchain.

    Creates a ``TracerProvider`` wired to Phoenix Cloud (if an API key is
    present) or local Phoenix (if running).  Falls back gracefully to a
    no-op provider when neither is available.

    Returns:
        The configured ``opentelemetry.sdk.trace.TracerProvider``.
    """
    from wco.config import get_settings

    settings = get_settings()

    # ── Build resource ───────────────────────────────────────────────────
    resource = Resource.create(
        {
            "service.name": "wco-agent",
            "service.version": "0.1.0",
            "deployment.environment": "production",
            "wco.project": settings.phoenix_project_name,
        }
    )

    provider = OtelTracerProvider(resource=resource)

    # ── Try Phoenix Cloud export ─────────────────────────────────────────
    if settings.phoenix_available:
        try:
            _setup_phoenix_cloud(provider, settings)
            logger.info("Phoenix Cloud instrumentation configured (project=%s)", settings.phoenix_project_name)
        except Exception as exc:
            logger.warning("Phoenix Cloud setup failed — tracing will be local only: %s", exc)
    else:
        logger.info(
            "No PHOENIX_API_KEY set — traces will be available locally only. "
            "Set PHOENIX_API_KEY to enable cloud observability."
        )

    # ── Instrument Google Genai ──────────────────────────────────────────
    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        GoogleGenAIInstrumentor().instrument(tracer_provider=provider)
        logger.info("Google GenAI instrumentation enabled")
    except Exception as exc:
        logger.warning("Failed to instrument Google GenAI: %s", exc)

    # ── Instrument Langchain ─────────────────────────────────────────────
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)
        logger.info("LangChain instrumentation enabled")
    except Exception as exc:
        logger.warning("Failed to instrument LangChain: %s", exc)

    # ── Set as global provider ───────────────────────────────────────────
    trace.set_tracer_provider(provider)
    return provider


def _setup_phoenix_cloud(
    provider: OtelTracerProvider,
    settings: Any,
) -> None:
    """Wire the provider to Phoenix Cloud via OTLP/HTTP.

    Uses the Phoenix REST API endpoint for trace ingestion.
    """
    try:
        from phoenix.trace import OpenInferenceSpanExporter  # type: ignore[import-untyped]

        # Build the Phoenix Cloud endpoint
        headers = {
            "Authorization": f"Bearer {settings.phoenix_api_key}",
            "Content-Type": "application/json",
        }

        exporter = OpenInferenceSpanExporter(
            endpoint=f"{settings.phoenix_base_url}/v1/traces",
            headers=headers,
        )

        provider.add_span_processor(SimpleSpanProcessor(exporter))
    except ImportError:
        logger.info("phoenix package not installed — skipping cloud export")
    except Exception as exc:
        raise RuntimeError(f"Cannot configure Phoenix Cloud exporter: {exc}") from exc


# ── Trace store for manual logging ────────────────────────────────────────

_trace_store: list[dict[str, Any]] = []
_trace_store_lock = __import__("threading").Lock()


def store_trace(
    agent_name: str,
    trace_id: str,
    span_name: str,
    attributes: dict[str, Any],
    duration_ms: float,
    status: str = "ok",
) -> None:
    """Store a trace span for later export to Phoenix.

    This is a lightweight alternative to full OTLP instrumentation,
    useful when the SDK instrumentation is unavailable.

    Args:
        agent_name: Name of the agent that produced the span.
        trace_id: Unique trace identifier.
        span_name: Name of the operation (e.g. "expand", "compress").
        attributes: Key-value attributes for the span.
        duration_ms: Span duration in milliseconds.
        status: "ok" or "error".
    """
    entry = {
        "trace_id": trace_id,
        "span_id": uuid.uuid4().hex[:16],
        "agent_name": agent_name,
        "span_name": span_name,
        "attributes": attributes,
        "start_time": time.time(),
        "duration_ms": duration_ms,
        "status": status,
        "project_name": "wco-agent",
    }
    with _trace_store_lock:
        _trace_store.append(entry)


async def log_traces_to_phoenix() -> dict[str, Any]:
    """Push all stored traces to Phoenix Cloud via its REST API.

    Returns:
        Dict with ``success``, ``count``, and optional ``error``.
    """
    from wco.config import get_settings

    settings = get_settings()

    if not settings.phoenix_available:
        return {"success": False, "count": 0, "error": "No PHOENIX_API_KEY configured"}

    with _trace_store_lock:
        traces = list(_trace_store)
        _trace_store.clear()

    if not traces:
        return {"success": True, "count": 0}

    url = f"{settings.phoenix_base_url}/v1/traces"
    headers = {
        "Authorization": f"Bearer {settings.phoenix_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "project_name": settings.phoenix_project_name,
        "spans": traces,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info("Logged %d traces to Phoenix Cloud", len(traces))
            return {"success": True, "count": len(traces)}
    except httpx.HTTPStatusError as exc:
        logger.error("Phoenix trace export failed: %s — %s", exc, exc.response.text)
        return {"success": False, "count": len(traces), "error": str(exc)}
    except Exception as exc:
        logger.error("Phoenix trace export failed: %s", exc)
        return {"success": False, "count": len(traces), "error": str(exc)}


def get_stored_traces() -> list[dict[str, Any]]:
    """Return a copy of all currently stored trace spans (for debugging)."""
    with _trace_store_lock:
        return list(_trace_store)
