# Checklist — Instalação Kubernetes Single-Node
> Baseado nos incidentes do setup de 05–06/Jun/2026.  
> Siga essa ordem. Não pule etapas.

---

## Pré-requisitos (ANTES de qualquer instalação)

- [ ] **Fixar IPs via reserva DHCP no roteador**
  ```bash
  # Verificar IP atual
  ip addr show enp5s0
  # Deve bater com o IP reservado no roteador
  ```

- [ ] **Identificar os discos corretamente**
  ```bash
  lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE
  sudo parted -l
  # Anotar: qual é o disco do SO, qual é o disco secundário
  ```

- [ ] **Montar disco secundário e criar symlink do containerd**
  ```bash
  sudo mkdir -p /var/lib/rancher
  sudo mount /dev/nvme1n1p2 /var/lib/rancher
  # Adicionar ao fstab:
  echo '/dev/nvme1n1p2 /var/lib/rancher ext4 defaults 0 2' | sudo tee -a /etc/fstab
  sudo mkdir -p /var/lib/rancher/containerd/data
  sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd
  # Verificar:
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
# Substitua pelo IP fixo do servidor
sudo kubeadm init \
  --pod-network-cidr=10.244.0.0/16 \
  --apiserver-advertise-address=192.168.15.14
```
✅ Verificar: output deve terminar com `Your Kubernetes control-plane has initialized successfully!`

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

## Verificação final

```bash
kubectl get nodes
# NAME               STATUS   ROLES           AGE   VERSION
# andre-reis-hm570   Ready    control-plane   Xm    v1.32.x

kubectl get pods -A
# Todos devem estar Running

helm version
# version.BuildInfo{Version:"v3.x.x" ...}

df -h /var/lib/rancher
# Deve mostrar ~526GB no nvme1n1p2
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
