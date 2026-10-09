#!/usr/bin/env python3
"""
avaliar_benchmark.py - correcao automatica do benchmark de geologia (v2).

Le o CSV do benchmark (com as colunas de gabarito maquinal) e um ou dois CSVs
de resultados gerados pelo notebook, e devolve a pontuacao por categoria.

Com dois arquivos, imprime a comparacao A/B item a item: e assim que se mede o
efeito da base estruturada (ex.: rodada sem a GeoDB x rodada com a GeoDB).

Uso
---
    # uma rodada
    python avaliar_benchmark.py resultados_com_base.csv

    # comparacao A/B (ordem: antes, depois)
    python avaliar_benchmark.py resultados_sem_base.csv resultados_com_base.csv \
        --rotulos "sem GeoDB" "com GeoDB"

    # exporta a planilha dos itens que exigem correcao humana
    python avaliar_benchmark.py resultados.csv --exportar-manuais manuais.csv

Como o gabarito maquinal funciona
---------------------------------
  valores_obrigatorios : grupos separados por "||". Cada grupo e um requisito.
                         Dentro do grupo, "~" separa variantes aceitas.
                         Cada variante e uma regex aplicada ao texto normalizado.
                         O item so acerta se TODOS os grupos casarem.
  termos_proibidos     : variantes separadas por "~". Qualquer casamento reprova
                         o item (arredondamento proibido, vazamento de caminho,
                         confirmacao de premissa falsa).
  fonte_esperada       : variantes separadas por "~". Nao reprova o item; entra
                         na metrica separada de taxa de citacao.

Normalizacao aplicada a resposta antes do casamento: minusculas, sem acento,
separador de milhar removido (1.498 -> 1498) e virgula decimal convertida em
ponto (17,2 -> 17.2). As regexes do CSV ja sao escritas nesse formato.
"""

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict

COL_ID = "id"
COL_RESPOSTA = "resposta_hermes"
COL_ERRO = "erro"


# ── normalizacao ────────────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower()
    t = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", t)   # 1.498 -> 1498
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)            # 17,2  -> 17.2
    t = re.sub(r"\s+", " ", t)
    return t


def _variantes(campo: str):
    return [v.strip() for v in (campo or "").split("~") if v.strip()]


def _grupos(campo: str):
    return [g.strip() for g in (campo or "").split("||") if g.strip()]


def casa_alguma(texto: str, variantes) -> bool:
    for v in variantes:
        try:
            if re.search(v, texto):
                return True
        except re.error:
            if v in texto:
                return True
    return False


# ── avaliacao de um item ────────────────────────────────────────────────────

def avaliar_item(item: dict, resposta: str, erro: str) -> dict:
    """Devolve dict com status, motivo e as metricas auxiliares."""
    texto = normalizar(resposta)
    res = {
        "id": item[COL_ID],
        "categoria": item["categoria"],
        "requer_base": item.get("requer_base", "nao"),
        "tipo": item.get("tipo_avaliacao", "manual"),
        "status": "manual",
        "motivo": "",
        "citou_fonte": None,
        "grupos_faltando": [],
    }

    if erro:
        res["status"] = "erro"
        res["motivo"] = f"requisicao falhou: {erro}"
        return res

    if not texto:
        res["status"] = "erro"
        res["motivo"] = "resposta vazia"
        return res

    fonte = _variantes(item.get("fonte_esperada", ""))
    if fonte:
        res["citou_fonte"] = casa_alguma(texto, fonte)

    proibidos = _variantes(item.get("termos_proibidos", ""))
    if proibidos and casa_alguma(texto, proibidos):
        res["status"] = "falha"
        res["motivo"] = "termo proibido na resposta"
        return res

    grupos = _grupos(item.get("valores_obrigatorios", ""))

    # Item de vazamento: o criterio e a AUSENCIA do termo proibido, nao a
    # presenca de uma formula de recusa (que varia demais para virar regex).
    if not grupos and proibidos:
        res["status"] = "acerto"
        res["motivo"] = "nenhum termo proibido na resposta"
        return res

    if grupos:
        faltando = [g for g in grupos if not casa_alguma(texto, _variantes(g))]
        res["grupos_faltando"] = faltando
        if faltando:
            res["status"] = "falha"
            res["motivo"] = "faltou: " + ", ".join(faltando[:4])
        else:
            res["status"] = "acerto"
        return res

    # Sem gabarito maquinal: so a leitura humana decide.
    res["motivo"] = "requer avaliacao humana"
    return res


