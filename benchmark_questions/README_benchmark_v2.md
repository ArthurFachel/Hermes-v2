# Benchmark de geologia v2 — protocolo de medicao

O v2 existe para responder uma pergunta que o v1 nao conseguia responder:
**a base estruturada (GeoDB) melhora as respostas, e em quanto?**

Arquivos:

| Arquivo | Para que serve |
|---|---|
| `benchmark_chatbot_geologia_v2.csv` | 78 itens, com gabarito legivel por maquina |
| `avaliar_benchmark.py` | corrige automaticamente e compara duas rodadas |
| `benchmark_chatbot_geologia.csv` | v1, mantido como esta (os 31 itens dele estao dentro do v2, com os mesmos ids) |
| `benchmark_seguranca_llm.csv` | benchmark de seguranca, separado (ver `README_seguranca.md`) |

## O que mudou em relacao ao v1

1. **Correcao automatica.** Cada item traz `valores_obrigatorios`,
   `termos_proibidos` e `fonte_esperada`. 63 dos 78 itens sao corrigidos sem
   leitura humana, o que torna viavel rodar a bateria duas vezes e comparar.
2. **Flag `requer_base`.** Separa o que so a base estruturada responde do que o
   modelo responde de memoria. E o recorte que vira o numero de capa.
3. **Categorias novas, desenhadas para discriminar com/sem base:**

   | Categoria | Itens | O que mede |
   |---|---|---|
   | Fato Pontual | 14 | valor exato com a referencia junto |
   | Controversia | 5 | apresenta as DUAS posicoes, sem fabricar consenso |
   | Agregacao | 5 | cruza formacao, grupo, fossil e COT entre tabelas |
   | Premissa Falsa | 4 | corrige o usuario em vez de concordar |
   | Ausencia de Dado | 4 | admite a lacuna em vez de inventar numero |
   | Tolerancia de Nome | 4 | `ipubi`, `IPUBI`, `missao-velha` resolvem igual |
   | Fidelidade Numerica | 3 | nao arredonda 17,2-28,6% para "cerca de 20%" |
   | Ordem Estratigrafica | 3 | sequencia correta da coluna |
   | Sigilo da Fonte | 3 | cita referencia, nunca caminho/tabela/porta |
   | Canario de Versao | 2 | discriminador binario (ver abaixo) |

4. **Perguntas sem muleta.** No v1, varios itens comecam com "Segundo os
   documentos...". Isso entrega ao modelo que ele deve buscar. No v2 as
   perguntas de fato pontual sao feitas como um usuario real faria, e parte do
   que se mede e justamente se o agente busca por conta propria.

5. **Canario de versao (`L01`).** A pergunta "qual a versao dos dados que voce
   consulta?" so pode ser respondida com `araripe-2026.10-r1`, string que nao
   existe em nenhum documento nem no conhecimento do modelo. Se o agente acerta,
   consultou a base. Se erra, nao consultou. E o teste mais limpo da bateria.

## Rodar o A/B

Duas rodadas identicas, mudando so a disponibilidade da base.

### Rodada A — sem a base

```bash
hermes config set mcp_servers.geodb.enabled false
hermes mcp test geodb          # deve falhar/nao listar ferramentas
```

Se o `config set` nao aceitar a chave aninhada, edite `~/.hermes/config.yaml` e
troque `enabled: true` por `false` no bloco `mcp_servers.geodb`.

Nao e preciso reiniciar a API: cada `POST /chat` dispara um `hermes chat` novo,
que le a configuracao na hora.

No notebook `hermes_benchmark.ipynb`:

```python
CSV_PATH = "benchmark_questions/benchmark_chatbot_geologia_v2.csv"
CSV_FALLBACK_URL = None
NOVA_SESSAO_POR_PERGUNTA = True
```

Rode e guarde o CSV gerado como, por exemplo,
`resultados_benchmark/sem_base_<data>.csv`.

### Rodada B — com a base

```bash
hermes config set mcp_servers.geodb.enabled true
hermes mcp test geodb          # deve conectar e listar as ferramentas
```

Mesma bateria, mesmo dia, mesmo modelo. Guarde como `com_base_<data>.csv`.

### Corrigir e comparar

```bash
cd ~/Lightsail-Petrobras
python benchmark_questions/avaliar_benchmark.py \
    resultados_benchmark/sem_base_<data>.csv \
    resultados_benchmark/com_base_<data>.csv \
    --rotulos "sem GeoDB" "com GeoDB"
```

Saida: acerto por categoria em cada rodada, o recorte `requer_base=sim`, a taxa
de citacao da referencia e a lista nominal de itens que passaram a acertar e dos
que regrediram.

Para os 15 itens que exigem leitura humana (conhecimento parametrico e web):

```bash
python benchmark_questions/avaliar_benchmark.py resultados_benchmark/com_base_<data>.csv \
    --exportar-manuais resultados_benchmark/manuais_<data>.csv
```

Planilha com `nota_0_1_2` em branco para preencher: 2 correto, 1 parcial,
0 incorreto.

## O que reportar

Quatro numeros, nessa ordem:

1. acerto no subconjunto `requer_base=sim`, sem e com a base;
2. acerto na categoria Fato Pontual, sem e com;
3. taxa de citacao da referencia, sem e com;
4. itens que regrediram (idealmente zero; se houver, nomeie e explique).

Registre junto o modelo usado, a data e a versao da base (`L01` devolve a
versao: `araripe-2026.10-r1`). Sem isso o resultado nao e reproduzivel.

Cuidados que mudam o resultado se ignorados:

- sessao nova por pergunta, senao a resposta de uma vaza na seguinte;
- mesma janela de tempo nas duas rodadas (modelo hospedado muda de
  comportamento entre versoes);
- nao editar o `SOUL.md` entre as rodadas.

## Sintaxe do gabarito maquinal

Para adicionar ou ajustar um item:

```
valores_obrigatorios : grupos separados por "||"  -> TODOS precisam casar
                       variantes dentro do grupo separadas por "~" -> QUALQUER uma serve
                       cada variante e uma regex
termos_proibidos     : variantes separadas por "~" -> QUALQUER casamento reprova
fonte_esperada       : variantes separadas por "~" -> nao reprova; entra na taxa de citacao
tipo_avaliacao       : auto | misto | manual
requer_base          : sim | nao
```

A resposta e normalizada antes do casamento: minusculas, sem acento, separador
de milhar removido (`1.498` -> `1498`) e virgula decimal virando ponto
(`17,2` -> `17.2`). Escreva as regexes ja nesse formato: `\b1498\b`,
`\b17\.20?\b`.

Itens so de vazamento (como `M02` e `M03`) tem `valores_obrigatorios` vazio e
apenas `termos_proibidos`: passam quando nada proibido aparece.

Ancore numeros com `\b` e, quando possivel, com a unidade (`\b20 ?m\b`). Sem
isso, `20` casa dentro de `2.500` e o item passa por acidente.

**Nao invente gabarito.** Todo valor dos itens novos saiu da carga atual da
GeoDB (`geodb/seed.py`), com a referencia que o acompanha. Ao estender a base,
estenda o benchmark na mesma leva.

## Sanidade do proprio benchmark

O corretor foi verificado com duas rodadas sinteticas:

- respostas = o proprio `gabarito_esperado`: 63/63 itens automaticos corretos
  (nenhum padrao inalcancavel);
- respostas = texto plausivel porem errado ("cerca de 20%", "2.500 m",
  "querogenio tipo II"): 6/63.

Se uma alteracao futura derrubar o primeiro numero, o padrao novo esta quebrado,
nao o agente.
