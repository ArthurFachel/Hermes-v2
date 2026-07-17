#!/usr/bin/env python3
"""
Hermes-Geo v2 — API FastAPI simplificada.
Sem Redis, sem RQ, sem dependências pesadas.
Toda requisição é salva em JSON com estrutura completa + histórico.
Cada chamada de API é traçada em traces/ com tool calls cronometradas.
"""

import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db.database import (
    create_session,
    load_session,
    append_message,
    list_sessions,
    delete_session,
    session_exists,
)
from tracer import save_trace, list_traces, load_trace, _parse_tool_calls
from db.auth import require_api_key, create_key, revoke_key, PREFIX_LEN
from db.db_keys import init_db as init_keys_db, list_keys as list_api_keys

# ── Config ──────────────────────────────────────────────────────────────────
MAX_TURNS = int(os.environ.get("MAX_TURNS", "50"))
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# ── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Hermes-Geo v2",
    description="API simplificada para Hermes Agent. Toda requisição salva em JSON com histórico + trace com tool calls cronometradas.",
    version="2.0.0"
)


# Inicializa DB de chaves na carga do módulo
init_keys_db()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Mensagem do usuário")
    session_id: Optional[str] = Field(None, description="ID da sessão existente")
    new_session: bool = Field(False, description="Forçar nova sessão")


class ChatResponse(BaseModel):
    session_id: str
    response: str
    turnos: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_stdout(raw: str) -> str:
    text = _ANSI_RE.sub("", raw).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()
    return text


