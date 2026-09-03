#!/usr/bin/env node
/**
 * Cubiczan WCO actions MCP launcher.
 *
 * CHP is the lock; MCP is the pipe. This package is the pipe: it execs the
 * existing Python mesh (`wco.mcp.actions_server`). It does not wrap Phoenix.
 */
import { spawnWcoActionsMcp } from "./launch.js";

const child = spawnWcoActionsMcp();
child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
