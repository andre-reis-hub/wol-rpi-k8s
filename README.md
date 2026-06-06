# wol-rpi-k8s

Painel de controle remoto hospedado num Raspberry Pi Zero W para ligar o PC via Wake-on-LAN, monitorar status e acessar serviços Kubernetes remotamente.

## Infraestrutura

### Raspberry Pi Zero W (sempre ligado)
- **Função:** Gateway de baixo consumo, hospeda o painel web
- **OS:** Raspberry Pi OS Lite (32-bit, ARMv6)
- **IP local:** fixo via reserva DHCP no roteador (MAC: `b8:27:eb:c1:50:af`)
- **Consumo:** ~1W — fica ligado 24/7

### PC Linux — servidor principal (acorda sob demanda)
- **CPU:** Intel Core i9 11ª geração (8 cores / 16 threads)
- **RAM:** 32GB
- **OS:** Ubuntu 24.04 LTS
- **Kubernetes:** kubeadm (k8s completo v1.32)
- **Interface de rede:** `enp5s0` — MAC `00:e0:4c:a6:00:3e`
- **Acionamento:** WoL magic packet enviado pelo Pi Zero

### Discos do servidor
| Disco | Tamanho | Uso |
|-------|---------|-----|
| `nvme1n1p3` | 206GB | Windows (dual boot) |
| `nvme1n1p6` | 29GB | Ubuntu `/` |
| `nvme0n1p1` | 450GB | Jogos Windows (NTFS) |
| `nvme0n1p2` | 526GB | Kubernetes (`/var/lib/rancher`) |

> O containerd foi movido via symlink para o disco secundário:
> `sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd`

### Acesso Remoto
- **Exposição:** Cloudflare Tunnel (`cloudflared` no Pi Zero)
- **HTTPS:** automático via Cloudflare

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
- **Helm:** instalado para gerenciar charts

### PC Linux — Agente de boot
- **Implementação:** Script Python + systemd service
- **Dispara após:** `network-online.target`
- **Ações:**
  1. Consulta IP público via `api.ipify.org`
  2. Consulta NodePort services do K8s (`kubectl get services`)
  3. POST para Pi Zero com `{ ip, servicos: [{nome, porta}] }`

## Arquitetura

```
Internet
    │
Cloudflare Tunnel (HTTPS)
    │
Pi Zero W [Flask — sempre ligado]
    ├── GET /               → Dashboard (status PC, links, botão WoL)
    ├── POST /wol           → Envia magic packet (requer login)
    └── POST /api/register  ← agente do PC registra IP e serviços

PC Linux [systemd: agente.py]
    ├── Consulta IP público (api.ipify.org)
    ├── Consulta K8s services (NodePort)
    └── POST → Pi Zero /api/register

Kubernetes no PC [kubeadm v1.32]
    └── NodePort services (jogos, monitoramento)
        → Port forwarding no roteador
        → Links exibidos no dashboard
```

## Fluxo de uso

1. Usuário acessa `https://subdominio` (Cloudflare Tunnel)
2. Faz login
3. Vê status: **PC offline**
4. Clica em "Ligar PC" → Pi Zero envia WoL magic packet para `enp5s0`
5. Dashboard mostra **"Ligando..."** (polling a cada 5s)
6. PC boota → agente registra IP e serviços no Pi Zero
7. Dashboard atualiza: links dos serviços disponíveis

## Roadmap

| Etapa | Descrição | Status |
|-------|-----------|--------|
| 1 | Site base no Pi Zero (Flask + HTMX + login + status do PC) | ✅ |
| 2 | Integração WoL (botão ligar + estado "ligando") | ✅ |
| 3 | Cloudflare Tunnel (exposição segura à internet) | ⏳ |
| 4 | Agente leve no PC (systemd + registro de IP e serviços) | ⏳ |
| 5 | Kubernetes no PC (kubeadm v1.32) | ✅ |
| 6 | Ferramentas de monitoramento como pods K8s | ⏳ |
| 7 | Links dinâmicos de serviços no dashboard | ⏳ |