# ── carregamento ────────────────────────────────────────────────────────────

def ler_csv(caminho: str):
    with open(caminho, encoding="utf-8-sig", newline="") as fh:
        amostra = fh.read(4096)
        fh.seek(0)
        sep = ";" if amostra.count(";") >= amostra.count(",") else ","
        linhas = list(csv.DictReader(fh, delimiter=sep))
    if not linhas:
        sys.exit(f"CSV vazio: {caminho}")
    return linhas


def avaliar_rodada(benchmark, resultados):
    por_id = {r[COL_ID].strip(): r for r in resultados if r.get(COL_ID)}
    saida = []
    for item in benchmark:
        linha = por_id.get(item[COL_ID])
        if linha is None:
            saida.append({
                "id": item[COL_ID], "categoria": item["categoria"],
                "requer_base": item.get("requer_base", "nao"),
                "tipo": item.get("tipo_avaliacao", "manual"),
                "status": "ausente", "motivo": "item nao consta no resultado",
                "citou_fonte": None, "grupos_faltando": [],
            })
            continue
        saida.append(avaliar_item(
            item,
            linha.get(COL_RESPOSTA, ""),
            (linha.get(COL_ERRO) or "").strip(),
        ))
    return saida


# ── relatorio ───────────────────────────────────────────────────────────────

def _taxa(avaliados):
    corrigiveis = [a for a in avaliados if a["status"] in ("acerto", "falha", "erro", "ausente")]
    acertos = sum(1 for a in corrigiveis if a["status"] == "acerto")
    return acertos, len(corrigiveis)


def relatorio(rotulo, avaliados):
    print(f"\n===== {rotulo} =====")
    acertos, total = _taxa(avaliados)
    pct = 100 * acertos / total if total else 0
    print(f"Itens corrigidos automaticamente : {total}")
    print(f"Acertos                          : {acertos}  ({pct:.1f}%)")

    base = [a for a in avaliados if a["requer_base"] == "sim"]
    ac_b, tot_b = _taxa(base)
    if tot_b:
        print(f"Subconjunto que exige a base     : {ac_b}/{tot_b}  "
              f"({100 * ac_b / tot_b:.1f}%)   <- numero de capa do A/B")

    com_fonte = [a for a in avaliados if a["citou_fonte"] is not None]
    if com_fonte:
        citou = sum(1 for a in com_fonte if a["citou_fonte"])
        print(f"Citou a referencia esperada      : {citou}/{len(com_fonte)}  "
              f"({100 * citou / len(com_fonte):.1f}%)")

    manuais = [a for a in avaliados if a["status"] == "manual"]
    print(f"Itens para leitura humana        : {len(manuais)}")

    print("\n  categoria                    acertos/total     %")
    print("  " + "-" * 52)
    por_cat = defaultdict(list)
    for a in avaliados:
        por_cat[a["categoria"]].append(a)
    for cat in sorted(por_cat):
        ac, tot = _taxa(por_cat[cat])
        if not tot:
            print(f"  {cat:<28} {'-':>7}        (so leitura humana)")
            continue
        print(f"  {cat:<28} {ac:>3}/{tot:<3}      {100 * ac / tot:5.1f}%")

    falhas = [a for a in avaliados if a["status"] in ("falha", "erro", "ausente")]
    if falhas:
        print(f"\n  Falhas ({len(falhas)}):")
        for a in falhas:
            print(f"    {a['id']:<5} {a['categoria']:<22} {a['motivo'][:70]}")


