# wol-rpi-k8s

Infraestrutura de game server doméstico com Wake-on-LAN, Kubernetes e painel de controle remoto. O servidor principal (i9) fica desligado e acorda sob demanda via Raspberry Pi Zero W — sempre ligado com consumo mínimo (~1W).

## Arquitetura

```
Internet
    │
Cloudflare Tunnel (HTTPS)
    ├── panel.areis-solution.com    → Flask painel (RPi Zero W)
    ├── grafana.areis-solution.com  → Grafana (i9 / k8s)
    └── argocd.areis-solution.com   → ArgoCD (i9 / k8s)

Raspberry Pi Zero W [sempre ligado — 192.168.15.12]
    ├── Flask painel (WoL, status, links)
    └── Cloudflare Tunnel (gateway de acesso)

PC Linux i9 [acorda sob demanda — 192.168.15.14]
    └── Kubernetes
          ├── Vault      (secrets)
          ├── ArgoCD     (GitOps)
          ├── Prometheus (métricas)
          ├── Grafana    (dashboards)
          └── Game servers (NodePort)
```

## Fluxo de uso

```
1. Acessa panel.areis-solution.com
2. Faz login
3. Clica "Ligar PC" → RPi envia WoL magic packet
4. i9 boota (~1-3 min)
5. Agente registra IP público e serviços k8s no painel
6. Dashboard atualiza com links dos serviços
```

## Fluxo de deploy (GitOps)

```
git push → GitHub Actions (CI)
              ├── testes
              ├── build imagem Docker
              ├── push ghcr.io (gratuito)
              └── atualiza manifesto k8s no repo
                      ↓
                  ArgoCD (CD) detecta mudança
                      ↓
                  Aplica no cluster k8s
                      ↓
                  Grafana exibe métricas do deploy
```

---

## Infraestrutura

### Raspberry Pi Zero W (sempre ligado)
- **Função:** Gateway leve — painel web + WoL + Cloudflare Tunnel
- **OS:** Raspberry Pi OS Lite (32-bit, ARMv6)
- **IP:** fixo `192.168.15.12` (MAC: `b8:27:eb:c1:50:af`)
- **Consumo:** ~1W

### PC Linux — servidor principal (acorda sob demanda)
- **CPU:** Intel Core i9 11ª geração (8 cores / 16 threads)
- **RAM:** 32GB
- **OS:** Ubuntu 24.04 LTS
- **IP:** fixo `192.168.15.14` (MAC: `00:e0:4c:a6:00:3e`)
- **Kubernetes:** kubeadm v1.32

### Discos do servidor
| Disco | Tamanho | Uso |
|-------|---------|-----|
| `nvme0n1p3` | 206GB | Windows (dual boot) |
| `nvme0n1p6` | 29GB | Ubuntu `/` |
| `nvme1n1p1` | 450GB | Jogos Windows (NTFS) |
| `nvme1n1p2` | 526GB | Kubernetes — `/var/lib/rancher` |

> O containerd usa symlink para o disco secundário:
> `sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd`

---

## Stack

### Raspberry Pi Zero W
| Componente | Função |
|-----------|--------|
| Flask + HTMX + Jinja2 | Painel web |
| wakeonlan | Envio do magic packet |
| cloudflared | Tunnel Cloudflare |
| systemd | Gerencia os serviços |

### Kubernetes (i9)
| Componente | Função |
|-----------|--------|
| kubeadm v1.32 | Cluster k8s |
| Flannel | CNI (`10.244.0.0/16`) |
| Helm v3 | Gerenciamento de charts |
| Vault (Raft) | Secrets persistentes |
| ArgoCD | GitOps — sync automático |
| Prometheus | Coleta de métricas |
| Grafana | Dashboards |
| GitHub Actions | CI/CD pipeline |
| Terraform | Infraestrutura como código |

### Acesso externo
| Subdomínio | Serviço | Host |
|-----------|---------|------|
| `panel.areis-solution.com` | Painel Flask | RPi Zero W |
| `grafana.areis-solution.com` | Grafana | i9 / k8s |
| `argocd.areis-solution.com` | ArgoCD | i9 / k8s |

---

## Roadmap

