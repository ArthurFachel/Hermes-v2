# Hermes-Geo v2

API FastAPI para o [Hermes Agent](https://hermes-agent.nousresearch.com), especializada em Geociências. Sem Redis, sem RQ, sem dependências pesadas — persistência 100% JSON.

Toda requisição é salva em arquivo JSON com histórico completo da sessão. Cada chamada de API é traçada automaticamente em `tool_traces/` com tool calls cronometradas.

## Estrutura do projeto

```
Hermes-v2/
├── main.py                          # Aplicação FastAPI — endpoints e lógica de chat
├── tracer.py                        # Engine de tracing (salva em tool_traces/)
├── SOUL.md                          # Personalidade do agente — Gonzaguinha (Geociências)
├── requirements.txt                 # Dependências Python
├── install_hermes_lightsail.sh      # Script de deploy para AWS Lightsail
├── benchmark_questions/             # Benchmark do agente (CSV)
│   └── benchmark_chatbot_geologia.csv
├── fontes_de_conhecimento/          # Base de conhecimento interna sobre Geociências
│   ├── artigos/                     # Artigos científicos em PDF e Markdown
│   └── bacias/                      # Descrições de bacias sedimentares
├── db/                              # Camada de persistência
│   ├── auth.py                      # Ciclo de vida das API keys + guard FastAPI
│   ├── database.py                  # Armazenamento de sessões (JSON em session_data/)
│   ├── db_keys.py                   # Persistência do arquivo JSON de chaves
│   ├── manage_keys.py               # CLI para gerenciar chaves via terminal
│   ├── api_keys.json                # Banco de chaves (criado automaticamente)
│   └── session_data/                # Sessões salvas (criado automaticamente)
└── tool_traces/                     # Traces de requisições (criado automaticamente)
```

## Requisitos

- Python 3.10+
- FastAPI + uvicorn
- Hermes Agent CLI instalado e no PATH

```bash
pip install -r requirements.txt
```

## Como rodar

```bash
cd /home/fachel/Desktop/Vscode/Hermes-v2
python main.py
```

Ou especificando a porta:

```bash
PORT=8080 python main.py
```

A API sobe em `http://0.0.0.0:8000` (ou porta definida em `PORT`).

## Autenticação

### Formato da chave

```
malta_<32 caracteres url-safe base64>

Exemplo: malta_Xk9mB2vQpL...
Prefixo armazenado: primeiros 8 caracteres -> "malta_Xk"
```

### Hashing

SHA-256 de toda a string da chave (UTF-8). O digest é armazenado como hexadecimal minúsculo. `secrets.compare_digest` é usado para comparação em tempo constante.

### Gerenciamento via CLI

```bash
# Criar chave
python db/manage_keys.py create <user_id>

# Listar todas as chaves (sem segredos)
python db/manage_keys.py list

# Revogar por prefixo (primeiros 8 chars da chave)
python db/manage_keys.py revoke <key_prefix>
```

Exemplos:

```bash
python db/manage_keys.py create unisinos
python db/manage_keys.py create malta_internal
python db/manage_keys.py list
python db/manage_keys.py revoke malta_Xk
```

### Gerenciamento via API

Todos os endpoints de gerenciamento de chaves também estão disponíveis via API (autenticados com uma chave válida):

```bash
# Criar chave
curl -X POST -H "X-API-Key: ***" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"novo_usuario"}' \
  http://localhost:8000/keys

# Listar chaves
curl -H "X-API-Key: ***" http://localhost:8000/keys

# Revogar chave(s)
curl -X DELETE -H "X-API-Key: ***" \
  http://localhost:8000/keys/malta_Xk
```

### Usando nas requisições

Toda requisição (exceto `/health`) exige o header `X-API-Key`:

```bash
curl -H "X-API-Key: malta_......" \
  http://localhost:8000/sessions
```

Se o header estiver ausente: `401 Missing 'X-API-Key' header`

Se a chave for inválida ou revogada: `401 Invalid or revoked API key`

## Endpoints

### Chat

**POST /chat** — Envia uma mensagem para o Hermes CLI e retorna a resposta.

Body:

```json
{
  "query": "O que é a Bacia do Araripe?",
  "session_id": null,
  "new_session": false
}
```

- `query` (obrigatório): mensagem do usuário
- `session_id` (opcional): ID de sessão existente para continuar conversa
- `new_session` (opcional, default false): força criação de nova sessão

Resposta:

```json
{
  "session_id": "uuid-da-sessao",
  "response": "resposta do hermes",
  "turnos": 1
}
```

### Sessões

**GET /sessions** — Lista todas as sessões com metadados.

**GET /sessions/{session_id}** — Retorna o JSON completo de uma sessão, incluindo todo o histórico de mensagens.

**DELETE /sessions/{session_id}** — Remove uma sessão e seu arquivo JSON.

### Traces

Cada requisição ao `/chat` gera um trace automaticamente com timing detalhado, salvo em `tool_traces/`.

**GET /traces** — Lista todos os traces com metadados.

**GET /traces/{trace_id}** — Retorna o JSON completo de um trace, incluindo request/response, stdout/stderr do Hermes, e tool calls cronometradas.

### Health Check

**GET /health** — Único endpoint público (sem autenticação). Verifica se a API e o Hermes CLI estão operacionais.

Resposta:

```json
{
  "status": "ok",
  "hermes_cli": "ok",
  "sessoes_ativas": 3,
  "traces_count": 10
}
```

## Segurança

- Chaves armazenadas como hash SHA-256 (nunca em texto plano)
- Chave raw mostrada uma única vez na criação
- Comparação em tempo constante via `hmac.compare_digest`
- Prefixo (8 chars) usado para identificar/revogar, nunca o hash completo
- `threading.Lock` protege escrita concorrente no arquivo JSON
- Escrita atômica via `os.replace` (arquivo temporário -> destino)
- Tool progress desligado no Telegram: `hermes config set display.platforms.telegram.tool_progress off`

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| PORT | 8000 | Porta do servidor HTTP |
| MAX_TURNS | 50 | Número máximo de turnos por sessão |
| API_KEYS_DB_PATH | ./db/api_keys.json | Caminho do arquivo JSON de chaves |

## Fluxo de uma requisição

1. Cliente envia `POST /chat` com `X-API-Key` no header
2. `require_api_key` dependency valida a chave (hash SHA-256, busca no JSON, compara em tempo constante)
3. Se a chave for válida, o `user_id` fica disponível em `request.state.api_user`
4. Sessão é carregada ou criada (UUID v4) e salva em `db/session_data/`
5. Histórico da sessão é injetado como contexto para o Hermes CLI via `subprocess.run`
6. Resposta do Hermes é limpa (ANSI codes, aspas extras) e salva no histórico
7. Tool calls são extraídas do stdout com regex e timestamps
8. Trace completo é salvo em `tool_traces/{trace_id}.json`
9. Resposta retornada ao cliente

## Base de conhecimento e benchmark

O repositório inclui uma base de conhecimento interna em `fontes_de_conhecimento/` com artigos científicos e descrições de bacias sedimentares, usada pelo agente Gonzaguinha para responder perguntas de Geociências. A pasta `benchmark_questions/` contém um benchmark com perguntas parametrizadas e de recuperação (RAG) para avaliar o desempenho do agente.

## Licença

Projeto MALTA-GEO — PUCRS / Petrobras / UNISINOS
