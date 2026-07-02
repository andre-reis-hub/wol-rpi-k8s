# Expansão: monitoramento FinOps + Gamer e novo servidor (Valheim)

## Conteúdo

1. docs/analise-jogos.md - viabilidade da sua lista de jogos
2. k8s/games/valheim/ - manifestos completos (Linux nativo, senha via Vault!)
3. k8s/monitoring/dashboards-extra/ - dashboards FinOps e Gamer Stats

## O que os dashboards mostram

### FinOps — Custos e Recursos do Homelab
- Custo estimado em R$ se o i9 ficasse 24/7 vs custo REAL (só horas ligadas)
  -> mostra sua ECONOMIA com o WoL em dinheiro!
- RAM/CPU por jogo (quanto cada servidor consome)
- Disco usado por jogo
- Horas/dia que cada servidor ficou ligado (otimizar desligando o ocioso)

AJUSTE os valores na query do painel de custo: potencia media (150W default)
e tarifa (R$0,95/kWh default) para os seus reais. Editar no Grafana (Edit) ou
no JSON versionado. Dica: um medidor de tomada (kWh) dá o valor real do i9.

### Gamer Stats — Jogadores, Sessões e Atividade
- Ranking de quem mais entrou (7d)
- Atividade por jogo (qual servidor bomba mais)
- Mensagens de chat por dia
- Horários de pico (agendar manutenção fora do pico!)
- Últimas conexões de todos os jogos

---

## PARTE 1 - Commitar tudo (TERMUX)

```
mkdir -p ~/wol-rpi-k8s/k8s/games/valheim ~/wol-rpi-k8s/k8s/monitoring/dashboards-extra
cp ~/storage/downloads/analise-jogos.md ~/wol-rpi-k8s/docs/
cp ~/storage/downloads/namespace.yaml ~/wol-rpi-k8s/k8s/games/valheim/
cp ~/storage/downloads/pvc.yaml ~/wol-rpi-k8s/k8s/games/valheim/
cp ~/storage/downloads/deployment.yaml ~/wol-rpi-k8s/k8s/games/valheim/
cp ~/storage/downloads/service.yaml ~/wol-rpi-k8s/k8s/games/valheim/
cp ~/storage/downloads/README.md ~/wol-rpi-k8s/k8s/games/valheim/
cp ~/storage/downloads/configmap-dashboard-finops.yaml ~/wol-rpi-k8s/k8s/monitoring/dashboards-extra/
cp ~/storage/downloads/configmap-dashboard-gamer.yaml ~/wol-rpi-k8s/k8s/monitoring/dashboards-extra/
cd ~/wol-rpi-k8s && git pull && git add . && git commit -m "feat: dashboards FinOps e Gamer Stats + servidor Valheim (Vault, Linux nativo)" && git push origin main
```

ATENCAO nomes duplicados nos downloads (namespace.yaml, README.md etc):
apague downloads antigos antes, como voce ja faz.

## PARTE 2 - Aplicar dashboards (i9) — pode fazer JA

```
cd ~/Documents/wol-rpi-k8s && git pull
kubectl apply -f k8s/monitoring/dashboards-extra/
```
Aparecem no Grafana em ~1min: "FinOps — Custos e Recursos" e "Gamer Stats".

## PARTE 3 - Subir o Valheim (i9) — quando quiser jogar

```
sudo mkdir -p /var/lib/rancher/valheim && sudo chown 1000:1000 /var/lib/rancher/valheim
kubectl apply -f k8s/games/valheim/namespace.yaml
export VT=<seu-token-vault>
bash scripts/add-game-secret.sh valheim <senha-min-5-chars>
kubectl apply -f k8s/games/valheim/
kubectl logs -f -n valheim deployment/valheim-server   # 1º boot baixa ~1GB
```

Port forward roteador: 30456/UDP e 30457/UDP -> 192.168.15.14 (IP Externo VAZIO)
Conectar: IP:30456

ArgoCD (opcional):
```
argocd app create valheim --repo https://github.com/andre-reis-hub/wol-rpi-k8s.git \
  --path k8s/games/valheim --dest-server https://kubernetes.default.svc \
  --dest-namespace valheim --sync-policy automated
kubectl patch application valheim -n argocd --type merge -p '{"spec":{"ignoreDifferences":[{"group":"apps","kind":"Deployment","jsonPointers":["/spec/replicas"]}]}}'
```

## PARTE 4 - Adicionar Valheim ao painel (depois do 1º jogador conectar)

1. Ver o log real de conexao: Grafana Explore -> {namespace="valheim"}
2. Adicionar entrada 'valheim' no GAMES do site/app.py (porta_conexao 30456,
   fonte_players loki, regex conforme o log real)
3. git commit + restart wol-panel no RPi

## Observação FinOps final

Com o dashboard voce vai VER em R$ o que o WoL economiza. Se o i9 ficar ligado
so 4h/dia em vez de 24h, a economia e ~83% do custo de energia dele. Esse
numero no dashboard e o "porque" de todo o projeto existir. 😄
