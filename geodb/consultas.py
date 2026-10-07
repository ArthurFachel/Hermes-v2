"""
Camada de consulta da GeoDB.

Abre o SQLite em modo somente-leitura (URI mode=ro) e expoe funcoes nomeadas.
Nao ha execucao de SQL arbitrario vindo de fora: o agente escolhe uma funcao e
passa parametros, que entram sempre por placeholder.

Todo retorno de fato traz o campo "fonte" com a referencia bibliografica. Nenhum
retorno contem caminho de arquivo, nome de tabela interna ou detalhe de deploy.
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("GEODB_PATH", Path(__file__).resolve().parent / "geo.db"))

_CAMPOS_REF = """
    r.autores || CASE WHEN r.ano IS NOT NULL THEN ' (' || r.ano || ')' ELSE '' END
"""


class BaseIndisponivel(RuntimeError):
    """A base nao existe ou nao pode ser aberta."""


def conectar() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise BaseIndisponivel("base de dados nao encontrada")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _linhas(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conectar() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _uma(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    linhas = _linhas(sql, params)
    return linhas[0] if linhas else None


def normalizar(texto: str) -> str:
    """Remove acentos, caixa e o prefixo 'formacao'/'fm' para casar nomes."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().strip()
    t = re.sub(r"^(formacao|formacao\s+geologica|fm\.?|grupo)\s+", "", t)
    return re.sub(r"\s+", " ", t)


# ── Bacias ───────────────────────────────────────────────────────────────────

def listar_bacias() -> list[dict[str, Any]]:
    return _linhas("SELECT nome, area_km2, orientacao FROM bacias ORDER BY nome")


def descrever_bacia(nome: str) -> dict[str, Any] | None:
    bacia = _uma(
        f"""SELECT b.nome, b.area_km2, b.area_nota, b.orientacao, b.provincia,
                   b.dominio, b.contexto, {_CAMPOS_REF} AS fonte
            FROM bacias b LEFT JOIN referencias r ON r.id = b.ref_id""",
    )
    if not bacia:
        return None
    if normalizar(nome) not in normalizar(bacia["nome"]):
        return None
    bacia["sequencias"] = _linhas(
        f"""SELECT s.nome, s.ordem, s.idade, s.descricao, {_CAMPOS_REF} AS fonte
            FROM sequencias s LEFT JOIN referencias r ON r.id = s.ref_id
            ORDER BY s.ordem"""
    )
    bacia["grupos"] = _linhas(
        "SELECT nome, supergrupo FROM grupos ORDER BY id"
    )
    return bacia


# ── Formacoes ────────────────────────────────────────────────────────────────

_SQL_FORMACAO = f"""
    SELECT f.nome, f.ordem, f.idade, f.litologia, f.espessura_m, f.espessura_nota,
           f.ambiente, f.fossilifera, f.observacoes,
           g.nome AS grupo, g.supergrupo, s.nome AS sequencia,
           {_CAMPOS_REF} AS fonte
    FROM formacoes f
    LEFT JOIN grupos g      ON g.id = f.grupo_id
    LEFT JOIN sequencias s  ON s.id = f.sequencia_id
    LEFT JOIN referencias r ON r.id = f.ref_id
"""


def listar_formacoes(grupo: str | None = None, sequencia: str | None = None) -> list[dict[str, Any]]:
    linhas = _linhas(_SQL_FORMACAO + " ORDER BY f.ordem")
    if grupo:
        alvo = normalizar(grupo)
        linhas = [l for l in linhas if l["grupo"] and normalizar(l["grupo"]) == alvo]
    if sequencia:
        alvo = normalizar(sequencia)
        linhas = [l for l in linhas if l["sequencia"] and normalizar(l["sequencia"]) == alvo]
    return linhas


def _achar_formacao(nome: str) -> dict[str, Any] | None:
    alvo = normalizar(nome)
    if not alvo:
        return None
    candidatos = _linhas(_SQL_FORMACAO + " ORDER BY f.ordem")
    for l in candidatos:
        if normalizar(l["nome"]) == alvo:
            return l
    for l in candidatos:
        if alvo in normalizar(l["nome"]) or normalizar(l["nome"]) in alvo:
            return l
    return None


def descrever_formacao(nome: str) -> dict[str, Any] | None:
    f = _achar_formacao(nome)
    if not f:
        return None
    f["geoquimica"] = geoquimica_formacao(f["nome"])
    f["fosseis"] = fosseis_formacao(f["nome"])
    return f


