# wol-rpi-k8s

Painel de controle remoto hospedado num Raspberry Pi Zero W para ligar o PC via Wake-on-LAN, monitorar status e acessar serviços Kubernetes remotamente.

## Infraestrutura

### Raspberry Pi Zero W (sempre ligado)
- **Função:** Gateway de baixo consumo, hospeda o painel web
- **OS:** Raspberry Pi OS Lite (32-bit, ARMv6)
- **IP local:** fixo via reserva DHCP — `192.168.15.12` (MAC: `b8:27:eb:c1:50:af`)
- **Consumo:** ~1W — fica ligado 24/7

### PC Linux — servidor principal (acorda sob demanda)
- **CPU:** Intel Core i9 11ª geração (8 cores / 16 threads)
- **RAM:** 32GB
- **OS:** Ubuntu 24.04 LTS
- **IP local:** fixo via reserva DHCP — `192.168.15.14` (MAC: `00:e0:4c:a6:00:3e`)
- **Kubernetes:** kubeadm (k8s completo v1.32)
- **Interface de rede:** `enp5s0`
- **Acionamento:** WoL magic packet enviado pelo Pi Zero

### Discos do servidor
| Disco | Tamanho | Uso |
|-------|---------|-----|
| `nvme0n1p3` | 206GB | Windows (dual boot) |
| `nvme0n1p6` | 29GB | Ubuntu `/` |
| `nvme1n1p1` | 450GB | Jogos Windows (NTFS) |
| `nvme1n1p2` | 526GB | Kubernetes — montado em `/var/lib/rancher` |

> O containerd foi movido via symlink para o disco secundário evitando disk-pressure na partição `/`:
> `sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd`

### Acesso Remoto
- **Exposição:** Cloudflare Tunnel (`cloudflared` no Pi Zero)
- **HTTPS:** automático via Cloudflare

---

## Stack

### Pi Zero — Backend
- **Linguagem:** Python
- **Framework:** Flask
- **Frontend:** HTMX + Jinja2
- **Estado do PC:** JSON file
- **Autenticação:** sessão Flask, credenciais em `.env`

### PC Linux — Kubernetes
- **Container runtime:** containerd
- **CNI:** Flannel (`10.244.0.0/16`)
- **Helm v3.21.0:** gerenciamento de charts
- **Vault:** gerenciamento de secrets (planejado)
- **ArgoCD:** GitOps — sync automático do repositório (planejado)

### PC Linux — Agente de boot
- **Implementação:** Script Python + systemd service
- **Dispara após:** `network-online.target`
- **Ações:**
  1. Consulta IP público via `api.ipify.org`
  2. Consulta NodePort services do K8s (`kubectl get services`)
  3. POST para Pi Zero com `{ ip, servicos: [{nome, porta}] }`

---

## Arquitetura

```
Internet
    │
Cloudflare Tunnel (HTTPS)
    │
Pi Zero W [Flask — sempre ligado — 192.168.15.12]
    ├── GET /               → Dashboard (status PC, links, botão WoL)
    ├── POST /wol           → Envia magic packet (requer login)
    └── POST /api/register  ← agente do PC registra IP e serviços

PC Linux [systemd: agente.py — 192.168.15.14]
    ├── Consulta IP público (api.ipify.org)
    ├── Consulta K8s services (NodePort)
    └── POST → Pi Zero /api/register

Kubernetes no PC [kubeadm v1.32]
    ├── Vault (secrets)
    ├── ArgoCD (GitOps)
    └── NodePort services (jogos, monitoramento)
        → Port forwarding no roteador
        → Links exibidos no dashboard
```

---

## Fluxo de uso

1. Usuário acessa `https://subdominio` (Cloudflare Tunnel)
2. Faz login
3. Vê status: **PC offline**
4. Clica em "Ligar PC" → Pi Zero envia WoL magic packet para `enp5s0`
5. Dashboard mostra **"Ligando..."** (polling a cada 5s)
6. PC boota → agente registra IP e serviços no Pi Zero
7. Dashboard atualiza: links dos serviços disponíveis

---

## Roadmap

| Etapa | Descrição | Status |
|-------|-----------|--------|
| 1 | Site base no Pi Zero (Flask + HTMX + login + status do PC) | ✅ |
| 2 | Integração WoL (botão ligar + estado "ligando") | ✅ |
| 3 | Cloudflare Tunnel (exposição segura à internet) | ⏳ |
| 4 | Agente leve no PC (systemd + registro de IP e serviços) | ⏳ |
| 5 | Kubernetes no PC (kubeadm v1.32 + Helm) | ✅ |
| 6 | HashiCorp Vault (gerenciamento de secrets) | ⏳ |
| 7 | ArgoCD (GitOps — sync automático do repo) | ⏳ |
| 8 | Ferramentas de monitoramento como pods K8s | ⏳ |
| 9 | Links dinâmicos de serviços no dashboard | ⏳ |

