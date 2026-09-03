# Publish checklist — WCO actions MCP

Do **not** publish to npm or PyPI from the change that introduced this package.
Packaging is prepared so a later human release can ship `@cubiczan/wco-mcp`
(alias intent: `@cubiczan/working-capital-optimizer-mcp`).

Brand: **Cubiczan** (never CubicZan).

## When a human is ready (not this run)

```bash
# npm (OTP in browser) — only after review
cd packages/wco-mcp
npm whoami          # expect: cubiczan
npm run build
npm publish --access public
# Do not run the above in the agent session that added this file.

# Optional second name once the first is live:
#   npm publish --access public --tag alias
```

PyPI `wco-agent` already exposes console scripts `wco` and `wco-mcp`.
Do not `twine upload` from this change.

## Verify locally instead

```bash
cd wco/agent
pip install -e ".[dev]"
WCO_OFFLINE=1 pytest tests/test_mcp_actions.py

# stdio smoke
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python -m wco.mcp.actions_server
```
