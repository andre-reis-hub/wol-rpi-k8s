# Setup Completo — Do Zero ao Cluster Funcional
**Ambiente:** Ubuntu 24.04, i9 11ª geração, Raspberry Pi Zero W  
**Data:** Junho 2026  
**Tempo estimado:** 4–6 horas

> Este guia cobre todo o processo de configuração do projeto wol-rpi-k8s do zero.  
> Para troubleshooting e incidentes, consulte [post-mortem-2026-06-05.md](post-mortem-2026-06-05.md).  
> Para instalação rápida do k8s apenas, consulte [checklist-k8s.md](checklist-k8s.md).

---

## Índice

1. [Pré-requisitos](#1-pré-requisitos)
2. [Configurar Wake-on-LAN na BIOS](#2-configurar-wake-on-lan-na-bios)
3. [Configurar Wake-on-LAN no Linux](#3-configurar-wake-on-lan-no-linux)
4. [Reservar IPs no roteador](#4-reservar-ips-no-roteador)
5. [Preparar disco secundário](#5-preparar-disco-secundário)
6. [Instalar Kubernetes](#6-instalar-kubernetes)
7. [Configurar Raspberry Pi Zero W](#7-configurar-raspberry-pi-zero-w)
8. [Configurar o painel Flask](#8-configurar-o-painel-flask)
9. [Configurar Cloudflare Tunnel](#9-configurar-cloudflare-tunnel)
10. [Configurar agente no i9](#10-configurar-agente-no-i9)
11. [Instalar Vault](#11-instalar-vault)
12. [Verificação final](#12-verificação-final)

---

## 1. Pré-requisitos

### Hardware necessário
- PC com suporte a Wake-on-LAN (verificar BIOS)
- Raspberry Pi Zero W com cartão SD (mínimo 8GB classe 10)
- Cabo ethernet conectado ao PC principal
- Roteador com suporte a reserva DHCP

### Contas necessárias
- Conta GitHub (gratuita)
- Conta Cloudflare (gratuita)
- Domínio próprio adicionado à Cloudflare (~R$15-40/ano)

### Software necessário no PC principal
- Ubuntu 24.04 LTS instalado
- Acesso SSH configurado

---

## 2. Configurar Wake-on-LAN na BIOS

> ⚠️ Faça isso antes de instalar qualquer software. Sem WoL na BIOS, o PC não acorda pelo RPi.

### Entrar na BIOS
Reinicie o PC e pressione `DEL` ou `F2` durante o boot.

### Localizar a opção WoL
O caminho varia por fabricante. No setup deste projeto (AMI BIOS):

```
Chipset → PCH-IO Configuration → DeepSx Power Policies → Enabled in S5
```

> **Por que "Enabled in S5"?**  
> S5 = estado de desligamento completo. Habilitar DeepSx no S5 mantém energia
> suficiente na placa de rede para receber o magic packet mesmo com o PC desligado.

### Salvar e sair
Pressione `F10` para salvar e reiniciar.

---

## 3. Configurar Wake-on-LAN no Linux

Após o Ubuntu iniciar, configure o WoL na interface de rede:

```bash
# Descobrir o nome da interface ethernet
ip link show
# Procure por: enp5s0 ou similar (estado UP, com cabo conectado)

# Verificar suporte a WoL
sudo ethtool enp5s0 | grep -i wake
# Deve mostrar: Supports Wake-on: pumbg

# Habilitar WoL (substitua enp5s0 pelo seu nome de interface)
sudo ethtool -s enp5s0 wol g

# Verificar se foi habilitado
sudo ethtool enp5s0 | grep -i wake
# Deve mostrar: Wake-on: g
```

### Tornar permanente via systemd

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
sudo systemctl start wol.service
```

### Anotar o MAC address
```bash
ip link show enp5s0
# Anote o MAC: link/ether XX:XX:XX:XX:XX:XX
```

> No setup deste projeto: MAC `00:e0:4c:a6:00:3e`

---

## 4. Reservar IPs no roteador

> ⚠️ **Crítico:** O Kubernetes embute o IP do servidor nos certificados TLS.
> Se o IP mudar após a instalação, o cluster fica inacessível.
> Faça isso **antes** de instalar o k8s.

### Acessar o painel do roteador
Abra `http://192.168.15.1` no browser.

### Criar reservas DHCP
Localize a opção **Reserva DHCP** ou **Address Reservation** e adicione:

| Dispositivo | MAC | IP Reservado |
|-------------|-----|--------------|
| PC Linux (i9) | `00:e0:4c:a6:00:3e` | `192.168.15.14` |
| Raspberry Pi Zero W | `b8:27:eb:c1:50:af` | `192.168.15.12` |

### Verificar
```bash
ip addr show enp5s0
# Deve mostrar o IP reservado
```

---

## 5. Preparar disco secundário

> O Kubernetes armazena imagens de containers em `/var/lib/containerd`.
> Se a partição `/` for pequena (<30GB), mova o containerd para um disco maior.

### Identificar os discos
```bash
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE
sudo parted -l
# Anote qual disco é qual antes de prosseguir
```

### Particionar o disco secundário
> ⚠️ Substitua `nvme1n1` pelo nome correto do seu disco secundário.

```bash
sudo parted /dev/nvme1n1
```

Dentro do parted:
```
print          # ver partições existentes
mkpart primary ext4 450GB 100%    # criar partição (ajuste o início conforme necessário)
print          # confirmar
quit
```

### Formatar e montar
```bash
sudo mkfs.ext4 /dev/nvme1n1p2

sudo mkdir -p /var/lib/rancher
sudo mount /dev/nvme1n1p2 /var/lib/rancher

# Tornar permanente
echo '/dev/nvme1n1p2 /var/lib/rancher ext4 defaults 0 2' | sudo tee -a /etc/fstab

# Verificar
df -h /var/lib/rancher
# Deve mostrar o tamanho correto da partição
```

### Mover containerd para o disco secundário
```bash
sudo mkdir -p /var/lib/rancher/containerd/data
sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd

# Verificar symlink
ls -la /var/lib/containerd
# Deve mostrar: /var/lib/containerd -> /var/lib/rancher/containerd/data
```

---

## 6. Instalar Kubernetes

### Desabilitar swap
```bash
sudo swapoff -a
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

# Verificar — Swap deve mostrar 0B
free -h
```

### Módulos do kernel
```bash
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

sudo sysctl --system
```

### Containerd
```bash
sudo apt install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd
sudo systemctl enable containerd
```

### kubeadm, kubelet, kubectl
```bash
sudo apt install -y apt-transport-https ca-certificates curl gpg

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | \
  sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /' | \
  sudo tee /etc/apt/sources.list.d/kubernetes.list

sudo apt update
sudo apt install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

### Inicializar o cluster
```bash
# Substitua pelo IP fixo reservado no roteador
sudo kubeadm init \
  --pod-network-cidr=10.244.0.0/16 \
  --apiserver-advertise-address=192.168.15.14
```

> ⚠️ Salve o comando `kubeadm join` gerado no final — necessário para adicionar nós futuramente.

### Configurar kubeconfig
```bash
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

### CNI — Flannel
```bash
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
```

### Permitir pods no control-plane (single-node)
```bash
kubectl taint nodes --all node-role.kubernetes.io/control-plane-
```

### Helm
```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### Verificar
```bash
kubectl get nodes
# NAME               STATUS   ROLES           AGE   VERSION
# andre-reis-hm570   Ready    control-plane   Xm    v1.32.x

kubectl get pods -A
# Todos devem estar Running
```

---

## 7. Configurar Raspberry Pi Zero W

### Gravar o SO no cartão SD
1. Baixe o **Raspberry Pi Imager**: [rpi.imager](https://www.raspberrypi.com/software/)
2. Insira o cartão SD no computador
3. Selecione:
   - **Dispositivo:** Raspberry Pi Zero W
   - **SO:** Raspberry Pi OS Lite (32-bit)
4. Clique no ícone de engrenagem ⚙️ **antes de gravar** e configure:
   - Hostname: `RBizero-A-Reis`
   - Usuário: `andre` / Senha: sua senha
   - WiFi: SSID e senha da sua rede
   - **Habilitar SSH** ✅
5. Grave e insira o SD no RPi

### Conectar via SSH
```bash
# Descubra o IP no painel do roteador ou use o hostname
ssh andre@192.168.15.12
```

### Atualizar e instalar dependências
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
```

### Clonar o repositório
```bash
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s
```

---

## 8. Configurar o painel Flask

```bash
cd ~/wol-rpi-k8s/site
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configurar variáveis de ambiente
```bash
cp .env.example .env
nano .env
```

Preencha:
```env
SECRET_KEY=        # python3 -c "import secrets; print(secrets.token_hex(32))"
USERNAME=admin
PASSWORD=sua-senha-forte
PC_MAC=00:e0:4c:a6:00:3e
PC_LOCAL_IP=192.168.15.14
REGISTER_TOKEN=    # python3 -c "import secrets; print(secrets.token_hex(32))"
TUNNEL_URL=https://panel.areis-solution.com
```

### Subir como serviço
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
sudo systemctl status wol-panel
```

### Testar
Acesse `http://192.168.15.12:5000` no browser local.

---

## 9. Configurar Cloudflare Tunnel

### Instalar cloudflared no RPi
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm -O cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
cloudflared --version
```

### Autenticar e criar tunnel
```bash
# Abre link no browser para autorizar
cloudflared tunnel login

# Criar tunnel
cloudflared tunnel create wol-panel

# Anotar o UUID gerado!
cloudflared tunnel list
```

### Configurar DNS
```bash
cloudflared tunnel route dns wol-panel panel.areis-solution.com
```

### Criar config.yml
```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

Conteúdo (substitua o UUID):
```yaml
tunnel: <TUNNEL-UUID>
credentials-file: /home/andre/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: panel.areis-solution.com
    service: http://localhost:5000
  - service: http_status:404
```

### Subir como serviço
```bash
sudo tee /etc/systemd/system/wol-tunnel.service << 'EOF'
[Unit]
Description=Cloudflare Tunnel — WoL Panel
After=network-online.target wol-panel.service
Wants=network-online.target
Requires=wol-panel.service

[Service]
User=andre
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/andre/.cloudflared/config.yml run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wol-tunnel
sudo systemctl start wol-tunnel
```

### Testar
Acesse `https://panel.areis-solution.com` de qualquer rede.

---

## 10. Configurar agente no i9

```bash
cd ~/Documents/wol-rpi-k8s/agent
python3 -m venv venv
source venv/bin/activate
pip install requests python-dotenv
```

### Configurar variáveis de ambiente
```bash
cp .env.example .env
nano .env
```

Preencha:
```env
PANEL_URL=http://192.168.15.12:5000
REGISTER_TOKEN=    # mesmo token configurado no RPi
INTERVAL=60
KUBECONFIG=/home/andre-reis/.kube/config
```

### Subir como serviço
```bash
sudo tee /etc/systemd/system/wol-agent.service << 'EOF'
[Unit]
Description=WoL Agent — registra IP e serviços no painel
After=network-online.target
Wants=network-online.target

[Service]
User=andre-reis
WorkingDirectory=/home/andre-reis/Documents/wol-rpi-k8s/agent
ExecStart=/home/andre-reis/Documents/wol-rpi-k8s/agent/venv/bin/python agent.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wol-agent
sudo systemctl start wol-agent
sudo systemctl status wol-agent
```

### Verificar
```bash
sudo journalctl -u wol-agent -f
# Deve mostrar: Registrado: ip=X.X.X.X, serviços=0
```

---

## 11. Instalar Vault

### Preparar storage
```bash
sudo mkdir -p /var/lib/rancher/vault
sudo chown 100:1000 /var/lib/rancher/vault
```

### Criar PersistentVolume
```bash
kubectl apply -f ~/Documents/wol-rpi-k8s/k8s/vault/pv.yaml
```

### Instalar via Helm
```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update
helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  -f ~/Documents/wol-rpi-k8s/k8s/vault/values.yaml
```

### Aguardar o pod subir
```bash
kubectl get pods -n vault -w
# Aguarde vault-0 aparecer como Running (pode levar 1-2 min)
```

### Inicializar (primeira vez apenas)
```bash
kubectl exec -it vault-0 -n vault -- vault operator init -key-shares=1 -key-threshold=1
```

> ⚠️ **CRÍTICO:** Salve o **Unseal Key** e **Root Token** em local seguro (ex: Bitwarden).
> Sem eles não consegue acessar o Vault após um restart.

### Fazer unseal
```bash
kubectl exec -it vault-0 -n vault -- vault operator unseal
# Cole o Unseal Key quando solicitado
```

### Verificar
```bash
kubectl get pods -n vault
# vault-0 deve mostrar 1/1 Running

kubectl exec -it vault-0 -n vault -- vault status | grep Sealed
# Sealed: false
```

### Configurar secrets do projeto
```bash
kubectl exec -it vault-0 -n vault -- sh
```

Dentro do pod:
```sh
vault login    # cole o Root Token

vault secrets enable -path=wol kv-v2

vault kv put wol/panel \
  SECRET_KEY="..." \
  USERNAME="..." \
  PASSWORD="..." \
  REGISTER_TOKEN="..."

vault kv put wol/agent \
  REGISTER_TOKEN="..." \
  PANEL_URL="http://192.168.15.12:5000"

exit
```

### Unseal após cada reboot do pod
```bash
# Verificar se está sealed
kubectl exec -it vault-0 -n vault -- vault status | grep Sealed

# Se Sealed: true
kubectl exec -it vault-0 -n vault -- vault operator unseal
```

---

## 12. Verificação final

### Checklist completo

```bash
# Kubernetes
kubectl get nodes
# andre-reis-hm570   Ready   control-plane

kubectl get pods -A
# Todos Running

# Vault
kubectl get pods -n vault
# vault-0   1/1 Running

# Agente
sudo systemctl status wol-agent
# Active: active (running)

# WoL
sudo systemctl status wol
# Active: active

# Disco secundário montado
df -h /var/lib/rancher
# /dev/nvme1n1p2  526G ...

# Swap desabilitado
free -h
# Swap: 0B 0B 0B
```

### Teste do fluxo completo

1. Desligue o i9: `sudo shutdown now`
2. Acesse `https://panel.areis-solution.com`
3. Faça login
4. Clique em **"Ligar PC"**
5. Aguarde 1-3 minutos
6. O painel deve atualizar para **● Online** com o IP público

---

## Próximos passos

| Etapa | Descrição |
|-------|-----------|
| ArgoCD | GitOps — sync automático do repositório |
| Prometheus + Grafana | Monitoramento do cluster |
| GitHub Actions | CI/CD pipeline |
| Terraform | Infraestrutura como código |
| Auto-unseal Vault | Automatizar unseal após reboot |
ENDOFFILE
