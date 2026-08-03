# Análise dos Resultados — Benchmark Hermes-Geo v2

**Dataset:** `benchmark_chatbot_geologia.csv`
**Total de perguntas:** 31
**Categorias:** Conhecimento Paramétrico (A), RAG (B), Web (C), Híbrida (D)

---

## 1. Resumo Geral

| Categoria | Corretas | Parciais | Incorretas/Falhas | Acurácia |
|---|---|---|---|---|
| A — Conhecimento Paramétrico | 7/7 | 0 | 0 | **100%** |
| B — RAG | 5/10 | 1 | 4 | **50%** |
| C — Web | 4/7 | 2 | 1 (bug) | **57%** |
| D — Híbrida | 4/7 | 0 | 3 | **57%** |
| **Total** | **20/31** | **3** | **8** | **~65%** |

O conhecimento paramétrico do modelo é sólido (100%). O gargalo de desempenho está concentrado na **recuperação de documentos (RAG)** e em falhas de **pipeline/engenharia**, não na capacidade de raciocínio geológico do modelo.

---

## 2. Categoria A — Conhecimento Paramétrico (7/7 corretas)

Todas as respostas bateram com o gabarito esperado, muitas vezes com mais profundidade do que o exigido.

- **A7** (Rock-Eval: S1, S2, Tmax, IH) acertou todos os parâmetros e limiares corretamente (Tmax <435°C imaturo, 435–470°C janela do óleo, >470°C supermaturo).
- Nenhuma armadilha ou lacuna identificada nesta categoria.

**Conclusão:** o modelo de base tem conhecimento geológico confiável quando não depende de recuperação externa.

---

## 3. Categoria B — RAG (5/10 corretas, 1 parcial, 4 incorretas)

| ID | Resultado | Observação |
|---|---|---|
| B1 | ⚠️ Parcial | Não encontrou os documentos; usou conhecimento geral e deu faixa aproximada (8.000–10.000 km²) em vez do valor preciso (~9.000 km²). Falha de retrieval, não de conteúdo. |
| B2 | ✅ Correta | As 5 sequências de Fambrini et al. (2020) batem exatamente. |
| B3 | ✅ Correta | 3 grupos e formações do Supergrupo Araripe corretos. |
| B4 | ❌ Incorreta | Diz não ter encontrado a faixa de COT nem o querogênio de Castro et al. (2017) — **mas o mesmo dado foi recuperado corretamente em D1**, na mesma sessão. |
| B5 | ✅ Correta | 1.498 m, sub-bacia de Feira Nova — correto. |
| B6 | ❌ Incorreta | Responde **Formação Crato**; o gabarito é **Formação Romualdo**. Erro factual direto. |
| B7 | ✅ Correta | Duas sequências, LAST/HAST, controle por razão A/S — consistente com Scherer et al. (2015). |
| B8 | ❌ Incorreta (armadilha) | Pergunta-armadilha do benchmark. Inverteu as direções: respondeu Goldberg=Tétis/norte e Melo=Atlântico Sul, quando o gabarito é o oposto (Goldberg=SSW, Melo=Norte/Tétis). |
| B9 | ❌ Incorreta | Diz que Assine (1992) definia **3** sequências (correto: 4), com nomenclatura divergente da que o próprio modelo usou corretamente em B2. |
| B10 | ✅ Correta | ~200 m, arenito quartzoso, lenhos silicificados, Sequência 1/2 — tudo correto. |

**Conclusão:** RAG é o ponto mais fraco do sistema. Além dos casos de "não encontrei", há **erros factuais com alta confiança** (B6, B9), que são mais perigosos do que reconhecer a lacuna.

---

## 4. Categoria C — Web (4/7 corretas, 2 parciais, 1 falha de pipeline)

| ID | Resultado | Observação |
|---|---|---|
| C1 | ✅ Correta | UNESCO 2006, primeiro geoparque das Américas. |
| C2 | ⚠️ Parcial | Não cita o dado quantitativo central (~90–97%/~95% da produção nacional de gipsita), que o critério de avaliação pede explicitamente. |
| C3 | ✅ Correta | Resposta completa e precisa sobre Karl Beurlen. |
| C4 | ⚠️ Parcial | Fica vago sobre a repatriação ("seria devolvido" em 2022), sem confirmar que ocorreu de fato em 2023 — indício de busca web desatualizada. |
| C5 | ✅ Correta | 4 dos 5 gêneros esperados de pterossauro, mais 2 extras válidos. |
| C6 | ✅ Correta | Datas do Aptiano/Albiano batem (diferença de ~0,2 Ma, dentro da margem aceitável). |
| C7 | ❌ **Falha crítica de pipeline** | A resposta contém sintaxe interna de chamada de ferramenta vazada para o usuário (`<｜DSML｜function_calls...`), em vez de texto processado. Bug de engenharia, não erro de conteúdo. |