def geoquimica_formacao(nome: str) -> list[dict[str, Any]]:
    f = _achar_formacao(nome)
    if not f:
        return []
    return _linhas(
        f"""SELECT q.litotipo, q.cot_min, q.cot_max, q.cot_nota, q.tipo_querogenio,
                   q.maturidade, q.metodo, q.ambiente_mo, {_CAMPOS_REF} AS fonte
            FROM geoquimica q
            JOIN formacoes f       ON f.id = q.formacao_id
            LEFT JOIN referencias r ON r.id = q.ref_id
            WHERE f.nome = ?""",
        (f["nome"],),
    )


def fosseis_formacao(nome: str) -> list[dict[str, Any]]:
    f = _achar_formacao(nome)
    if not f:
        return []
    return _linhas(
        f"""SELECT x.grupo_bio, x.detalhe, {_CAMPOS_REF} AS fonte
            FROM fosseis x
            JOIN formacoes f       ON f.id = x.formacao_id
            LEFT JOIN referencias r ON r.id = x.ref_id
            WHERE f.nome = ? ORDER BY x.grupo_bio""",
        (f["nome"],),
    )


def buscar_fossil(grupo_bio: str) -> list[dict[str, Any]]:
    """Em quais formacoes ocorre determinado grupo fossil."""
    return _linhas(
        f"""SELECT f.nome AS formacao, x.grupo_bio, x.detalhe, {_CAMPOS_REF} AS fonte
            FROM fosseis x
            JOIN formacoes f       ON f.id = x.formacao_id
            LEFT JOIN referencias r ON r.id = x.ref_id
            WHERE x.grupo_bio LIKE ? ORDER BY f.ordem""",
        (f"%{grupo_bio.strip().lower()}%",),
    )


# ── Pocos, controversias, busca ──────────────────────────────────────────────

def buscar_poco(nome: str) -> dict[str, Any] | None:
    return _uma(
        f"""SELECT p.nome, p.sub_bacia, p.prof_embasamento_m, p.observacoes,
                   {_CAMPOS_REF} AS fonte
            FROM pocos p LEFT JOIN referencias r ON r.id = p.ref_id
            WHERE UPPER(p.nome) = UPPER(?)""",
        (nome.strip(),),
    )


def listar_pocos() -> list[dict[str, Any]]:
    return _linhas("SELECT nome, sub_bacia, prof_embasamento_m FROM pocos ORDER BY nome")


def controversias(tema: str | None = None) -> list[dict[str, Any]]:
    linhas = _linhas(
        """SELECT c.tema, c.posicao_a, c.posicao_b, c.situacao,
                  ra.autores || ' (' || ra.ano || ')' AS fonte_a,
                  rb.autores || ' (' || rb.ano || ')' AS fonte_b
           FROM controversias c
           LEFT JOIN referencias ra ON ra.id = c.ref_a_id
           LEFT JOIN referencias rb ON rb.id = c.ref_b_id
           ORDER BY c.id"""
    )
    if tema:
        termos = [t for t in normalizar(tema).split() if len(t) > 3]
        if termos:
            linhas = [
                l for l in linhas
                if any(t in normalizar(l["tema"] + " " + l["posicao_a"] + " " + l["posicao_b"])
                       for t in termos)
            ]
    return linhas


def busca_livre(termo: str, limite: int = 10) -> list[dict[str, Any]]:
    """Busca textual (FTS5) sobre nome, litologia, ambiente e observacoes das formacoes."""
    termo = (termo or "").strip()
    if not termo:
        return []
    # Converte a consulta do usuario em prefix-match seguro para o FTS5.
    tokens = [t for t in re.findall(r"\w+", termo, flags=re.UNICODE) if len(t) > 2]
    if not tokens:
        return []
    consulta = " OR ".join(f'"{t}"*' for t in tokens)
    try:
        return _linhas(
            f"""SELECT f.nome, f.idade, f.litologia, f.ambiente, g.nome AS grupo,
                       {_CAMPOS_REF} AS fonte
                FROM formacoes_fts fts
                JOIN formacoes f        ON f.id = fts.rowid
                LEFT JOIN grupos g      ON g.id = f.grupo_id
                LEFT JOIN referencias r ON r.id = f.ref_id
                WHERE formacoes_fts MATCH ?
                ORDER BY rank LIMIT ?""",
            (consulta, limite),
        )
    except sqlite3.OperationalError:
        return []


def estatisticas() -> dict[str, Any]:
    """Identidade e tamanho da carga. Usada para verificar que a base foi consultada."""
    with conectar() as conn:
        tabelas = ["bacias", "sequencias", "grupos", "formacoes",
                   "geoquimica", "fosseis", "pocos", "controversias", "referencias"]
        registros = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tabelas}
        try:
            meta = {r["chave"]: r["valor"] for r in conn.execute("SELECT chave, valor FROM metadados")}
        except sqlite3.OperationalError:
            meta = {}
    return {**meta, "registros": registros}