## Decisões

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Exposição à internet | Cloudflare Tunnel | Grátis, HTTPS automático, sem abrir portas no roteador |
| Autenticação | Flask session + `.env` | Um único usuário, sem overhead |
| Backend Pi Zero | Python + Flask | ARMv6 compatível, ecossistema simples |
| Frontend | HTMX + Jinja2 | Updates dinâmicos sem framework JS pesado |
| Estado persistido | JSON file | Sem banco de dados, suficiente para o escopo |
| IP fixo do Pi Zero | Reserva DHCP por MAC | Agente do PC precisa de endereço local estável |
| Agente no PC | Python + systemd | Nativo Linux, boot automático |
| IP público reportado | `api.ipify.org` | Fonte simples e autoritativa |
| Acesso a game servers | NodePort k8s + port forwarding | CGNAT descartado, IP público real confirmado |
| Kubernetes | kubeadm (k8s completo v1.32) | 32GB RAM disponível, aprendizado mais próximo do mercado |
| Armazenamento k8s | Disco secundário 526GB via symlink | Partição `/` de 29GB insuficiente para imagens de containers |
| WoL | Via cabo ethernet (`enp5s0`) | Placa WiFi discreta perde energia no S5 |
| Estratégia de commits | Direto na main, um commit por funcionalidade | Histórico linear e legível |

---

## Instalação — Raspberry Pi Zero W

Acesse o Pi via SSH e execute os passos abaixo.

### 1. Pré-requisitos

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Clonar o repositório

```bash
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s/site
```

### 3. Criar ambiente virtual e instalar dependências

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
nano .env
```

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `USERNAME` | Usuário do login |
| `PASSWORD` | Senha do login |
| `PC_MAC` | MAC do PC — `00:e0:4c:a6:00:3e` |
| `PC_LOCAL_IP` | IP local do PC na rede |
| `REGISTER_TOKEN` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |

### 5. Rodar como serviço (systemd)

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

### 1. Pré-requisito: disco secundário

Se a partição `/` for pequena (<30GB), mova o containerd para um disco maior após a instalação:

```bash
sudo systemctl stop kubelet containerd
sudo mkdir -p /var/lib/rancher/containerd
sudo mv /var/lib/containerd /var/lib/rancher/containerd/data
sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd
sudo systemctl start containerd kubelet
```

### 2. Rodar o script de instalação

```bash
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s/k8s
chmod +x setup-k8s.sh
./setup-k8s.sh
```

### 3. Verificar o cluster

```bash
kubectl get nodes
kubectl get pods -A
```

---

## Wake-on-LAN no Linux

### Configurar na BIOS
- **Chipset → PCH-IO Configuration → DeepSx Power Policies:** `Enabled in S5`

### Configurar no Linux

```bash
# Verificar suporte
sudo ethtool enp5s0 | grep -i wake
# Deve mostrar: Wake-on: g

# Habilitar permanentemente via systemd
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

- **IP do Pi Zero:** fixar via reserva DHCP antes de subir o agente no PC
- **Disco:** partição `/` do Ubuntu tem 29GB — imagens k8s ficam no disco secundário via symlink
- **Port forwarding para jogos:** configuração manual no roteador; pods expostos via NodePort (30000–32767)
- **Segurança WoL:** endpoint protegido por login
- **Estado intermediário:** entre WoL enviado e PC online leva 1–3 min
- **single-node:** taint do control-plane removido com `kubectl taint nodes --all node-role.kubernetes.io/control-plane-`
irtual e instalar dependências

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
nano .env
```

| Variável | Descrição |
|----------|-----------|
| `PANEL_URL` | URL local do Pi Zero (ex: `http://192.168.15.9:5000`) |
| `REGISTER_TOKEN` | Mesmo token configurado no `.env` do site |
| `INTERVAL` | Intervalo de atualização em segundos (padrão: `60`) |

### 4. Testar manualmente

```bash
source venv/bin/activate
python agent.py
```

Verifique no painel do Pi se o IP público aparece no dashboard.

### 5. Rodar como serviço (systemd)

