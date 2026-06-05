#!/bin/bash
set -e

# ─── Instala k3s ──────────────────────────────────────────────────────────────
if command -v k3s &>/dev/null; then
  echo "k3s já instalado: $(k3s --version | head -1)"
else
  echo "Instalando k3s..."
  curl -sfL https://get.k3s.io | sh -
fi

# ─── Aguarda o cluster ficar pronto ───────────────────────────────────────────
echo "Aguardando k3s inicializar..."
until sudo kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes &>/dev/null; do
  sleep 2
done
echo "Cluster pronto."

# ─── Kubeconfig para o usuário atual ──────────────────────────────────────────
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$USER:$USER" ~/.kube/config
chmod 600 ~/.kube/config
echo "Kubeconfig configurado em ~/.kube/config"

# ─── Instala Helm ─────────────────────────────────────────────────────────────
if command -v helm &>/dev/null; then
  echo "Helm já instalado: $(helm version --short)"
else
  echo "Instalando Helm..."
  curl -sfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# ─── Cria namespace homelab ───────────────────────────────────────────────────
kubectl apply -f "$(dirname "$0")/namespace-homelab.yml"

echo ""
echo "=== Setup concluído ==="
kubectl get nodes
echo ""
echo "Próximo passo: kubectl get pods -A"
