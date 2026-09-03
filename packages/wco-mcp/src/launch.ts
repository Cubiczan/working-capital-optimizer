import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/**
 * Resolve the WCO Python agent `src/` directory when this package lives
 * inside the working-capital-optimizer repo (`packages/wco-mcp`).
 */
export function resolveBundledAgentSrc(): string | undefined {
  const candidates = [
    process.env.WCO_AGENT_SRC,
    path.resolve(here, "../../../wco/agent/src"),
    path.resolve(here, "../../wco/agent/src"),
  ].filter((value): value is string => Boolean(value));

  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, "wco", "mcp", "actions_server.py"))) {
      return candidate;
    }
  }
  return undefined;
}

export function spawnWcoActionsMcp(): ChildProcess {
  const python = process.env.WCO_PYTHON || "python3";
  const env = { ...process.env };
  const bundled = resolveBundledAgentSrc();
  if (bundled) {
    env.PYTHONPATH = env.PYTHONPATH
      ? `${bundled}${path.delimiter}${env.PYTHONPATH}`
      : bundled;
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
  return child;
}
