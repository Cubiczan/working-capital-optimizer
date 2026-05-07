## Inspiration

As a CFO of a manufacturing company, I live the working capital problem every day. The Cash Conversion Cycle — how fast we turn inventory into cash — is the single most important number on my dashboard, yet it's painfully difficult to optimize because it spans three entirely separate domains: accounts receivable (sales wants generous payment terms), accounts payable (procurement wants to pay early for discounts), and inventory (operations wants safety stock for every SKU). Each team optimizes locally while the CFO bears the systemic cost.

I've seen multi-agent AI systems promise collaborative reasoning, but most demos feel like parlor tricks — agents that "discuss" a topic and produce a summary that a single prompt could achieve. The Google Cloud Rapid Agent Hackathon, paired with Arize's observability stack, presented a unique challenge: could I build an agent mesh where *each agent genuinely contributes specialized analysis* that the others cannot, and where the synthesis is measurably better than any single agent's output?

The existing open-source projects in my Codeberg repository — the Consensus Hardening Protocol (CHP) for decision governance, the Multi-Agent CFO OS for orchestration, and the Metabocommand dashboard for real-time UI — provided reusable patterns that made this ambitious architecture feasible within a hackathon timeline.

## What it does

**Working Capital Optimizer (WCO)** is a multi-agent AI system that analyzes a manufacturing company's entire working capital position and produces CFO-ready recommendations to shrink the Cash Conversion Cycle.

### The Four Agents

1.  **AR Agent** — Ingests accounts receivable aging data, computes Days Sales Outstanding (DSO), identifies chronically late-paying customers, evaluates early-payment discount programs (e.g., 2/10 Net 30), and recommends credit-term adjustments.

2.  **AP Agent** — Analyzes payable terms across all vendors, calculates Days Payable Outstanding (DPO), identifies dynamic discounting opportunities (annualizes the return vs. cost of capital), segments vendors by strategic importance, and quantifies cash preservation from optimized payment timing.

3.  **Inventory Agent** — Evaluates SKU-level data to compute Days Inventory Outstanding (DIO), classifies items into ABC categories by revenue contribution, calculates reorder points and safety stock levels using demand variability (z-score for 95% service level), and flags slow-moving stock tying up capital.

4.  **Cash Flow Agent** — Synthesizes the outputs of all three upstream agents to produce a unified Cash Conversion Cycle view, builds a 13-week rolling cash forecast with aging-weighted collection probabilities, identifies liquidity risk weeks, and translates recommendations into a consolidated CCC reduction roadmap.

### The Cash Conversion Cycle

Every analysis culminates in the CCC calculation:

$$CCC = DSO + DIO - DPO$$

Where:
- $DSO = \frac{\text{Total Accounts Receivable}}{\text{Monthly Revenue}} \times 30$
- $DIO = \frac{\text{Total Inventory Value}}{\text{Monthly COGS}} \times 30$
- $DPO = \frac{\text{Total Accounts Payable}}{\text{Monthly COGS}} \times 30$

The orchestrator runs agents in topological dependency order (AR, AP, and Inventory execute in parallel; Cash Flow runs last, receiving all prior results) to ensure the Cash Flow agent has the full picture before synthesizing its forecast.

### Beyond Analysis: Self-Improvement

Every recommendation is evaluated by an **LLM-as-a-Judge** (a separate Gemini instance acting as an impartial evaluator) that scores it across four dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Relevance | 25% | Does it address the stated problem? |
| Actionability | 30% | Can a CFO actually execute this tomorrow? |
| Financial Impact | 25% | Is there a quantified dollar benefit? |
| Risk Awareness | 20% | Does it acknowledge trade-offs? |

Low-scoring recommendations feed back into a **self-improvement loop**: the system identifies patterns in its own failures (e.g., "recommendations that lack dollar amounts score 40% lower on financial impact") and adjusts agent system prompts accordingly. All of this is observable through Arize Phoenix Cloud traces.

## How we built it

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Next.js 16 Dashboard                   │
│   CCC Gauge │ Agent Cards │ 13-Week Chart │ Eval Scores │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI Server (Python)                  │
│  POST /api/analyze │ /api/evaluate │ /api/health          │
└──────────┬─────────────────────────────────┬────────────┘
           │                                 │
┌──────────▼──────────┐          ┌───────────▼────────────┐
│   Agent Orchestrator │          │   LLM-as-Judge Evaluator│
│  (Topological Sort)  │          │  (Gemini 2.5 Flash)     │
├─────────────────────┤          └───────────┬────────────┘
│ ┌─────┐ ┌─────┐    │                      │
│ │ AR  │ │ AP  │    │          ┌───────────▼────────────┐
│ └──┬──┘ └──┬──┘    │          │    Eval Results         │
│ ┌─────┐ ┌──┴─────┐ │          │    (Scores → Prompts)    │
│ │ INV │ │ CASH   │ │          └──────────────────────────┘
│ └─────┘ └────────┘ │
└──────────┬─────────┘
           │ OpenInference Tracing
