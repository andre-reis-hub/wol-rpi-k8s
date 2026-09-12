# Guia de Setup do RPi (painel wol-panel) do zero

Reconstroi o painel de controle no Raspberry Pi apos perda do cartao SD.
Testado no RPi Zero W com Raspberry Pi OS (Bookworm, 32-bit).

> LICAO QUE ORIGINOU ESTE GUIA: quedas de energia corromperam o cartao SD.
> Considere um no-break (UPS) pequeno para o RPi + i9. Ver secao "Prevencao".

## 0. Gravar o sistema
- Raspberry Pi Imager -> Raspberry Pi OS Lite (32-bit) (sem desktop, mais leve)
- Nas opcoes avancadas do Imager (engrenagem), JA configure:
  - Hostname: RBizero-A-Reis
  - Habilitar SSH (com senha)
  - Usuario: andre + senha
  - WiFi (SSID + senha) + pais BR
- Isso evita precisar de teclado/monitor no RPi.

## 1. Primeiro acesso
```
ssh-keygen -R 192.168.15.12          # limpa chave antiga (host key changed)
ssh andre@192.168.15.12              # aceita a nova (yes) + senha
```

## 2. Modo console (sem grafico) — economiza recursos e escrita no SD
```
sudo systemctl set-default multi-user.target
sudo systemctl isolate multi-user.target
```

## 3. Pacotes base
```
sudo apt update
sudo apt install -y git python3 python3-full python3-venv python3-pip
```
> python3-full e ESSENCIAL: sem ele o venv vem sem pip (erro comum no RPi OS novo).

## 4. Clonar o projeto (repo publico, sem token)
```
cd ~ && git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
```

## 5. Ambiente virtual + dependencias
```
cd ~/wol-rpi-k8s/site
python3 -m venv venv
ls venv/bin/pip                      # confirmar que existe
venv/bin/pip install -r requirements.txt
```

## 6. Montar o .env
```
cp .env.example .env    # se existir; senao criar do zero (ver .env.example)
nano .env
```
Preencher os segredos (ver .env.example para a lista e de onde tirar cada um).
Os que vem do i9 estao documentados no proprio .env.example.

## 7. Confianca SSH do RPi -> i9 (para o botao Desligar PC)
No RPi:
```
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
ssh-copy-id andre-reis@192.168.15.14     # pede a senha do i9 uma vez
ssh andre-reis@192.168.15.14 "echo ok"   # deve responder sem pedir senha
```
No i9 (shutdown sem senha de sudo):
```
which shutdown    # confirmar caminho (/sbin/shutdown na maioria)
echo "andre-reis ALL=(ALL) NOPASSWD: /sbin/shutdown" | sudo tee /etc/sudoers.d/wol-shutdown
```

## 8. Testar o painel na mao
```
cd ~/wol-rpi-k8s/site
venv/bin/python app.py
```
Abrir http://192.168.15.12:5000 -> logar -> conferir cards.
CTRL+C para parar. (Erros de timeout na porta 6443 = i9 desligado, normal.)

## 9. Servico systemd (sobe no boot, reinicia se cair)
Criar /etc/systemd/system/wol-panel.service (ver arquivo wol-panel.service).
```
sudo systemctl daemon-reload
sudo systemctl enable wol-panel
sudo systemctl start wol-panel
sudo systemctl status wol-panel      # deve estar active (running)
```

## 10. Cloudflared (acesso externo pelo dominio)
Ver GUIA-CLOUDFLARED.md.

## Prevencao (para nao repetir a perda)
- No-break (UPS) para RPi e i9 — quedas de energia sao a causa raiz.
- Backups do cartao: de tempos em tempos, dd do SD para um .img guardado.
- Considerar log2ram ou fs read-only no RPi para reduzir escrita no SD.
- Guardar o .env num cofre (Bitwarden) — os segredos sao o que mais custa remontar.
