"""
Armazenamento em JSON — toda requisição é salva com estrutura completa.
Cada sessão é um arquivo JSON em data/ contendo todo o histórico.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"


def _session_path(session_id: str) -> Path:
    return DATA_DIR / f"{session_id}.json"


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(session_id: str) -> dict:
    _ensure_dir()
    path = _session_path(session_id)
    if path.exists():
        return load_session(session_id)
    session = {
        "session_id": session_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "turnos": 0,
        "history": []
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    return session


def load_session(session_id: str) -> dict | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_session(session: dict):
    path = _session_path(session["session_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def append_message(session_id: str, role: str, content: str):
    session = load_session(session_id)
    if not session:
        session = create_session(session_id)
    from datetime import datetime, timezone
    session["history"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    session["turnos"] = len([m for m in session["history"] if m["role"] == "user"])
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return session


def list_sessions() -> list:
    _ensure_dir()
    sessions = []
    for f in sorted(DATA_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        with open(f, "r", encoding="utf-8") as fh:
            s = json.load(fh)
            sessions.append({
                "session_id": s["session_id"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "turnos": s["turnos"]
            })
    return sessions


def delete_session(session_id: str) -> bool:
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def session_exists(session_id: str) -> bool:
    return _session_path(session_id).exists()
