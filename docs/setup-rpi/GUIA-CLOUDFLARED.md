# Cloudflared — tunnel LOCAL (recuperacao e setup)

O tunnel liga o RPi a Cloudflare SEM abrir portas no roteador. Serve:
panel / grafana / argocd . areis-solution.com

> ESTE TUNNEL E DO TIPO LOCAL: as rotas ficam no config.yml NO RPI (nao na
> nuvem). As credenciais do tunnel (.json) tambem ficam no RPi e NAO podem ser
> rebaixadas da Cloudflare — se perder o cartao, recria-se o tunnel (abaixo).

## Pre-requisito: binario do cloudflared (RPi Zero W = ARMv6)
O RPi Zero W e ARMv6. Use o binario oficial ATUAL (>=2025 voltou a funcionar
em ARMv6; versoes intermediarias davam "Illegal instruction").
```
cd /tmp
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
chmod +x cloudflared-linux-arm
./cloudflared-linux-arm --version      # tem que responder a versao (nao "Illegal instruction")
sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared
```
> uname -m no RPi deve dizer armv6l. (Cuidado: nao confundir com a arch do celular.)

## Recuperar o tunnel local (quando o SD/credenciais se perdem)

### 1. Limpar instalacao remota, se houver
Se antes foi feito `cloudflared service install <token>` (modo remoto), remova:
```
sudo cloudflared service uninstall
sudo rm -f /etc/cloudflared/token
```

### 2. Autenticar na conta Cloudflare
```
cloudflared tunnel login
```
Abre uma URL -> logar no navegador -> autorizar o dominio areis-solution.com.
Salva o certificado em ~/.cloudflared/cert.pem (permite gerar credenciais).

### 3. Recriar o tunnel (credenciais antigas nao voltam)
```
cloudflared tunnel list                       # ver o tunnel existente
cloudflared tunnel delete wol-panel           # apaga o antigo (credencial perdida)
cloudflared tunnel create wol-panel           # cria novo + gera o .json de credenciais
```
Anote o UUID novo que aparece (ex: f0135be1-...). O .json fica em ~/.cloudflared/.

### 4. Montar o config.yml (as 3 rotas)
```
nano ~/.cloudflared/config.yml
```
Conteudo (trocar o UUID pelo do passo 3):
```
tunnel: <UUID-NOVO>
credentials-file: /home/andre/.cloudflared/<UUID-NOVO>.json

ingress:
  - hostname: panel.areis-solution.com
    service: http://localhost:5000
  - hostname: grafana.areis-solution.com
    service: http://192.168.15.14:32593
  - hostname: argocd.areis-solution.com
    service: https://192.168.15.14:30956
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```
> Portas NodePort podem mudar. Confirmar no i9:
>   kubectl get svc -n monitoring | grep grafana        (ex 80:32593)
>   kubectl get svc -n argocd | grep argocd-server       (ex 443:30956, usa https)
> argocd e HTTPS com cert proprio -> https + noTLSVerify: true.
> A ultima linha http_status:404 e obrigatoria (catch-all).

### 5. Reapontar o DNS para o tunnel novo
```
cloudflared tunnel route dns wol-panel panel.areis-solution.com
cloudflared tunnel route dns wol-panel grafana.areis-solution.com
cloudflared tunnel route dns wol-panel argocd.areis-solution.com
```
Se der "record already exists" (CNAMEs antigos apontando pro tunnel deletado):
apagar os 3 CNAMEs no painel Cloudflare (dominio > DNS > Records: panel, grafana,
argocd, do tipo CNAME -> ...cfargotunnel.com) e rodar os 3 comandos de novo.

### 6. Testar na mao
```
cloudflared tunnel --config /home/andre/.cloudflared/config.yml run
```
Deve aparecer "Registered tunnel connection" (~4x). Com ele rodando, testar
os dominios de FORA (dados moveis). CTRL+C para parar depois do teste.

### 7. Virar servico (sobe no boot)
```
sudo cp ~/wol-rpi-k8s/cloudflared/wol-tunnel.service.example /etc/systemd/system/cloudflared-tunnel.service
cat /etc/systemd/system/cloudflared-tunnel.service    # conferir ExecStart e User=andre
sudo systemctl daemon-reload
sudo systemctl enable cloudflared-tunnel
sudo systemctl start cloudflared-tunnel
sudo systemctl status cloudflared-tunnel              # active (running)
```

### 8. Teste final: reboot
```
sudo reboot
```
Esperar ~2 min e abrir panel.areis-solution.com de fora SEM tocar no RPi.
Se abrir, painel + tunnel sobem sozinhos no boot.

## SEGREDOS (nunca commitar)
- ~/.cloudflared/cert.pem
- ~/.cloudflared/<UUID>.json  (credenciais do tunnel)
- ~/.cloudflared/config.yml   (contem o UUID; por seguranca, manter fora do repo)
Estes ficam so no RPi. O repo guarda apenas os .example.
