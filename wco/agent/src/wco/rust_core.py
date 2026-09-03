from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]
_RUST_DIR = _ROOT / "rust"
_BINARY = _RUST_DIR / "target" / "release" / "wco-core"


def _run(command: list[str], payload: Any) -> dict[str, Any] | None:
    proc = subprocess.run(
        command,
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return None
    output = proc.stdout.decode("utf-8").strip()
    return json.loads(output) if output else {}


def run_rust_core(command: str, payload: Any) -> dict[str, Any] | None:
    if _BINARY.exists():
        result = _run([str(_BINARY), command], payload)
        if result is not None:
            return result

    if shutil.which("cargo"):
        return _run(
            ["cargo", "run", "--quiet", "--manifest-path", str(_RUST_DIR / "Cargo.toml"), "--", command],
            payload,
        )

    return None


def select_context(
    entries: list[dict[str, Any]],
    query: str,
    *,
    kind: str | None = None,
    source_agent: str | None = None,
    top_k: int = 10,
) -> list[str] | None:
    result = run_rust_core(
        "select-context",
        {
            "entries": entries,
            "query": query,
            "kind": kind,
            "source_agent": source_agent,
            "top_k": top_k,
        },
    )
    if result is None:
        return None
    return [str(entry_id) for entry_id in result.get("selected_entry_ids", [])]
