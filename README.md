# Hermes-Geo v2

API FastAPI simplificada para o Hermes Agent. Sem Redis, sem RQ, sem dependencias pesadas. Toda requisicao e salva em JSON com estrutura completa + historico. Cada chamada de API e tracada em `traces/` com tool calls cronometradas.

## Estrutura do projeto

```
Hermes-v2/
├── main.py          # Aplicacao FastAPI — endpoints e configuracao
├── auth.py          # Helpers de API key + dependency FastAPI
├── db_keys.py       # Persistencia JSON das chaves (api_keys.json)
├── database.py      # Persistencia JSON das sessoes (data/*.json)
├── tracer.py        # Tracing de requisicoes (traces/*.json)
├── manage_keys.py   # CLI para gerenciar chaves via terminal
├── api_keys.json    # Banco de chaves (criado automaticamente)
├── data/            # Sessoes salvas (criado automaticamente)
└── traces/          # Traces de requisicoes (criado automaticamente)
```

## Requisitos

- Python 3.10+
- FastAPI + uvicorn
- Hermes Agent CLI instalado e no PATH

```
pip install fastapi uvicorn pydantic
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

## Autenticacao

### Formato da chave

```
malta_<32 caracteres url-safe base64>

Exemplo: malta_Xk9mB2vQpL...
Prefixo armazenado: primeiros 8 caracteres -> "malta_Xk"
```

### Hashing

SHA-256 de toda a string da chave (UTF-8). O digest e armazenado como hexadecimal minusculo. `secrets.compare_digest` e usado para comparacao em tempo constante.

### Gerenciamento via CLI

```bash
# Criar chave
python manage_keys.py create <user_id>

# Listar todas as chaves (sem segredos)
python manage_keys.py list

# Revogar por prefixo (primeiros 8 chars da chave)
python manage_keys.py revoke <key_prefix>
```

Exemplos:

```bash
python manage_keys.py create unisinos
python manage_keys.py create malta_internal
python manage_keys.py list
python manage_keys.py revoke malta_Xk
```

### Gerenciamento via API

Todos os endpoints de gerenciamento de chaves tambem estao disponiveis via API (autenticados com uma chave valida):

```bash
# Criar chave
curl -X POST -H "X-API-Key: sua_chave" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"novo_usuario"}' \
  http://localhost:8000/keys

# Listar chaves
curl -H "X-API-Key: sua_chave" http://localhost:8000/keys

# Revogar chave(s)
curl -X DELETE -H "X-API-Key: sua_chave" \
  http://localhost:8000/keys/malta_Xk
```

### Usando nas requisicoes

Toda requisicao (exceto `/health`) exige o header `X-API-Key`:

```bash
curl -H "X-API-Key: malta_Xk9mB2vQpL..." \
  http://localhost:8000/sessions
```

Se o header estiver ausente: `401 Missing 'X-API-Key' header`

Se a chave for invalida ou revogada: `401 Invalid or revoked API key`

## Endpoints

### Chat

**POST /chat** — Envia uma mensagem para o Hermes CLI e retorna a resposta.

Body:

```json
{
  "query": "O que e o projeto MALTA?",
  "session_id": null,
  "new_session": false
}
```

- `query` (obrigatorio): mensagem do usuario
- `session_id` (opcional): ID de sessao existente para continuar conversa
- `new_session` (opcional, default false): forca criacao de nova sessao

Resposta:

```json
{
  "session_id": "uuid-da-sessao",
  "response": "resposta do hermes",
  "turnos": 1
}
```

### Sessoes

**GET /sessions** — Lista todas as sessoes com metadados.

Resposta:

```json
{
  "total": 2,
  "sessions": [
    {
      "session_id": "uuid",
      "created_at": "2025-01-01T00:00:00+00:00",
      "updated_at": "2025-01-01T00:01:00+00:00",
      "turnos": 3
    }
  ]
}
```

**GET /sessions/{session_id}** — Retorna o JSON completo de uma sessao, incluindo todo o historico de mensagens.

**DELETE /sessions/{session_id}** — Remove uma sessao e seu arquivo JSON.

### Traces

Cada requisicao ao `/chat` gera um trace automaticamente com timing detalhado.

**GET /traces** — Lista todos os traces com metadados.

Resposta:

```json
{
  "total": 5,
  "traces": [
    {
      "trace_id": "uuid",
      "session_id": "uuid",
      "timestamp": "2025-01-01T00:00:00+00:00",
      "duration_s": 12.345,
      "tool_calls_count": 3,
      "error": null
    }
  ]
}
```

**GET /traces/{trace_id}** — Retorna o JSON completo de um trace, incluindo request/response, stdout/stderr do Hermes, e tool calls cronometradas.

### Health Check

**GET /health** — Unico endpoint publico (sem autenticacao). Verifica se a API e o Hermes CLI estao operacionais.

Resposta:

```json
{
  "status": "ok",
  "hermes_cli": "ok",
  "sessoes_ativas": 3,
  "traces_count": 10
}
```

## Seguranca

- Chaves armazenadas como hash SHA-256 (nunca em texto plano)
- Chave raw mostrada uma unica vez na criacao
- Comparacao em tempo constante via `hmac.compare_digest`
- Prefixo (8 chars) usado para identificar/revogar, nunca o hash completo
- `threading.Lock` protege escrita concorrente no arquivo JSON
- Escrita atomica via `os.replace` (arquivo temporario -> destino)

## Variaveis de ambiente

| Variavel | Default | Descricao |
|----------|---------|-----------|
| PORT | 8000 | Porta do servidor HTTP |
| MAX_TURNS | 50 | Numero maximo de turnos por sessao |
| API_KEYS_DB_PATH | ./api_keys.json | Caminho do arquivo JSON de chaves |

## Fluxo de uma requisicao

1. Cliente envia `POST /chat` com `X-API-Key` no header
2. `require_api_key` dependency valida a chave (hash SHA-256, busca no JSON, compara em tempo constante)
3. Se a chave for valida, o `user_id` fica disponivel em `request.state.api_user`
4. Sessao e carregada ou criada (UUID v4)
5. Query e enviada para o Hermes CLI via `subprocess.run`
6. Resposta do Hermes e limpa (ANSI codes, aspas extras) e salva no historico
7. Tool calls sao extraidas do stdout com regex e timestamps
8. Trace completo e salvo em `traces/{trace_id}.json`
9. Resposta retornada ao cliente

## Licenca

Projeto MALTA-GEO — PUCRS / Petrobras / UNISINOS
