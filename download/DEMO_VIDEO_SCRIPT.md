# Working Capital Optimizer — 3-Minute Demo Video Script

## Setup Instructions
1. Open `wco-demo.html` in Chrome/Edge (fullscreen recommended — press F11)
2. Use OBS Studio, Loom, or built-in screen recorder
3. The presentation auto-plays for exactly 3 minutes
4. Record your screen + narrate using the script below
5. Export as MP4, upload to YouTube

---

## Narration Script with Timing

### [0:00–0:10] Title Slide

> "Hi, I'm presenting the Working Capital Optimizer — an AI agent mesh built for the Google Cloud Rapid Agent Hackathon on the Arize track."

*(Slide auto-advances)*

### [0:10–0:30] The Problem

> "Manufacturing CFOs manage a two-point-four trillion dollar working capital puzzle. The average cash conversion cycle sits at fifty-eight days, and one in three companies can't predict their cash flow even thirty days out. Existing tools give you dashboards but not decisions. That's the problem we solve."

*(Slide auto-advances)*

### [0:30–0:55] Architecture

> "Here's how it works. A Next.js dashboard talks to a FastAPI backend running a four-agent orchestrator. Each agent — AR, AP, Inventory, and Cash Flow — is powered by Gemini 2.5 Flash using the Agent Development Kit with a custom expand-then-compress reasoning cycle. Every single LLM call is instrumented with OpenInference and traced to Arize Phoenix Cloud in real time."

*(Slide auto-advances)*

### [0:55–1:20] The Four Agents

> "Let me walk through the agents. The AR Agent analyzes receivables aging and collection patterns to find early-payment discount opportunities. The AP Agent optimizes payment timing across vendors, calculating the annualized return on dynamic discounting. The Inventory Agent classifies SKUs by ABC analysis and flags safety-stock issues. Finally, the Cash Flow Agent consolidates everything into a unified thirteen-week forecast with liquidity risk flags."

*(Slide auto-advances)*

### [1:20–1:45] CCC Formula & Impact

> "The Cash Conversion Cycle — DSO plus DIO minus DPO — is the key metric. In our sample dataset modeling a fourteen-million-dollar manufacturer, we start at a CCC of seventy-five days. After the agents run, they identify actions that bring it down to forty-seven days. That's a thirty-seven percent improvement — which for this company means roughly two-point-eight million dollars freed up in working capital."

*(Slide auto-advances)*

### [1:45–2:10] Arize Phoenix Integration

> "Now here's what makes this a proper Arize track submission. First, every Gemini call is traced using OpenInference instrumentation. Second, traces export to Phoenix Cloud with bearer authentication. Third, we use LLM-as-Judge — Gemini Flash evaluates every recommendation on four dimensions: relevance, actionability, financial impact, and risk awareness. Fourth — and this is the self-improvement loop — when rolling average eval scores drop below a threshold, the system generates targeted prompt amendments and applies them to the next run. The agents literally get better over time."

*(Slide auto-advances)*

### [2:10–2:35] Dashboard Preview

> "The dashboard brings it all together. The main CCC gauge shows your current cycle. Agent cards report status and recent findings. A thirteen-week forecast chart shows projected cash position with confidence bands. And the recommendation feed surfaces the highest-impact actions ranked by the LLM-as-Judge scores."

*(Slide auto-advances)*

### [2:35–3:00] Closing

> "Working Capital Optimizer: four specialized AI agents, full Phoenix Cloud observability, and a self-improvement loop that makes every run smarter than the last. Check out the repo at github.com/Cubiczan/working-capital-optimizer. Thanks for watching."

---

## Quick Reference: What Judges Need to See

| Time | Must Show |
|------|-----------|
| 0:30 | Multi-agent architecture (4 agents) |
| 0:55 | Gemini + ADK runtime (code-owned) |
| 1:45 | Phoenix tracing + MCP + LLM-as-Judge |
| 2:00 | Self-improvement loop mechanism |
| 2:35 | Dashboard + repo link |

## Recording Tips
- **Resolution:** 1920×1080 (1080p minimum)
- **Audio:** Use a decent microphone — clear narration matters more than fancy visuals
- **Pacing:** Don't rush — the slides auto-advance on a comfortable timer
- **If you mess up:** Just restart the HTML — it resets to slide 1 on page reload
- **YouTube title suggestion:** "Working Capital Optimizer — Google Cloud Rapid Agent Hackathon"
- **YouTube description:** Link to the GitHub repo + Devpost submission
