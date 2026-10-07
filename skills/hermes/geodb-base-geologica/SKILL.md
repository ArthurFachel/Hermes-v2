---
name: geodb-base-geologica
description: Use when deploying, troubleshooting, extending, or querying the GeoDB service (SQLite + porta, REST + MCP) do projeto Hermes-Geo. Cobre o serviço geodb/, a ponte MCP, a carga de dados com referência obrigatória e as armadilhas de autenticação e transporte.
---

# GeoDB — base geológica estruturada atrás de uma porta

A GeoDB serve dados geológicos exatos (área de bacia, faixa de COT, profundidade
de poço) em uma porta própria, somente leitura. Existe porque fato numérico em
texto corrido convida o modelo a errar casa decimal, e porque a base precisa
poder trocar de dono sem arrastar o resto do projeto.

```
Hermes ──stdio──► mcp_bridge.py ──HTTP──► server.py ──► geo.db (mode=ro)
                                   :9000   /v1  REST + OpenAPI (/docs)
                                           /mcp MCP streamable
```

A ponte roda do lado do agente; o `server.py` e o `geo.db`, do lado de quem é
dono do dado. Essa separação é o ponto do desenho, não um detalhe.

## Operar

```bash
cd ~/Hermes-v2/geodb
./.venv/bin/python seed.py                  # recria geo.db do zero
./.venv/bin/python -m pytest tests/ -q      # 22 testes

systemctl --user status geodb
systemctl --user restart geodb
journalctl --user -u geodb -f

curl -s localhost:9000/health                                   # público
curl -s -H "X-API-Key: $(cat ~/.hermes/.secrets/geodb_token)" \
     localhost:9000/v1/formacoes/Ipubi/geoquimica
hermes mcp test geodb
```

`seed.py` apaga e recria o arquivo. Nunca rode contra uma base que recebeu
edições manuais — não há migração, a fonte da verdade é o `seed.py`.

## Estender os dados

Cada linha nova precisa corresponder a uma afirmação presente em um documento de
`fontes_de_conhecimento/`, com `ref_id` preenchido. Não invente número,
formação, fóssil ou referência: a base existe justamente para ser o lugar onde o
dado é confiável. Se o documento não traz o valor, a linha não entra.

Fluxo: adicionar a referência em `REFERENCIAS`, adicionar a linha na lista
correspondente, rodar `seed.py`, rodar os testes. O teste
`test_toda_formacao_tem_fonte` pega linha órfã.

A tabela `controversias` é deliberada. Quando dois trabalhos divergem, codifique
a divergência como dado em vez de esperar que o RAG ache os dois lados. Ex.:
direção da ingressão marinha aptiana, Goldberg et al. (2019) de SSW contra Melo
et al. (2020) do Norte.

## Mover a base para outro dono

Do lado do dono: copiar `geodb/`, rodar `seed.py`, subir `server.py` com
`GEODB_TOKEN` próprio e `GEODB_ALLOWED_HOSTS` incluindo o host público.

Do lado do agente:

```bash
GEODB_REMOTE_URL=https://geodb.exemplo.br \
GEODB_REMOTE_TOKEN=geodb_... \
./install_hermes_lightsail.sh
```

Os passos [12/13] e [13/13] detectam `GEODB_REMOTE_URL`, pulam o serviço local e
apontam só a ponte.

## Armadilhas

**`app.mount()` não herda o `Depends` do FastAPI.** Autenticação declarada nas
rotas REST deixa o `/mcp` montado completamente aberto — a base inteira sai sem
token. Autentique em middleware ASGI, que cobre as duas superfícies, e mantenha
o teste que verifica 401 no `/mcp`.

**O transporte HTTP do MCP pode não funcionar no Hermes.** Algumas instalações
falham com `requires HTTP transport but mcp.client.streamable_http is not
available`. Use a ponte stdio (`mcp_bridge.py`), que funciona em todas. O
endpoint `/mcp` continua no ar para Claude Desktop e Cursor.

**O SDK `mcp` precisa estar no runtime do Hermes, não em um venv qualquer.** Se
`hermes mcp test` responder `requires the 'mcp' Python SDK`, o pacote existe mas
em um Python diferente do runtime (checar versão do interpretador contra a do
`site-packages`). Resolver com `hermes setup tools --non-interactive`, não
instalando `mcp` na mão.

**Proteção contra DNS rebinding bloqueia acesso remoto.** O MCP liga
`enable_dns_rebinding_protection` por padrão. Sem o host público em
`GEODB_ALLOWED_HOSTS`, a conexão de fora morre sem erro óbvio.

**Não nomeie o módulo de consulta como `db.py`.** O repositório já tem um pacote
`db/` e o import fica ambíguo dependendo do diretório de execução. O arquivo
chama `consultas.py` por esse motivo.

**Entrada de usuário não vai crua para `MATCH` do FTS5.** Pontuação levanta
`OperationalError`. Extraia tokens com `\w+`, descarte os de até 3 caracteres e
monte `"termo"* OR "termo"*`.

**A base é somente leitura por conexão, não por permissão.** `file:geo.db?mode=ro`
é o que garante; o `chmod 444` é cinto extra. Mantenha o teste que espera
`OperationalError` em `DELETE`.

## Como o agente deve consultar

Consulte a base antes de responder qualquer pergunta com número, nome de
formação, faixa de valor ou profundidade. O valor da base ganha de estimativa e
de memória paramétrica.

Chame `controversias` antes de afirmar que algo é consenso. Se o tema tiver duas
posições registradas, apresente as duas com suas fontes.

Cite o campo `fonte` que vem na resposta. Nunca cite caminho de arquivo, nome de
tabela ou endpoint — nenhuma resposta da base contém isso, e há teste cobrindo,
mas a regra vale para o texto que você escreve por cima.

Se a base estiver indisponível, a ferramenta devolve um aviso neutro. Responda
pelas demais fontes e diga que o dado estruturado não pôde ser consultado. Não
tente adivinhar o número.
