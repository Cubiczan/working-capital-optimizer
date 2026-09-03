# Design: WCO actions MCP

## Pattern

`@cubiczan/chp-mcp` is the lock/pipe split: CHP engine stays in the published
library; the MCP server is a thin stdio transport. Here the lock is the existing
WCO Python mesh. The pipe is stdio MCP.

```text
MCP client (Cursor / Claude / …)
        │  tools/call
        ▼
┌───────────────────────────────────┐
│  MCP server (transport)           │  @cubiczan/wco-mcp  /  wco mcp-actions
│  recommend_ar_actions             │
│  recommend_ap_actions             │
│  recommend_inventory_actions      │
│  recommend_cash_conversion_actions│
└─────────────────┬─────────────────┘
                  │ wraps
                  ▼
┌───────────────────────────────────┐
│  WCO Python agents (lock)         │
│  ARAgent · APAgent                │
│  InventoryAgent · CashFlowAgent   │
│  WorkingCapitalOrchestrator       │
└───────────────────────────────────┘
```

Phoenix (`wco mcp` / `npx @arizeai/phoenix-mcp`) stays on the side as
**trace introspection only**. It is not a dependency of the actions server.

## Offline path

`Settings.gemini_api_key` becomes optional. When `WCO_OFFLINE=1` or no Gemini
key is set, each specialist still runs `prepare_context()` (real aging / DSO /
DPO / DIO / CCC math) and emits grounded `CompressionStep` recommendations.
Gemini calls are skipped. This is how CI and keyless Cursor installs work.

When a Gemini key is present and offline is not forced, tools call the live
expand → compress cycle (same as FastAPI `/api/analyze`).

## Transport

- Python stdio JSON-RPC (newline-delimited MCP) is the real server.
- `@cubiczan/wco-mcp` is a Node launcher that execs `python -m wco.mcp.actions_server`.
- CLI: `wco mcp-actions` and console script `wco-mcp`.
- `wco mcp` remains the Phoenix traces helper.

## Non-goals

- Do not wrap Phoenix tools.
- Do not rebuild the Next.js UI.
- Do not publish npm or PyPI from this change.
