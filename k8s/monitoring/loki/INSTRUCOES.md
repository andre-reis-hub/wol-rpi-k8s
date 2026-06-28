# Loki - Agregacao de logs + dashboard de jogadores

Adiciona o Loki (logs) a stack de monitoramento existente. Usa o Grafana que
ja temos (kube-prometheus-stack), so adicionando o Loki como datasource.

## Por que Loki

Os servidores de jogo logam conexoes de jogadores (entrar/sair com nome).
O A2S (Steam Query) deu timeout nos dois jogos, e so o Palworld tem REST API.
O Loki le os LOGS dos pods - funciona para qualquer jogo, de forma unificada.

---

## PARTE 1 - Criar storage do Loki (no i9)

```
sudo mkdir -p /var/lib/rancher/loki
sudo chown 10001:10001 /var/lib/rancher/loki
kubectl apply -f ~/Documents/wol-rpi-k8s/k8s/monitoring/loki/pv.yaml
```

> O Loki roda com UID 10001 por padrao. Se der erro de permissao no pod,
> ajuste o chown conforme o usuario que o pod usar (veja kubectl logs).

## PARTE 2 - Instalar via Helm (no i9)

```
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install loki grafana/loki-stack \
  --namespace monitoring \
  -f ~/Documents/wol-rpi-k8s/k8s/monitoring/loki/values.yaml
```

## PARTE 3 - Aguardar os pods (no i9)

```
kubectl get pods -n monitoring -l app=loki -w
kubectl get pods -n monitoring -l app.kubernetes.io/name=promtail -w
```

Aguarde Loki e Promtail (1 pod por node, DaemonSet) ficarem Running.

## PARTE 4 - Adicionar o Loki como datasource no Grafana

O Loki fica acessivel dentro do cluster em: http://loki:3100

No Grafana (grafana.areis-solution.com), como admin:
- Connections -> Data sources -> Add data source -> Loki
- URL: http://loki.monitoring.svc.cluster.local:3100
- Save & Test

> Alternativa GitOps: criar um ConfigMap de datasource com label
> grafana_datasource: "1" (o sidecar do Grafana detecta). Posso gerar depois
> se quiser versionar o datasource tambem.

## PARTE 5 - Aplicar o dashboard de jogadores (no i9)

```
kubectl apply -f ~/Documents/wol-rpi-k8s/k8s/monitoring/loki/configmap-players-dashboard.yaml
```

O sidecar do Grafana detecta em ~1 min. Aparece em Dashboards:
"Game Servers - Jogadores e Conexoes (Loki)"

---

## Como usar

No Grafana -> Explore -> datasource Loki, voce pode buscar:

```
{namespace="palworld"}
{namespace="abiotic-factor"}
{namespace="palworld"} |= "join"
```

O dashboard ja traz 3 paineis:
1. Conexoes Palworld (filtrando linhas de join/connect/left)
2. Conexoes Abiotic Factor
3. Taxa de eventos de conexao no tempo

> Os filtros usam regex amplo (join|connect|login|player|left|disconnect).
> Depois de ver os logs reais, da pra refinar para o texto exato que cada
> jogo usa quando um player entra (ex: Palworld loga o nome e Steam ID).

---

## Ajuste fino (depois)

Quando tiver jogadores conectando, veja no Explore qual a frase exata que
cada servidor escreve no log ao entrar/sair. Com isso refinamos as queries
LogQL para extrair so o que interessa (nome do jogador, horario).
