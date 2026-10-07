# GeoDB

Base geológica estruturada servida em uma porta. SQLite somente-leitura, com
REST para humanos e MCP para o agente.

O ponto do desenho é a **fronteira de propriedade**: a base não precisa morar na
mesma máquina do agente. Quem hospeda o serviço é dono do dado. Hoje roda local;
quando a base passar para a UNISINOS, muda uma URL do lado do Hermes e nada mais.

```
                    ┌──────────── máquina de quem é dono do dado ────────────┐
   Hermes           │                                                        │
     │              │   server.py ──► geo.db (sqlite, mode=ro)               │
     │  stdio       │      ▲                                                 │
     ▼              │      │ :9000                                           │
 mcp_bridge.py ─────┼──────┘   /v1/...  REST + OpenAPI  (humanos, /docs)     │
       HTTP         │          /mcp     MCP streamable  (outros agentes)     │
                    └────────────────────────────────────────────────────────┘
```

## Por que existe

As perguntas factuais do benchmark não são texto corrido, são linha de tabela:
área da bacia, faixa de COT da Ipubi, profundidade do embasamento no poço
2-AP-1-CE. Buscar esses números dentro de um `.md` convida o modelo a errar uma
casa decimal. Aqui ele consulta e recebe o valor exato, sempre o mesmo, já
acompanhado da referência que o sustenta.

Os documentos continuam valendo para o raciocínio interpretativo. A base vale
para o fato pontual.

## Subir

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python seed.py                 # cria geo.db

GEODB_TOKEN="$(python3 -c 'import secrets;print("geodb_"+secrets.token_urlsafe(32))')" \
  ./.venv/bin/python server.py
```

Abra `http://127.0.0.1:9000/docs`. É a API navegável — serve de demonstração
para quem não é desenvolvedor.

## Variáveis de ambiente

| Variável | Default | Para que serve |
|---|---|---|
| `GEODB_PATH` | `./geo.db` | caminho do SQLite |
| `GEODB_TOKEN` | *(vazio)* | token exigido em `X-API-Key`. Vazio = serve aberto, com aviso no log |
| `GEODB_ALLOWED_HOSTS` | `localhost,127.0.0.1` | hosts aceitos pelo MCP. **Precisa incluir o host público para acesso remoto** |
| `HOST` | `127.0.0.1` | interface de bind. `0.0.0.0` só atrás de proxy/TLS |
| `PORT` | `9000` | porta HTTP |

## Endpoints

| REST | Ferramenta MCP |
|---|---|
| `GET /v1/bacias` | `listar_bacias` |
| `GET /v1/bacias/{nome}` | `descrever_bacia` |
| `GET /v1/formacoes?grupo=&sequencia=` | `listar_formacoes` |
| `GET /v1/formacoes/{nome}` | `descrever_formacao` |
| `GET /v1/formacoes/{nome}/geoquimica` | `geoquimica_formacao` |
| `GET /v1/formacoes/{nome}/fosseis` | `fosseis_formacao` |
| `GET /v1/fosseis?grupo_biologico=` | `buscar_fossil` |
| `GET /v1/pocos/{nome}` | `buscar_poco` |
| `GET /v1/controversias?tema=` | `controversias` |
| `GET /v1/busca?termo=` | `busca_livre` |

`GET /health` é público. Todo o resto exige `X-API-Key` quando `GEODB_TOKEN`
está definido — inclusive `/mcp`, que é um app montado e por isso tem a
autenticação no nível ASGI, não no `Depends` do FastAPI.

## Ligar no Hermes

O instalador (`install_hermes_lightsail.sh`, passos 12 e 13) faz isso sozinho.
Manualmente, em `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  geodb:
    command: /caminho/para/geodb/.venv/bin/python
    args: [/caminho/para/geodb/mcp_bridge.py]
    env:
      GEODB_URL: http://127.0.0.1:9000     # ou o host da UNISINOS
      GEODB_TOKEN: geodb_...
    tools:
      prompts: false
      resources: false
```

Depois: `hermes mcp test geodb`.

### Por que a ponte stdio, se o serviço já fala MCP em `/mcp`

O SDK `mcp` embutido em algumas instalações do Hermes não resolve o cliente HTTP
em runtime (`requires HTTP transport but mcp.client.streamable_http is not
available`). O transporte stdio funciona em todas. A ponte é um subprocesso que
fala stdio com o Hermes e HTTP com a porta, então **a separação de máquinas é
preservada**: a ponte roda do lado do agente, a base do lado do dono.

O endpoint `/mcp` continua no ar para clientes que suportem HTTP (Claude
Desktop, Cursor).

## Quando a base mudar de dono

Do lado da UNISINOS: copiar esta pasta, rodar `seed.py`, subir o `server.py` com
um `GEODB_TOKEN` próprio e `GEODB_ALLOWED_HOSTS` com o host público. Nada mais
do projeto precisa ir junto.

Do lado de vocês: rodar o instalador com

```bash
GEODB_REMOTE_URL=https://geodb.unisinos.br \
GEODB_REMOTE_TOKEN=... \
./install_hermes_lightsail.sh
```

Os passos 12 e 13 detectam `GEODB_REMOTE_URL`, pulam o serviço local e apontam
o Hermes para lá.

## Garantias

- **Somente leitura.** A conexão é aberta como `file:geo.db?mode=ro`. Um `DELETE`
  levanta `OperationalError`, e há teste cobrindo isso.
- **Sem SQL vindo de fora.** O agente escolhe uma função nomeada e passa
  parâmetros; tudo entra por placeholder.
- **Sem vazamento de caminho.** Nenhuma resposta contém path, nome de arquivo ou
  detalhe de infraestrutura — há teste cobrindo isso também. Alinha com a regra
  de sigilo do `SOUL.md`, mas por código, não por instrução.
- **Toda afirmação tem fonte.** Cada linha carrega `ref_id`, e o campo `fonte`
  volta em todo retorno. O agente cita "Castro et al. (2017)" sem nunca tocar no
  arquivo de origem.

## Dados

A carga atual vem de `fontes_de_conhecimento/bacias/Descricao_geral_da_bacia.md`:
1 bacia, 5 sequências, 3 grupos, 10 formações, 4 registros de geoquímica,
37 de fósseis, 1 poço e 4 controvérsias.

A tabela `controversias` é deliberada. O benchmark cobra que o agente apresente
as **duas** interpretações sobre a direção da ingressão marinha aptiana
(Goldberg et al. 2019, de SSW, contra Melo et al. 2020, do Norte). Codificar a
divergência como dado é mais confiável do que torcer para o RAG achar as duas.

Os outros nove artigos de `fontes_de_conhecimento/artigos/` ainda não foram
extraídos — são ~670 KB.

**Ao estender, não invente.** Cada linha nova precisa corresponder a uma
afirmação presente em um documento, com `ref_id` preenchido.

## Testes

```bash
./.venv/bin/python -m pytest tests/ -q
```

22 testes: integridade dos dados (toda formação e toda geoquímica têm fonte,
ordem estratigráfica sem buracos), os casos factuais que o benchmark cobra,
tolerância de nome (`ipubi` = `Formação Ipubi` = `IPUBI`) e a superfície HTTP
(token exigido em REST e em MCP, nenhum caminho vazado).
