#!/usr/bin/env node
/**
 * Cubiczan WCO actions MCP — stdio pipe over the Python agent mesh.
 * Phoenix MCP (`wco mcp` / @arizeai/phoenix-mcp) is traces-only.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const python = process.env.WCO_PYTHON || "python3";
const env = { ...process.env };

const candidates = [
  process.env.WCO_AGENT_SRC,
  path.resolve(here, "../../../wco/agent/src"),
  path.resolve(here, "../../wco/agent/src"),
].filter(Boolean);

for (const candidate of candidates) {
  if (existsSync(path.join(candidate, "wco", "mcp", "actions_server.py"))) {
    env.PYTHONPATH = env.PYTHONPATH
      ? `${candidate}${path.delimiter}${env.PYTHONPATH}`
      : candidate;
    break;
  }
}

if (!env.GEMINI_API_KEY && env.WCO_OFFLINE === undefined) {
  env.WCO_OFFLINE = "1";
}

const child = spawn(python, ["-m", "wco.mcp.actions_server"], {
  stdio: "inherit",
  env,
});

child.on("error", (error) => {
  console.error(
    "[@cubiczan/wco-mcp] failed to start the Python actions server.",
    "Install the WCO agent (`pip install -e wco/agent`) or set WCO_PYTHON / WCO_AGENT_SRC.",
    error,
  );
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
