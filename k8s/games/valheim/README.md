# Valheim Server

Servidor Linux NATIVO (sem Wine!) via ghcr.io/community-valheim-tools/valheim-server.
Backups automaticos a cada 2h, auto-update quando ocioso, senha via VAULT.

## Instalacao

1. Storage (i9):
   sudo mkdir -p /var/lib/rancher/valheim && sudo chown 1000:1000 /var/lib/rancher/valheim

2. Segredo no Vault (i9) - usa o script do projeto:
   export VT=<token-vault>
   ./scripts/add-game-secret.sh valheim <senha-minimo-5-chars>
   (o script cria KV wol/valheim, policy, SA valheim-sa e role)
   OBS: criar o namespace ANTES do script: kubectl apply -f namespace.yaml

3. Aplicar: kubectl apply -f k8s/games/valheim/

4. Primeiro boot baixa ~1GB via SteamCMD. Acompanhar:
   kubectl logs -f -n valheim deployment/valheim-server

## Portas
| Externa | Protocolo | Uso |
|---------|-----------|-----|
| 30456/UDP | UDP | jogo (interna 2456) |
| 30457/UDP | UDP | query (interna 2457) |

Port forward no roteador: 30456+30457/UDP -> 192.168.15.14 (IP Externo VAZIO)

## Conectar
Steam -> Valheim -> Join by IP: IP:30456 (senha do Vault)
IMPORTANTE: no Valheim conecta-se na porta do JOGO (30456).

## Recursos
~3-4GB RAM. Linux nativo, mais leve que os jogos Wine.

## Monitoramento (Loki)
Apos o primeiro jogador conectar, verificar no Grafana Explore o texto exato
do log de conexao ({namespace="valheim"}) e adicionar ao painel/app.py
(log_join/log_leave/chat_regex) e ao dashboard do Grafana.
