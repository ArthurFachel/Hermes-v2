#!/usr/bin/env bash
# ============================================================
#  Instalador Hermes-v2 (Hermes-Geo) — AWS Lightsail / Ubuntu
#  Autor: Arthur Fachel — MALTA-LAB / PUCRS
#
#  Uso:
#    1. Edite as variáveis AWS_* abaixo (template)
#    2. chmod +x install_hermes_lightsail.sh
#    3. ./install_hermes_lightsail.sh   (rodar como ubuntu, SEM sudo)
# ============================================================
set -euo pipefail

# ============================================================
# TEMPLATE — CREDENCIAIS AWS (EDITE ANTES DE RODAR)
# ============================================================
AWS_ACCESS_KEY_ID="SUA_ACCESS_KEY_ID_AQUI"
AWS_SECRET_ACCESS_KEY="SUA_SECRET_ACCESS_KEY_AQUI"
AWS_REGION="us-east-1"   # DeepSeek no Bedrock: us-east-1 / us-west-2

# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================
REPO_URL="https://github.com/ArthurFachel/Hermes-v2.git"
INSTALL_DIR="$HOME/Hermes-v2"
BEDROCK_MODEL="deepseek.v3.2"   # ID do DeepSeek V3.2 no AWS Bedrock

echo "=========================================="
echo " [1/13] sudo apt update + dependências"
echo "=========================================="
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-yaml git

echo "=========================================="
echo " [2/13] Clonando o repositório"
echo "=========================================="
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repo já existe em $INSTALL_DIR — atualizando (git pull)..."
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "=========================================="
echo " [3/13] Criando e ativando o venv"
echo "=========================================="
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "=========================================="
echo " [4/13] Instalando requirements.txt"
echo "=========================================="
pip install --upgrade pip
pip install -r requirements.txt
# boto3 é necessário pro Hermes falar com o Bedrock
# (não está no requirements.txt — awscli sozinho não basta)
pip install boto3

echo "=========================================="
echo " [5/13] Configurando AWS CLI (aws configure)"
echo "=========================================="
if [[ "$AWS_ACCESS_KEY_ID" == *"AQUI"* || "$AWS_SECRET_ACCESS_KEY" == *"AQUI"* ]]; then
    echo "⚠  Você não editou o template de credenciais no topo do script."
    echo "   Entrando no modo interativo do 'aws configure'..."
    aws configure
    AWS_REGION="$(aws configure get region || echo us-east-1)"
else
    aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
    aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
    aws configure set region "$AWS_REGION"
    aws configure set output json
fi

echo "-- Verificando credenciais (sts get-caller-identity)..."
aws sts get-caller-identity || echo "⚠  Não foi possível validar as credenciais — confira as chaves."

echo "=========================================="
echo " [6/13] Hermes Agent → DeepSeek V3.2 via AWS Bedrock"
echo "=========================================="
# Esses comandos também criam o ~/.hermes na primeira execução
hermes config set model.provider bedrock
hermes config set model.default "$BEDROCK_MODEL"
hermes config set bedrock.region "$AWS_REGION"

echo "=========================================="
echo " [7/13] Substituindo o SOUL.md do Hermes"
echo "=========================================="
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_HOME"
cp -f "$INSTALL_DIR/SOUL.md" "$HERMES_HOME/SOUL.md"
echo "SOUL.md do repositório copiado para $HERMES_HOME/SOUL.md"

echo "=========================================="
echo " [8/13] Personalizando a mensagem de pairing do gateway"
echo "=========================================="
# Reescreve o texto fixo enviado a usuários não reconhecidos (DM pairing),
# embutido em gateway/run.py. Idempotente e version-robusto: localiza a string
# antiga pelo marcador "I don't recognize you yet" (nunca duplica) e valida a
# sintaxe após a edição. Feito em Python para não quebrar escapes/acentos.
GW_RUN="$(python - <<'PY'
import gateway, os
print(os.path.join(os.path.dirname(gateway.__file__), "run.py"))
PY
)"
python - "$GW_RUN" <<'PY'
import ast, re, sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text(encoding="utf-8")

# Texto novo. Montado sem backslashes no fonte: usamos um placeholder NL
# que é trocado por "barra + n" em runtime, evitando ambiguidade de escapes.
NL = chr(92) + "n"  # "\n" literal (barra + n), como aparece no arquivo destino
NEW = (
    'f"Olá, parece que você não tem acesso ainda!' + NL + NL + '"'
    "\n"
    '                            f"Envie esse código `{code}` para o admnistrador"'
)

