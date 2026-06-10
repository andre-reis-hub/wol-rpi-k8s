# Checklist — Instalação Kubernetes Single-Node
> Baseado nos incidentes do setup de 05–09/Jun/2026.  
> Siga essa ordem. Não pule etapas.

---

## Pré-requisitos (ANTES de qualquer instalação)

- [ ] **Fixar IPs via reserva DHCP no roteador**
  ```bash
  ip addr show enp5s0
  # IP deve bater com o reservado no roteador
  ```

- [ ] **Identificar os discos corretamente**
  ```bash
  lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE
  sudo parted -l
  # Anotar: qual é o disco do SO, qual é o secundário
  ```

- [ ] **Montar disco secundário e criar symlink do containerd**
  ```bash
  sudo mkdir -p /var/lib/rancher
  sudo mount /dev/nvme1n1p2 /var/lib/rancher
  echo '/dev/nvme1n1p2 /var/lib/rancher ext4 defaults 0 2' | sudo tee -a /etc/fstab
  sudo mkdir -p /var/lib/rancher/containerd/data
  sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd
  df -h /var/lib/rancher  # deve mostrar ~526GB
  ```

- [ ] **Verificar espaço no disco principal**
  ```bash
  df -h /
  # Deve ter pelo menos 10GB livres
  ```

---

## Instalação

### 1. Desabilitar swap
```bash
sudo swapoff -a
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
```
✅ Verificar:
```bash
free -h
# Swap deve mostrar: 0B 0B 0B
```

### 2. Módulos do kernel
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

### 3. Containerd
```bash
sudo apt install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd
sudo systemctl enable containerd
```
✅ Verificar:
```bash
sudo systemctl status containerd
# Active: active (running)
```

### 4. kubeadm, kubelet, kubectl
```bash
sudo apt install -y apt-transport-https ca-certificates curl gpg
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt update
sudo apt install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

### 5. Inicializar o cluster
```bash
sudo kubeadm init \
  --pod-network-cidr=10.244.0.0/16 \
  --apiserver-advertise-address=192.168.15.14
```
✅ Output deve terminar com: `Your Kubernetes control-plane has initialized successfully!`

### 6. Kubeconfig
```bash
rm -rf $HOME/.kube
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

### 7. CNI — Flannel
```bash
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
```

### 8. Permitir pods no control-plane (single-node)
```bash
kubectl taint nodes --all node-role.kubernetes.io/control-plane-
```

### 9. Helm
```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

---

## Vault (Raft + auto-unseal)

### Instalar
```bash
sudo mkdir -p /var/lib/rancher/vault
sudo chown 100:1000 /var/lib/rancher/vault
kubectl apply -f k8s/vault/pv.yaml
helm repo add hashicorp https://helm.releases.hashicorp.com && helm repo update
helm install vault hashicorp/vault --namespace vault --create-namespace -f k8s/vault/values.yaml
```

### Inicializar (primeira vez)
```bash
kubectl exec -it vault-0 -n vault -- vault operator init -key-shares=1 -key-threshold=1
# ⚠️ SALVAR Unseal Key e Root Token no Bitwarden!
kubectl exec -it vault-0 -n vault -- vault operator unseal
```

### Auto-unseal
```bash
sudo mkdir -p /etc/vault && sudo chmod 700 /etc/vault
sudo nano /etc/vault/unseal-key   # colar a unseal key
sudo chmod 400 /etc/vault/unseal-key
sudo cp k8s/vault/unseal.sh.example /etc/vault/unseal.sh
sudo chmod 500 /etc/vault/unseal.sh

sudo tee /etc/systemd/system/vault-unseal.service << 'EOF'
[Unit]
Description=Auto-unseal do HashiCorp Vault
After=network-online.target kubelet.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/etc/vault/unseal.sh
RemainAfterExit=yes
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vault-unseal
```

---

## ArgoCD

### Instalar
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "NodePort"}}'
```

### Senha inicial
```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```

### CLI
```bash
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x argocd && sudo mv argocd /usr/local/bin/
argocd login argocd.areis-solution.com --username admin --grpc-web
```

### Conectar repo e criar Application
```bash
argocd repo add https://github.com/andre-reis-hub/wol-rpi-k8s.git --username andre-reis-hub --password <PAT>

argocd app create wol-infra \
  --repo https://github.com/andre-reis-hub/wol-rpi-k8s.git \
  --path k8s/vault \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace vault \
  --sync-policy automated \
  --auto-prune \
  --self-heal
```

---

## Verificação final

```bash
kubectl get nodes
# Ready

kubectl get pods -A
# Todos Running

kubectl exec -n vault vault-0 -- vault status | grep Sealed
# Sealed: false

argocd app list
# STATUS: Synced, HEALTH: Healthy

df -h /var/lib/rancher
# ~526GB disponível

free -h
# Swap: 0B
```

---

## Troubleshooting rápido

| Sintoma | Causa provável | Solução |
|---------|---------------|---------|
| `connection refused :6443` | IP mudou ou kubelet parado | Verificar IP, `systemctl restart kubelet` |
| `swap is not supported` | Swap ativo | `swapoff -a` + corrigir fstab |
| `disk-pressure` no node | Disco `/` cheio | Verificar symlink containerd |
| `x509: certificate` | IP mudou após kubeadm init | `kubeadm reset` + `kubeadm init` com IP correto |
| containerd não inicia | Disco secundário não montado | `mount /dev/nvme1n1p2 /var/lib/rancher` |
| superblock inválido | Corrupção após resize | `mkfs.ext4 -F /dev/nvme1n1p2` |
| Vault sealed após reboot | Comportamento esperado | `vault operator unseal` ou auto-unseal |
| ArgoCD downtime no deploy | PV ReadWriteOnce | Aceito para homelab — auto-unseal resolve |
| PAT GitHub expirado | Token vencido | Gerar novo PAT e `argocd repo update` |
