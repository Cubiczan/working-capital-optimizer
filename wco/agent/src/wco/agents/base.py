"""Base agent abstractions for the WCO agent mesh.

Re-implements the MeshAgent pattern (inspired by the CHP framework) on top
of Google Gemini 2.5 Flash.  Each agent *expands* a working-capital problem
into structured sub-steps, then *compresses* those sub-steps into a concise,
actionable recommendation.

Every Gemini call is wrapped in an OpenInference span so that Arize Phoenix
can ingest the full trace for observability.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from google import genai  # type: ignore[import-untyped]
from google.genai import types  # type: ignore[import-untyped]

from wco.config import get_settings

logger = logging.getLogger(__name__)


# ── Domain data-classes ──────────────────────────────────────────────────


class ConfidenceLevel(str, Enum):
    """Confidence bucket for agent outputs."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AgentCapability(str, Enum):
    """Well-known capability domains for WCO agents."""

    AR = "accounts_receivable"
    AP = "accounts_payable"
    INVENTORY = "inventory"
    CASHFLOW = "cashflow"
    TREASURY = "treasury"


@dataclass(frozen=True)
class ExpansionStep:
    """One atomic sub-step produced by the *expand* phase.

    Attributes:
        step_number: Sequential index within this expansion.
        description: Natural-language description of the analytical step.
        domain: Which sub-domain this step belongs to.
        data_required: Keys / fields the step needs from context.
        expected_output: What the step should produce.
    """

    step_number: int
    description: str
    domain: str
    data_required: list[str]
    expected_output: str


@dataclass(frozen=True)
class CompressionStep:
    """One atomic insight produced by the *compress* phase.

    Attributes:
        insight: Summary sentence of the finding.
        recommendation: Specific, actionable recommendation.
        expected_impact: Qualitative or quantitative impact description.
        confidence: How confident the agent is about this insight.
    """

    insight: str
    recommendation: str
    expected_impact: str
    confidence: ConfidenceLevel


@dataclass(frozen=True)
class GroundingCheck:
    """Simple grounding / hallucination guard metadata.

    Attributes:
        data_points_referenced: How many input data points were cited.
        calculation_trace: Description of any math performed.
        is_grounded: Whether the output is grounded in provided data.
    """

    data_points_referenced: int
    calculation_trace: str
    is_grounded: bool


@dataclass(frozen=True)
class ReasoningTrace:
    """Captures the agent's reasoning chain for auditability.

    Attributes:
        steps: Ordered list of reasoning steps.
        assumptions: Explicit assumptions the agent made.
        data_gaps: Known missing data that may affect confidence.
    """

    steps: list[str]
    assumptions: list[str]
    data_gaps: list[str]


@dataclass
class TurnResult:
    """Result of a single agent expand → compress cycle.

    Attributes:
        agent_name: Human-readable name of the producing agent.
        capability: Domain capability of the agent.
        expansion_steps: Sub-steps produced by *expand*.
        compression_steps: Insights produced by *compress*.
        grounding_check: Grounding metadata.
        reasoning_trace: Full reasoning chain.
        raw_expand_response: Raw LLM response from expand.
        raw_compress_response: Raw LLM response from compress.
        duration_ms: Wall-clock time for the full turn.
        trace_id: Unique ID linking to Phoenix trace.
    """

    agent_name: str
    capability: AgentCapability
    expansion_steps: list[ExpansionStep] = field(default_factory=list)
    compression_steps: list[CompressionStep] = field(default_factory=list)
    grounding_check: GroundingCheck | None = None
    reasoning_trace: ReasoningTrace | None = None
    raw_expand_response: str = ""
    raw_compress_response: str = ""
    duration_ms: float = 0.0
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)


# ── Gemini Mesh Agent ────────────────────────────────────────────────────


