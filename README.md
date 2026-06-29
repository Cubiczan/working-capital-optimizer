# Working Capital Optimizer (WCO)

> **Cubiczan stack** — [Profile](https://github.com/Cubiczan) · [Strata](https://github.com/Cubiczan/Strata) · **You are here:** `working-capital-optimizer`

AI agent mesh that monitors accounts receivable, accounts payable, inventory, and cash flow to recommend specific actions that shrink the cash conversion cycle -- traced, evaluated, and self-improving via Arize Phoenix.

[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript)](https://typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org/)
[![Bun](https://img.shields.io/badge/Bun-1.0+-f472b6?logo=bun)](https://bun.sh/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

Working capital is the oxygen of any manufacturing business, yet optimizing it requires coordinating analysis across four separate domains -- accounts receivable, accounts payable, inventory management, and cash flow forecasting -- that are typically managed in silos. The Working Capital Optimizer (WCO) breaks down these silos by deploying four specialized AI agents powered by Google Gemini 2.5 Flash, orchestrated through topological dependency ordering and unified by a shared context engine.

Each agent follows a two-phase reasoning cycle: **expand** (decompose the problem into 3-5 analytical sub-steps) and **compress** (synthesize expansion results into structured insights with actionable recommendations, expected financial impact, and confidence levels). The Cash Flow Agent runs last because it depends on outputs from the AR, AP, and Inventory agents. Every Gemini call is wrapped in OpenInference-compatible tracing spans so Arize Phoenix can ingest the full reasoning chain for observability and debugging.

The system includes a **self-improvement loop** where an LLM-as-Judge evaluator scores each recommendation on four dimensions (Relevance, Actionability, Financial Impact, Risk Awareness). When rolling average scores fall below threshold, targeted prompt amendments are automatically generated and applied to the relevant agents, producing measurably better recommendations on subsequent runs. The result is a dashboard showing the cash conversion cycle (CCC = DSO + DIO - DPO), 13-week cash forecasts, per-agent analysis cards with reasoning traces, and evaluation score panels.

## Architecture

```
+-------------------------------------------------------------------+
|                  Next.js 16 Dashboard (Bun)                        |
|   CCC Gauge | Agent Cards | 13-Week Chart | Eval Scores           |
+-------------------------------+-----------------------------------+
|                               | REST API                            |
+-------------------------------v-----------------------------------+
|                    Next.js API Routes (proxy)                       |
+-------------------------------+-----------------------------------+
|                               |                                     |
+---------------v---------------+---------------v--------------------+
|                FastAPI Server (Python)            |                  |
+---------------+---------------------------------+------------------+
|               v                                   v                  |
|  +------------------------+         +---------------------------+  |
|  |   Agent Orchestrator   |         |  LLM-as-Judge Evaluator   |  |
|  |  (Topological Sort)    |         |  (Gemini 2.5 Flash)       |  |
|  |                        |         |  4-dimension rubric       |  |
|  | +------+ +------+     |         +-------------+             |  |
|  | | AR   | | AP   |     |                       |             |  |
|  | +--+---+ +--+---+     |         +-------------v             |  |
|  | | INV  | | CASH |     |         |   Eval Results            |  |
|  | +------+ +------+     |         |   (Scores -> Prompts)     |  |
|  +-----------+------------+         +---------------------------+  |
|              |                                                   |
+--------------v---------------------------------------------------+
|              Arize Phoenix Cloud                                   |
|   OpenInference Traces | Datasets | Experiments | MCP Server      |
+-------------------------------+-----------------------------------+
|                               |                                     |
+-------------------------------v-----------------------------------+
|                    CockroachDB                                       |
|    recommendations | evaluations | traces                         |
+-------------------------------------------------------------------+
```

### Agent Dependency Graph

```
AR Agent ──────> Cash Flow Agent
AP Agent ──────> Cash Flow Agent
Inventory Agent > Cash Flow Agent
```

The Cash Flow Agent depends on all three domain agents. The orchestrator uses Kahn's algorithm for topological sorting, ensuring AR, AP, and Inventory run before Cash Flow.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend Framework | Next.js 16 + TypeScript 5 |
| Runtime | Bun |
| UI Components | shadcn/ui + Radix UI |
| Styling | Tailwind CSS 4 |
| Charts | Recharts |
| Animation | Framer Motion |
| State Management | Zustand |
| Backend Language | Python 3.11+ |
| API Framework | FastAPI + Uvicorn |
| LLM | Google Gemini 2.5 Flash |
| Tracing | OpenInference + OpenTelemetry |
| Observability | Arize Phoenix Cloud |
| Database | CockroachDB (via asyncpg + SQLAlchemy) |
| Schema Validation | Pydantic v2 |
| LLM Framework | LangChain Google GenAI |
| MCP | Phoenix MCP Server |

## Key Features

- **Four Specialized AI Agents** -- AR Agent (receivables aging, DSO trends, collection patterns), AP Agent (payment timing, vendor terms, dynamic discounting ROI), Inventory Agent (SKU-level demand, carrying costs, safety stock, ABC classification), and Cash Flow Agent (consolidated view, CCC calculation, 13-week forecast, liquidity risk flags).

- **Expand-Compress Reasoning** -- Each agent follows a two-phase cycle. In the expand phase, Gemini decomposes the working capital problem into 3-5 concrete analytical sub-steps specifying domain, data requirements, and expected outputs. In the compress phase, Gemini synthesizes the expansion results into structured insights with specific recommendations, expected financial impact, and confidence levels (high/medium/low).

- **Topological Agent Orchestration** -- Agents are sorted using Kahn's algorithm based on declared dependencies. The Cash Flow Agent always runs last because it consumes outputs from all three domain agents. Prior agent results are injected into the Cash Flow Agent's context for holistic analysis.

- **Grounding and Hallucination Guards** -- Each compression step includes a grounding check tracking data points referenced, calculation trace descriptions, and a binary grounded flag. A reasoning trace captures the agent's reasoning steps, explicit assumptions, and known data gaps for full auditability.

- **Self-Improvement Loop** -- An LLM-as-Judge evaluator scores each recommendation on four dimensions using weighted rubrics. When rolling average scores fall below threshold, the SelfImprovementEngine generates targeted prompt amendments for underperforming agents and applies them automatically for the next analysis cycle.

- **Arize Phoenix Observability** -- Full OpenInference instrumentation on every Gemini call via `openinference-instrumentation-google-genai` and `openinference-instrumentation-langchain`. Traces are exported to Phoenix Cloud via OTLP/HTTP with bearer authentication. A manual trace store provides a lightweight fallback when SDK instrumentation is unavailable.

- **Comprehensive Dashboard** -- Next.js dashboard showing the cash conversion cycle gauge (CCC = DSO + DIO - DPO), agent pipeline visualization with per-agent timing, 13-week cash flow forecast chart, recommendations feed with confidence badges, and evaluation scores panel tracking quality trends over time.

- **CockroachDB Persistence** -- Recommendations, evaluation scores, and trace metadata are persisted in CockroachDB for historical analysis and trend tracking.

## Getting Started

### Prerequisites

- Python 3.11+
- Bun 1.0+ or Node.js 20+
- Google Gemini API key
- Arize Phoenix Cloud account (free tier works)

### Installation

```bash
# Clone the repository
git clone https://github.com/icohangar-ops/working-capital-optimizer.git
cd working-capital-optimizer

# Copy environment template and fill in your keys
cp .env.example .env
```

### Backend Setup (Python Agent Mesh)

```bash
cd wco/agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run with sample data
wco analyze --data-file src/wco/data/sample_data.json

# Or start the API server
wco serve
```

### Frontend Setup (Next.js Dashboard)

```bash
# From the project root
bun install

# Start the development server
bun run dev
# Open http://localhost:3000
```

### Full Pipeline

1. Start the Python backend on port 8000 (`wco serve`)
2. Start the Next.js dashboard (`bun run dev`)
3. Open `http://localhost:3000`
4. Click "Run Analysis" to execute all four agents
5. View results with Phoenix Cloud traces

## Usage

### CLI Commands

```bash
# Run a full 4-agent analysis with sample data
wco analyze --data-file src/wco/data/sample_data.json

# Start the FastAPI server
wco serve

# Start the Phoenix MCP server for trace introspection
wco mcp
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/wco/analyze` | Run full 4-agent analysis pipeline |
| POST | `/api/wco/evaluate` | LLM-as-Judge evaluation of a recommendation |
| GET | `/api/wco/recommendations` | List past recommendations (limit 50) |
| GET | `/api/wco/evaluations` | List past evaluation scores |
| GET | `/api/wco/health` | Backend health check (agent readiness, DB status) |

### Analysis Request Format

```json
{
  "ar_invoices": [
    {
      "invoice_id": "INV-001",
      "customer_name": "Acme Corp",
      "amount": 45000,
      "issue_date": "2025-01-15",
      "due_date": "2025-02-15",
      "payment_terms_days": 30,
      "days_outstanding": 45,
      "aging_bucket": "31-60",
      "payment_status": "overdue"
    }
  ],
  "ap_invoices": [...],
  "skus": [...],
  "opening_cash_balance": 2500000,
  "monthly_revenue": 4200000,
  "monthly_cogs": 2800000,
  "problem_description": "Optimize working capital for Q3",
  "cost_of_capital": 0.08,
  "carrying_cost_rate": 0.25,
  "target_service_level": 0.95,
  "min_cash_threshold": 500000
}
```

### Environment Variables

```env
# Google Gemini
GEMINI_API_KEY=your-gemini-api-key-here

# Arize Phoenix Cloud
PHOENIX_API_KEY=your-phoenix-api-key-here
PHOENIX_PROJECT_NAME=wco-agent
PHOENIX_BASE_URL=https://app.phoenix.arize.com

# CockroachDB
COCKROACHDB_USERNAME=your-username
COCKROACHDB_PASSWORD=your-password
COCKROACHDB_HOST=your-cluster.cockroachlabs.cloud
COCKROACHDB_PORT=26257
COCKROACHDB_DATABASE=wco
```

## Project Structure

```
working-capital-optimizer/
├── package.json                # Frontend dependencies (Next.js, shadcn, Recharts)
├── bun.lock                    # Bun lock file
├── tsconfig.json               # TypeScript configuration
├── tailwind.config.ts          # Tailwind CSS configuration
├── next.config.ts              # Next.js configuration
├── prisma/
│   └── schema.prisma           # Database schema (Prisma ORM)
├── .env.example                # Environment variable template
├── Caddyfile                   # Reverse proxy configuration
├── wco/
│   └── agent/
│       ├── pyproject.toml      # Python package (wco-agent)
│       └── src/wco/
│           ├── cli.py          # CLI entry point (wco analyze, wco serve)
│           ├── config.py       # Pydantic settings (Gemini, Phoenix, CockroachDB)
│           ├── agents/
│           │   ├── base.py          # GeminiMeshAgent base class
│           │   ├── ar_agent.py      # Accounts Receivable agent
│           │   ├── ap_agent.py      # Accounts Payable agent
│           │   ├── inventory_agent.py  # Inventory agent
│           │   └── cashflow_agent.py   # Cash Flow agent
│           ├── orchestration/
│           │   ├── orchestrator.py  # WorkingCapitalOrchestrator
│           │   └── context.py       # ContextEngine (shared state)
│           ├── eval/
│           │   ├── evaluator.py     # LLM-as-Judge evaluation
│           │   └── self_improvement.py  # Prompt amendment loop
│           ├── tracing/
│           │   └── phoenix_setup.py # OpenInference + Phoenix Cloud setup
│           ├── api/
│           │   └── server.py       # FastAPI server
│           ├── db/
│           │   └── connection.py   # CockroachDB async connection
│           ├── data/
│           │   └── sample_data.py  # Sample AR/AP/invoice data
│           └── mcp/
│               └── mcp_config.json # Phoenix MCP server config
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout
│   │   ├── page.tsx            # Main dashboard page
│   │   ├── globals.css         # Global styles
│   │   └── api/
│   │       └── wco/
│   │           ├── analyze/route.ts        # Analysis proxy endpoint
│   │           ├── evaluate/route.ts       # Evaluation proxy endpoint
│   │           ├── recommendations/route.ts # Recommendations proxy
│   │           ├── evaluations/route.ts    # Evaluations proxy
│   │           └── health/route.ts         # Health check proxy
│   ├── components/
│   │   ├── ui/                 # shadcn/ui primitives
│   │   └── wco/
│   │       ├── ccc-summary.tsx       # Cash Conversion Cycle gauge
│   │       ├── agent-pipeline.tsx     # Agent execution pipeline view
│   │       ├── cash-forecast-chart.tsx # 13-week forecast chart
│   │       ├── recommendations-feed.tsx # Recommendations list
│   │       └── eval-scores-panel.tsx  # Evaluation score trends
│   ├── hooks/
│   │   ├── use-toast.ts        # Toast notification hook
│   │   └── use-mobile.ts       # Mobile detection hook
│   └── lib/
│       ├── wco-types.ts        # TypeScript type definitions
│       ├── wco-store.ts        # Zustand state store
│       ├── wco-sample-data.ts  # Frontend sample data
│       ├── db.ts               # Database client
│       └── utils.ts            # Utility functions
├── modenrich/                  # Moderation enrichment module
└── examples/
    └── websocket/              # WebSocket demo (server + frontend)
```

## Contributing

Contributions are welcome. To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes with appropriate tests
4. Run `bun run lint` for the frontend
5. Run `pytest` for the Python backend
6. Commit with descriptive messages
7. Open a Pull Request against the `main` branch

---

## Cubiczan stack

| Finance | [Strata](https://github.com/Cubiczan/Strata) · [Metabocommand](https://github.com/Cubiczan/Metabocommand) · [meshcfo](https://github.com/Cubiczan/meshcfo) · [working-capital-optimizer](https://github.com/Cubiczan/working-capital-optimizer) · [cash-flow-optimizer](https://github.com/Cubiczan/cash-flow-optimizer) · [finance-cockpit](https://github.com/Cubiczan/finance-cockpit) |
| Governance | [consensus-hardening-protocol](https://github.com/Cubiczan/consensus-hardening-protocol) · [agent-conductor](https://github.com/Cubiczan/agent-conductor) · [compliance-as-code-agent](https://github.com/Cubiczan/compliance-as-code-agent) · [cleanmandate](https://github.com/Cubiczan/cleanmandate) |

WCO shrinks the **cash conversion cycle** — feeds forecasts into [cash-flow-optimizer](https://github.com/Cubiczan/cash-flow-optimizer) and board packets from [meshcfo](https://github.com/Cubiczan/meshcfo).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
