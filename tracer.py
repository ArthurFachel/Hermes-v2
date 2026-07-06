"""
Tracing — registra cada chamada de API com timing detalhado.
Cada requisição vira um arquivo JSON em traces/ com:
  - request/response completos
  - tool calls extraídas do output do Hermes (com duração)
  - timestamps de cada etapa
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

TRACES_DIR = Path(__file__).parent / "traces"


def _ensure_dir():
    TRACES_DIR.mkdir(parents=True, exist_ok=True)


def _trace_path(trace_id: str) -> Path:
    return TRACES_DIR / f"{trace_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_tool_calls(hermes_stdout: str) -> list:
    """Extrai tool calls do output do Hermes com duração cronometrada."""
    tools = []
    lines = hermes_stdout.split("\n")
    current_tool = None
    current_start = None

    for line in lines:
        # Procura início de tool call
        m = re.search(
            r"(?:\[TOOL_CALL\]|Tool[:\s]+|⚡|→|>>>|using tool|chamando)\s*(?P<name>[\w_.-]+)",
            line, re.IGNORECASE
        )
        if m:
            if current_tool:
                tools.append({
                    "tool": current_tool,
                    "duration_s": None,
                    "started_at": current_start,
                    "finished_at": None,
                    "note": "tool call sem duração detectada"
                })
            current_tool = m.group("name")
            current_start = _now_iso()
            continue

        # Procura duração
        dur_m = re.search(
            r"(?:duration|took|levou|em|finished|completed)[\s:]*"
            r"(?P<secs>[\d.]+)\s*(?:s|sec|seconds|segundos)?",
            line, re.IGNORECASE
        )
        if dur_m and current_tool:
            tools.append({
                "tool": current_tool,
                "duration_s": float(dur_m.group("secs")),
                "started_at": current_start,
                "finished_at": _now_iso()
            })
            current_tool = None
            current_start = None

    # Fecha tool call pendente
    if current_tool:
        tools.append({
            "tool": current_tool,
            "duration_s": None,
            "started_at": current_start,
            "finished_at": None,
            "note": "tool call sem duração detectada"
        })

    return tools


def save_trace(
    trace_id: str,
    session_id: str,
    request_data: dict,
    response_data: dict,
    hermes_stdout: str,
    hermes_stderr: str,
    hermes_returncode: int,
    duration_s: float,
    tool_calls: list,
    error: Optional[str] = None,
):
    """Salva um trace completo de uma requisição."""
    _ensure_dir()
    path = _trace_path(trace_id)
    trace = {
        "trace_id": trace_id,
        "session_id": session_id,
        "timestamp": _now_iso(),
        "duration_s": round(duration_s, 3),
        "request": request_data,
        "response": response_data,
        "hermes": {
            "returncode": hermes_returncode,
            "stdout": hermes_stdout,
            "stderr": hermes_stderr,
        },
        "tool_calls": tool_calls,
        "error": error,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
    return trace


def list_traces() -> list:
    _ensure_dir()
    traces = []
    for f in sorted(TRACES_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        with open(f, "r", encoding="utf-8") as fh:
            t = json.load(fh)
            traces.append({
                "trace_id": t["trace_id"],
                "session_id": t["session_id"],
                "timestamp": t["timestamp"],
                "duration_s": t["duration_s"],
                "tool_calls_count": len(t.get("tool_calls", [])),
                "error": t.get("error"),
            })
    return traces


def load_trace(trace_id: str) -> dict | None:
    path = _trace_path(trace_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