**Conclusão:** desempenho razoável quando a busca web funciona; C7 expõe um problema real no tratamento de saída do `main.py`/`tracer.py`.

---

## 5. Categoria D — Híbrida (4/7 corretas, 3 falhas)

| ID | Resultado | Observação |
|---|---|---|
| D1 | ✅ Correta | Recupera corretamente os dados de Castro et al. (2017) que **B4 não conseguiu** — mesma fonte, mesma sessão de benchmark. |
| D2 | ✅ Correta | Boa cobertura dos grupos fossilíferos de Crato e Romualdo. |
| D3 | ❌ Incorreta (armadilha repetida) | Mesma pergunta-armadilha de B8; o modelo erra **na mesma direção invertida** novamente (Goldberg=Tétis, Melo=Atlântico Sul). |
| D4 | ✅ Correta (com ressalva) | Datas da ICS corretas; porém inclui idades específicas para Crato/Romualdo que não estão claramente amparadas nos documentos — possível fabricação não verificada. |
| D5 | ❌ Incorreta | Admite não ter busca web disponível; erra a idade da Formação Cariri ("neoproterozoica" em vez de "neo-ordoviciana/eossiluriana") e não confirma a correlação com o Grupo Serra Grande. |
| D6 | ✅ Correta | Conclusões paleoambientais e regra de Pr/Fi corretas; honesto ao admitir que não encontrou os valores numéricos específicos. |
| D7 | ❌ **Resposta truncada** | Corta logo após o título "Posicionamento estratigráfico:", sem nunca abordar o Aquífero Exu — núcleo da pergunta. |

**Conclusão:** perguntas híbridas têm os maiores tempos de resposta (73–107s) e concentram tanto os erros de conteúdo quanto os únicos casos de truncamento observados no benchmark.

---

## 6. Padrões Críticos Identificados

### 6.1 RAG é o gargalo real, não o conhecimento do modelo
Conhecimento paramétrico: 100%. RAG: 50%. O modelo "sabe" a geologia — o problema está na recuperação de documentos.

### 6.2 Inconsistência de retrieval sobre o mesmo fato
B4 falha e D1 acerta a **mesma citação** de Castro et al. (2017), na mesma execução. Isso sugere sensibilidade à formulação da query, chunking inadequado, ou top-k inconsistente — não ausência de dado na base.

### 6.3 A pergunta-armadilha falhou duas vezes, sempre na mesma direção errada
B8 e D3 avaliam se o modelo distingue as interpretações opostas de Goldberg et al. (2019) e Melo et al. (2020). Em ambos os casos o modelo inverteu as direções — e não admitiu incerteza, respondendo com confiança total. Este é o achado mais preocupante: **quando o RAG falha, o modelo não diz "não sei" — ele inventa, e erra sistematicamente no mesmo sentido**.

### 6.4 Bug de pipeline vazando sintaxe interna (C7)
A saída bruta de uma chamada de ferramenta malformada chegou ao usuário final. Indica que a etapa de limpeza de resposta (remoção de códigos ANSI/aspas) não trata adequadamente saídas inesperadas do Hermes CLI.

### 6.5 Truncamento em perguntas de alta latência (D7)
A única resposta cortada no meio ocorreu na pergunta híbrida mais lenta da categoria. Vale investigar timeout no FastAPI ou no `subprocess.run` que chama o Hermes CLI.

### 6.6 Comportamento divergente diante de lacunas de recuperação
- **B1**: admite a lacuna e aproxima com conhecimento geral (comportamento seguro).
- **B6, B9**: preenche a lacuna com fatos específicos incorretos, sem sinalizar incerteza (comportamento de risco).

Para um agente de domínio técnico, esse segundo padrão é mais perigoso do que simplesmente reconhecer a limitação.

---

## 7. Recomendações

1. **Investigar o pipeline de RAG** (chunking, embeddings, top-k) — priorizar por ser a categoria com menor acurácia e pela inconsistência observada entre B4/D1.
2. **Corrigir o vazamento de sintaxe interna** em `main.py`/`tracer.py` (caso C7) antes de qualquer nova rodada de avaliação.
3. **Investigar timeout/truncamento** em perguntas híbridas de alta latência (caso D7).
4. **Reforçar instrução de abstenção**: o agente deveria ser incentivado a admitir incerteza explicitamente quando o RAG não retorna contexto suficiente, em vez de completar com conhecimento paramétrico não verificado e apresentá-lo como fato dos documentos.
5. **Repetir B8/D3** (a pergunta-armadilha) após ajustes no RAG para verificar se a inversão sistemática persiste — isso indicaria um problema mais profundo do que recuperação (possível confusão de contexto entre as duas fontes).