```bash
# Substitua <seu-usuario-linux> pelo seu usuário real
sudo cp ~/wol-rpi-k8s/agent/wol-agent.service.example \
        /etc/systemd/system/wol-agent.service

sudo nano /etc/systemd/system/wol-agent.service
# Substitua os placeholders <seu-usuario-linux>

sudo systemctl daemon-reload
sudo systemctl enable wol-agent
sudo systemctl start wol-agent
sudo systemctl status wol-agent
```

### 6. Verificar logs

```bash
sudo journalctl -u wol-agent -f
```

---

## k3s no PC Linux (etapa 5)

k3s é uma distribuição K8s certificada pela CNCF, em binário único, ideal para homelab e estudo.

### Setup automatizado

```bash
cd ~/wol-rpi-k8s/k8s
chmod +x setup-k3s.sh
./setup-k3s.sh
```

O script faz:
1. Instala k3s
2. Aguarda o cluster ficar pronto
3. Copia o kubeconfig para `~/.kube/config`
4. Instala o Helm (necessário para o step 6)
5. Cria o namespace `homelab`

### Verificar o cluster

```bash
kubectl get nodes
kubectl get pods -A
```

### Atualizar o agente para usar o kubeconfig

No `.env` do agente (`~/wol-rpi-k8s/agent/.env`), ajuste a variável:

```bash
KUBECONFIG=/home/<seu-usuario-linux>/.kube/config
```

Reinicie o serviço:

```bash
sudo systemctl restart wol-agent
sudo journalctl -u wol-agent -f
```

Após isso, o agente começará a reportar os NodePort services do K8s no painel.

---

## Monitoramento K8s (etapa 6)

Stack instalado via Helm no namespace `homelab`:

| Ferramenta | Função |
|------------|--------|
| **Prometheus** | Coleta e armazena métricas do cluster e pods |
| **Grafana** | Dashboards — exposto na porta `30300` |
| **Loki** | Armazena logs dos pods |
| **Promtail** | Coleta logs de todos os pods e envia ao Loki |

### Pré-requisitos

- k3s instalado (etapa 5 concluída)
- Helm instalado (o script da etapa 5 já instala)

### Instalar

```bash
# Antes de rodar: edite a senha do Grafana
nano ~/wol-rpi-k8s/k8s/monitoring/prometheus-values.yml
# Altere o campo: adminPassword

chmod +x ~/wol-rpi-k8s/k8s/monitoring/setup-monitoring.sh
~/wol-rpi-k8s/k8s/monitoring/setup-monitoring.sh
```

> A instalação pode levar 3–5 minutos — os containers precisam ser baixados.

### Acessar o Grafana

```
http://<ip-do-pc>:30300
Usuário: admin
Senha: definida em prometheus-values.yml
```

Os datasources **Prometheus** e **Loki** já estão pré-configurados.

### Verificar pods

```bash
kubectl get pods -n homelab
```

Todos devem estar `Running`. Se algum ficar em `Pending`, verifique espaço em disco:

```bash
kubectl describe pod -n homelab <nome-do-pod>
```

### Dashboards recomendados para importar no Grafana

| Dashboard | ID | Conteúdo |
|-----------|----|----------|
| Kubernetes cluster | `315` | CPU, memória, rede por node |
| Node Exporter Full | `1860` | Métricas detalhadas do host Linux |
| Loki logs | `13639` | Explorador de logs |

Importar: Grafana → Dashboards → Import → colar o ID.

---

## Pontos de atenção

- **IP do Pi Zero:** Fixar via reserva DHCP no roteador (MAC: `b8:27:eb:c1:50:af`) antes de subir o agente no PC
- **Port forwarding para jogos:** Configuração manual no roteador; pods expostos via NodePort (faixa 30000–32767)
- **CGNAT:** Descartado — IP público real confirmado
- **Segurança WoL:** Endpoint protegido por login — sem autenticação qualquer um poderia ligar o PC
- **Estado intermediário:** Entre WoL enviado e PC online leva 1–3 min; dashboard deve refletir isso