# Já personalizado? Nada a fazer.
if "Envie esse código" in src:
    print(f"⚠  Mensagem de pairing já personalizada em {path} — nada a fazer.")
    sys.exit(0)

# Bloco antigo: 4 f-strings encadeadas que começam com o marcador reconhecível.
pattern = re.compile(
    r'f"Hi~ I don\'t recognize you yet!\\n\\n"\s*\n'
    r'\s*f"Here\'s your pairing code: `\{code\}`\\n\\n"\s*\n'
    r'\s*f"Ask the bot owner to run:\\n"\s*\n'
    r'\s*f"`hermes pairing approve \{platform_name\} \{code\}`"'
)
# subn com FUNÇÃO de substituição: o valor retornado é inserido literalmente,
# sem o motor de regex interpretar "\n" como quebra de linha nem "\g"/"\1".
new_src, n = pattern.subn(lambda _m: NEW, src)
if n != 1:
    print(f"✗ Não foi possível localizar a mensagem de pairing padrão em {path} "
          f"(ocorrências: {n}). O layout do pacote pode ter mudado.")
    sys.exit(1)

# Backup + escrita atômica, restaurando em caso de falha de validação.
path.with_suffix(".py.bak").write_text(src, encoding="utf-8")
try:
    ast.parse(new_src)  # valida a sintaxe antes de sobrescrever
except SyntaxError as e:
    print(f"✗ Edição gerou sintaxe inválida ({e}); restaurando backup.")
    sys.exit(1)
path.write_text(new_src, encoding="utf-8")
print(f"✅ Mensagem de pairing personalizada em {path}")
PY

echo "=========================================="
echo " [9/13] Restringindo o menu de comandos do Telegram (/help e /new)"
echo "=========================================="
# Por padrão o Hermes registra ~50 comandos internos + as skills instaladas no
# menu de botões do Telegram (setMyCommands). Aqui restringimos o menu a apenas
# /help e /new, injetando uma allowlist na função telegram_menu_commands do
# hermes_cli.commands. Os demais comandos continuam funcionando se digitados à
# mão — apenas somem do menu "/". Idempotente e version-robusto: marca a edição
# por um comentário-âncora (nunca duplica), valida a sintaxe e restaura backup
# em caso de falha.
CMDS_PY="$(python - <<'PY'
import hermes_cli.commands as c
print(c.__file__)
PY
)"
python - "$CMDS_PY" <<'PY'
import ast, sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text(encoding="utf-8")

MARKER = "_TELEGRAM_MENU_ALLOWLIST"

# Já personalizado? Nada a fazer.
if MARKER in src:
    print(f"⚠  Menu do Telegram já restrito em {path} — nada a fazer.")
    sys.exit(0)

# Âncora: a linha de assinatura da função. Localizamos o alvo pela assinatura
# (estável entre versões) e inserimos a allowlist logo após o docstring.
anchor = "def telegram_menu_commands(max_commands: int = 100) -> tuple[list[tuple[str, str]], int]:"
idx = src.find(anchor)
if idx == -1:
    print(f"✗ Não foi possível localizar telegram_menu_commands em {path}. "
          f"O layout do pacote pode ter mudado.")
    sys.exit(1)

# Ponto de inserção: logo após o fechamento do docstring (primeira linha que
# contém apenas aspas triplas após a âncora) — inserimos ANTES da primeira
# atribuição core_commands, que é estável.
ins_anchor = "    core_commands = _prioritize_telegram_menu_commands(list(telegram_bot_commands()))"
pos = src.find(ins_anchor, idx)
if pos == -1:
    print(f"✗ Não foi possível localizar o corpo de telegram_menu_commands em {path}.")
    sys.exit(1)

BLOCK = (
    "    # Local customization: restrict the Telegram command menu to a minimal\n"
    "    # allowlist. Set to None to restore stock behavior (all commands + skills).\n"
    '    _TELEGRAM_MENU_ALLOWLIST = {"help", "new"}\n'
    "\n"
    "    if _TELEGRAM_MENU_ALLOWLIST is not None:\n"
    "        _core = _prioritize_telegram_menu_commands(list(telegram_bot_commands()))\n"
    "        _core = [c for c in _core if c[0] in _TELEGRAM_MENU_ALLOWLIST]\n"
    "        _dropped = max(0, len(telegram_bot_commands()) - len(_core))\n"
    "        return _core[:max_commands], _dropped\n"
)

