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
echo " [1/7] sudo apt update + dependências"
echo "=========================================="
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

echo "=========================================="
echo " [2/7] Clonando o repositório"
echo "=========================================="
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repo já existe em $INSTALL_DIR — atualizando (git pull)..."
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "=========================================="
echo " [3/7] Criando e ativando o venv"
echo "=========================================="
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "=========================================="
echo " [4/7] Instalando requirements.txt"
echo "=========================================="
pip install --upgrade pip
pip install -r requirements.txt
# boto3 é necessário pro Hermes falar com o Bedrock
# (não está no requirements.txt — awscli sozinho não basta)
pip install boto3

echo "=========================================="
echo " [5/7] Configurando AWS CLI (aws configure)"
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
echo " [6/7] Hermes Agent → DeepSeek V3.2 via AWS Bedrock"
echo "=========================================="
# Esses comandos também criam o ~/.hermes na primeira execução
hermes config set model.provider bedrock
hermes config set model.default "$BEDROCK_MODEL"
hermes config set bedrock.region "$AWS_REGION"

echo "=========================================="
echo " [7/7] Substituindo o SOUL.md do Hermes"
echo "=========================================="
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_HOME"
cp -f "$INSTALL_DIR/SOUL.md" "$HERMES_HOME/SOUL.md"
echo "SOUL.md do repositório copiado para $HERMES_HOME/SOUL.md"

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
