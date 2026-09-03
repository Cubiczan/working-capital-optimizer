# Change: WCO actions MCP

## Why

Cursor and Claude can already attach Phoenix MCP (`wco mcp` / `@arizeai/phoenix-mcp`)
and inspect traces. That is not the gap. Operators need the four specialist agents’
working-capital **actions** — AR collections, AP payment timing, inventory
policy, and cash-conversion recommendations — as product-native MCP tools.

CHP is the lock; MCP is the pipe. Follow `@cubiczan/chp-mcp`: stdio transport,
Cursor `mcp.json`, `claude mcp add`, intended npm name `@cubiczan/wco-mcp`.

## What Changes

- Add a stdio MCP server that wraps the existing Python/FastAPI agent mesh
  (`ARAgent`, `APAgent`, `InventoryAgent`, `CashFlowAgent`) and returns
  recommended actions with the same `TurnResult` shape the product already uses.
- Add an offline / fixture path so tools run without a Gemini key (demo data +
  deterministic, grounded recommendations from each agent’s `prepare_context()`).
- Prepare `@cubiczan/wco-mcp` packaging (npm + `wco mcp-actions` / `wco-mcp`
  entry points). Do not publish to npm or PyPI in this change.
- Document that Phoenix MCP is traces-only and must not be wrapped.

## Impact

- Affected: `wco/agent` Python mesh, new `packages/wco-mcp` transport, root README.
- Not affected: Next.js dashboard (do not rebuild the UI).
- Tests: `tools/list` plus one AR or cash-conversion recommendation against
  demo/fixture data.
