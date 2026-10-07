#!/usr/bin/env bash
# Ensaio dos passos [12/13] e [13/13] do instalador, isolado do ambiente real.
# Nao toca em ~/.hermes: usa um HERMES_HOME temporario e uma porta alta.
# Roda sob as mesmas flags do instalador para pegar aborto por `set -e`.
set -euo pipefail

INSTALL_DIR="$HOME/Hermes-v2"
BASE_TESTE="${TMPDIR:-/tmp}/ensaio_geodb"
rm -rf "$BASE_TESTE"
mkdir -p "$BASE_TESTE"
HERMES_HOME="$BASE_TESTE/hermes_home"
mkdir -p "$HERMES_HOME"
printf 'model:\n  provider: bedrock\n' > "$HERMES_HOME/config.yaml"

GEODB_DIR="$INSTALL_DIR/geodb"
GEODB_PORT=9777
GEODB_SECRETS_DIR="$BASE_TESTE/secrets"
GEODB_TOKEN_FILE="$GEODB_SECRETS_DIR/geodb_token"

echo "### [12/13] serviço"
mkdir -p "$GEODB_SECRETS_DIR"; chmod 700 "$GEODB_SECRETS_DIR"
python3 -c "import secrets; print('geodb_' + secrets.token_urlsafe(32))" > "$GEODB_TOKEN_FILE"
chmod 600 "$GEODB_TOKEN_FILE"

# Reusa o venv já existente para não baixar pacotes de novo no ensaio.
[ -x "$GEODB_DIR/.venv/bin/python" ] || python3 -m venv "$GEODB_DIR/.venv"
"$GEODB_DIR/.venv/bin/python" "$GEODB_DIR/seed.py" --db "$BASE_TESTE/geo.db" > /dev/null
chmod 444 "$BASE_TESTE/geo.db"

# Caminho nohup (systemd --user não existe dentro do agente) — é o mesmo
# fallback que o instalador usa quando o bus não está disponível.
GEODB_TOKEN="$(cat "$GEODB_TOKEN_FILE")" \
GEODB_PATH="$BASE_TESTE/geo.db" HOST=127.0.0.1 PORT="$GEODB_PORT" \
GEODB_ALLOWED_HOSTS="localhost,127.0.0.1" \
nohup "$GEODB_DIR/.venv/bin/python" "$GEODB_DIR/server.py" > "$BASE_TESTE/geodb.log" 2>&1 &
SERVIDOR_PID=$!
trap 'kill $SERVIDOR_PID 2>/dev/null || true' EXIT

for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:$GEODB_PORT/health" > /dev/null 2>&1; then
        echo "✅ serviço no ar"; break
    fi
    [ "$i" = "20" ] && { echo "❌ não subiu"; cat "$BASE_TESTE/geodb.log"; exit 1; }
    sleep 1
done

echo "### [13/13] registro MCP"
GEODB_MCP_URL="http://127.0.0.1:$GEODB_PORT"
GEODB_MCP_TOKEN="$(cat "$GEODB_TOKEN_FILE")"

if [ ! -x "$GEODB_DIR/.venv/bin/python" ] || [ ! -f "$GEODB_DIR/mcp_bridge.py" ]; then
    echo "❌ ponte ausente"; exit 1
fi

GEODB_YAML_PY=""
for _py in python3 "$GEODB_DIR/.venv/bin/python"; do
    if "$_py" -c "import yaml" 2>/dev/null; then GEODB_YAML_PY="$_py"; break; fi
done
if [ -z "$GEODB_YAML_PY" ]; then
    echo "-- PyYAML ausente; instalando no venv da GeoDB..."
    "$GEODB_DIR/.venv/bin/pip" install -q pyyaml || true
    "$GEODB_DIR/.venv/bin/python" -c "import yaml" 2>/dev/null \
        && GEODB_YAML_PY="$GEODB_DIR/.venv/bin/python"
fi
[ -n "$GEODB_YAML_PY" ] || { echo "❌ sem PyYAML"; exit 1; }
echo "-- usando $GEODB_YAML_PY para escrever o yaml"

