# Dashboards do Grafana — versionados como código

Esta pasta contém dashboards customizados do Grafana versionados junto com a infraestrutura. O `kube-prometheus-stack` já é configurado (via `sidecar`) para detectar automaticamente qualquer ConfigMap no namespace `monitoring` com o label `grafana_dashboard: "1"` e carregá-lo no Grafana — sem precisar importar manualmente.

## Como funciona

```
git push → ArgoCD aplica o ConfigMap
              ↓
Grafana sidecar detecta o label grafana_dashboard: "1"
              ↓
Dashboard aparece automaticamente em Dashboards → General
```

## Dashboards disponíveis

| Arquivo | Título no Grafana | Descrição |
|---------|-------------------|-----------|
| `configmap-game-servers.yaml` | Game Servers — Recursos por Namespace | CPU, memória, pods running, restarts e requests/limits filtráveis por namespace |

## Como adicionar um novo dashboard

1. Crie/exporte o JSON do dashboard no Grafana (⚙️ → JSON Model)
2. Crie um novo arquivo `configmap-<nome>.yaml` seguindo o padrão abaixo:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: dashboard-<nome>
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  <nome>.json: |
    { ... conteúdo do JSON exportado ... }
```

3. Commit e push — o ArgoCD aplica automaticamente

## Aplicar manualmente (sem ArgoCD)

```bash
kubectl apply -f k8s/monitoring/dashboards/configmap-game-servers.yaml
```

O Grafana detecta em até 1 minuto (intervalo padrão do sidecar).
