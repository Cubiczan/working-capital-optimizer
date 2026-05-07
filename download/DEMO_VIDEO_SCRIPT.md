# WCO 3-Minute Demo Video Script

## Timing Guide
| Segment | Time | Duration |
|---------|------|----------|
| Hook + Problem | 0:00 | 30s |
| Architecture Overview | 0:30 | 20s |
| Live Demo — Dashboard | 0:50 | 60s |
| Phoenix Cloud Traces | 1:50 | 30s |
| Self-Improvement Loop | 2:20 | 20s |
| Summary + CTA | 2:40 | 20s |

---

## Script

### [0:00–0:30] Hook — The Problem

**[Screen: Title card with WCO logo + "Cash Conversion Cycle" visual]**

"As a CFO of a manufacturing company, I stare at three numbers every day: Days Sales Outstanding, Days Inventory Outstanding, and Days Payable Outstanding. Together they form the Cash Conversion Cycle — how fast we turn inventory into cash. But here's the problem: my sales team owns AR, procurement owns AP, and operations owns inventory. Each team optimizes locally while I bear the systemic cost."

**[Screen: Split view — AR aging report, AP payment queue, inventory dashboard — all disconnected]**

"Nobody is looking at the full picture. That's why I built the Working Capital Optimizer."

---

### [0:30–0:50] Architecture — How It Works

**[Screen: Architecture diagram — 4 agents → Orchestrator → Phoenix Cloud]**

"WCO is a multi-agent AI system with four specialized agents, each powered by Google Gemini 2.5 Flash. The AR Agent analyzes receivables aging and collection patterns. The AP Agent optimizes payment timing and evaluates dynamic discounts. The Inventory Agent classifies SKUs and calculates safety stock. And the Cash Flow Agent synthesizes everything into a 13-week forecast."

**[Screen: Diagram zooms into Phoenix Cloud + CockroachDB]**

"Every Gemini call is traced with OpenInference and sent to Arize Phoenix Cloud. Every recommendation is evaluated by an LLM-as-Judge on four dimensions. And the results persist to CockroachDB."

---

### [0:50–1:50] Live Demo — Dashboard

**[Screen: Open browser → localhost:3000 → WCO Dashboard]**

"Let me show you the dashboard. Here's our sample company — a $14.4 million manufacturer with $2.5 million in cash and a declining cash position."

**[Action: Click "Run Analysis" button]**

"When I click Run Analysis, the orchestrator fires up all four agents in topological order. AR, AP, and Inventory run in parallel — they don't depend on each other. Then Cash Flow runs last, receiving all their outputs."

**[Screen: Agent cards animate — showing status idle → running → complete]**

"You can see each agent completing — the AR Agent found 18 invoices across 5 aging buckets, the AP Agent analyzed 12 vendor invoices with 4 discount opportunities, and the Inventory Agent classified 10 SKUs into ABC categories."

**[Screen: CCC summary cards populate with DSO, DIO, DPO, CCC values]**

"Here's our Cash Conversion Cycle: DSO of 48 days, DIO of 72 days, DPO of only 37 days, giving us a CCC of 83 days. The industry benchmark is 60. We're leaving 23 days of cash on the table."

**[Screen: Scroll to 13-week cash forecast chart]**

"The Cash Flow Agent built a 13-week rolling forecast. You can see our cash position declining through weeks 4 through 7 — that's our liquidity danger zone."

**[Screen: Scroll to recommendations feed]**

"Here are the actionable recommendations — each tagged with confidence level and financial impact. For example, the AP Agent identified three early-payment discounts where the annualized return exceeds our 8% cost of capital. Taking those discounts would save $12,000 per year."

---

### [1:50–2:20] Phoenix Cloud Traces

**[Screen: Switch to app.phoenix.arize.com — show trace dashboard]**

"Now here's what makes this different from a typical AI demo. Every single Gemini call is fully traced in Arize Phoenix Cloud."

**[Screen: Click on a trace — show the span details with prompt, response, latency]**

"I can drill into any agent's trace, see the exact prompt we sent, the raw LLM response, the parsed JSON, and the grounding check. This isn't a black box — judges can verify every claim."

**[Screen: Show Phoenix MCP server config]**

"We also configured the Phoenix MCP server, which means the agents can introspect their own traces at runtime — querying past prompts and identifying failure patterns."

---

### [2:20–2:40] Self-Improvement Loop

**[Screen: Evaluation scores panel — show radar/bar chart of 4 dimensions]**

"Each recommendation is evaluated by an LLM-as-Judge on four dimensions: relevance, actionability, financial impact, and risk awareness. Here you can see that our first run scored 6.2 overall."

**[Screen: Show score improving from 6.2 → 7.1 → 7.8 across three runs]**

"The self-improvement loop reads these scores, identifies systematic weaknesses — like recommendations that lack dollar amounts scoring 40% lower — and adjusts the agent prompts. After three iterations, our average score climbed from 6.2 to 7.8."

---

### [2:40–3:00] Summary + CTA

**[Screen: Back to WCO Dashboard — full view]**

"Working Capital Optimizer proves that multi-agent AI can deliver genuine domain expertise — not just summaries, but actionable financial recommendations that a CFO can execute tomorrow."

**[Screen: GitHub URL + Architecture diagram]**

"The code is open source. It's built with Gemini, Arize Phoenix, CockroachDB, and Next.js. Every agent is specialized, every trace is observable, and the system gets better on its own."

**[Screen: End card — WCO logo + Devpost URL]**

"Thank you."

---

## Recording Tips

- **Resolution**: 1920×1080 minimum
- **Browser**: Use a clean Chrome profile with the dashboard fullscreen (F11)
- **Phoenix Cloud**: Pre-login to app.phoenix.arize.com so you can switch tabs quickly
- **Timing**: Practice the click-through once before recording
- **Voice**: Speak slowly and clearly — 180 words per minute max
- **Edits**: Cut loading/spinner moments — jump straight to results appearing
- **Format**: MP4 or MOV, under 5 MB for Devpost (may need to compress)
