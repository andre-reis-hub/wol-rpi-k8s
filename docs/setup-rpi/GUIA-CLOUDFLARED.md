# Cloudflared — acesso externo pelo dominio (areis-solution.com)

O tunnel liga o RPi a Cloudflare SEM abrir portas no roteador. Serve:
panel.areis-solution.com, grafana.areis-solution.com, argocd.areis-solution.com

## Metodo usado: tunnel gerenciado pela nuvem (token)
As rotas (qual subdominio -> qual servico) ficam salvas no painel da Cloudflare
(Zero Trust > Networks > Tunnels). Recuperar = reinstalar + reconectar com o token.

## 1. Instalar o cloudflared no RPi
```
# ARM (RPi Zero e ARMv6/32-bit) — baixar o binario certo da Cloudflare:
# ver https://github.com/cloudflare/cloudflared/releases (arquitetura arm)
# exemplo (confirmar arquitetura com: uname -m):
cd /tmp
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared
cloudflared --version
```

## 2. Pegar o token do tunnel
No painel Cloudflare: Zero Trust > Networks > Tunnels > (seu tunnel) >
Configure > ele mostra o comando `cloudflared service install <TOKEN>`.
Copie o TOKEN (string longa).

## 3. Instalar como servico com o token
```
sudo cloudflared service install <TOKEN>
```
Isso cria e habilita o servico cloudflared, ja com as rotas da nuvem.
```
sudo systemctl status cloudflared     # deve estar active
```

## 4. Conferir as rotas (Public Hostnames) no painel Cloudflare
- panel.areis-solution.com  -> http://localhost:5000
- grafana.areis-solution.com -> http://192.168.15.14:<porta-grafana>
- argocd.areis-solution.com  -> http://192.168.15.14:<porta-argocd>
(as rotas ja devem estar salvas na nuvem; so confirmar)

## Alternativa: tunnel por arquivo (metodo antigo)
Se preferir config local: ~/.cloudflared/config.yml + credentials .json.
Requer `cloudflared tunnel login` + `cloudflared tunnel create`. Mais passos.
O metodo por token (acima) e mais simples para recuperar.

## Teste final
Abrir https://panel.areis-solution.com de FORA da rede (dados moveis).
Deve pedir login do painel e funcionar igual ao acesso local.
