#!/usr/bin/env python3
"""
Popula geo.db a partir de fatos extraidos dos documentos da base interna.

Regra do projeto: nada aqui e inventado. Cada linha corresponde a uma afirmacao
presente nos documentos de fontes_de_conhecimento/, e carrega a referencia
bibliografica citada no proprio texto. Ao estender, mantenha ref_id preenchido.

Uso:
    python seed.py                 # cria ./geo.db (recria se existir)
    python seed.py --db /caminho/geo.db
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

AQUI = Path(__file__).resolve().parent

# Identificador da carga. Mude a cada alteracao relevante nos dados.
# Serve de canario para verificar se o agente consultou mesmo a base: a string
# nao aparece em nenhum documento e o modelo nao tem como adivinhar.
VERSAO_BASE = "araripe-2026.10-r1"

REFERENCIAS = [
    ("fambrini2020", "Fambrini, G. L. et al.", 2020,
     "Estratigrafia da Bacia do Araripe: estado da arte, revisao critica e resultados novos",
     "Geologia USP - Serie Cientifica"),
    ("assine2007", "Assine, M. L.", 2007, "Bacia do Araripe", "Boletim de Geociencias da Petrobras"),
    ("assine1992", "Assine, M. L.", 1992, "Analise estratigrafica da Bacia do Araripe, Nordeste do Brasil",
     "Revista Brasileira de Geociencias"),
    ("assine1994", "Assine, M. L.", 1994, "Paleocorrentes e paleogeografia na Bacia do Araripe", None),
    ("assine2014", "Assine, M. L. et al.", 2014, "Sequencias deposicionais do Andar Alagoas da Bacia do Araripe",
     "Boletim de Geociencias da Petrobras"),
    ("castro2017", "Castro, J. C. et al.", 2017,
     "Caracterizacao geoquimica da materia organica dos folhelhos da Formacao Ipubi", None),
    ("goldberg2019", "Goldberg, K. et al.", 2019,
     "Ingressao marinha nos evaporitos da Formacao Ipubi, Bacia do Araripe", None),
    ("melo2020", "Melo, R. M. et al.", 2020,
     "Idade e carater marinho da Formacao Romualdo, Bacia do Araripe", None),
    ("catto2016", "Catto, B. et al.", 2016,
     "The microbial nature of laminated limestones, Crato Formation", "Sedimentary Geology"),
    ("maisey1991", "Maisey, J. G.", 1991, "Santana Fossils: an illustrated atlas", "TFH Publications"),
    ("neumann1999", "Neumann, V. H.", 1999,
     "Estratigrafia, sedimentologia, geoquimica y diagenesis de los sistemas lacustres aptiense-albienses de la Cuenca de Araripe",
     "Tese, Universidad de Barcelona"),
    ("barretojr2020", "Barreto Junior, A. et al.", 2020, "Formacao Missao Velha, Bacia do Araripe", None),
    ("ponteappi1990", "Ponte, F. C. & Appi, C. J.", 1990,
     "Proposta de revisao da coluna litoestratigrafica da Bacia do Araripe",
     "Congresso Brasileiro de Geologia"),
    ("pontefilho1996", "Ponte, F. C. & Ponte-Filho, F. C.", 1996,
     "Estrutura geologica e evolucao tectonica da Bacia do Araripe", None),
    ("costa2014", "Costa, A. et al.", 2014, "Sistema deltaico da Formacao Abaiara", None),
    ("nascimentojr2016", "Nascimento Junior, D. R. et al.", 2016,
     "Texturas e ambiente dos evaporitos da Formacao Ipubi", None),
    ("spigolon2015", "Spigolon, A. L. D. et al.", 2015,
     "Geoquimica organica dos folhelhos da Camada Batateira", None),
    ("valenca1987", "Valenca, L. M. M.", 1987, "Formacao Exu, Bacia do Araripe", None),
    ("martill1988", "Martill, D. M.", 1988,
     "Preservation of fish in the Cretaceous Santana Formation of Brazil", "Palaeontology"),
    ("sales2005", "Sales, A. M. F.", 2005,
     "Analise tafonomica das ocorrencias fossiliferas da Formacao Romualdo", None),
]

BACIA = dict(
    nome="Bacia do Araripe",
    area_km2=9000.0,
    area_nota="mais de 9.000 km2; maior das bacias interiores do Nordeste",
    orientacao="alongada E-W, com suave mergulho da chapada para oeste",
    provincia="Provincia Borborema",
    dominio="Dominio da Zona Transversal",
    contexto=("Depositos mesozoicos originados por subsidencia mecanica em resposta ao "
              "estiramento litosferico que compos a Depressao Afro-Brasileira"),
    ref="assine2007",
)

SEQUENCIAS = [
    ("Paleozoica", 1, "Neo-ordoviciano-Eossiluriano",
     "Constituida apenas pela Formacao Cariri. Deposicao basal da bacia em estagio de "
     "grandes bacias intracratonicas da Plataforma Sul-Americana.", "fambrini2020"),
    ("Inicio de Rifte", 2, "Jurassico superior",
     "Formacao Brejo Santo na base e porcao basal da Formacao Missao Velha no topo. "
     "Subsidencia mecanica por estiramento litosferico.", "fambrini2020"),
    ("Climax de Rifte", 3, "Jurassico superior-Cretaceo inferior",
     "Porcao superior da Formacao Missao Velha e toda a Formacao Abaiara. Maior variacao "
     "faciologica lateral e vertical do empilhamento.", "fambrini2020"),
    ("Pos-Rifte I", 4, "Aptiano superior-Albiano inferior",
     "Grupo Santana, em discordancia angular sobre a unidade sotoposta. Relacionada a "
     "subsidencia flexural termica.", "assine2007"),
    ("Pos-Rifte II", 5, "Albiano-Cenomaniano",
     "Formacao Araripina na base e Exu no topo. Sedimentos aluviais de sistemas de rios "
     "meandrantes.", "assine1992"),
]

GRUPOS = [
    ("Juazeiro do Norte", "Supergrupo Araripe", "assine1992"),
    ("Santana", "Supergrupo Araripe", "neumann1999"),
    ("Chapada", "Supergrupo Araripe", "fambrini2020"),
]

# (nome, ordem, grupo, sequencia, idade, litologia, espessura_m, espessura_nota,
#  ambiente, fossilifera, observacoes, ref)
FORMACOES = [
    ("Cariri", 1, None, "Paleozoica", "Neo-ordoviciano/Eossiluriano",
     "Arenitos quartzosos e arcoseanos mal selecionados, bem litificados e fraturados, "
     "com niveis conglomeraticos contendo fragmentos liticos do embasamento e corpos "
     "decimetricos descontinuos de siltito",
     None, None, "Sistemas fluviais entrelacados sob clima arido a semiarido", 0,
     "Unidade basal, em contato com o embasamento. Aflora apenas na porcao leste; a oeste "
     "ocorre so em subsuperficie. Afossilifera.", "fambrini2020"),

    ("Brejo Santo", 2, "Juazeiro do Norte", "Inicio de Rifte", "Jurassico superior",
     "Sucessao essencialmente pelitica: argilitos e folhelhos calciferos avermelhados a "
     "acastanhados, bem laminados e de baixo grau diagenetico; siltitos e corpos de "
     "arenito fino a muito fino argiloso",
     450.0, "ate 450 m", "Sistemas lacustres com influencia fluvial (primeira fase lacustre da bacia)", 1,
     "Contato gradacional e concordante com a Formacao Missao Velha. Poucos afloramentos "
     "naturais por acao pedogenetica.", "fambrini2020"),

    ("Missao Velha", 3, "Juazeiro do Norte", "Climax de Rifte", "Jurassico superior",
     "Arenosa, de composicao quartzosa, por vezes feldspatica e/ou caulinica; arenitos "
     "grossos e conglomerados na Sequencia 2",
     200.0, "espessura media de 200 m, constante ao longo da bacia",
     "Sistemas lacustre com influencia fluvial, fluvial meandrante com retrabalhamento "
     "eolico e fluvial entrelacado", 1,
     "Dividida informalmente por Fambrini et al. (2011) em Sequencia 1 e Sequencia 2, com "
     "contato erosivo marcado por nivel de paleossolo seguido de conglomerados. Os arenitos "
     "grossos abrigam lenhos fosseis silicificados, vestigio de uma ampla floresta de "
     "coniferas.", "barretojr2020"),

    ("Abaiara", 4, "Juazeiro do Norte", "Climax de Rifte", "Cretaceo inferior",
     "Unidade heterogenea: alternancia de arenitos medios a finos (localmente "
     "conglomeraticos, variegados, lateralmente descontinuos), siltitos argilosos e "
     "folhelhos vermelho-arroxeados a verde-oliva",
     None, None,
     "Rios meandrantes na base passando a sistema lacustre raso; interpretacao alternativa "
     "de sistema deltaico", 1,
     "Alta variacao faciologica lateral e vertical. Contato basal brusco e discordante com "
     "a Formacao Missao Velha. Folhelhos papiraceos no topo com escamas de peixes e "
     "ostracodes.", "fambrini2020"),

    ("Barbalha", 5, "Santana", "Pos-Rifte I", "Aptiano",
     "Litologias psamiticas e, secundariamente, peliticas; arenitos grossos a "
     "conglomeraticos com estratificacao cruzada tabular e acanalada, folhelhos betuminosos "
     "pretos e calcarios micriticos laminados no topo",
     None, None, "Fluvio-lacustre; lagos em condicoes de anoxia (Camada Batateira)", 1,
     "Limitada na base pela discordancia pre-Alagoas. Formada por duas sequencias fluviais "
     "granodecrescentes que terminam em pelitos lacustres ou fluviais. Palinologia das "
     "Camadas Batateira indica clima quente e seco, semiarido.", "assine2007"),

    ("Crato", 6, "Santana", "Pos-Rifte I", "Aptiano",
     "Folhelhos papiraceos calciferos interestratificados com calcarios micriticos "
     "laminados e argilosos, formando bancos com mais de 20 m; folhelhos pirobetuminosos",
     20.0, "bancos de calcario com mais de 20 m de espessura",
     "Sistema lacustre de baixa energia, com aporte terrigeno decrescente para o topo", 1,
     "Carbonatos de origem bacteriana em condicoes anoxicas; Catto et al. (2016) inferiram "
     "que ao menos 90% da sucessao carbonatica proveio de organismos redutores de sulfeto. "
     "Pseudomorfos de halita indicam aridez crescente para o topo.", "assine1992"),

    ("Ipubi", 7, "Santana", "Pos-Rifte I", "Aptiano",
     "Evaporitos, principalmente gipsita, com textura de palicada (cristais colunares "
     "agrupados), texturas secundarias em roseta e nodulares; intercalados com folhelhos "
     "verdes e pretos, camadas arenosas e calcario laminado",
     30.0, "lentes de decimetros a mais de 30 m em alguns pontos",
     "Playa-lake; evaporitos em ambiente costeiro de supramare sob clima arido a semiarido", 1,
     "Concentra-se na borda oeste da bacia, onde apresenta continuidade lateral. Sustenta o "
     "Polo Gesseiro do Araripe.", "assine2007"),

    ("Romualdo", 8, "Santana", "Pos-Rifte I", "Aptiano",
     "Arenitos interestratificados com folhelhos cinza-escuros a pretos ricos em materia "
     "organica (ate 5 m), folhelhos esverdeados e margas, com concrecoes de calcario "
     "micritico finamente laminado, frequentemente fossiliferas",
     5.0, "intervalos de folhelho rico em materia organica com ate 5 m",
     "Aguas calmas, possivelmente lagunar, com ingressoes marinhas", 1,
     "Maior e mais conhecido jazigo paleontologico da bacia, reconhecida mundialmente como "
     "Konservat-Lagerstatte. Horizonte de coquinas de ate 1 m na porcao superior. Moluscos "
     "marinhos, dinoflagelados, foraminiferos e equinoides atestam ingressao marinha.",
     "maisey1991"),

    ("Araripina", 9, "Chapada", "Pos-Rifte II", "Albiano",
     "Ritmitos de arenitos finos argilosos e argilitos, do amarelo ao roxo, com corpos "
     "lenticulares de arenito medio a grosso intercalados; laminacoes plano-paralelas, "
     "estratificacoes cruzadas e marcas de onda",
     None, None,
     "Leques aluviais medianos a distais em ambiente lagunar e planicie de inundacao", 0,
     "Estruturas de sobrecarga (almofadas, pseudonodulos) e truncamentos interpretados como "
     "produto de tectonica sindeposicional. Anteriormente chamada Exu Inferior ou Formacao "
     "Arajara.", "assine2007"),

    ("Exu", 10, "Chapada", "Pos-Rifte II", "Albiano-Cenomaniano",
     "Arenitos vermelho-alaranjados friaveis, argilosos, com porcoes cauliniticas e "
     "granulometria variavel, com leitos intercalados de arenito grosso a conglomeratico e "
     "porcoes silicificadas",
     None, None, "Sistema fluvial entrelacado de carater torrencial", 0,
     "Recobre toda a Chapada do Araripe como capa continua sub-horizontal; contato erosivo "
     "com a Formacao Araripina. Paleocorrentes com mergulho deposicional para oeste, "
     "mudanca paleogeografica relacionada ao Soerguimento Epirogenico do Nordeste.",
     "valenca1987"),
]

GEOQUIMICA = [
    ("Barbalha", "folhelhos escuros da Camada Batateira", None, 28.5,
     "COT atinge valores de ate 28,5%", "Tipo I", None, None,
     "continental, lagos em anoxia", "spigolon2015"),
    ("Crato", "folhelhos pirobetuminosos", None, 25.0, "teores de COT menores ou iguais a 25%",
     None, None, None, "lacustre anoxico", "neumann1999"),
    ("Crato", "calcarios laminados", 1.0, None, "valores gerais de COT acima de 1%",
     None, None, None, "lacustre", "catto2016"),
    ("Ipubi", "folhelhos", 17.2, 28.6, "COT entre 17,2% e 28,6%", "Tipo I (lacustre)",
     "imatura, porem com grande potencial de geracao de hidrocarbonetos",
     "pirolise Rock-Eval e biomarcadores", "lacustre, anoxico e hipersalino", "castro2017"),
]

FOSSEIS = [
    ("Brejo Santo", "ostracodes", "ostracodes nao marinhos, comuns nos estratos", "fambrini2020"),
    ("Brejo Santo", "conchostraceos", None, "fambrini2020"),
    ("Brejo Santo", "peixes", "ossos e restos de peixes", "fambrini2020"),
    ("Missao Velha", "plantas", "lenhos fosseis silicificados, vestigio de ampla floresta de coniferas",
     "fambrini2020"),
    ("Abaiara", "peixes", "escamas de peixes em folhelhos papiraceos", "fambrini2020"),
    ("Abaiara", "ostracodes", None, "fambrini2020"),
    ("Barbalha", "peixes", "ictiolitos e restos de peixes de ambiente fluvio-lacustre", "fambrini2020"),
    ("Barbalha", "conchostraceos", None, "fambrini2020"),
    ("Barbalha", "ostracodes", "ostracodes nao marinhos", "assine2007"),
    ("Barbalha", "plantas", "fragmentos vegetais carbonizados e polens", "fambrini2020"),
    ("Barbalha", "icnofosseis", "coprolitos nas Camadas Batateira", "assine2007"),
    ("Crato", "insetos", "varios insetos, registro abundante e diversificado", "neumann1999"),
    ("Crato", "peixes", None, "neumann1999"),
    ("Crato", "anuros", None, "neumann1999"),
    ("Crato", "pterossauros", None, "neumann1999"),
    ("Crato", "dinossauros", None, "neumann1999"),
    ("Crato", "aves", "incluindo penas preservadas", "neumann1999"),
    ("Crato", "crocodilomorfos", None, "neumann1999"),
    ("Crato", "quelonios", "quelonios e lagartos", "neumann1999"),
    ("Crato", "aracnideos", None, "neumann1999"),
    ("Crato", "crustaceos", None, "neumann1999"),
    ("Crato", "plantas", "fragmentos lenhosos carbonizados e plantas", "neumann1999"),
    ("Crato", "ostracodes", None, "neumann1999"),
    ("Crato", "conchostraceos", None, "neumann1999"),
    ("Ipubi", "ostracodes", "ostracodes nao marinhos nos folhelhos pirobetuminosos pretos", "assine2007"),
    ("Ipubi", "conchostraceos", None, "assine2007"),
    ("Ipubi", "foraminiferos", "microforaminiferos na base dos evaporitos, evidencia de ingressao marinha",
     "goldberg2019"),
    ("Ipubi", "plantas", "fragmentos vegetais carbonizados", "assine2007"),
    ("Romualdo", "peixes", "mais de 18 especies no interior das concrecoes calcarias; ictiofauna marinha",
     "assine2007"),
    ("Romualdo", "pterossauros", "com tecidos moles preservados", "maisey1991"),
    ("Romualdo", "dinossauros", None, "maisey1991"),
    ("Romualdo", "tartarugas", None, "maisey1991"),
    ("Romualdo", "moluscos", "moluscos marinhos no horizonte de coquinas", "sales2005"),
    ("Romualdo", "equinoides", "evidencia incontestavel de ingressao marinha", "melo2020"),
    ("Romualdo", "foraminiferos", "microfauna de afinidade tetiana", "melo2020"),
    ("Romualdo", "dinoflagelados", None, "melo2020"),
    ("Romualdo", "ostracodes", "abundantes nos folhelhos esverdeados", "assine1992"),
]

POCOS = [
    ("2-AP-1-CE", "Feira Nova", 1498.0,
     "Atingiu o embasamento cristalino a 1.498 m. A sub-bacia de Feira Nova foi descoberta "
     "por metodos geofisicos.", "assine2007"),
]

CONTROVERSIAS = [
    ("Direcao da ingressao marinha aptiana na Bacia do Araripe",
     "Ingressao marinha inequivoca proveniente de sul-sudoeste (SSW), atestada por "
     "microforaminiferos nos folhelhos pirobetuminosos na base dos evaporitos da Formacao "
     "Ipubi, na porcao da bacia onde as camadas de gipsita sao mais espessas.", "goldberg2019",
     "Carater marinho inequivoco na porcao superior da Formacao Romualdo, com microfauna de "
     "afinidade tetiana e conexao marinha provinda do Norte, contrastando com trabalhos "
     "preteritos que sugeriam ingressao de SSE.", "melo2020",
     "Divergencia em aberto. Qualquer resposta sobre o tema deve apresentar as duas posicoes."),

    ("Numero de sequencias estratigraficas da Bacia do Araripe",
     "Quatro sequencias limitadas por discordancias: Paleozoica, Juro-Neocomiana, "
     "Aptiano-Albiana e Albiano-Cenomaniana.", "assine1992",
     "Cinco sequencias: Paleozoica, Inicio de Rifte, Climax de Rifte, Pos-Rifte I e "
     "Pos-Rifte II, desdobrando as fases rifte e pos-rifte.", "fambrini2020",
     "Evolucao do modelo ao longo do tempo. O modelo de cinco sequencias e o atual; o de "
     "quatro e historico. Antes deles, Ponte e Ponte-Filho (1996) reconheciam tres estagios "
     "tectonicos (pre-rifte, sin-rifte, pos-rifte)."),

    ("Ambiente deposicional da Formacao Abaiara",
     "Sedimentacao continental: lacustre raso na base, passando a fluvial entrelacado e "
     "terminando com arenitos finos a medios intercalados a pelitos de lagos efemeros.",
     "ponteappi1990",
     "Grande sistema deltaico: pelitos de prodelta na base, arenitos de frente deltaica e "
     "planicies deltaicas associadas a sistema fluvial meandrante no topo.", "costa2014",
     "Interpretacoes concorrentes para a mesma associacao de facies."),

    ("Ambiente deposicional da Formacao Araripina",
     "Planicies de leques aluviais medianos a distais depositados em ambiente lagunar e "
     "planicie de inundacao sob condicoes oxidantes.", "assine2007",
     "Ambiente lagunar e de planicie de inundacao sob condicoes anoxicas.", "ponteappi1990",
     "Divergencia quanto as condicoes redox do ambiente."),
]


def construir(db_path: Path) -> sqlite3.Connection:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript((AQUI / "schema.sql").read_text(encoding="utf-8"))

    from datetime import datetime, timezone

    conn.executemany(
        "INSERT INTO metadados (chave, valor) VALUES (?,?)",
        [
            ("versao_base", VERSAO_BASE),
            ("gerada_em", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
            ("cobertura", "Bacia do Araripe"),
        ],
    )

    refs: dict[str, int] = {}
    for chave, autores, ano, titulo, veiculo in REFERENCIAS:
        cur = conn.execute(
            "INSERT INTO referencias (chave, autores, ano, titulo, veiculo) VALUES (?,?,?,?,?)",
            (chave, autores, ano, titulo, veiculo),
        )
        refs[chave] = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO bacias (nome, area_km2, area_nota, orientacao, provincia, dominio, contexto, ref_id)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (BACIA["nome"], BACIA["area_km2"], BACIA["area_nota"], BACIA["orientacao"],
         BACIA["provincia"], BACIA["dominio"], BACIA["contexto"], refs[BACIA["ref"]]),
    )
    bacia_id = cur.lastrowid

    seqs: dict[str, int] = {}
    for nome, ordem, idade, desc, ref in SEQUENCIAS:
        cur = conn.execute(
            "INSERT INTO sequencias (bacia_id, nome, ordem, idade, descricao, ref_id) VALUES (?,?,?,?,?,?)",
            (bacia_id, nome, ordem, idade, desc, refs[ref]),
        )
        seqs[nome] = cur.lastrowid

    grupos: dict[str, int] = {}
    for nome, supergrupo, ref in GRUPOS:
        cur = conn.execute(
            "INSERT INTO grupos (bacia_id, nome, supergrupo, ref_id) VALUES (?,?,?,?)",
            (bacia_id, nome, supergrupo, refs[ref]),
        )
        grupos[nome] = cur.lastrowid

    forms: dict[str, int] = {}
    for (nome, ordem, grupo, seq, idade, litologia, esp, esp_nota, ambiente,
         fossilifera, obs, ref) in FORMACOES:
        cur = conn.execute(
            "INSERT INTO formacoes (bacia_id, grupo_id, sequencia_id, nome, ordem, idade,"
            " litologia, espessura_m, espessura_nota, ambiente, fossilifera, observacoes, ref_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bacia_id, grupos.get(grupo), seqs.get(seq), nome, ordem, idade, litologia,
             esp, esp_nota, ambiente, fossilifera, obs, refs[ref]),
        )
        forms[nome] = cur.lastrowid

    for (form, litotipo, cot_min, cot_max, cot_nota, querogenio, maturidade,
         metodo, ambiente_mo, ref) in GEOQUIMICA:
        conn.execute(
            "INSERT INTO geoquimica (formacao_id, litotipo, cot_min, cot_max, cot_nota,"
            " tipo_querogenio, maturidade, metodo, ambiente_mo, ref_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (forms[form], litotipo, cot_min, cot_max, cot_nota, querogenio, maturidade,
             metodo, ambiente_mo, refs[ref]),
        )

    for form, grupo_bio, detalhe, ref in FOSSEIS:
        conn.execute(
            "INSERT INTO fosseis (formacao_id, grupo_bio, detalhe, ref_id) VALUES (?,?,?,?)",
            (forms[form], grupo_bio, detalhe, refs[ref]),
        )

    for nome, sub_bacia, prof, obs, ref in POCOS:
        conn.execute(
            "INSERT INTO pocos (bacia_id, nome, sub_bacia, prof_embasamento_m, observacoes, ref_id)"
            " VALUES (?,?,?,?,?,?)",
            (bacia_id, nome, sub_bacia, prof, obs, refs[ref]),
        )

    for tema, pos_a, ref_a, pos_b, ref_b, situacao in CONTROVERSIAS:
        conn.execute(
            "INSERT INTO controversias (bacia_id, tema, posicao_a, ref_a_id, posicao_b, ref_b_id, situacao)"
            " VALUES (?,?,?,?,?,?,?)",
            (bacia_id, tema, pos_a, refs[ref_a], pos_b, refs[ref_b], situacao),
        )

    conn.commit()
    return conn


def main() -> None:
    ap = argparse.ArgumentParser(description="Popula a base GeoDB.")
    ap.add_argument("--db", default=str(AQUI / "geo.db"), help="caminho do arquivo SQLite")
    args = ap.parse_args()

    db_path = Path(args.db)
    conn = construir(db_path)
    tabelas = ["referencias", "bacias", "sequencias", "grupos", "formacoes",
               "geoquimica", "fosseis", "pocos", "controversias"]
    print(f"Base criada em {db_path}")
    for t in tabelas:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<16} {n:>4}")
    conn.close()


if __name__ == "__main__":
    main()
