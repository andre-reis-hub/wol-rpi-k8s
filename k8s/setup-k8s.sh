#!/bin/bash
# Setup Kubernetes (kubeadm) no Ubuntu 24.04
# Testado em: i9 11ª geração, 32GB RAM, Ubuntu 24.04
set -e

echo "=== 1. Desabilitar swap ==="
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

echo "=== 2. Módulos do kernel ==="
cat <<MODULES | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
MODULES
sudo modprobe overlay
sudo modprobe br_netfilter

cat <<SYSCTL | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
SYSCTL
sudo sysctl --system

echo "=== 3. Containerd ==="
sudo apt install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

# IMPORTANTE: se /var/lib estiver em disco pequeno, mover containerd para disco secundário
# sudo systemctl stop containerd
# sudo mkdir -p /var/lib/rancher/containerd
# sudo mv /var/lib/containerd /var/lib/rancher/containerd/data
# sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd

sudo systemctl restart containerd
sudo systemctl enable containerd

echo "=== 4. kubeadm, kubelet, kubectl ==="
sudo apt install -y apt-transport-https ca-certificates curl gpg
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt update
sudo apt install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl

echo "=== 5. Inicializar cluster ==="
sudo kubeadm init --pod-network-cidr=10.244.0.0/16

echo "=== 6. Kubeconfig ==="
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

echo "=== 7. Rede (Flannel) ==="
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

echo "=== 8. Permitir pods no control-plane (single-node) ==="
kubectl taint nodes --all node-role.kubernetes.io/control-plane-

echo ""
echo "=== Setup concluído ==="
kubectl get nodes
kubectl get pods -A