---

## Decisões

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Exposição à internet | Cloudflare Tunnel | Grátis, HTTPS automático, sem abrir portas no roteador |
| Autenticação painel | Flask session + `.env` | Um único usuário, sem overhead |
| Backend Pi Zero | Python + Flask | ARMv6 compatível, ecossistema simples |
| Frontend | HTMX + Jinja2 | Updates dinâmicos sem framework JS pesado |
| Estado persistido | JSON file | Sem banco de dados, suficiente para o escopo |
| IP fixo dos dispositivos | Reserva DHCP por MAC | Certificados k8s e agente dependem de IPs estáveis |
| Agente no PC | Python + systemd | Nativo Linux, boot automático |
| IP público reportado | `api.ipify.org` | Fonte simples e autoritativa |
| Acesso a game servers | NodePort k8s + port forwarding | CGNAT descartado, IP público real confirmado |
| Kubernetes | kubeadm (k8s completo v1.32) | 32GB RAM disponível, mais próximo do mercado |
| Armazenamento k8s | Disco secundário 526GB via symlink | Partição `/` de 29GB insuficiente para imagens |
| WoL | Via cabo ethernet (`enp5s0`) | Placa WiFi discreta perde energia no S5 |
| Secrets | HashiCorp Vault | Self-hosted, integração nativa com k8s |
| GitOps | ArgoCD | Padrão de mercado, UI intuitiva |
| Estratégia de commits | Direto na main, um commit por funcionalidade | Histórico linear e legível |

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/checklist-k8s.md](docs/checklist-k8s.md) | Checklist completo de instalação do cluster |
| [docs/post-mortem-2026-06-05.md](docs/post-mortem-2026-06-05.md) | Incidentes e lições aprendidas do setup inicial |

---

## Instalação — Raspberry Pi Zero W

> Veja o checklist completo em [docs/checklist-k8s.md](docs/checklist-k8s.md)

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s/site
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `USERNAME` | Usuário do login |
| `PASSWORD` | Senha do login |
| `PC_MAC` | MAC do PC — `00:e0:4c:a6:00:3e` |
| `PC_LOCAL_IP` | IP local do PC — `192.168.15.14` |
| `REGISTER_TOKEN` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |

```bash
sudo tee /etc/systemd/system/wol-panel.service << 'EOF'
[Unit]
Description=WoL Panel
After=network-online.target
Wants=network-online.target

[Service]
User=andre
WorkingDirectory=/home/andre/wol-rpi-k8s/site
ExecStart=/home/andre/wol-rpi-k8s/site/venv/bin/python app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wol-panel
sudo systemctl start wol-panel
```

---

## Instalação — PC Linux (Kubernetes)

> Siga o [docs/checklist-k8s.md](docs/checklist-k8s.md) para a ordem correta de instalação.

```bash
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s/k8s
chmod +x setup-k8s.sh
./setup-k8s.sh
```

---

## Wake-on-LAN no Linux

### BIOS
- **Chipset → PCH-IO Configuration → DeepSx Power Policies:** `Enabled in S5`
- **Wake on WLAN and BT Enable:** `Enabled`

### Linux

```bash
# Verificar suporte
sudo ethtool enp5s0 | grep -i wake
# Deve mostrar: Wake-on: g

# Serviço systemd para habilitar no boot
sudo tee /etc/systemd/system/wol.service << 'EOF'
[Unit]
Description=Enable Wake-on-LAN on enp5s0
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/ethtool -s enp5s0 wol g

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable wol.service
sudo systemctl start wol.service
```

---

## Pontos de atenção

- **IPs fixos:** reservar DHCP por MAC **antes** de instalar k8s — certificados TLS são gerados com o IP do momento
- **Disco:** partição `/` tem 29GB — containerd fica no disco secundário via symlink
- **Swap:** deve estar desabilitado — verificar com `free -h` antes do `kubeadm init`
- **Port forwarding:** pods expostos via NodePort (30000–32767) — configurar manualmente no roteador
- **Single-node:** taint do control-plane removido com `kubectl taint nodes --all node-role.kubernetes.io/control-plane-`
- **Boot time:** entre WoL enviado e PC online leva 1–3 min
