# Lightsail-Petrobras — Hermes-Geo

Agente de Geociências ("Gonzaguinha") servido por uma API HTTP, pensado para rodar
em uma instância AWS Lightsail e ser consumido por quem precisa fazer perguntas
técnicas sobre bacias sedimentares, formações, geoquímica, poços e fósseis.

O projeto entrega três coisas em um único deploy:

1. uma **API REST autenticada** (`main.py`) que conversa com o agente e guarda tudo
   em disco, em JSON: histórico de sessão e trace de cada requisição;
2. uma **base geológica estruturada** (`geodb/`) que devolve números exatos com a
   referência bibliográfica que os sustenta, em vez de deixar o modelo "lembrar"
   de uma faixa de COT;
3. um **instalador único** (`install_hermes_lightsail.sh`) que sobe tudo isso em
   uma máquina Ubuntu limpa, incluindo o agente, o modelo no AWS Bedrock, a base
   geológica como serviço e as skills do projeto.

Repositório: <https://github.com/ArthurFachel/Lightsail-Petrobras>
Projeto MALTA-GEO — PUCRS / Petrobras / UNISINOS.

---

## Para que serve

O objetivo é responder pergunta de Geociências com rastreabilidade. O agente é
instruído (`SOUL.md`) a:

- consultar a base estruturada **antes** de responder qualquer dado pontual
  (área de bacia, idade, litologia, espessura, COT, tipo de querogênio,
  profundidade de poço, conteúdo fossilífero) e usar o valor retornado, sem
  arredondar;
- apresentar as **duas interpretações** quando a literatura diverge, em vez de
  escolher uma e chamar de consenso;
- citar a referência bibliográfica ("Castro et al., 2017") e **nunca** expor
  caminho de arquivo, nome de tabela, porta, endpoint ou detalhe de
  infraestrutura;
- responder em português e recusar educadamente o que estiver fora de
  Geociências.

Essa última regra não depende só de instrução: a camada `security.py` filtra a
saída, e a base geológica foi construída para não ter path algum em resposta.

## O que ele consegue fazer

| Capacidade | Onde fica |
|---|---|
| Chat com o agente por HTTP, com sessão persistente | `POST /chat` |
| Histórico completo de cada conversa, em JSON | `db/session_data/` |
| Trace de cada requisição com tool calls cronometradas | `tool_traces/` |
| Autenticação por API key (`malta_...`), criação e revogação | CLI e `/keys` |
| Consulta determinística a dados geológicos com fonte | serviço `geodb/` |
| Atendimento por Telegram, com transcrição automática de áudio | gateway do Hermes |
| Benchmark de qualidade geológica e de segurança | `hermes_benchmark.ipynb` |

## Arquitetura

```
        cliente (curl, notebook, app)
                 │  HTTP + X-API-Key
                 ▼
        main.py  ── FastAPI :8000
                 │   sessões em db/session_data/*.json
                 │   traces  em tool_traces/*.json
                 ▼
        hermes chat (CLI)  ──►  DeepSeek V3.2 no AWS Bedrock
                 │
                 │ MCP (stdio)
                 ▼
        geodb/mcp_bridge.py ──HTTP──► geodb/server.py :9000 ──► geo.db (somente leitura)

        Telegram ──► gateway do Hermes ──► mesmo agente (com STT)
```

A API e a base geológica são deployáveis **separados**. A GeoDB pode sair desta
máquina sem arrastar o resto do projeto: muda uma URL do lado do agente.

---

## Instalação

### Pré-requisitos

- Instância Ubuntu (AWS Lightsail ou EC2), acesso SSH como usuário `ubuntu`
- Par de credenciais AWS com permissão no **Bedrock**, na região onde o
  DeepSeek V3.2 está habilitado (`us-east-1` ou `us-west-2`)
- Porta 8000 liberada no firewall da instância, se a API for acessada de fora

### Rodar o instalador

```bash
# na instância, como usuário comum (NÃO use sudo)
curl -fsSLO https://raw.githubusercontent.com/ArthurFachel/Lightsail-Petrobras/main/install_hermes_lightsail.sh
chmod +x install_hermes_lightsail.sh
./install_hermes_lightsail.sh
```

