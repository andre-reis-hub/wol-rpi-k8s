#!/bin/bash
# setup-rpi.sh — automatiza o setup do painel wol-panel no Raspberry Pi.
# Roda DEPOIS de: sistema gravado, SSH ok, e repo clonado em ~/wol-rpi-k8s.
# Uso: bash ~/wol-rpi-k8s/scripts/setup-rpi.sh
# O que NAO automatiza (precisa de voce): preencher o .env e o token do cloudflared.
set -e

REPO_DIR="$HOME/wol-rpi-k8s"
SITE_DIR="$REPO_DIR/site"
I9_IP="192.168.15.14"
I9_USER="andre-reis"

echo "==> 1/6 Modo console (sem grafico)"
sudo systemctl set-default multi-user.target || true

echo "==> 2/6 Pacotes base"
sudo apt update
sudo apt install -y git python3 python3-full python3-venv python3-pip

echo "==> 3/6 Ambiente virtual + dependencias"
cd "$SITE_DIR"
[ -d venv ] && rm -rf venv
python3 -m venv venv
if [ ! -f venv/bin/pip ]; then
  echo "ERRO: venv sem pip. Rode: sudo apt install -y python3-full ; e tente de novo."
  exit 1
fi
venv/bin/pip install -r requirements.txt

echo "==> 4/6 .env"
if [ ! -f "$SITE_DIR/.env" ]; then
  if [ -f "$SITE_DIR/.env.example" ]; then
    cp "$SITE_DIR/.env.example" "$SITE_DIR/.env"
  fi
  echo "  >>> ATENCAO: preencha os segredos em $SITE_DIR/.env antes de iniciar!"
  echo "  >>> (SECRET_KEY, PASSWORD, PC_MAC, K8S_TOKEN, PALWORLD_API_PASS)"
else
  echo "  .env ja existe, mantendo."
fi

echo "==> 5/6 Confianca SSH RPi -> i9 (para o botao Desligar)"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519"
  echo "  Chave criada. Rode manualmente (pede senha do i9 uma vez):"
  echo "    ssh-copy-id $I9_USER@$I9_IP"
  echo "  E no i9: echo \"$I9_USER ALL=(ALL) NOPASSWD: /sbin/shutdown\" | sudo tee /etc/sudoers.d/wol-shutdown"
else
  echo "  Chave ja existe."
fi

echo "==> 6/6 Servico systemd"
sudo cp "$REPO_DIR/scripts/wol-panel.service" /etc/systemd/system/wol-panel.service 2>/dev/null \
  || echo "  (copie wol-panel.service para /etc/systemd/system/ manualmente)"
sudo systemctl daemon-reload
sudo systemctl enable wol-panel
sudo systemctl restart wol-panel
sleep 2
sudo systemctl status wol-panel --no-pager | head -5

echo ""
echo "==> PRONTO (quase). Faltam passos manuais:"
echo "  1. Preencher $SITE_DIR/.env (se ainda nao fez) e: sudo systemctl restart wol-panel"
echo "  2. ssh-copy-id $I9_USER@$I9_IP  (confianca para desligar)"
echo "  3. sudoers do shutdown no i9 (ver acima)"
echo "  4. cloudflared para acesso externo (ver docs/setup-rpi/GUIA-CLOUDFLARED.md)"
echo "  Teste local: http://192.168.15.12:5000"