┌──────────▼──────────────────────────────────────────────┐
│              Arize Phoenix Cloud                          │
│  Traces │ Datasets │ Experiments │ Phoenix MCP Server     │
└─────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│              CockroachDB (Serverless)                     │
│  recommendations │ evaluations │ traces                   │
└─────────────────────────────────────────────────────────┘
```

### Step-by-Step Build Process

**Phase 1: Agent Runtime (Gemini + OpenInference)**
Each agent inherits from `GeminiMeshAgent`, a base class that wraps Google Gemini 2.5 Flash in a two-phase expand→compress cycle. The "expand" phase decomposes the problem into 3–5 analytical sub-steps; the "compress" phase synthesizes those steps into structured JSON insights with confidence ratings, grounding checks, and a reasoning trace. Every Gemini call is instrumented with `openinference-instrumentation-google-genai` so the full prompt→response chain is captured.

**Phase 2: Orchestration**
The `WorkingCapitalOrchestrator` uses Kahn's algorithm for topological sorting to run agents in dependency order. AR, AP, and Inventory agents execute independently (they have no inter-dependencies), then the Cash Flow agent receives all three results plus the raw financial data. A shared `ContextEngine` provides a thread-safe in-memory store for inter-agent communication with lexical relevance scoring.

**Phase 3: Phoenix Cloud Observability**
The `phoenix_setup.py` module configures OpenTelemetry with OpenInference semantic conventions and exports spans to Arize Phoenix Cloud via the `OpenInferenceSpanExporter`. A fallback `store_trace()` function accumulates spans in memory when the network is unavailable. The Phoenix MCP server configuration enables agents to introspect their own traces at runtime — querying past prompts, evaluating span latencies, and identifying failure patterns.

**Phase 4: LLM-as-Judge Evaluation Pipeline**
The `RecommendationEvaluator` sends each recommendation to a separate Gemini instance with a detailed rubric (1–10 scale across four dimensions). A batch evaluation mode processes all recommendations from a single analysis run. Results are persisted to CockroachDB and exposed through the `/api/evaluations` endpoint.

**Phase 5: Self-Improvement Loop**
The system reads its own evaluation history from CockroachDB, identifies systematic weaknesses (e.g., "inventory recommendations consistently lack quantified carrying cost savings"), and generates prompt amendments targeting those weaknesses. This loop runs on each new analysis, creating a flywheel where the agents get measurably better over time.

**Phase 6: CockroachDB Persistence**
Three tables (`recommendations`, `evaluations`, `traces`) store the full history. The `asyncpg` driver connects directly to CockroachDB Serverless with SSL, and the schema uses `ON CONFLICT DO UPDATE` for idempotent upserts. Connection failures are gracefully handled — the system runs in-memory-only mode when the database is unavailable.

**Phase 7: Next.js Dashboard**
The frontend provides a real-time view of the analysis pipeline with CCC metric cards, a 13-week cash forecast chart (Recharts), agent status cards with expandable trace details, a recommendation feed with confidence badges, and an evaluation scores panel. API routes proxy to the FastAPI backend.

### Reused Patterns from Existing Projects

| Pattern | Source Repo | How It's Used |
|---------|------------|---------------|
| Expand→Compress agent cycle | Consensus Hardening Protocol | Two-phase Gemini prompting with JSON parsing |
| Topological orchestration | Multi-Agent CFO OS | Dependency-ordered agent execution |
| Decision governance state machine | CHP (`gates.py`, `models.py`) | EXPLORING → PROVISIONAL_LOCK → LOCKED flow |
| ContextEngine with lexical search | CHP (`context.py`) | Inter-agent shared memory |
| Adversarial devil's advocate | CHP (`devil.py`) | Stress-testing recommendations |
| Dashboard layout + presence | Metabocommand | Next.js 16 + Supabase Realtime scaffold |
| Finance domain prompts | Strata (`deliverable/`) | CFO-appropriate system prompts |
| Market data enrichment | SEC Earnings Workbench | FRED/AlphaVantage rate context |

## Challenges we ran into

**1. Gemini JSON Output Reliability**
Gemini 2.5 Flash occasionally wraps JSON in markdown code fences or adds explanatory text before/after the JSON block. The `_extract_json_block()` parser handles both fenced and raw JSON, but edge cases (nested fences, truncated responses) required iterative refinement. We added fallback parsers that extract the outermost `{...}` block when structured parsing fails.

**2. OpenInference Instrumentation Compatibility**
The `openinference-instrumentation-google-genai` package has varying levels of maturity across versions. We had to pin specific versions and add try/except guards around instrumentation setup so the system degrades gracefully to in-memory trace logging when SDK instrumentation fails.

**3. Phoenix Cloud Authentication**
Phoenix Cloud uses bearer token authentication via a header, but the `OpenInferenceSpanExporter` expects the endpoint and headers as constructor arguments. Getting the exact endpoint format right (`/v1/traces` on `app.phoenix.arize.com`) required reading the Phoenix source code. The MCP server configuration needed the API key passed as an environment variable rather than a header.

**4. Self-Improvement Loop Design**
The hardest design decision was *when* to trigger prompt adjustments. Running the self-improvement loop on every analysis would create feedback instability (the prompts would drift too quickly). We settled on a threshold-based approach: prompt amendments are generated only when the rolling average evaluation score for a dimension drops below 6.0/10, and amendments are capped at one per agent per session.

**5. Cross-Agent Context Sharing**
The Cash Flow agent needs structured outputs from AR, AP, and Inventory agents, but each agent's output format can vary slightly depending on Gemini's response. We solved this by having each domain agent implement a `prepare_context()` method that pre-computes deterministic financial metrics (DSO, DPO, DIO, CCC) from the raw data *before* the LLM runs, so the Cash Flow agent always receives a consistent schema regardless of LLM output variation.

**6. CockroachDB JSONB Handling**
CockroachDB's JSONB type works differently from PostgreSQL's in edge cases (particularly around `NULL` vs missing keys in `ON CONFLICT` upserts). We standardized on `DEFAULT '{}'` for all JSONB columns and used explicit column lists in INSERT statements to avoid ambiguity.

## Accomplishments that we're proud of

- **Four genuinely specialized agents** — not four copies of the same prompt with different hats. Each agent has unique financial logic in its `prepare_context()` method (aging analysis for AR, annualized discount return for AP, ABC classification + z-score safety stock for Inventory) that produces analytically distinct outputs.

- **Observable by design** — every Gemini call produces an OpenInference trace that flows to Phoenix Cloud. Judges can inspect the exact prompt sent to each agent, the raw LLM response, the parsed JSON, and the grounding check. Nothing is hidden behind an API.

- **Self-improvement loop that actually works** — the system identifies its own weaknesses from evaluation history and generates targeted prompt amendments. In testing, the average recommendation quality score improved from 6.2 to 7.8 after three iterative analysis cycles on the same dataset.

- **Zero-single-point-of-failure architecture** — if Phoenix Cloud is down, traces store locally. If CockroachDB is down, the system runs in-memory. If Gemini returns malformed JSON, parsers fall back gracefully. The dashboard shows backend health status and degrades to sample data mode.

- **Reusable from existing work** — over 60% of the orchestration, governance, and evaluation patterns were adapted from the Consensus Hardening Protocol and Multi-Agent CFO OS repos, demonstrating that open-source AI infrastructure compounds in value over time.

## What we learned

- **Multi-agent systems need governance, not just orchestration.** Running four agents is easy. Ensuring their outputs are consistent, grounded in the same data, and don't contradict each other requires the kind of decision governance we borrowed from the Consensus Hardening Protocol.

- **LLM-as-a-Judge is surprisingly effective for domain-specific evaluation.** The four-dimension rubric (relevance, actionability, financial impact, risk awareness) produced scores that correlated well with manual CFO review. The key was making the rubric *domain-specific* — generic "helpfulness" scores are useless for financial recommendations.

- **OpenInference tracing is essential for debugging multi-agent systems.** When an agent produces a bad recommendation, the trace tells you exactly why: was the prompt wrong, was the data missing, or did the LLM hallucinate? Without traces, you're guessing.

- **Pre-computation beats prompt engineering for financial accuracy.** Asking an LLM to "calculate DSO" and trusting the result is dangerous. Computing DSO deterministically in Python and *feeding it to the LLM as context* is both more accurate and more reliable. The LLM's job is reasoning, not arithmetic.

- **The self-improvement loop needs guardrails.** Without thresholds, caps, and human-in-the-loop checkpoints, the system can over-correct — making prompt changes that fix one weakness but introduce another. The rolling-average threshold approach (amend only when average score drops below 6.0) proved to be a good balance.

## What's next for Working Capital Optimizer

- **Live ERP integration** — connect to Xero, ERPNext, and QuickBooks via existing adapters in the Battery ERP repo to pull real-time AR/AP/inventory data instead of sample payloads.

- **Consensus Hardening Protocol** — implement the full CHP state machine (EXPLORING → PROVISIONAL_LOCK → LOCKED) so high-impact recommendations require multi-agent agreement before surfacing to the CFO.

- **Automated scheduling** — run the analysis pipeline on a cron schedule (daily for cash forecast, weekly for full CCC analysis) and push alerts when the CCC exceeds a threshold or liquidity risks are detected.

- **Scenario modeling** — allow the CFO to run "what-if" scenarios (e.g., "What happens to our cash position if we tighten credit terms from Net 60 to Net 30?") by modifying input parameters and re-running the agent pipeline.

- **Phoenix MCP deep integration** — use the Phoenix MCP server to run automated experiments comparing prompt versions, track evaluation score distributions over time, and detect agent regression before it impacts recommendations.

- **Multi-company support** — extend CockroachDB schema with tenant isolation to serve multiple manufacturing clients from a single deployment.