GEODB_MCP_URL="$GEODB_MCP_URL" GEODB_MCP_TOKEN="$GEODB_MCP_TOKEN" \
GEODB_PY="$GEODB_DIR/.venv/bin/python" GEODB_BRIDGE="$GEODB_DIR/mcp_bridge.py" \
HERMES_CFG="$HERMES_HOME/config.yaml" "$GEODB_YAML_PY" - <<'PY'
import os

import yaml

caminho = os.environ["HERMES_CFG"]
url = os.environ["GEODB_MCP_URL"]
token = os.environ.get("GEODB_MCP_TOKEN", "")

try:
    with open(caminho, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
except FileNotFoundError:
    cfg = {}

ambiente = {"GEODB_URL": url}
if token:
    ambiente["GEODB_TOKEN"] = token

cfg.setdefault("mcp_servers", {})["geodb"] = {
    "command": os.environ["GEODB_PY"],
    "args": [os.environ["GEODB_BRIDGE"]],
    "env": ambiente,
    "enabled": True,
    "connect_timeout": 20,
    "timeout": 60,
    "tools": {
        "include": [
            "listar_bacias", "descrever_bacia", "listar_formacoes",
            "descrever_formacao", "geoquimica_formacao", "fosseis_formacao",
            "buscar_fossil", "buscar_poco", "controversias", "busca_livre",
        ],
        "prompts": False,
        "resources": False,
    },
}

with open(caminho, "w", encoding="utf-8") as fh:
    yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)

print(f"-- mcp_servers.geodb (stdio) -> {url}")
PY

echo "### conferindo o config escrito"
"$GEODB_YAML_PY" - <<PY
import yaml
cfg = yaml.safe_load(open("$HERMES_HOME/config.yaml", encoding="utf-8"))
g = cfg["mcp_servers"]["geodb"]
assert cfg["model"]["provider"] == "bedrock", "config preexistente foi perdido"
assert g["command"].endswith("python"), g["command"]
assert g["env"]["GEODB_URL"] == "http://127.0.0.1:$GEODB_PORT"
assert g["env"]["GEODB_TOKEN"].startswith("geodb_")
assert len(g["tools"]["include"]) == 10
print("✅ config.yaml correto e sem perda do conteudo anterior")
PY

echo "### exercitando a ponte stdio contra o serviço"
GEODB_PORT="$GEODB_PORT" GEODB_TOKEN_FILE="$GEODB_TOKEN_FILE" GEODB_DIR="$GEODB_DIR" \
"$GEODB_DIR/.venv/bin/python" - <<'PY'
import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters, stdio_client

porta = os.environ["GEODB_PORT"]
token = open(os.environ["GEODB_TOKEN_FILE"]).read().strip()
diretorio = os.environ["GEODB_DIR"]


async def main():
    params = StdioServerParameters(
        command=f"{diretorio}/.venv/bin/python",
        args=[f"{diretorio}/mcp_bridge.py"],
        env={"GEODB_URL": f"http://127.0.0.1:{porta}", "GEODB_TOKEN": token,
             "PATH": "/usr/bin:/bin"},
    )
    async with stdio_client(params) as fluxos:
        async with ClientSession(fluxos[0], fluxos[1]) as s:
            await s.initialize()
            t = await s.list_tools()
            assert len(t.tools) == 10, len(t.tools)
            print(f"✅ ponte expos {len(t.tools)} ferramentas")
            r = await s.call_tool("geoquimica_formacao", {"nome": "Formação Ipubi"})
            dado = json.loads("".join(c.text for c in r.content if hasattr(c, "text")))
            assert dado["cot_min"] == 17.2 and dado["cot_max"] == 28.6, dado
            assert "Castro" in dado["fonte"], dado
            print(f"✅ tool call retornou COT {dado['cot_min']}-{dado['cot_max']}% "
                  f"({dado['fonte']})")

asyncio.run(main())
PY

echo ""
echo "======================================"
echo " ✅ ENSAIO COMPLETO — passos 12 e 13 ok"
echo "======================================"
