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
echo " [1/11] sudo apt update + dependências"
echo "=========================================="
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

echo "=========================================="
echo " [2/11] Clonando o repositório"
echo "=========================================="
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repo já existe em $INSTALL_DIR — atualizando (git pull)..."
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "=========================================="
echo " [3/11] Criando e ativando o venv"
echo "=========================================="
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "=========================================="
echo " [4/11] Instalando requirements.txt"
echo "=========================================="
pip install --upgrade pip
pip install -r requirements.txt
# boto3 é necessário pro Hermes falar com o Bedrock
# (não está no requirements.txt — awscli sozinho não basta)
pip install boto3

echo "=========================================="
echo " [5/11] Configurando AWS CLI (aws configure)"
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
echo " [6/11] Hermes Agent → DeepSeek V3.2 via AWS Bedrock"
echo "=========================================="
# Esses comandos também criam o ~/.hermes na primeira execução
hermes config set model.provider bedrock
hermes config set model.default "$BEDROCK_MODEL"
hermes config set bedrock.region "$AWS_REGION"

echo "=========================================="
echo " [7/11] Substituindo o SOUL.md do Hermes"
echo "=========================================="
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_HOME"
cp -f "$INSTALL_DIR/SOUL.md" "$HERMES_HOME/SOUL.md"
echo "SOUL.md do repositório copiado para $HERMES_HOME/SOUL.md"

echo "=========================================="
echo " [8/11] Personalizando a mensagem de pairing do gateway"
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
echo " [9/11] Restringindo o menu de comandos do Telegram (/help e /new)"
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
echo " [10/11] Instalando a skill de transcrição de áudio"
echo "=========================================="
# Copia a skill "audio-transcription-telegram" versionada no repositório para o
# diretório de skills do HERMES_HOME do destino (~/.hermes/skills/). É isso que
# ensina o agente a configurar/depurar a transcrição automática de áudio que o
# passo [11/11] liga. Idempotente: sobrescreve com a versão do repo a cada run.
SKILL_SRC="$INSTALL_DIR/skills/hermes/audio-transcription-telegram"
SKILL_DST="$HERMES_HOME/skills/hermes/audio-transcription-telegram"
if [ -f "$SKILL_SRC/SKILL.md" ]; then
    mkdir -p "$SKILL_DST"
    cp -f "$SKILL_SRC/SKILL.md" "$SKILL_DST/SKILL.md"
    echo "✅ Skill copiada para $SKILL_DST/SKILL.md"
else
    echo "⚠  Skill não encontrada em $SKILL_SRC — pulando (o repo pode estar desatualizado)."
fi

echo "=========================================="
echo " [11/11] Ativando a transcrição automática de áudio (STT)"
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
