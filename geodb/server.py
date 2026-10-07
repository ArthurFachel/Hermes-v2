#!/usr/bin/env python3
"""
GeoDB — servico de consulta a base geologica estruturada.

Uma porta, dois consumidores:

  REST  /v1/...   para humanos e para quem mantem o dado (OpenAPI em /docs)
  MCP   /mcp      para o Hermes, como ferramentas tipadas

O servico e somente-leitura e nao devolve caminho de arquivo nem detalhe de
infraestrutura. Autenticacao por header X-API-Key quando GEODB_TOKEN esta
definido.

Variaveis de ambiente:
  GEODB_PATH           caminho do SQLite (default: ./geo.db)
  GEODB_TOKEN          token exigido no header X-API-Key. Se vazio, serve aberto
                       e registra um aviso no log.
  GEODB_ALLOWED_HOSTS  hosts aceitos pelo MCP, separados por virgula. Necessario
                       para acesso remoto (default: localhost,127.0.0.1).
  PORT                 porta HTTP (default: 9000)
  HOST                 interface de bind (default: 127.0.0.1)
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import consultas as gdb

log = logging.getLogger("geodb")

TOKEN = os.environ.get("GEODB_TOKEN", "").strip()
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("GEODB_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

DESCRICAO = (
    "Base estruturada de geologia sedimentar. Cada fato devolvido traz a "
    "referencia bibliografica que o sustenta. Consulte esta base antes de "
    "responder qualquer pergunta sobre bacias, formacoes, geoquimica organica, "
    "fosseis ou pocos; os valores aqui sao exatos e preferem-se a estimativas."
)


# ── Autenticacao ─────────────────────────────────────────────────────────────

def exigir_token(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if not TOKEN:
        return
    if not x_api_key:
        raise HTTPException(status_code=401, detail="header X-API-Key ausente")
    if not secrets.compare_digest(x_api_key, TOKEN):
        raise HTTPException(status_code=401, detail="chave invalida")


# Rotas publicas: health e a documentacao OpenAPI.
ROTAS_ABERTAS = ("/health", "/docs", "/redoc", "/openapi.json")


class AutenticacaoMiddleware:
    """
    Autentica no nivel ASGI.

    O Depends do FastAPI nao alcanca apps montados, entao /mcp ficaria aberto se
    a verificacao vivesse apenas nas rotas REST. Este middleware cobre as duas
    superficies.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not TOKEN:
            await self.app(scope, receive, send)
            return
        caminho = scope.get("path", "")
        if caminho.startswith(ROTAS_ABERTAS):
            await self.app(scope, receive, send)
            return
        enviada = ""
        for nome, valor in scope.get("headers", []):
            if nome.lower() == b"x-api-key":
                enviada = valor.decode("latin-1")
                break
        if not (enviada and secrets.compare_digest(enviada, TOKEN)):
            resposta = JSONResponse({"detail": "chave invalida ou ausente"}, status_code=401)
            await resposta(scope, receive, send)
            return
        await self.app(scope, receive, send)


# ── Ferramentas MCP ──────────────────────────────────────────────────────────

mcp = MCPServer(
    name="geodb",
    title="GeoDB — Bacias Sedimentares",
    instructions=DESCRICAO,
    version="0.1.0",
)


@mcp.tool(description="Lista as bacias sedimentares disponiveis na base.")
def listar_bacias() -> list[dict[str, Any]]:
    return gdb.listar_bacias()


@mcp.tool(description=(
    "Ficha completa de uma bacia: area, orientacao, contexto tectonico, "
    "sequencias estratigraficas e grupos. Use para perguntas gerais sobre a bacia."))
def descrever_bacia(nome: str) -> dict[str, Any]:
    r = gdb.descrever_bacia(nome)
    return r or {"encontrado": False, "mensagem": f"Nenhuma bacia chamada '{nome}' na base."}


@mcp.tool(description=(
    "Lista as formacoes de uma bacia em ordem estratigrafica, da base para o topo. "
    "Filtre por grupo (ex.: 'Santana') ou por sequencia (ex.: 'Pos-Rifte I')."))
def listar_formacoes(grupo: str | None = None, sequencia: str | None = None) -> list[dict[str, Any]]:
    return gdb.listar_formacoes(grupo=grupo, sequencia=sequencia)


@mcp.tool(description=(
    "Ficha completa de uma formacao geologica: idade, litologia, espessura, "
    "ambiente deposicional, geoquimica e conteudo fossilifero. Aceita o nome com "
    "ou sem o prefixo 'Formacao'."))
def descrever_formacao(nome: str) -> dict[str, Any]:
    r = gdb.descrever_formacao(nome)
    return r or {"encontrado": False, "mensagem": f"Nenhuma formacao chamada '{nome}' na base."}


@mcp.tool(description=(
    "Dados de geoquimica organica de uma formacao: faixa de COT, tipo de "
    "querogenio, maturidade termica e metodo analitico. Use sempre que a pergunta "
    "envolver COT, querogenio, rocha geradora ou potencial de geracao."))
def geoquimica_formacao(nome: str) -> list[dict[str, Any]]:
    return gdb.geoquimica_formacao(nome)


@mcp.tool(description="Conteudo fossilifero registrado para uma formacao.")
def fosseis_formacao(nome: str) -> list[dict[str, Any]]:
    return gdb.fosseis_formacao(nome)


