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
          ├── Vault       (secrets — Raft + auto-unseal)
          ├── ArgoCD      (GitOps)
          ├── Prometheus  (métricas)
          ├── Grafana     (dashboards)
          └── Game servers (NodePort)
```

## Fluxo de uso

```
1. Acessa panel.areis-solution.com
2. Faz login
3. Clica "Ligar PC" → RPi envia WoL magic packet
4. i9 boota (~1-3 min)
5. Agente registra IP público e serviços k8s no painel
6. Vault faz auto-unseal automaticamente
7. Dashboard atualiza com links dos serviços
```

## Fluxo de deploy (GitOps)

```
git push → ArgoCD detecta mudança no repo
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
- **GPU:** NVIDIA GTX 1660
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

> Containerd, Vault e Prometheus usam o disco secundário via symlink/PV:
> - `/var/lib/containerd` → symlink para `/var/lib/rancher/containerd/data`
> - Vault PV → `/var/lib/rancher/vault`
> - Prometheus PV → `/var/lib/rancher/prometheus`
> - StorageClass `local-storage` (provisioner manual, `WaitForFirstConsumer`)

---

## Stack

### Raspberry Pi Zero W
| Componente | Função |
|-----------|--------|
| Flask + HTMX + Jinja2 | Painel web |
| wakeonlan | Envio do magic packet |
| cloudflared | Tunnel Cloudflare (multi-hostname) |
| systemd | Gerencia os serviços |

### Kubernetes (i9)
| Componente | Função |
|-----------|--------|
| kubeadm v1.32 | Cluster k8s |
| Flannel | CNI (`10.244.0.0/16`) |
| Helm v3 | Gerenciamento de charts |
| Vault (Raft) | Secrets persistentes + auto-unseal |
| ArgoCD | GitOps — sync automático |
| kube-prometheus-stack | Prometheus + Grafana + AlertManager |
| GitHub Actions | CI/CD pipeline (planejado) |
| Terraform | Infraestrutura como código (planejado) |

### Acesso externo (mesmo Cloudflare Tunnel)
| Subdomínio | Serviço | Host |
|-----------|---------|------|
| `panel.areis-solution.com` | Painel Flask | RPi Zero W |
| `grafana.areis-solution.com` | Grafana | i9 / k8s NodePort |
| `argocd.areis-solution.com` | ArgoCD | i9 / k8s NodePort |

---

## Roadmap

| Etapa | Descrição | Status |
|-------|-----------|--------|
| 1 | Painel Flask (WoL + login + status) | ✅ |
| 2 | Integração WoL (botão ligar + estado "ligando") | ✅ |
| 3 | Cloudflare Tunnel + domínio próprio | ✅ |
| 4 | Agente no i9 (registro de IP e serviços) | ✅ |
| 5 | Kubernetes + Helm | ✅ |
| 6 | Vault (Raft + auto-unseal) | ✅ |
| 7 | ArgoCD (GitOps) | ✅ |
| 8 | Prometheus + Grafana (monitoramento) | ✅ |
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
| Vault unseal | Script systemd + chave em `/etc/vault` | Simples e gratuito; suficiente para homelab |
| GitOps | ArgoCD | Padrão de mercado, UI intuitiva |
| Monitoramento | kube-prometheus-stack | Prometheus + Grafana + dashboards prontos em um chart |
| Storage k8s | StorageClass `local-storage` manual | Disco secundário sem provisioner dinâmico; PVs por serviço |
| Pesado no i9, leve no RPi | ArgoCD/Prometheus/Grafana no i9 | RPi Zero W (512MB RAM, ARMv6) não suporta essas cargas |
| CI/CD | GitHub Actions | Gratuito, integrado ao repo, ghcr.io para imagens |
| IaC | Terraform | HCL simples, fácil migração para AWS, mais adotado no mercado |
| Armazenamento k8s | Disco secundário 526GB via symlink/PV | Partição `/` de 29GB insuficiente para imagens e dados |
| WoL | Via cabo ethernet (`enp5s0`) | Placa WiFi discreta perde energia no S5 |
| IP fixo | Reserva DHCP por MAC | Certificados k8s e agente dependem de IPs estáveis |

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/setup-completo.md](docs/setup-completo.md) | Guia completo do zero ao cluster funcional |
| [docs/checklist-k8s.md](docs/checklist-k8s.md) | Checklist de instalação k8s + Vault + ArgoCD |
| [docs/post-mortem-2026-06-05.md](docs/post-mortem-2026-06-05.md) | Incidentes e lições aprendidas |

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

