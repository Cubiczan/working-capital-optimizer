"""Working Capital Orchestrator.

Topologically sorts domain agents, runs them in dependency order with a
shared context, and assembles an ``OrchestrationReport`` containing the
full analysis pipeline output.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from wco.agents.base import (
    AgentCapability,
    GeminiMeshAgent,
    TurnResult,
)
from wco.orchestration.context import ContextEngine

logger = logging.getLogger(__name__)


# ── Dependency graph ──────────────────────────────────────────────────────

# Maps agent capability → set of capabilities that must run *before* it.
AGENT_DEPENDENCIES: dict[AgentCapability, set[AgentCapability]] = {
    AgentCapability.AR: set(),
    AgentCapability.AP: set(),
    AgentCapability.INVENTORY: set(),
    AgentCapability.CASHFLOW: {AgentCapability.AR, AgentCapability.AP, AgentCapability.INVENTORY},
}


def _topological_sort(
    agents: list[GeminiMeshAgent],
) -> list[GeminiMeshAgent]:
    """Topologically sort agents by their declared dependencies.

    Uses Kahn's algorithm.  If a cycle is detected (should never happen
    with the fixed dependency graph above) the remaining agents are
    appended in their original order with a warning.

    Args:
        agents: List of agents to sort.

    Returns:
        Agents in execution order.
    """
    # Build adjacency lists
    capability_to_agent: dict[AgentCapability, GeminiMeshAgent] = {
        a.capability: a for a in agents
    }
    in_degree: dict[AgentCapability, int] = {a.capability: 0 for a in agents}
    dependents: dict[AgentCapability, list[AgentCapability]] = {
        a.capability: [] for a in agents
    }

    for agent in agents:
        deps = AGENT_DEPENDENCIES.get(agent.capability, set())
        # Only count deps that are present in the agent list
        present_deps = deps & set(capability_to_agent.keys())
        in_degree[agent.capability] = len(present_deps)
        for dep in present_deps:
            dependents[dep].append(agent.capability)

    # Kahn's algorithm
    queue = [cap for cap, deg in in_degree.items() if deg == 0]
    sorted_caps: list[AgentCapability] = []

    while queue:
        cap = queue.pop(0)
        sorted_caps.append(cap)
        for dependent in dependents.get(cap, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Handle any remaining (cycle)
    if len(sorted_caps) < len(agents):
        remaining = [a.capability for a in agents if a.capability not in sorted_caps]
        logger.warning("Dependency cycle detected among: %s — appending in original order", remaining)
        sorted_caps.extend(remaining)

    return [capability_to_agent[cap] for cap in sorted_caps if cap in capability_to_agent]


# ── Orchestration report ──────────────────────────────────────────────────


@dataclass
class OrchestrationReport:
    """Aggregated output from the full agent-mesh execution.

    Attributes:
        problem: Original problem description.
        turns: Ordered list of TurnResult from each agent.
        duration_ms: Total wall-clock time.
        cash_conversion_cycle: Computed CCC (DSO + DIO − DPO).
        recommendations: Flat list of all actionable recommendations.
        context_dump: Debug dump of the shared context.
    """

    problem: str = ""
    turns: list[TurnResult] = field(default_factory=list)
    duration_ms: float = 0.0
    cash_conversion_cycle: dict[str, float] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    context_dump: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return {
            "problem": self.problem,
            "duration_ms": self.duration_ms,
            "cash_conversion_cycle": self.cash_conversion_cycle,
            "turns": [
                {
                    "agent_name": t.agent_name,
                    "capability": t.capability.value,
                    "expansion_steps": [
                        {
                            "step_number": s.step_number,
                            "description": s.description,
                            "domain": s.domain,
                            "expected_output": s.expected_output,
                        }
                        for s in t.expansion_steps
                    ],
                    "compression_steps": [
                        {
                            "insight": s.insight,
                            "recommendation": s.recommendation,
                            "expected_impact": s.expected_impact,
                            "confidence": s.confidence.value,
                        }
                        for s in t.compression_steps
                    ],
                    "grounding_check": (
                        {
                            "data_points_referenced": t.grounding_check.data_points_referenced,
                            "calculation_trace": t.grounding_check.calculation_trace,
                            "is_grounded": t.grounding_check.is_grounded,
                        }
                        if t.grounding_check
                        else None
                    ),
                    "reasoning_trace": (
                        {
                            "steps": t.reasoning_trace.steps,
                            "assumptions": t.reasoning_trace.assumptions,
                            "data_gaps": t.reasoning_trace.data_gaps,
                        }
                        if t.reasoning_trace
                        else None
                    ),
                    "duration_ms": t.duration_ms,
                    "trace_id": t.trace_id,
                }
                for t in self.turns
            ],
            "recommendations": self.recommendations,
        }


# ── Orchestrator ──────────────────────────────────────────────────────────


class WorkingCapitalOrchestrator:
    """Orchestrates the WCO agent mesh.

    Topologically sorts agents, runs them sequentially with a shared
    ``ContextEngine``, and assembles a final ``OrchestrationReport``.

    Parameters:
        agents: List of domain-specialist agents to orchestrate.
        context: Optional pre-populated context engine.
    """

    def __init__(
        self,
        agents: list[GeminiMeshAgent],
        context: ContextEngine | None = None,
    ) -> None:
        self._agents = _topological_sort(agents)
        self._context = context or ContextEngine()

        logger.info(
            "Orchestrator initialised with %d agents in order: %s",
            len(self._agents),
            [a.name for a in self._agents],
        )

    @property
    def context(self) -> ContextEngine:
        """Access the shared context engine."""
        return self._context

    async def run(self, data: dict[str, Any]) -> OrchestrationReport:
        """Execute all agents and return the final report.

        Args:
            data: Raw input payload containing AR, AP, inventory, and
                cash-balance data.

        Returns:
            An ``OrchestrationReport`` with all agent results.
        """
        t0 = time.perf_counter()

        # ── Seed context with raw data ───────────────────────────────
        self._context.write("raw_data", data, source_agent="system", kind=EntryKind.RESULT)

        # ── Run agents in topological order ──────────────────────────
        turns: list[TurnResult] = []
        agent_results: dict[str, Any] = {}

        for agent in self._agents:
            logger.info("Running agent: %s", agent.name)

            # Build agent-specific context from raw data + prior results
            agent_context = self._build_agent_context(agent, data, agent_results)

            turn = await agent.run(agent_context)
            turns.append(turn)

            # Store result in shared context
            turn_dict = self._serialise_turn(turn)
            agent_results[agent.capability.value] = turn_dict

            self._context.write(
                key=f"{agent.capability.value}_result",
                value=turn_dict,
                source_agent=agent.name,
                kind=EntryKind.RESULT,
                text=f"{agent.name} analysis result",
            )

            logger.info(
                "Agent %s finished in %.1f ms — %d compression steps",
                agent.name,
                turn.duration_ms,
                len(turn.compression_steps),
            )

        elapsed = (time.perf_counter() - t0) * 1000

        # ── Assemble report ──────────────────────────────────────────
        ccc = self._extract_ccc(turns)
        recommendations = self._extract_recommendations(turns)

        report = OrchestrationReport(
            problem=data.get("problem_description", "Working capital optimization analysis"),
            turns=turns,
            duration_ms=round(elapsed, 2),
            cash_conversion_cycle=ccc,
            recommendations=recommendations,
            context_dump=self._context.dump(),
        )

        logger.info(
            "Orchestration complete in %.1f ms — CCC: %.1f days, %d recommendations",
            elapsed,
            ccc.get("ccc", 0),
            len(recommendations),
        )
        return report

    # ── Helpers ──────────────────────────────────────────────────────────

    def _build_agent_context(
        self,
        agent: GeminiMeshAgent,
        raw_data: dict[str, Any],
        prior_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the context dict passed to an agent's ``run()`` method.

        Domain agents (AR, AP, Inventory) get their ``prepare_context()``
        method called.  The CashFlow agent gets the additional prior
        agent results injected.
        """
        # Check if agent has a prepare_context method
        if hasattr(agent, "prepare_context"):
            if agent.capability == AgentCapability.CASHFLOW:
                # Pass prior agent results
                return agent.prepare_context(
                    raw_data,
                    ar_result=prior_results.get("accounts_receivable"),
                    ap_result=prior_results.get("accounts_payable"),
                    inventory_result=prior_results.get("inventory"),
                )
            else:
                return agent.prepare_context(raw_data)
        return raw_data

    @staticmethod
    def _serialise_turn(turn: TurnResult) -> dict[str, Any]:
        """Convert a TurnResult to a JSON-serialisable dict."""
        from wco.orchestration.context import ContextEngine

        return ContextEngine._dataclass_to_dict(turn)

    @staticmethod
    def _extract_ccc(turns: list[TurnResult]) -> dict[str, float]:
        """Try to extract CCC components from agent results.

        Falls back to zero values if not found in the LLM output.
        """
        ccc: dict[str, float] = {"dso": 0, "dio": 0, "dpo": 0, "ccc": 0}

        # Look for CCC data in the CashFlow agent's raw response
        for turn in turns:
            if turn.capability == AgentCapability.CASHFLOW:
                # Check compression steps for CCC-related insights
                for step in turn.compression_steps:
                    text = (step.insight + step.recommendation + step.expected_impact).lower()
                    for key in ("dso", "dio", "dpo", "ccc", "cash conversion cycle"):
                        # Try to extract numeric value
                        import re

                        pattern = rf"{key}\s*(?:is|:|=|=~)?\s*(\d+\.?\d*)"
                        match = re.search(pattern, text)
                        if match:
                            ccc[key] = float(match.group(1))
        return ccc

    @staticmethod
    def _extract_recommendations(turns: list[TurnResult]) -> list[dict[str, Any]]:
        """Flatten all compression steps into a single recommendation list."""
        recs: list[dict[str, Any]] = []
        for turn in turns:
            for step in turn.compression_steps:
                recs.append(
                    {
                        "agent": turn.agent_name,
                        "capability": turn.capability.value,
                        "insight": step.insight,
                        "recommendation": step.recommendation,
                        "expected_impact": step.expected_impact,
                        "confidence": step.confidence.value,
                    }
                )
        return recs


# Avoid circular import
from wco.orchestration.context import EntryKind  # noqa: E402
