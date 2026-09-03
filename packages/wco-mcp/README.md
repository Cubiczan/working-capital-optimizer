# `@cubiczan/wco-mcp`

Stdio MCP for **Cubiczan Working Capital Optimizer *actions*** — AR collections,
AP payment timing, inventory policy, and cash-conversion recommendations.

Wraps the existing Python agent mesh (`ARAgent`, `APAgent`, `InventoryAgent`,
`CashFlowAgent`). Does **not** wrap Phoenix.

Intended npm name: `@cubiczan/wco-mcp` (longer alias:
`@cubiczan/working-capital-optimizer-mcp`). Packaging is prepared; this tree is
not published from the change that added it.

## CHP is the lock; MCP is the pipe

```text
MCP client (Cursor / Claude / …)
        |  tools/call
        v
+-----------------------------------+
|  MCP server (transport)           |  <-- you are here (@cubiczan/wco-mcp)
|  recommend_ar_actions             |
|  recommend_ap_actions             |
|  recommend_inventory_actions      |
|  recommend_cash_conversion_actions|
+-----------------+-----------------+
                  | wraps
                  v
+-----------------------------------+
|  WCO Python agents (lock)         |
|  same FastAPI / CLI mesh          |
+-----------------------------------+
```

Same split as [`@cubiczan/chp-mcp`](https://www.npmjs.com/package/@cubiczan/chp-mcp):
the protocol engine stays in the product library; MCP is only transport.

## This is not Phoenix MCP

| Server | Command | What it returns |
|--------|---------|-----------------|
| **WCO actions** (this package) | `npx -y @cubiczan/wco-mcp` or `wco mcp-actions` | Recommended working-capital **actions** |
| **Phoenix** | `wco mcp` or `npx -y @arizeai/phoenix-mcp` | OpenInference **traces** only |

Phoenix MCP cannot recommend AR/AP/inventory/cash actions. Do not point an
actions client at `@arizeai/phoenix-mcp`.

## Install

From this repo (offline / fixture path, no Gemini key):

```bash
cd wco/agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Cursor / Claude Desktop (`mcp.json`)

```json
{
  "mcpServers": {
    "wco": {
      "command": "npx",
      "args": ["-y", "@cubiczan/wco-mcp"],
      "env": {
        "WCO_OFFLINE": "1"
      }
    }
  }
}
```

From a clone, until the npm package is published:

```json
{
  "mcpServers": {
    "wco": {
      "command": "node",
      "args": ["/absolute/path/to/working-capital-optimizer/packages/wco-mcp/bin/wco-mcp.js"],
      "env": {
        "WCO_OFFLINE": "1"
      }
    }
  }
}
```

Or call Python directly:

```json
{
  "mcpServers": {
    "wco": {
      "command": "python",
      "args": ["-m", "wco.mcp.actions_server"],
      "cwd": "/absolute/path/to/working-capital-optimizer/wco/agent",
      "env": {
        "WCO_OFFLINE": "1"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add wco -- npx -y @cubiczan/wco-mcp
# or, from a clone:
claude mcp add wco -- python -m wco.mcp.actions_server
```

Set `WCO_OFFLINE=1` for demo fixtures. Set `GEMINI_API_KEY` and omit
`WCO_OFFLINE` to run the live expand → compress cycle.

## Tools

| Tool | Maps to | Purpose |
|------|---------|---------|
| `recommend_ar_actions` | `ARAgent` | Collections, DSO, credit-term actions |
| `recommend_ap_actions` | `APAgent` | Payment timing, dynamic discounts, DPO |
| `recommend_inventory_actions` | `InventoryAgent` | DIO, safety stock, ABC policy |
| `recommend_cash_conversion_actions` | Full mesh → `CashFlowAgent` | CCC = DSO + DIO − DPO plus 13-week actions |
| `wco_version` | — | Package / mode / Phoenix split |

All action tools accept `use_sample_data` (default `true`) and optional `data`.

## Licence

MIT. Brand: Cubiczan.
