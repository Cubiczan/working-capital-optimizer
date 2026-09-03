## ADDED Requirements

### Requirement: Actions MCP exposes specialist working-capital tools

The system SHALL expose a stdio MCP server whose tools run the existing WCO
Python mesh (receivable, payable, inventory, cash) and return recommended
actions. The server SHALL NOT wrap Phoenix trace tools.

#### Scenario: tools/list names the four action tools

- **WHEN** a client sends MCP `tools/list`
- **THEN** the response includes `recommend_ar_actions`, `recommend_ap_actions`,
  `recommend_inventory_actions`, and `recommend_cash_conversion_actions`

#### Scenario: AR recommendation against demo data

- **GIVEN** fixture / sample manufacturing data and no Gemini key (offline path)
- **WHEN** a client calls `recommend_ar_actions` with `use_sample_data: true`
- **THEN** the tool returns at least one recommendation from `ARAgent` with
  insight, recommendation text, expected impact, and a trace id

### Requirement: Offline path without Gemini

When `WCO_OFFLINE` is set or `GEMINI_API_KEY` is empty, tools SHALL still run
each specialist’s `prepare_context()` and return grounded recommendations.

#### Scenario: Cash conversion on fixtures

- **GIVEN** sample AR, AP, and inventory fixtures
- **WHEN** `recommend_cash_conversion_actions` is called
- **THEN** the response includes CCC components derived from the mesh and at
  least one cash-conversion recommendation

### Requirement: Phoenix MCP stays traces-only

Documentation and the `wco mcp` command SHALL describe Phoenix MCP as
trace introspection only and SHALL point action clients at `@cubiczan/wco-mcp`
or `wco mcp-actions`.

#### Scenario: Install docs distinguish the two servers

- **WHEN** a reader follows the README MCP section
- **THEN** they see Cursor `mcp.json` and `claude mcp add` for the actions
  server, plus an explicit note that Phoenix MCP is traces-only