### Cloudflare Tunnel (multi-hostname)

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm -O cloudflared
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/

cloudflared tunnel login
cloudflared tunnel create wol-panel
cloudflared tunnel route dns wol-panel panel.areis-solution.com
cloudflared tunnel route dns wol-panel grafana.areis-solution.com
cloudflared tunnel route dns wol-panel argocd.areis-solution.com

mkdir -p ~/.cloudflared
cp cloudflared/config.yml.example ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml  # preencher UUID, domínio e os 3 hostnames

sudo cp cloudflared/wol-tunnel.service.example /etc/systemd/system/wol-tunnel.service
sudo systemctl daemon-reload
sudo systemctl enable wol-tunnel
sudo systemctl start wol-tunnel
```

---

## Instalação — PC Linux (Kubernetes)

> Siga o [docs/checklist-k8s.md](docs/checklist-k8s.md) para a ordem correta — inclui Vault e ArgoCD.

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

### Vault (Raft + auto-unseal)

```bash
cd k8s/vault
sudo mkdir -p /var/lib/rancher/vault && sudo chown 100:1000 /var/lib/rancher/vault
kubectl apply -f pv.yaml
helm install vault hashicorp/vault --namespace vault --create-namespace -f values.yaml

# Primeira vez apenas
kubectl exec -it vault-0 -n vault -- vault operator init -key-shares=1 -key-threshold=1
# ⚠️ Salvar Unseal Key e Root Token em local seguro

kubectl exec -it vault-0 -n vault -- vault operator unseal

# Auto-unseal
sudo mkdir -p /etc/vault && sudo chmod 700 /etc/vault
sudo nano /etc/vault/unseal-key  # colar unseal key
sudo chmod 400 /etc/vault/unseal-key
sudo cp unseal.sh.example /etc/vault/unseal.sh
sudo chmod 500 /etc/vault/unseal.sh
# configurar serviço systemd vault-unseal — ver docs/checklist-k8s.md
```

### Prometheus + Grafana

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring

kubectl apply -f k8s/monitoring/storageclass.yaml
sudo mkdir -p /var/lib/rancher/prometheus && sudo chown 1000:2000 /var/lib/rancher/prometheus
kubectl apply -f k8s/monitoring/prometheus-pv.yaml

helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword='senha-temporaria' \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName=local-storage \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi

kubectl patch svc monitoring-grafana -n monitoring -p '{"spec": {"type": "NodePort"}}'
```

### ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "NodePort"}}'

kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo

curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x argocd && sudo mv argocd /usr/local/bin/
argocd login argocd.areis-solution.com --username admin --grpc-web
argocd repo add https://github.com/andre-reis-hub/wol-rpi-k8s.git --username andre-reis-hub --password <PAT>
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
- **Disco:** containerd, Vault e Prometheus no disco secundário via symlink/PV
- **Vault:** Raft + auto-unseal — secrets persistem após reboot
- **ArgoCD + PV ReadWriteOnce:** updates causam ~30s de downtime (Recreate strategy) — aceitável em homelab
- **GPU NVIDIA:** mitigação de freezes via `nvidia.NVreg_EnableGpuFirmware=0` no GRUB
- **Single-node:** taint removido com `kubectl taint nodes --all node-role.kubernetes.io/control-plane-`
- **Boot time:** entre WoL e PC online leva 1–3 min