def _build_query(history: list, query: str) -> str:
    if not history:
        return query
    historico_json = json.dumps(history, ensure_ascii=False, indent=2)
    instruction = (
        "INSTRUCAO DE SISTEMA: a pergunta a seguir faz parte de uma sessao ja em "
        "andamento. Responda usando as informacoes contidas no "
        "historico desta sessao (fornecido em JSON abaixo). "
    )
    return f"{instruction}\n\nHistorico da sessao (JSON):\n{historico_json}\n\nPergunta atual: {query}"


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/chat", summary="Enviar mensagem para o Hermes")
async def chat(body: ChatRequest, _: str = Depends(require_api_key)):
    """Envia uma mensagem para o Hermes CLI e retorna a resposta."""
    import time as time_module
    _start = time_module.time()

    session_id = body.session_id
    if body.new_session or not session_id:
        session_id = str(uuid.uuid4())
        create_session(session_id)
    elif not session_exists(session_id):
        return JSONResponse(
            {"error": "session_id invalida ou expirada"}, status_code=404
        )

    session = load_session(session_id)
    history = session["history"] if session else []

    query_to_send = _build_query(history, body.query)
    append_message(session_id, "user", body.query)

    error = None
    hermes_stdout = ""
    hermes_stderr = ""
    hermes_returncode = -1
    resposta = ""

    try:
        result = subprocess.run(
            ["hermes", "chat", "-q", query_to_send, "-Q"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        hermes_stdout = result.stdout
        hermes_stderr = result.stderr
        hermes_returncode = result.returncode

        if result.returncode != 0:
            stderr = result.stderr.strip() or "(sem saida de erro)"
            resposta = f"Erro no hermes (rc={result.returncode}): {stderr}"
            error = resposta
        else:
            resposta = _clean_stdout(result.stdout)
    except FileNotFoundError:
        resposta = "Erro: comando 'hermes' nao encontrado no PATH."
        error = "hermes_not_found"
        hermes_returncode = -1
        append_message(session_id, "assistant", resposta)
        _duration = time.time() - _start
        save_trace(
            trace_id=str(uuid.uuid4()),
            session_id=session_id,
            request_data=body.model_dump(),
            response_data={"error": error},
            hermes_stdout="",
            hermes_stderr="",
            hermes_returncode=-1,
            duration_s=_duration,
            tool_calls=[],
            error=error,
        )
        return JSONResponse(
            {"session_id": session_id, "response": resposta, "error": error},
            status_code=500
        )
    except subprocess.TimeoutExpired:
        resposta = "Erro: tempo limite excedido (120s)."
        error = "timeout"
        append_message(session_id, "assistant", resposta)
        _duration = time.time() - _start
        save_trace(
            trace_id=str(uuid.uuid4()),
            session_id=session_id,
            request_data=body.model_dump(),
            response_data={"error": error},
            hermes_stdout="",
            hermes_stderr="",
            hermes_returncode=-1,
            duration_s=_duration,
            tool_calls=[],
            error=error,
        )
        return JSONResponse(
            {"session_id": session_id, "response": resposta, "error": "timeout"},
            status_code=504
        )

    # Salva resposta do assistente
    session = append_message(session_id, "assistant", resposta)

    # Extrai tool calls do stdout
    tool_calls = _parse_tool_calls(hermes_stdout)

    # Salva trace
    _duration = time.time() - _start
    save_trace(
        trace_id=str(uuid.uuid4()),
        session_id=session_id,
        request_data=body.model_dump(),
        response_data={"response": resposta, "turnos": session["turnos"]},
        hermes_stdout=hermes_stdout,
        hermes_stderr=hermes_stderr,
        hermes_returncode=hermes_returncode,
        duration_s=_duration,
        tool_calls=tool_calls,
        error=error,
    )

    return {
        "session_id": session_id,
        "response": resposta,
        "turnos": session["turnos"]
    }


@app.get("/sessions", summary="Listar todas as sessões")
async def list_all_sessions(_: str = Depends(require_api_key)):
    """Retorna todas as sessões com metadados."""
    sessions = list_sessions()
    return {"total": len(sessions), "sessions": sessions}


@app.get("/sessions/{session_id}", summary="Obter histórico completo de uma sessão")
async def get_session(session_id: str, _: str = Depends(require_api_key)):
    """Retorna o JSON completo de uma sessão, incluindo todo o histórico."""
    session = load_session(session_id)
    if not session:
        return JSONResponse({"error": "session_id nao encontrada"}, status_code=404)
    return session


@app.delete("/sessions/{session_id}", summary="Deletar uma sessão")
async def delete_session_endpoint(session_id: str, _: str = Depends(require_api_key)):
    """Remove uma sessão e seu arquivo JSON."""
    if not session_exists(session_id):
        return JSONResponse({"error": "session_id nao encontrada"}, status_code=404)
    delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.get("/traces", summary="Listar todos os traces")
async def list_all_traces(_: str = Depends(require_api_key)):
    """Retorna todos os traces com metadados."""
    traces = list_traces()
    return {"total": len(traces), "traces": traces}


@app.get("/traces/{trace_id}", summary="Obter trace completo")
async def get_trace(trace_id: str, _: str = Depends(require_api_key)):
    """Retorna o JSON completo de um trace."""
    trace = load_trace(trace_id)
    if not trace:
        return JSONResponse({"error": "trace_id nao encontrado"}, status_code=404)
    return trace


@app.get("/health", summary="Health check")
async def health():
    """Verifica se a API e o Hermes CLI estão operacionais."""
    hermes_ok = True
    try:
        subprocess.run(["hermes", "--version"], capture_output=True, timeout=5)
    except Exception:
        hermes_ok = False

    return {
        "status": "ok" if hermes_ok else "degraded",
        "hermes_cli": "ok" if hermes_ok else "not_found",
        "sessoes_ativas": len(list_sessions()),
        "traces_count": len(list_traces())
    }


# ── API Key management endpoints ────────────────────────────────────────────


class CreateKeyRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Owner label, e.g. 'unisinos'")


@app.post("/keys", summary="Criar nova API key")
async def create_api_key(body: CreateKeyRequest, _: str = Depends(require_api_key)):
    """Gera uma nova API key. A chave raw é mostrada apenas uma vez."""
    raw_key = create_key(body.user_id)
    return {
        "user_id": body.user_id,
        "prefix": raw_key[:PREFIX_LEN],
        "key": raw_key,
        "warning": "Store this key now — it will NOT be shown again."
    }


@app.get("/keys", summary="Listar todas as API keys")
async def list_api_keys_endpoint(_: str = Depends(require_api_key)):
    """Retorna todas as chaves (sem segredos)."""
    return {"keys": list_api_keys()}


@app.delete("/keys/{key_prefix}", summary="Revogar chave(s) por prefixo")
async def revoke_api_key(key_prefix: str, _: str = Depends(require_api_key)):
    """Revoga todas as chaves ativas com o prefixo informado."""
    count = revoke_key(key_prefix)
    if count:
        return {"status": "revoked", "prefix": key_prefix, "count": count}
    return JSONResponse(
        {"error": f"No active keys found with prefix '{key_prefix}'"},
        status_code=404,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"Hermes-Geo v2 rodando em http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
