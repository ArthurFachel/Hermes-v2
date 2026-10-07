"""
Testes da GeoDB. Rode com:
    cd geodb && ./.venv/bin/python -m pytest -q
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))

import consultas as gdb  # noqa: E402
import seed  # noqa: E402

TOKEN = "token_de_teste"


@pytest.fixture(scope="module", autouse=True)
def base(tmp_path_factory, monkeypatch_module=None):
    """Constroi uma base temporaria e aponta o modulo de consultas para ela."""
    caminho = tmp_path_factory.mktemp("geodb") / "geo.db"
    seed.construir(caminho).close()
    gdb.DB_PATH = caminho
    yield caminho


@pytest.fixture(scope="module")
def cliente(base):
    import os

    os.environ["GEODB_TOKEN"] = TOKEN
    os.environ["GEODB_PATH"] = str(base)
    for mod in ("server",):
        sys.modules.pop(mod, None)
    import server

    server.gdb.DB_PATH = base
    with TestClient(server.app) as c:
        yield c


# ── Integridade dos dados ────────────────────────────────────────────────────

def test_toda_formacao_tem_fonte(base):
    for f in gdb.listar_formacoes():
        assert f["fonte"], f"formacao sem referencia: {f['nome']}"


def test_toda_geoquimica_tem_fonte(base):
    for f in gdb.listar_formacoes():
        for g in gdb.geoquimica_formacao(f["nome"]):
            assert g["fonte"], f"geoquimica sem referencia em {f['nome']}"


def test_ordem_estratigrafica_sem_buracos(base):
    ordens = [f["ordem"] for f in gdb.listar_formacoes()]
    assert ordens == sorted(ordens)
    assert ordens == list(range(1, len(ordens) + 1))


def test_base_e_somente_leitura(base):
    conn = gdb.conectar()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM formacoes")


# ── Casos que o benchmark cobra ──────────────────────────────────────────────

def test_cot_ipubi(base):
    (g,) = gdb.geoquimica_formacao("Formação Ipubi")
    assert g["cot_min"] == 17.2 and g["cot_max"] == 28.6
    assert "Tipo I" in g["tipo_querogenio"]
    assert "Castro" in g["fonte"]


def test_poco_2ap1ce(base):
    p = gdb.buscar_poco("2-AP-1-CE")
    assert p["prof_embasamento_m"] == 1498.0
    assert p["sub_bacia"] == "Feira Nova"


def test_grupo_santana_tem_quatro_formacoes(base):
    nomes = [f["nome"] for f in gdb.listar_formacoes(grupo="Santana")]
    assert nomes == ["Barbalha", "Crato", "Ipubi", "Romualdo"]


def test_area_da_bacia(base):
    b = gdb.descrever_bacia("Araripe")
    assert b["area_km2"] == 9000.0
    assert "E-W" in b["orientacao"]
    assert len(b["sequencias"]) == 5


def test_controversia_devolve_as_duas_posicoes(base):
    (c,) = gdb.controversias("ingressão marinha")
    assert "SSW" in c["posicao_a"] or "sul-sudoeste" in c["posicao_a"]
    assert "Norte" in c["posicao_b"]
    assert "Goldberg" in c["fonte_a"] and "Melo" in c["fonte_b"]


def test_romualdo_e_lagerstatte(base):
    f = gdb.descrever_formacao("Romualdo")
    assert "Lagerstatte" in f["observacoes"]
    grupos = {x["grupo_bio"] for x in f["fosseis"]}
    assert {"peixes", "pterossauros", "tartarugas"} <= grupos


# ── Tolerancia de nomes ──────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada", ["Ipubi", "ipubi", "Formação Ipubi", "formacao ipubi", "IPUBI"])
def test_nome_tolerante_a_acento_e_prefixo(base, entrada):
    assert gdb.descrever_formacao(entrada)["nome"] == "Ipubi"


def test_formacao_inexistente_nao_explode(base):
    assert gdb.descrever_formacao("Formação Inventada") is None


def test_busca_livre_encontra_evaporito(base):
    nomes = [r["nome"] for r in gdb.busca_livre("evaporitos gipsita")]
    assert "Ipubi" in nomes


# ── Superficie HTTP ──────────────────────────────────────────────────────────

def test_health_e_publico(cliente):
    assert cliente.get("/health").status_code == 200


def test_rest_exige_token(cliente):
    assert cliente.get("/v1/formacoes").status_code == 401
    r = cliente.get("/v1/formacoes", headers={"X-API-Key": TOKEN})
    assert r.status_code == 200 and len(r.json()) == 10


def test_mcp_exige_token(cliente):
    """O /mcp e um app montado: o Depends do FastAPI nao o alcanca."""
    r = cliente.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401


def test_token_errado_recusado(cliente):
    assert cliente.get("/v1/formacoes", headers={"X-API-Key": "errado"}).status_code == 401


def test_resposta_nao_vaza_caminho(cliente):
    r = cliente.get("/v1/formacoes/Ipubi", headers={"X-API-Key": TOKEN})
    corpo = r.text
    for proibido in ("/home/", "geo.db", "geodb/", ".venv", "sqlite"):
        assert proibido not in corpo, f"resposta vazou '{proibido}'"