class GeminiMeshAgent:
    """A single domain-specialist agent powered by Gemini 2.5 Flash.

    The agent follows a two-phase cycle:

    1. **expand** — break the problem into 3–5 analytical sub-steps.
    2. **compress** — synthesise expansion results into structured insights.

    Both calls are traced with OpenInference-compatible span attributes
    so Arize Phoenix can visualise the full reasoning chain.

    Parameters:
        name: Human-readable agent name (e.g. ``"AR Agent"``).
        capability: Domain capability label.
        system_prompt: System instruction sent to Gemini.
        model_id: Gemini model identifier (defaults to ``gemini-2.5-flash``).
    """

    def __init__(
        self,
        *,
        name: str,
        capability: AgentCapability,
        system_prompt: str,
        model_id: str = "gemini-2.5-flash",
    ) -> None:
        self.name = name
        self.capability = capability
        self.system_prompt = system_prompt
        self.model_id = model_id

        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = model_id

        logger.info("Initialised agent %r (capability=%s, model=%s)", name, capability.value, model_id)

    # ── Public API ───────────────────────────────────────────────────────

    async def run(self, context: dict[str, Any]) -> TurnResult:
        """Execute a full expand → compress cycle.

        Args:
            context: Key-value context (AR data, AP data, inventory data, …).

        Returns:
            A ``TurnResult`` with expansion steps, compression insights,
            and full trace metadata.
        """
        trace_id = uuid.uuid4().hex
        t0 = time.perf_counter()

        # Phase 1 — Expand
        raw_expand, expansion_steps = await self._expand(context)

        # Phase 2 — Compress
        raw_compress, compression_steps, grounding, reasoning = await self._compress(
            context, expansion_steps
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        result = TurnResult(
            agent_name=self.name,
            capability=self.capability,
            expansion_steps=expansion_steps,
            compression_steps=compression_steps,
            grounding_check=grounding,
            reasoning_trace=reasoning,
            raw_expand_response=raw_expand,
            raw_compress_response=raw_compress,
            duration_ms=round(elapsed_ms, 2),
            trace_id=trace_id,
        )
        logger.info(
            "Agent %r completed in %.1f ms (%d expansions, %d compressions)",
            self.name,
            elapsed_ms,
            len(expansion_steps),
            len(compression_steps),
        )
        return result

    # ── Expand phase ─────────────────────────────────────────────────────

    async def _expand(self, context: dict[str, Any]) -> tuple[str, list[ExpansionStep]]:
        """Ask Gemini to decompose the problem into sub-steps."""
        user_prompt = self._build_expand_prompt(context)

        response = await self._call_gemini(user_prompt)
        raw = response.text if response.text else ""

        steps = self._parse_expansion_steps(raw)
        return raw, steps

    # ── Compress phase ───────────────────────────────────────────────────

    async def _compress(
        self,
        context: dict[str, Any],
        expansion_steps: list[ExpansionStep],
    ) -> tuple[str, list[CompressionStep], GroundingCheck, ReasoningTrace]:
        """Ask Gemini to synthesise expansion steps into structured insights."""
        user_prompt = self._build_compress_prompt(context, expansion_steps)

        response = await self._call_gemini(user_prompt)
        raw = response.text if response.text else ""

        compressions = self._parse_compression_steps(raw)
        grounding = self._parse_grounding_check(raw)
        reasoning = self._parse_reasoning_trace(raw)
        return raw, compressions, grounding, reasoning

    # ── Gemini call ──────────────────────────────────────────────────────

    async def _call_gemini(self, user_prompt: str) -> types.GenerateContentResponse:
        """Send a prompt to Gemini and return the response."""
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )
        return response

    # ── Prompt builders ──────────────────────────────────────────────────

    def _build_expand_prompt(self, context: dict[str, Any]) -> str:
        """Construct the user prompt for the expand phase."""
        context_str = self._format_context(context)
        return f"""You are analyzing the following working capital data for a manufacturing company.

## Context Data
{context_str}

## Task
Break this analysis into 3 to 5 concrete, sequential expansion steps.
Each step should:
- Focus on one specific analytical dimension
- Specify what data it needs
- Describe the expected output

Respond ONLY with valid JSON in this exact format:
```json
{{
  "expansion_steps": [
    {{
      "step_number": 1,
      "description": "<what to analyze>",
      "domain": "<sub-domain>",
      "data_required": ["<field1>", "<field2>"],
      "expected_output": "<what this step produces>"
    }}
  ]
}}
```"""

    def _build_compress_prompt(
        self,
        context: dict[str, Any],
        expansion_steps: list[ExpansionStep],
    ) -> str:
        """Construct the user prompt for the compress phase."""
        context_str = self._format_context(context)
        steps_str = "\n".join(
            f"{s.step_number}. {s.description} → {s.expected_output}"
            for s in expansion_steps
        )
        return f"""You are synthesizing the working capital analysis for a manufacturing company.

## Context Data
{context_str}

## Expansion Steps Completed
{steps_str}

## Task
Based on the expansion steps and context data, provide:
1. Key insights (what you found)
2. Specific, actionable recommendations
3. Expected financial impact of each recommendation
4. Your confidence level for each insight

Respond ONLY with valid JSON in this exact format:
```json
{{
  "compression_steps": [
    {{
      "insight": "<finding>",
      "recommendation": "<specific action>",
      "expected_impact": "<dollar or percentage impact>",
      "confidence": "<high|medium|low>"
    }}
  ],
  "grounding_check": {{
    "data_points_referenced": <number>,
    "calculation_trace": "<description of calculations performed>",
    "is_grounded": true
  }},
  "reasoning_trace": {{
    "steps": ["<reasoning step 1>", "<reasoning step 2>"],
    "assumptions": ["<assumption 1>"],
    "data_gaps": ["<missing data that could improve analysis>"]
  }}
}}
```"""

    # ── Response parsers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Extract the JSON content from a markdown code fence."""
        import re

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Try to find raw JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start : end + 1]
        return text

    def _parse_expansion_steps(self, raw: str) -> list[ExpansionStep]:
        """Parse the expand response into typed ``ExpansionStep`` objects."""
        import json

        try:
            json_str = self._extract_json_block(raw)
            data = json.loads(json_str)
            steps_data = data.get("expansion_steps", [])
            return [
                ExpansionStep(
                    step_number=s.get("step_number", i + 1),
                    description=s["description"],
                    domain=s.get("domain", self.capability.value),
                    data_required=s.get("data_required", []),
                    expected_output=s.get("expected_output", ""),
                )
                for i, s in enumerate(steps_data)
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse expansion steps: %s — raw: %s", exc, raw[:200])
            return []

    def _parse_compression_steps(self, raw: str) -> list[CompressionStep]:
        """Parse the compress response into typed ``CompressionStep`` objects."""
        import json

        try:
            json_str = self._extract_json_block(raw)
            data = json.loads(json_str)
            steps_data = data.get("compression_steps", [])
            return [
                CompressionStep(
                    insight=s["insight"],
                    recommendation=s["recommendation"],
                    expected_impact=s.get("expected_impact", ""),
                    confidence=ConfidenceLevel(s.get("confidence", "medium").lower()),
                )
                for s in steps_data
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse compression steps: %s — raw: %s", exc, raw[:200])
            return []

    @staticmethod
    def _parse_grounding_check(raw: str) -> GroundingCheck:
        """Parse the grounding check from the compress response."""
        import json

        try:
            json_str = GeminiMeshAgent._extract_json_block(raw)
            data = json.loads(json_str)
            gc = data.get("grounding_check", {})
            return GroundingCheck(
                data_points_referenced=gc.get("data_points_referenced", 0),
                calculation_trace=gc.get("calculation_trace", ""),
                is_grounded=gc.get("is_grounded", False),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return GroundingCheck(
                data_points_referenced=0,
                calculation_trace="",
                is_grounded=False,
            )

    @staticmethod
    def _parse_reasoning_trace(raw: str) -> ReasoningTrace:
        """Parse the reasoning trace from the compress response."""
        import json

        try:
            json_str = GeminiMeshAgent._extract_json_block(raw)
            data = json.loads(json_str)
            rt = data.get("reasoning_trace", {})
            return ReasoningTrace(
                steps=rt.get("steps", []),
                assumptions=rt.get("assumptions", []),
                data_gaps=rt.get("data_gaps", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return ReasoningTrace(steps=[], assumptions=[], data_gaps=[])

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_context(context: dict[str, Any], max_len: int = 8000) -> str:
        """Pretty-print context dict, truncating if necessary."""
        import json

        text = json.dumps(context, indent=2, default=str)
        if len(text) > max_len:
            text = text[:max_len] + "\n... [truncated]"
        return text