@mcp.tool(description=(
    "Em quais formacoes ocorre um grupo fossil (ex.: 'pterossauros', 'ostracodes')."))
def buscar_fossil(grupo_biologico: str) -> list[dict[str, Any]]:
    return gdb.buscar_fossil(grupo_biologico)


@mcp.tool(description=(
    "Dados de um poco exploratorio: sub-bacia e profundidade do embasamento."))
def buscar_poco(nome: str) -> dict[str, Any]:
    r = gdb.buscar_poco(nome)
    return r or {"encontrado": False, "mensagem": f"Nenhum poco '{nome}' na base."}


@mcp.tool(description=(
    "Divergencias conhecidas da literatura sobre um tema (ex.: 'ingressao marinha', "
    "'sequencias estratigraficas'). Devolve SEMPRE as duas posicoes com suas fontes. "
    "Chame esta ferramenta antes de afirmar algo como consenso."))
def controversias(tema: str | None = None) -> list[dict[str, Any]]:
    return gdb.controversias(tema)


@mcp.tool(description=(
    "Busca textual livre nas descricoes das formacoes quando voce nao sabe o nome "
    "exato. Ex.: 'evaporitos gipsita', 'calcario laminado'."))
def busca_livre(termo: str, limite: int = 10) -> list[dict[str, Any]]:
    return gdb.busca_livre(termo, limite=min(max(limite, 1), 50))


# ── App HTTP ─────────────────────────────────────────────────────────────────

mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=ALLOWED_HOSTS + [f"{h}:*" for h in ALLOWED_HOSTS],
        allowed_origins=["*"],
    ),
)

app = FastAPI(
    title="GeoDB",
    description=DESCRICAO + "\n\nEndpoint MCP para agentes: `/mcp`.",
    version="0.1.0",
    lifespan=lambda _app: mcp_app.router.lifespan_context(_app),
)

V1 = "/v1"
protegido = [Depends(exigir_token)]


@app.get("/health", summary="Health check (publico)")
def health() -> dict[str, Any]:
    try:
        stats = gdb.estatisticas()
        return {"status": "ok", "registros": stats, "auth": bool(TOKEN)}
    except gdb.BaseIndisponivel:
        return JSONResponse({"status": "degraded", "erro": "base indisponivel"}, status_code=503)


@app.get(V1 + "/bacias", dependencies=protegido, summary="Lista bacias")
def r_bacias() -> list[dict[str, Any]]:
    return gdb.listar_bacias()


@app.get(V1 + "/bacias/{nome}", dependencies=protegido, summary="Ficha da bacia")
def r_bacia(nome: str) -> dict[str, Any]:
    r = gdb.descrever_bacia(nome)
    if not r:
        raise HTTPException(404, f"bacia '{nome}' nao encontrada")
    return r


@app.get(V1 + "/formacoes", dependencies=protegido, summary="Lista formacoes")
def r_formacoes(
    grupo: str | None = Query(None), sequencia: str | None = Query(None)
) -> list[dict[str, Any]]:
    return gdb.listar_formacoes(grupo=grupo, sequencia=sequencia)


@app.get(V1 + "/formacoes/{nome}", dependencies=protegido, summary="Ficha da formacao")
def r_formacao(nome: str) -> dict[str, Any]:
    r = gdb.descrever_formacao(nome)
    if not r:
        raise HTTPException(404, f"formacao '{nome}' nao encontrada")
    return r


@app.get(V1 + "/formacoes/{nome}/geoquimica", dependencies=protegido, summary="Geoquimica organica")
def r_geoquimica(nome: str) -> list[dict[str, Any]]:
    return gdb.geoquimica_formacao(nome)


@app.get(V1 + "/formacoes/{nome}/fosseis", dependencies=protegido, summary="Conteudo fossilifero")
def r_fosseis(nome: str) -> list[dict[str, Any]]:
    return gdb.fosseis_formacao(nome)


@app.get(V1 + "/fosseis", dependencies=protegido, summary="Formacoes que contem um grupo fossil")
def r_busca_fossil(grupo_biologico: str = Query(...)) -> list[dict[str, Any]]:
    return gdb.buscar_fossil(grupo_biologico)


@app.get(V1 + "/pocos", dependencies=protegido, summary="Lista pocos")
def r_pocos() -> list[dict[str, Any]]:
    return gdb.listar_pocos()


@app.get(V1 + "/pocos/{nome}", dependencies=protegido, summary="Ficha do poco")
def r_poco(nome: str) -> dict[str, Any]:
    r = gdb.buscar_poco(nome)
    if not r:
        raise HTTPException(404, f"poco '{nome}' nao encontrado")
    return r


@app.get(V1 + "/controversias", dependencies=protegido, summary="Divergencias na literatura")
def r_controversias(tema: str | None = Query(None)) -> list[dict[str, Any]]:
    return gdb.controversias(tema)


@app.get(V1 + "/busca", dependencies=protegido, summary="Busca textual nas formacoes")
def r_busca(termo: str = Query(...), limite: int = Query(10, ge=1, le=50)) -> list[dict[str, Any]]:
    return gdb.busca_livre(termo, limite=limite)


app.mount("/mcp", mcp_app)
app.add_middleware(AutenticacaoMiddleware)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not TOKEN:
        log.warning("GEODB_TOKEN nao definido: o servico esta servindo SEM autenticacao.")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "9000"))
    log.info("GeoDB em http://%s:%d  (REST /v1, MCP /mcp, docs /docs)", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
