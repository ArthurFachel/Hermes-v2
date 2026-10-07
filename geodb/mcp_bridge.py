#!/usr/bin/env python3
"""
Ponte stdio → HTTP para a GeoDB.

O Hermes conversa com esta ponte por stdio (um subprocesso), e a ponte conversa
com o servico GeoDB pela rede. A base continua do outro lado da porta: trocar
GEODB_URL de 127.0.0.1 para o host da UNISINOS e nada mais muda.

Por que existir, se o servico ja fala MCP em /mcp: o SDK mcp embutido em algumas
instalacoes do Hermes nao resolve o cliente HTTP em runtime, e o transporte stdio
funciona em todas. O endpoint /mcp segue disponivel para clientes que o suportem.

Variaveis de ambiente:
  GEODB_URL    base do servico (default: http://127.0.0.1:9000)
  GEODB_TOKEN  token enviado em X-API-Key
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

BASE = os.environ.get("GEODB_URL", "http://127.0.0.1:9000").rstrip("/")
TOKEN = os.environ.get("GEODB_TOKEN", "").strip()
TIMEOUT = float(os.environ.get("GEODB_TIMEOUT", "20"))

_INDISPONIVEL = (
    "A base geologica esta indisponivel no momento. Responda a partir das demais "
    "fontes e sinalize que o dado estruturado nao pode ser consultado."
)

mcp = MCPServer(
    name="geodb",
    title="GeoDB — Bacias Sedimentares",
    instructions=(
        "Base estruturada de geologia sedimentar. Cada fato devolvido traz a referencia "
        "bibliografica que o sustenta. Consulte esta base antes de responder perguntas "
        "sobre bacias, formacoes, geoquimica organica, fosseis ou pocos: os valores aqui "
        "sao exatos e devem ser preferidos a estimativas."
    ),
    version="0.1.0",
)


def _buscar(caminho: str, params: dict[str, Any] | None = None) -> Any:
    cabecalhos = {"X-API-Key": TOKEN} if TOKEN else {}
    limpos = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        r = httpx.get(f"{BASE}{caminho}", params=limpos, headers=cabecalhos, timeout=TIMEOUT)
    except httpx.HTTPError:
        # Nunca vaza URL, host ou stack para o modelo.
        return {"erro": _INDISPONIVEL}
    if r.status_code == 404:
        return {"encontrado": False, "mensagem": "Nao ha registro correspondente na base."}
    if r.status_code == 401:
        return {"erro": _INDISPONIVEL}
    if r.status_code >= 400:
        return {"erro": _INDISPONIVEL}
    return r.json()


@mcp.tool(description="Lista as bacias sedimentares disponiveis na base.")
def listar_bacias() -> Any:
    return _buscar("/v1/bacias")


@mcp.tool(description=(
    "Ficha completa de uma bacia: area, orientacao, contexto tectonico, sequencias "
    "estratigraficas e grupos. Use para perguntas gerais sobre a bacia."))
def descrever_bacia(nome: str) -> Any:
    return _buscar(f"/v1/bacias/{nome}")


@mcp.tool(description=(
    "Lista as formacoes em ordem estratigrafica, da base para o topo. Filtre por grupo "
    "(ex.: 'Santana') ou por sequencia (ex.: 'Pos-Rifte I')."))
def listar_formacoes(grupo: str | None = None, sequencia: str | None = None) -> Any:
    return _buscar("/v1/formacoes", {"grupo": grupo, "sequencia": sequencia})


@mcp.tool(description=(
    "Ficha completa de uma formacao: idade, litologia, espessura, ambiente deposicional, "
    "geoquimica e conteudo fossilifero. Aceita o nome com ou sem o prefixo 'Formacao'."))
def descrever_formacao(nome: str) -> Any:
    return _buscar(f"/v1/formacoes/{nome}")


@mcp.tool(description=(
    "Geoquimica organica de uma formacao: faixa de COT, tipo de querogenio, maturidade "
    "termica e metodo analitico. Use sempre que a pergunta envolver COT, querogenio, "
    "rocha geradora ou potencial de geracao."))
def geoquimica_formacao(nome: str) -> Any:
    return _buscar(f"/v1/formacoes/{nome}/geoquimica")


@mcp.tool(description="Conteudo fossilifero registrado para uma formacao.")
def fosseis_formacao(nome: str) -> Any:
    return _buscar(f"/v1/formacoes/{nome}/fosseis")


@mcp.tool(description="Em quais formacoes ocorre um grupo fossil (ex.: 'pterossauros').")
def buscar_fossil(grupo_biologico: str) -> Any:
    return _buscar("/v1/fosseis", {"grupo_biologico": grupo_biologico})


@mcp.tool(description="Dados de um poco exploratorio: sub-bacia e profundidade do embasamento.")
def buscar_poco(nome: str) -> Any:
    return _buscar(f"/v1/pocos/{nome}")


@mcp.tool(description=(
    "Divergencias conhecidas da literatura sobre um tema (ex.: 'ingressao marinha'). "
    "Devolve SEMPRE as duas posicoes com suas fontes. Chame antes de afirmar consenso."))
def controversias(tema: str | None = None) -> Any:
    return _buscar("/v1/controversias", {"tema": tema})


@mcp.tool(description=(
    "Identidade da base: versao da carga, data de geracao e numero de registros por "
    "tabela. Use quando perguntarem qual versao da base esta ativa ou o que ela cobre."))
def versao_base() -> Any:
    return _buscar("/v1/versao")


@mcp.tool(description=(
    "Busca textual livre nas descricoes das formacoes quando voce nao sabe o nome exato. "
    "Ex.: 'evaporitos gipsita', 'calcario laminado'."))
def busca_livre(termo: str, limite: int = 10) -> Any:
    return _buscar("/v1/busca", {"termo": termo, "limite": max(1, min(limite, 50))})


if __name__ == "__main__":
    mcp.run(transport="stdio")
