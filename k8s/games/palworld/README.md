# Palworld Server

Servidor dedicado de Palworld rodando via `thijsvanloef/palworld-server-docker`.

## Configuracao

- Jogadores: 8 (PvE)
- PvP: desabilitado
- Friendly fire: desabilitado
- Backup automatico: a cada 6h, mantem 7 dias
- Recursos: 8Gi/2vCPU (request) - 16Gi/6vCPU (limit)
- REST API: habilitada (monitoramento via painel)

## Secrets necessarios

Antes de aplicar, criar o secret com as senhas (NAO commitar senhas em texto puro):

  kubectl create secret generic palworld-secrets \
    --namespace palworld \
    --from-literal=admin-password='SUA_SENHA_ADMIN' \
    --from-literal=server-password='SUA_SENHA_SERVIDOR'

## Storage

Save do mundo persistido em `/var/lib/rancher/palworld` (disco secundario, 20Gi).

Criar o diretorio antes de aplicar o PV:

  sudo mkdir -p /var/lib/rancher/palworld
  sudo chown 1000:1000 /var/lib/rancher/palworld

## Portas (NodePort)

| Porta | Protocolo | Uso |
|-------|-----------|-----|
| 30211 | UDP | Porta do jogo (mapeada para 8211 interno) |
| 30015 | UDP | Query/Steam (mapeada para 27015 interno) |
| 30212 | TCP | REST API (mapeada para 8212 interno) - usada pelo painel |

## Conectar do Windows (Steam)

No Palworld, em "Join Multiplayer Game" > "Join via IP", usar:

- Da rede local: `192.168.15.14:30211`
- De fora: `IP_PUBLICO:30211`

Port forwarding no roteador: `30211/UDP` -> `192.168.15.14`.
Senha do servidor definida no secret `palworld-secrets`.

## REST API (monitoramento)

A REST API expoe metricas consumidas pelo painel do RPi:

  curl -s http://192.168.15.14:30212/v1/api/metrics -u admin:SENHA_ADMIN

Retorna: currentplayernum, maxplayernum, serverfps, days, basecampnum, uptime.

A porta 30212 NAO deve ter port forwarding no roteador (acesso so interno/RPi).

## Primeiro boot

A primeira inicializacao baixa os arquivos do servidor (~3.7GB) e pode
levar varios minutos. Acompanhar com:

  kubectl logs -f -n palworld deployment/palworld-server

## RCON (administracao remota)

RCON habilitado na porta 25575 (interna ao cluster). Para usar:

  kubectl exec -it -n palworld deployment/palworld-server -- rcon-cli
