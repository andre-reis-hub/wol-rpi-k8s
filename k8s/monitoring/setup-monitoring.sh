#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ─── Helm repos ───────────────────────────────────────────────────────────────
echo "Adicionando repositórios Helm..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# ─── Prometheus + Grafana ─────────────────────────────────────────────────────
echo ""
echo "Instalando kube-prometheus-stack (Prometheus + Grafana)..."
helm upgrade --install kube-prometheus prometheus-community/kube-prometheus-stack \
  --namespace homelab \
  --values "$SCRIPT_DIR/prometheus-values.yml" \
  --wait --timeout 5m

# ─── Loki + Promtail ──────────────────────────────────────────────────────────
echo ""
echo "Instalando loki-stack (Loki + Promtail)..."
helm upgrade --install loki grafana/loki-stack \
  --namespace homelab \
  --values "$SCRIPT_DIR/loki-stack-values.yml" \
  --wait --timeout 5m

# ─── Resultado ────────────────────────────────────────────────────────────────
echo ""
echo "=== Monitoramento instalado ==="
kubectl get pods -n homelab
echo ""
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "Grafana:    http://${LOCAL_IP}:30300"
echo "Usuário:    admin"
echo "Senha:      definida em prometheus-values.yml (adminPassword)"
echo ""
echo "Datasources pré-configurados: Prometheus e Loki"