new_src = src[:pos] + BLOCK + src[pos:]

# Backup + escrita atômica, restaurando em caso de falha de validação.
path.with_suffix(".py.bak").write_text(src, encoding="utf-8")
try:
    ast.parse(new_src)  # valida a sintaxe antes de sobrescrever
except SyntaxError as e:
    print(f"✗ Edição gerou sintaxe inválida ({e}); restaurando backup.")
    sys.exit(1)
path.write_text(new_src, encoding="utf-8")
print(f"✅ Menu do Telegram restrito a /help e /new em {path}")
PY

echo "=========================================="
echo " [10/13] Instalando as skills versionadas no repositório"
echo "=========================================="
# Copia TODA skill de $INSTALL_DIR/skills/hermes/ para o diretório de skills do
# HERMES_HOME do destino (~/.hermes/skills/hermes/). São elas que ensinam o agente
# a operar os recursos que este instalador liga — transcrição de áudio no passo
# [11/13], base geológica nos passos [12/13] e [13/13].
#
# Estas skills existem para a MÁQUINA DE DESTINO. Não as instale na estação de
# desenvolvimento: lá não há serviço geodb nem gateway de Telegram rodando.
#
# Idempotente: sobrescreve com a versão do repo a cada run.
SKILLS_SRC="$INSTALL_DIR/skills/hermes"
SKILLS_DST="$HERMES_HOME/skills/hermes"
if [ -d "$SKILLS_SRC" ]; then
    mkdir -p "$SKILLS_DST"
    _skills_copiadas=0
    for _skill_dir in "$SKILLS_SRC"/*/; do
        [ -f "$_skill_dir/SKILL.md" ] || continue
        _skill_nome="$(basename "$_skill_dir")"
        # cp -a preserva subpastas (references/, scripts/) se a skill tiver.
        rm -rf "$SKILLS_DST/$_skill_nome"
        cp -a "$_skill_dir" "$SKILLS_DST/$_skill_nome"
        echo "✅ Skill instalada: $_skill_nome"
        _skills_copiadas=$((_skills_copiadas + 1))
    done
    if [ "$_skills_copiadas" -eq 0 ]; then
        echo "⚠  Nenhuma SKILL.md encontrada em $SKILLS_SRC — pulando."
    else
        echo "-- $_skills_copiadas skill(s) em $SKILLS_DST"
    fi
else
    echo "⚠  $SKILLS_SRC não encontrado — pulando (o repo pode estar desatualizado)."
fi

echo "=========================================="
echo " [11/13] Ativando a transcrição automática de áudio (STT)"
echo "=========================================="
# Liga a transcrição de mensagens de voz no gateway e fixa o provider "local"
# (faster-whisper, sem API key). Instala o faster-whisper no venv já ativo para
# que a transcrição funcione de imediato, sem depender do lazy-install. O
# download do modelo Whisper (~150MB, "base") acontece no primeiro uso.
hermes config set stt.enabled true
hermes config set stt.provider local
hermes config set stt.local.model base
hermes config set stt.echo_transcripts true
echo "-- Instalando faster-whisper (transcrição local, sem API key)..."
pip install "faster-whisper==1.2.1" || echo "⚠  Falha ao instalar faster-whisper — a transcrição fará lazy-install no primeiro uso."

echo "=========================================="
echo " [12/13] Subindo o serviço GeoDB (SQLite + porta)"
echo "=========================================="
# A GeoDB é um deployável SEPARADO do restante da aplicação: ela serve a base
# geológica em uma porta própria, em modo somente-leitura, falando REST (para
# humanos, com OpenAPI em /docs) e MCP (para o Hermes) ao mesmo tempo.
#
# O dado é de quem hospeda o serviço. Quando a base passar para a UNISINOS,
# NÃO rode este bloco: defina GEODB_REMOTE_URL e GEODB_REMOTE_TOKEN antes de
# executar o instalador, e o passo [13/13] aponta o Hermes para o host deles
# sem instalar nada localmente.
GEODB_DIR="$INSTALL_DIR/geodb"
GEODB_PORT="${GEODB_PORT:-9000}"
GEODB_SECRETS_DIR="$HOME/.hermes/.secrets"
GEODB_TOKEN_FILE="$GEODB_SECRETS_DIR/geodb_token"

if [ -n "${GEODB_REMOTE_URL:-}" ]; then
    echo "-- GEODB_REMOTE_URL definido ($GEODB_REMOTE_URL): pulando o serviço local."
elif [ ! -d "$GEODB_DIR" ]; then
    echo "⚠  $GEODB_DIR não encontrado no repositório — pulando a GeoDB."
else
    # Token: gerado uma vez e reaproveitado em reinstalações.
    mkdir -p "$GEODB_SECRETS_DIR"
    chmod 700 "$GEODB_SECRETS_DIR"
    if [ ! -s "$GEODB_TOKEN_FILE" ]; then
        python3 -c "import secrets; print('geodb_' + secrets.token_urlsafe(32))" > "$GEODB_TOKEN_FILE"
        echo "-- Token da GeoDB gerado em $GEODB_TOKEN_FILE"
    else
        echo "-- Reaproveitando o token existente em $GEODB_TOKEN_FILE"
    fi
    chmod 600 "$GEODB_TOKEN_FILE"

    # Venv próprio: a GeoDB não compartilha dependências com a API principal,
    # justamente para poder ser movida de máquina sem arrastar o resto.
    echo "-- Criando venv da GeoDB..."
    python3 -m venv "$GEODB_DIR/.venv"
    "$GEODB_DIR/.venv/bin/pip" install --upgrade pip -q
    "$GEODB_DIR/.venv/bin/pip" install -q -r "$GEODB_DIR/requirements.txt"

    echo "-- Populando geo.db a partir das fontes..."
    "$GEODB_DIR/.venv/bin/python" "$GEODB_DIR/seed.py" --db "$GEODB_DIR/geo.db"
    chmod 444 "$GEODB_DIR/geo.db"

    # Serviço systemd de usuário: sobe junto com a máquina e reinicia sozinho.
    # O linger vem ANTES do daemon-reload: é ele que cria /run/user/$UID, sem o
    # qual `systemctl --user` morre com "Failed to connect to bus" numa sessão
    # SSH não-interativa (caso comum em Lightsail/EC2).
    loginctl enable-linger "$USER" 2>/dev/null || true
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/geodb.service" <<SERVICE
[Unit]
Description=GeoDB - base geologica estruturada (REST + MCP)
After=network.target

[Service]
Type=simple
WorkingDirectory=$GEODB_DIR
Environment=GEODB_PATH=$GEODB_DIR/geo.db
Environment=HOST=${GEODB_BIND:-127.0.0.1}
Environment=PORT=$GEODB_PORT
Environment=GEODB_ALLOWED_HOSTS=${GEODB_ALLOWED_HOSTS:-localhost,127.0.0.1}
ExecStart=/usr/bin/env bash -c 'GEODB_TOKEN="\$(cat $GEODB_TOKEN_FILE)" exec $GEODB_DIR/.venv/bin/python $GEODB_DIR/server.py'
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SERVICE

    # O script roda sob `set -e`: um systemctl que falha abortaria a instalação
    # inteira. Por isso cada chamada é tolerada e há queda para nohup.
    GEODB_VIA_SYSTEMD=0
    if systemctl --user daemon-reload 2>/dev/null \
       && systemctl --user enable --now geodb.service 2>/dev/null; then
        GEODB_VIA_SYSTEMD=1
        echo "-- GeoDB sob systemd (systemctl --user status geodb)"
    else
        echo "⚠  systemd --user indisponível nesta máquina — subindo a GeoDB com nohup."
        echo "   O serviço NÃO volta sozinho após reboot. Para corrigir depois:"
        echo "     sudo loginctl enable-linger $USER && systemctl --user enable --now geodb"
        GEODB_TOKEN="$(cat "$GEODB_TOKEN_FILE")" \
        GEODB_PATH="$GEODB_DIR/geo.db" \
        HOST="${GEODB_BIND:-127.0.0.1}" PORT="$GEODB_PORT" \
        GEODB_ALLOWED_HOSTS="${GEODB_ALLOWED_HOSTS:-localhost,127.0.0.1}" \
        nohup "$GEODB_DIR/.venv/bin/python" "$GEODB_DIR/server.py" \
            > "$GEODB_DIR/geodb.log" 2>&1 &
        disown || true
    fi

    echo "-- Aguardando a GeoDB responder..."
    for i in $(seq 1 15); do
        if curl -fsS "http://127.0.0.1:$GEODB_PORT/health" >/dev/null 2>&1; then
            echo "✅ GeoDB no ar: http://127.0.0.1:$GEODB_PORT  (docs em /docs)"
            curl -fsS "http://127.0.0.1:$GEODB_PORT/health"; echo
            break
        fi
        [ "$i" = "15" ] && echo "⚠  GeoDB não respondeu em 15s — veja: systemctl --user status geodb"
        sleep 1
    done
fi

echo "=========================================="
echo " [13/13] Registrando a GeoDB como ferramenta MCP do Hermes"
echo "=========================================="
# Registro por stdio: o Hermes sobe a ponte (mcp_bridge.py) como subprocesso, e a
# ponte fala HTTP com a GeoDB. A porta continua sendo a fronteira do dado — basta
# trocar GEODB_URL para o host da UNISINOS.
#
# Por que nao apontar o Hermes direto para /mcp: o SDK mcp embutido em algumas
# instalacoes do Hermes nao resolve o cliente HTTP em runtime ("requires HTTP
# transport but mcp.client.streamable_http is not available"). O transporte stdio
# funciona em todas. O endpoint /mcp do servico segue disponivel para outros
# clientes (Claude Desktop, Cursor) que o suportem.
GEODB_MCP_URL="${GEODB_REMOTE_URL:-http://127.0.0.1:$GEODB_PORT}"
if [ -n "${GEODB_REMOTE_TOKEN:-}" ]; then
    GEODB_MCP_TOKEN="$GEODB_REMOTE_TOKEN"
elif [ -s "$GEODB_TOKEN_FILE" ]; then
    GEODB_MCP_TOKEN="$(cat "$GEODB_TOKEN_FILE")"
else
    GEODB_MCP_TOKEN=""
fi

# A ponte roda no venv da GeoDB. Sem ele não há o que registrar.
if [ ! -x "$GEODB_DIR/.venv/bin/python" ] || [ ! -f "$GEODB_DIR/mcp_bridge.py" ]; then
    echo "⚠  Ponte MCP ausente em $GEODB_DIR — pulando o registro."
    echo "   Rode o passo [12/13] antes, ou registre à mão (ver geodb/README.md)."
else
    # Escolhe um python que tenha PyYAML. Sob `set -e`, um heredoc que sai com
    # erro abortaria a instalação inteira, então a verificação vem antes.
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

    if [ -z "$GEODB_YAML_PY" ]; then
        echo "⚠  PyYAML indisponível — registre a GeoDB à mão em $HERMES_HOME/config.yaml"
        echo "   (bloco mcp_servers; o modelo está em geodb/README.md)."
    else
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
    # Somente leitura: nenhuma destas ferramentas escreve na base.
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
    fi
fi

# O suporte a MCP precisa estar instalado no runtime do Hermes, senão a ferramenta
# nunca aparece para o agente. Este é o ponto que mais falha: o pacote `mcp` pode
# existir em um venv e o Hermes rodar com outro interpretador.
echo "-- Verificando se o Hermes enxerga a GeoDB..."
GEODB_TESTE="$(hermes mcp test geodb 2>&1 || true)"
if printf '%s' "$GEODB_TESTE" | grep -qiE "✓|connected|[0-9]+ tool"; then
    echo "✅ Hermes conectado na GeoDB."
    printf '%s\n' "$GEODB_TESTE" | tail -5
else
    echo "⚠  O Hermes NÃO conectou na GeoDB. Saída do teste:"
    printf '%s\n' "$GEODB_TESTE" | tail -8
    echo ""
    echo "   Se a mensagem citar o SDK 'mcp', instale o suporte e repita:"
    echo "     hermes setup tools --non-interactive"
    echo "     hermes mcp test geodb"
    echo "   A API REST continua funcionando em http://127.0.0.1:$GEODB_PORT/docs"
fi

echo ""
echo "=========================================="
echo " ✅ Instalação concluída!"
echo "=========================================="
hermes config show | sed -n '/◆ Model/,/^$/p' || true
echo ""
echo "Próximos passos:"
echo "  cd $INSTALL_DIR && source venv/bin/activate"
echo "  python db/manage_keys.py create <user_id>   # criar chave malta_..."
echo "  python main.py                             # sobe a API na porta 8000"
echo "  hermes -z \"teste\"                        # testar o agente direto"
echo ""
echo "GeoDB (base geológica):"
echo "  http://127.0.0.1:$GEODB_PORT/docs          # API navegável no browser"
echo "  systemctl --user status geodb              # estado do serviço"
echo "  journalctl --user -u geodb -f              # logs"
echo "  hermes -z \"Qual o COT dos folhelhos da Formação Ipubi?\"   # testa a ferramenta MCP"