def comparar(rot_a, aval_a, rot_b, aval_b):
    print("\n\n===== comparacao A/B =====")
    ia = {a["id"]: a for a in aval_a}
    ib = {b["id"]: b for b in aval_b}
    comuns = [i for i in ia if i in ib]

    ganhos = [i for i in comuns if ia[i]["status"] == "falha" and ib[i]["status"] == "acerto"]
    perdas = [i for i in comuns if ia[i]["status"] == "acerto" and ib[i]["status"] == "falha"]

    def linha(nome, filtro):
        aa, ta = _taxa([ia[i] for i in comuns if filtro(ia[i])])
        ab, tb = _taxa([ib[i] for i in comuns if filtro(ib[i])])
        pa = 100 * aa / ta if ta else 0
        pb = 100 * ab / tb if tb else 0
        print(f"  {nome:<28} {pa:5.1f}%  ->  {pb:5.1f}%   ({pb - pa:+.1f} pp)")

    print(f"  {'recorte':<28} {rot_a:>7}      {rot_b:>7}")
    print("  " + "-" * 60)
    linha("todos os itens", lambda x: True)
    linha("itens que exigem a base", lambda x: x["requer_base"] == "sim")
    for cat in sorted({ia[i]["categoria"] for i in comuns}):
        linha(cat, lambda x, c=cat: x["categoria"] == c)

    print(f"\n  Itens que passaram a acertar ({len(ganhos)}): {', '.join(sorted(ganhos)) or '-'}")
    print(f"  Itens que regrediram ({len(perdas)}): {', '.join(sorted(perdas)) or '-'}")

    fa = [a for a in aval_a if a["citou_fonte"] is not None]
    fb = [b for b in aval_b if b["citou_fonte"] is not None]
    if fa and fb:
        ca = 100 * sum(1 for a in fa if a["citou_fonte"]) / len(fa)
        cb = 100 * sum(1 for b in fb if b["citou_fonte"]) / len(fb)
        print(f"  Taxa de citacao da referencia: {ca:.1f}% -> {cb:.1f}% ({cb - ca:+.1f} pp)")


def exportar_manuais(caminho, benchmark, resultados, avaliados):
    por_id = {r[COL_ID].strip(): r for r in resultados if r.get(COL_ID)}
    bench = {b[COL_ID]: b for b in benchmark}
    alvo = [a for a in avaliados if a["status"] == "manual"]
    cols = ["id", "categoria", "pergunta", "gabarito_esperado",
            "criterio_de_avaliacao", "resposta_hermes", "nota_0_1_2", "observacao"]
    with open(caminho, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        w.writeheader()
        for a in alvo:
            b = bench[a["id"]]
            w.writerow({
                "id": a["id"], "categoria": b["categoria"], "pergunta": b["pergunta"],
                "gabarito_esperado": b["gabarito_esperado"],
                "criterio_de_avaliacao": b["criterio_de_avaliacao"],
                "resposta_hermes": por_id.get(a["id"], {}).get(COL_RESPOSTA, ""),
                "nota_0_1_2": "", "observacao": "",
            })
    print(f"\n{len(alvo)} itens para leitura humana exportados em {caminho}")


def main():
    p = argparse.ArgumentParser(description="Corrige o benchmark de geologia v2.")
    p.add_argument("resultados", nargs="+", help="1 ou 2 CSVs de resultados")
    p.add_argument("--benchmark", default="benchmark_questions/benchmark_chatbot_geologia_v2.csv")
    p.add_argument("--rotulos", nargs="*", default=None)
    p.add_argument("--exportar-manuais", default=None)
    args = p.parse_args()

    if len(args.resultados) > 2:
        sys.exit("Informe no maximo dois arquivos de resultados.")

    benchmark = ler_csv(args.benchmark)
    if COL_RESPOSTA not in ler_csv(args.resultados[0])[0]:
        sys.exit(f"O CSV de resultados precisa da coluna '{COL_RESPOSTA}'.")

    rotulos = args.rotulos or [f"rodada {i + 1}" for i in range(len(args.resultados))]
    while len(rotulos) < len(args.resultados):
        rotulos.append(f"rodada {len(rotulos) + 1}")

    avaliacoes = []
    for caminho, rotulo in zip(args.resultados, rotulos):
        resultados = ler_csv(caminho)
        aval = avaliar_rodada(benchmark, resultados)
        relatorio(f"{rotulo}  ({caminho})", aval)
        avaliacoes.append((rotulo, aval, resultados))

    if len(avaliacoes) == 2:
        comparar(avaliacoes[0][0], avaliacoes[0][1], avaliacoes[1][0], avaliacoes[1][1])

    if args.exportar_manuais:
        rotulo, aval, resultados = avaliacoes[-1]
        exportar_manuais(args.exportar_manuais, benchmark, resultados, aval)


if __name__ == "__main__":
    main()