Edite as três variáveis `AWS_*` no topo do script antes de rodar. Se não editar,
ele cai no modo interativo do `aws configure` e pergunta na hora.

O script é idempotente: rodar de novo atualiza o repositório e reaplica as
configurações, sem duplicar nada. Em 13 passos ele:

1. instala dependências de sistema e clona o repositório em `~/Lightsail-Petrobras`;
2. cria o venv e instala o `requirements.txt` (inclui o `hermes-agent[mcp]`);
3. configura as credenciais AWS e aponta o Hermes para o DeepSeek V3.2 no Bedrock;
4. instala o `SOUL.md` do repositório como personalidade do agente;
5. ajusta o gateway: mensagem de pareamento em português e menu do Telegram
   reduzido a `/help` e `/new`;
6. instala as skills versionadas em `skills/hermes/`;
7. liga a transcrição de áudio local (faster-whisper, sem API key);
8. sobe a GeoDB como serviço systemd de usuário e registra a base como
   ferramenta MCP do agente.

### Base geológica em outra máquina

Quando a base passar a ser hospedada pela UNISINOS, rode o instalador assim e
ele pula o serviço local, apontando o agente para lá:

```bash
GEODB_REMOTE_URL=https://geodb.unisinos.br \
GEODB_REMOTE_TOKEN=geodb_... \
./install_hermes_lightsail.sh
```

### Instalação manual da API (sem o instalador)

```bash
git clone https://github.com/ArthurFachel/Lightsail-Petrobras.git
cd Lightsail-Petrobras
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt boto3
```

Requer Python 3.10+ e o comando `hermes` disponível no PATH.

---

## Primeiros passos

### 1. Criar uma API key

Todos os comandos abaixo rodam a partir da **raiz do repositório**, com o venv
ativo:

```bash
python -m db.manage_keys create unisinos     # cria e mostra a chave UMA vez
python -m db.manage_keys list                # lista as chaves, sem segredos
python -m db.manage_keys revoke malta_Xk     # revoga pelo prefixo (8 primeiros chars)
```

A chave tem o formato `malta_<32 caracteres>` e só é exibida no momento da
criação. O que fica em disco é o hash SHA-256 e o prefixo de 8 caracteres.
Guarde a chave na hora: não há como recuperá-la depois.

### 2. Subir a API

```bash
python main.py              # sobe em http://0.0.0.0:8000
PORT=8080 python main.py    # ou na porta que preferir
```

Para deixar rodando após fechar o SSH, use `tmux`, `nohup` ou um serviço systemd.

### 3. Conferir se está no ar

```bash
curl http://SEU_IP:8000/health
```

```json
{"status": "ok", "hermes_cli": "ok", "sessoes_ativas": 3, "traces_count": 10}
```

`status: degraded` significa que a API subiu mas o CLI do Hermes não foi
encontrado. `/health` é o único endpoint público; todo o resto exige a chave.

### 4. Primeira pergunta

```bash
curl -X POST http://SEU_IP:8000/chat \
  -H "X-API-Key: malta_SUA_CHAVE" \
  -H "Content-Type: application/json" \
  -d '{"query":"Quais são as formações geológicas da Bacia do Araripe?"}'
```

```json
{
  "session_id": "3f1c...",
  "response": "Da base para o topo: Cariri, Brejo Santo, Missão Velha, ...",
  "turnos": 1
}
```

Para continuar a conversa, mande o mesmo `session_id` na próxima requisição.

---

## Usando a API

Toda requisição, exceto `/health`, exige o header `X-API-Key`.
Sem o header: `401 Missing 'X-API-Key' header`.
Chave inválida ou revogada: `401 Invalid or revoked API key`.

Documentação interativa (OpenAPI) em `http://SEU_IP:8000/docs`.

### Chat

**POST /chat**

| Campo | Obrigatório | Descrição |
|---|---|---|
| `query` | sim | a pergunta |
| `session_id` | não | continua uma sessão existente |
| `new_session` | não (default `false`) | força abrir sessão nova |

Resposta: `session_id`, `response`, `turnos`.

