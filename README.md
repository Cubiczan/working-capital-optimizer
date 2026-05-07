# Working Capital Optimizer (WCO)

> AI agent mesh that monitors AR, AP, inventory and cash flow to recommend specific actions that shrink the cash conversion cycle — traced and self-improving via Arize Phoenix.

Built for the **[Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com)** — Arize Resources Track.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Next.js 16 Dashboard                   │
│   CCC Gauge │ Agent Cards │ 13-Week Chart │ Eval Scores │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI Server (Python)                  │
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
│              CockroachDB                                  │
│  recommendations │ evaluations │ traces                   │
└─────────────────────────────────────────────────────────┘
```

## The Four Agents

| Agent | Analyzes | Key Metrics |
|-------|----------|-------------|
| **AR Agent** | Receivables aging, DSO trends, collection patterns | DSO, overdue concentration, discount ROI |
| **AP Agent** | Payment timing, vendor terms, dynamic discounting | DPO, annualized discount return, cash preserved |
| **Inventory Agent** | SKU-level demand, carrying costs, safety stock | DIO, ABC classification, reorder points |
| **Cash Flow Agent** | Consolidates all agents into unified cash view | CCC, 13-week forecast, liquidity risk flags |

### Cash Conversion Cycle

$$CCC = DSO + DIO - DPO$$

## Self-Improvement Loop

1. Agents produce recommendations → **LLM-as-Judge** evaluates each on 4 dimensions (Relevance, Actionability, Financial Impact, Risk Awareness)
2. Low-scoring patterns identified from evaluation history
3. Targeted prompt amendments generated and applied
4. Next analysis run produces measurably better recommendations

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ / Bun
- Google Gemini API key
- Arize Phoenix Cloud account (free tier works)

### 1. Clone and configure

```bash
git clone https://github.com/cubiczan/working-capital-optimizer.git
cd working-capital-optimizer

# Copy env template and fill in your keys
cp .env.example .env
```

### 2. Backend (Python)

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

### 3. Frontend (Next.js)

```bash
cd ../..
npm install
npm run dev
# Open http://localhost:3000
```

### 4. Full pipeline

Start the backend on port 8000, then open the dashboard. Click **"Run Analysis"** to execute all four agents and see results with Phoenix Cloud traces.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Run full 4-agent analysis pipeline |
| `POST` | `/api/evaluate` | LLM-as-Judge evaluation of a recommendation |
| `GET` | `/api/recommendations` | List past recommendations |
| `GET` | `/api/evaluations` | List past evaluation scores |
| `GET` | `/api/health` | Backend health check |

## Technologies

**Backend:** Python, FastAPI, Google Gemini 2.5 Flash, OpenInference, OpenTelemetry, Arize Phoenix, CockroachDB, asyncpg, Pydantic, SQLAlchemy, LangChain Google GenAI, Phoenix MCP Server

**Frontend:** TypeScript, Next.js 16, Recharts, shadcn/ui, Tailwind CSS 4, Zustand, Framer Motion, Lucide React, Radix UI

## Arize Track Compliance

| Requirement | Implementation |
|-------------|---------------|
| Code-owned agent runtime | Gemini 2.5 Flash with custom expand→compress cycle |
| OpenInference instrumentation | `openinference-instrumentation-google-genai` on every call |
| Phoenix Cloud traces | `OpenInferenceSpanExporter` with bearer auth |
| Phoenix MCP server | Configured for runtime trace introspection |
| LLM-as-Judge evals | 4-dimension rubric with weighted scoring |
| Self-improvement loop | Rolling-average threshold prompt amendments |

## License

Apache-2.0
