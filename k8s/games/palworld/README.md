# Palworld Server

Servidor dedicado de Palworld rodando via `thijsvanloef/palworld-server-docker`.

## Configuracao

- Jogadores: 8 (PvE)
- PvP: desabilitado
- Friendly fire: desabilitado
- Backup automatico: a cada 6h, mantem 7 dias
- Recursos: 8Gi/2vCPU (request) - 16Gi/6vCPU (limit)

## Secrets necessarios

Antes de aplicar, criar o secret com as senhas (NAO commitar senhas em texto puro):

```
kubectl create secret generic palworld-secrets \
  --namespace palworld \
  --from-literal=admin-password='SUA_SENHA_ADMIN' \
  --from-literal=server-password='SUA_SENHA_SERVIDOR'
```

## Storage

Save do mundo persistido em `/var/lib/rancher/palworld` (disco secundario, 20Gi).

Criar o diretorio antes de aplicar o PV:

```
sudo mkdir -p /var/lib/rancher/palworld
sudo chown 1000:1000 /var/lib/rancher/palworld
```

## Portas

| Porta | Protocolo | Uso |
|-------|-----------|-----|
| 30211 | UDP | Porta do jogo (mapeada para 8211 interno) |
| 27015 | UDP | Query/Steam |

## Conectar do Windows (Steam)

No Palworld, em "Join Multiplayer Game" > "Join via IP", usar:

```
IP_PUBLICO:30211
```

O IP publico e exibido no painel (panel.areis-solution.com) apos o agente
registrar. Sera necessario configurar port forwarding no roteador para a
porta 30211/UDP apontando para 192.168.15.14.

## Primeiro boot

A primeira inicializacao baixa os arquivos do servidor (~3-5GB) e pode
levar varios minutos. Acompanhar com:

```
kubectl logs -f -n palworld deployment/palworld-server
```

## RCON (administracao remota)

RCON habilitado na porta 25575 (interna ao cluster). Para usar:

```
kubectl exec -it -n palworld deployment/palworld-server -- rcon-cli
```