Erros possíveis: `404` (session_id inexistente), `500` (CLI do Hermes não
encontrado), `504` (o agente passou de 120 s).

### Sessões

| Método | Rota | O que faz |
|---|---|---|
| GET | `/sessions` | lista todas as sessões com metadados |
| GET | `/sessions/{id}` | histórico completo da sessão |
| DELETE | `/sessions/{id}` | apaga a sessão e seu arquivo |

### Traces

Cada chamada ao `/chat` gera um trace com a duração total, o retorno do CLI e as
tool calls cronometradas. Serve para auditar o que o agente consultou antes de
responder.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/traces` | lista os traces |
| GET | `/traces/{id}` | trace completo de uma requisição |

### Chaves

Os mesmos comandos do CLI existem via API, sempre autenticados com uma chave
válida:

```bash
# criar
curl -X POST http://SEU_IP:8000/keys \
  -H "X-API-Key: malta_SUA_CHAVE" -H "Content-Type: application/json" \
  -d '{"user_id":"novo_usuario"}'

# listar
curl http://SEU_IP:8000/keys -H "X-API-Key: malta_SUA_CHAVE"

# revogar por prefixo
curl -X DELETE http://SEU_IP:8000/keys/malta_Xk -H "X-API-Key: malta_SUA_CHAVE"
```

### Variáveis de ambiente da API

| Variável | Default | Para que serve |
|---|---|---|
| `PORT` | `8000` | porta do servidor HTTP |
| `API_KEYS_DB_PATH` | `db/api_keys.json` | arquivo onde ficam os hashes das chaves |

---

## Base geológica (GeoDB)

Serviço separado, em `geodb/`: SQLite **somente leitura** servido em uma porta,
falando REST para humanos (`/docs`) e MCP para o agente ao mesmo tempo.

Existe porque dado pontual é linha de tabela, não texto corrido. Buscar a faixa
de COT da Ipubi dentro de um `.md` convida o modelo a errar uma casa decimal;
aqui ele consulta e recebe o valor exato, sempre o mesmo, já com a referência.

Cobertura atual: 1 bacia (Araripe), 5 sequências, 3 grupos, 10 formações, 4
registros de geoquímica, 37 de fósseis, 1 poço e 4 controvérsias registradas.

Operação do dia a dia na instância:

```bash
systemctl --user status geodb      # estado do serviço
journalctl --user -u geodb -f      # logs
curl http://127.0.0.1:9000/health  # health check (público)
hermes mcp test geodb              # o agente enxerga a base?
```

Detalhes de deploy, endpoints, variáveis de ambiente, testes e como passar a
base para outra instituição: [`geodb/README.md`](geodb/README.md).

## Documentos de apoio

`fontes_de_conhecimento/` guarda os artigos científicos e as descrições de bacias
que o agente usa para o conteúdo **interpretativo**: contexto tectônico,
histórico de propostas estratigráficas, discussão de ambientes deposicionais.
A divisão de trabalho é clara: a base estruturada responde o fato, os documentos
explicam o fato.

## Telegram e transcrição de áudio

O instalador liga o atendimento por Telegram no gateway do Hermes com:

- mensagem de pareamento em português para quem ainda não tem acesso
  (o usuário recebe um código e o administrador aprova com
  `hermes pairing approve telegram <codigo>`);
- menu de comandos reduzido a `/help` e `/new`;
- transcrição automática de mensagens de voz com faster-whisper rodando local,
  sem API key (o modelo `base`, ~150 MB, baixa no primeiro uso).

As skills versionadas em `skills/hermes/` documentam esses dois recursos para o
próprio agente, e são instaladas em `~/.hermes/skills/hermes/`. Elas servem à
máquina de destino: não faz sentido instalá-las em estação de desenvolvimento.

## Benchmark

`hermes_benchmark.ipynb` roda uma bateria de perguntas contra a API e salva as
respostas em `resultados_benchmark/` (CSV + JSON) para conferência contra o
gabarito.

Para usar, ajuste no notebook:

```python
BASE_URL = "http://SEU_IP:8000"
CSV_PATH = "benchmark_questions/benchmark_chatbot_geologia.csv"
NOVA_SESSAO_POR_PERGUNTA = True
```

A chave é pedida via `getpass`, não fica salva no notebook. Use sempre uma
sessão nova por pergunta, senão o contexto de uma contamina a seguinte.

Conjuntos disponíveis:

- `benchmark_chatbot_geologia_v2.csv` — 78 itens com gabarito legível por
  máquina, corrigidos por `benchmark_questions/avaliar_benchmark.py`. É o
  conjunto a usar para medir o efeito da base estruturada (protocolo A/B em
  [`benchmark_questions/README_benchmark_v2.md`](benchmark_questions/README_benchmark_v2.md));
- `benchmark_chatbot_geologia.csv` — v1, 31 itens, correção manual;
- `benchmark_seguranca_llm.csv` — 20 casos adversariais (vazamento de caminhos,
  credenciais, prompts internos, dados de outra sessão, prompt injection).
  Critério de pontuação em
  [`benchmark_questions/README_seguranca.md`](benchmark_questions/README_seguranca.md).

---

## Segurança

- Chaves guardadas como hash SHA-256, nunca em texto plano; comparação em tempo
  constante; a chave crua aparece uma única vez, na criação.
- Revogação por prefixo de 8 caracteres, sem expor o hash.
- `security.py` sanitiza respostas, históricos e traces antes de expor ou
  persistir: caminhos, tokens, hashes, variáveis de ambiente, IPs e dados SSH
  são redigidos.
- A GeoDB abre o SQLite em modo `ro` e não aceita SQL vindo de fora: o agente
  escolhe uma função nomeada e passa parâmetros. Nenhuma resposta contém
  caminho, e há teste cobrindo isso.
- Escrita do arquivo de chaves protegida por `threading.Lock` e feita de forma
  atômica (`os.replace`).
- O arquivo de chaves (`db/api_keys.json`), as sessões (`db/session_data/`) e os
  traces (`tool_traces/`) contêm dados de operação. Não versione nem publique.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `/health` responde `degraded` | `hermes` fora do PATH | ative o venv antes de subir a API |
| `401` em toda requisição | chave ausente, revogada ou com espaço sobrando | `python -m db.manage_keys list` |
| `504` no `/chat` | o agente passou de 120 s | pergunta muito ampla, ou o Bedrock está lento |
| Agente responde número sem citar fonte | não enxergou a base | `hermes mcp test geodb` |
| `hermes mcp test geodb` falha citando o SDK `mcp` | suporte MCP ausente no runtime | `hermes setup tools --non-interactive` |
| GeoDB não volta após reboot | systemd de usuário sem linger | `sudo loginctl enable-linger $USER && systemctl --user enable --now geodb` |
| `ModuleNotFoundError: No module named 'db'` | script chamado por caminho | use `python -m db.manage_keys ...` a partir da raiz do repositório |

## Estrutura do repositório

```
Lightsail-Petrobras/
├── main.py                        # API FastAPI: /chat, /sessions, /traces, /keys
├── tracer.py                      # gravação dos traces
├── security.py                    # sanitização de saída
├── SOUL.md                        # personalidade e regras do agente (Gonzaguinha)
├── requirements.txt
├── install_hermes_lightsail.sh    # instalador completo (13 passos)
├── hermes_benchmark.ipynb         # runner do benchmark
├── db/                            # chaves e persistência de sessões
│   ├── auth.py, db_keys.py, database.py
│   ├── manage_keys.py             # CLI de chaves
│   ├── api_keys.json              # criado automaticamente
│   └── session_data/              # criado automaticamente
├── geodb/                         # base geológica (serviço separado) — ver README próprio
├── fontes_de_conhecimento/        # artigos e descrições de bacias
├── benchmark_questions/           # CSVs de benchmark + critério de segurança
├── resultados_benchmark/          # saídas das execuções
├── skills/hermes/                 # skills instaladas na máquina de destino
├── tests/                         # testes da camada de sanitização
└── tool_traces/                   # criado automaticamente
```

## Créditos

MALTA-LAB / PUCRS — Arthur Fachel e Otávio Parraga.
Projeto MALTA-GEO: PUCRS / Petrobras / UNISINOS.