| Etapa | Descrição | Status |
|-------|-----------|--------|
| 1 | Painel Flask (WoL + login + status) | ✅ |
| 2 | Integração WoL (botão ligar + estado "ligando") | ✅ |
| 3 | Cloudflare Tunnel + domínio próprio | ✅ |
| 4 | Agente no i9 (registro de IP e serviços) | ✅ |
| 5 | Kubernetes + Helm | ✅ |
| 6 | Vault (Raft — storage persistente) | 🔄 em andamento |
| 7 | ArgoCD (GitOps) | ⏳ |
| 8 | Prometheus + Grafana (monitoramento) | ⏳ |
| 9 | GitHub Actions (CI/CD pipeline) | ⏳ |
| 10 | Terraform (infraestrutura como código) | ⏳ |
| 11 | Links dinâmicos de serviços no dashboard | ⏳ |

---

## Decisões

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Gateway sempre ligado | RPi Zero W | ~1W consumo, suficiente para Flask + WoL + tunnel |
| Kubernetes | kubeadm (k8s completo v1.32) | 32GB RAM disponível, mais próximo do mercado |
| CNI | Flannel | Simples, funciona bem em single-node |
| Exposição | Cloudflare Tunnel | Grátis, HTTPS automático, sem abrir portas |
| Múltiplos subdomínios | Mesmo tunnel, múltiplos hostnames | Grafana e ArgoCD acessíveis externamente sem custo extra |
| Secrets | Vault (Raft) | Self-hosted, persistente, integração nativa k8s |
| GitOps | ArgoCD | Padrão de mercado, UI intuitiva |
| CI/CD | GitHub Actions | Gratuito, integrado ao repo, ghcr.io para imagens |
| IaC | Terraform | HCL simples, fácil migração para AWS, mais adotado no mercado |
| Monitoramento | kube-prometheus-stack | Instala Prometheus + Grafana + dashboards prontos em um chart |
| Armazenamento k8s | Disco secundário 526GB via symlink | Partição `/` de 29GB insuficiente para imagens |
| WoL | Via cabo ethernet (`enp5s0`) | Placa WiFi discreta perde energia no S5 |
| IP fixo | Reserva DHCP por MAC | Certificados k8s e agente dependem de IPs estáveis |
| IaC migração AWS | Terraform providers | Mesmo código, troca provider local → AWS |

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/checklist-k8s.md](docs/checklist-k8s.md) | Checklist completo de instalação do cluster |
| [docs/post-mortem-2026-06-05.md](docs/post-mortem-2026-06-05.md) | Incidentes e lições aprendidas do setup inicial |

---

## Instalação — Raspberry Pi Zero W

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
| `TUNNEL_URL` | URL fixa do tunnel — `https://panel.areis-solution.com` |

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

### Cloudflare Tunnel

```bash
# Instalar cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm -O cloudflared
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/

# Autenticar e criar tunnel
cloudflared tunnel login
cloudflared tunnel create wol-panel
cloudflared tunnel route dns wol-panel panel.areis-solution.com

# Configurar
mkdir -p ~/.cloudflared
cp cloudflared/config.yml.example ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml  # preencher UUID e domínio

# Subir como serviço
sudo cp cloudflared/wol-tunnel.service.example /etc/systemd/system/wol-tunnel.service
sudo systemctl daemon-reload
sudo systemctl enable wol-tunnel
sudo systemctl start wol-tunnel
```

---

## Instalação — PC Linux (Kubernetes)

> Siga o [docs/checklist-k8s.md](docs/checklist-k8s.md) para a ordem correta.

```bash
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s/k8s
chmod +x setup-k8s.sh
./setup-k8s.sh
```

### Agente

```bash
cd wol-rpi-k8s/agent
python3 -m venv venv
source venv/bin/activate
pip install requests python-dotenv
cp .env.example .env
nano .env

sudo cp wol-agent.service.example /etc/systemd/system/wol-agent.service
sudo systemctl daemon-reload
sudo systemctl enable wol-agent
sudo systemctl start wol-agent
```

---

## Wake-on-LAN

### BIOS
- **Chipset → PCH-IO → DeepSx Power Policies:** `Enabled in S5`

### Linux
```bash
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
```

---

## Pontos de atenção

- **IPs fixos:** reservar DHCP por MAC **antes** de instalar k8s
- **Swap:** deve estar desabilitado — verificar com `free -h` antes do `kubeadm init`
- **Disco:** containerd no disco secundário via symlink — partição `/` tem 29GB
- **Vault:** modo Raft — secrets persistem no disco mesmo após reboot do pod
- **Single-node:** taint removido com `kubectl taint nodes --all node-role.kubernetes.io/control-plane-`
- **Boot time:** entre WoL e PC online leva 1–3 min
