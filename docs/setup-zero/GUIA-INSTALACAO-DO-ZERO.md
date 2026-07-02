# wol-rpi-k8s — Guia de instalação do ZERO (reinstalação limpa 2026)

Guia mestre para reconstruir todo o projeto do zero no i9, incorporando as
licoes dos 20 incidentes. Substitui/complementa docs/setup-completo.md.

Premissas desta reinstalacao:
- Ubuntu Desktop 24.04 (voce joga no i9 -> precisa de GUI)
- Root de 150GB (fim do problema de disco pequeno!)
- Resto do disco de sistema + disco de 526GB para o k8s
- Melhorias aplicadas: disco por UUID desde o inicio, containerd data-root
  no disco grande, limites de log, GPU mitigada

====================================================================
FASE 0 — PARTICIONAMENTO (durante a instalacao do Ubuntu)
====================================================================

No instalador do Ubuntu Desktop 24.04, escolha "Something else"
(particionamento manual). Disco de sistema (o NVMe de ~238GB):

| Particao | Tamanho | Tipo | Mount |
|----------|---------|------|-------|
| EFI      | 512MB   | EFI System | /boot/efi |
| root     | 150GB   | ext4 | / |
| (restante deste disco pode virar swap OU deixar livre) | | | |

O disco de 526GB (NVMe separado): NAO formatar durante a instalacao se ja
tiver dados que queira manter. Se for zerar tudo, criar 1 particao ext4 que
sera montada em /var/lib/rancher (faremos por UUID depois).

> LICAO INCIDENTE 16/20: nunca dependa de /dev/nvmeXnY. Vamos montar por UUID.
> LICAO INCIDENTE 20: root de 150GB (nao 29GB) elimina o disk-pressure.

Durante a instalacao:
- Hostname sugerido: andre-reis-hm570 (mantem compatibilidade com manifestos)
- Usuario: andre-reis
- Marque "Install third-party software" (drivers NVIDIA)

====================================================================
FASE 1 — PREPARACAO DO SISTEMA (pos-primeiro-boot)
====================================================================

## 1.1 Atualizar e ferramentas base
```
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl ca-certificates gnupg lsb-release jq net-tools \
  iproute2 iputils-ping dnsutils git openssh-server
```

## 1.2 IP fixo na rede (192.168.15.14)
Via GUI (Settings > Network > IPv4 > Manual) ou netplan. Confirme:
```
ip -br addr    # enp5s0 deve ter 192.168.15.14/24
```
> Se houver WiFi (wlp*), desative para evitar rota assimetrica (licao antiga).

## 1.3 Montar o disco de 526GB por UUID
```
lsblk -o NAME,SIZE,FSTYPE,UUID          # descubra o UUID da particao de 526GB
sudo mkdir -p /var/lib/rancher
# adicione ao /etc/fstab (troque UUID-AQUI):
echo 'UUID=UUID-AQUI /var/lib/rancher ext4 defaults 0 2' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount -a
df -h /var/lib/rancher                  # confirme 526G montado
```
> CRITICO: sempre UUID, nunca /dev/nvme... (Incidente 16).

## 1.4 GPU NVIDIA — mitigacao anti-congelamento (voce joga no i9)
```
# Confirmar driver
nvidia-smi
# Mitigacao PCIe (Incidente da GPU travando). NAO usar pcie_aspm=off pois
# tira o video em algumas placas! Usar so o EnableGpuFirmware=0:
sudo sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash nvidia.NVreg_EnableGpuFirmware=0"/' /etc/default/grub
sudo update-grub
```
> LICAO: pcie_aspm=off resolvia trava mas TIRAVA O VIDEO. Como voce joga no
> i9, ficamos so com EnableGpuFirmware=0. Se travar, investigar BIOS (C-states)
> em vez de empilhar mitigacoes que quebram video.

## 1.5 Swap OFF (requisito do kubelet)
```
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab    # comenta swap no fstab
```

====================================================================
FASE 2 — CONTAINERD + KUBERNETES (kubeadm)
====================================================================

## 2.1 Modulos de kernel e sysctl
```
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
sudo modprobe overlay && sudo modprobe br_netfilter
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF
sudo sysctl --system
```

## 2.2 Containerd COM data-root no disco grande (MELHORIA anti-Incidente 20)
```
sudo apt install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
# cgroup driver systemd (obrigatorio):
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
# MELHORIA: mover o data-root do containerd para o disco de 526GB
sudo mkdir -p /var/lib/rancher/containerd
sudo sed -i 's#root = "/var/lib/containerd"#root = "/var/lib/rancher/containerd"#' /etc/containerd/config.toml
sudo systemctl restart containerd
sudo systemctl enable containerd
```
> LICAO INCIDENTE 20: as imagens de container incham o disco. Colocando o
> data-root no disco de 526GB, o root de 150GB nunca enche por imagens.

## 2.3 Instalar kubeadm/kubelet/kubectl (v1.32)
```
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | \
  sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /' | \
  sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt update
sudo apt install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

## 2.4 Inicializar o cluster (single-node)
```
sudo kubeadm init --pod-network-cidr=10.244.0.0/16
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
# permitir pods no unico node (control-plane):
kubectl taint nodes --all node-role.kubernetes.io/control-plane- 2>/dev/null || true
```

## 2.5 CNI Flannel
```
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
kubectl get nodes    # deve ficar Ready em 1-2min
```

====================================================================
FASE 3 — CLONAR O REPO E STORAGE
====================================================================

## 3.1 Clonar
```
mkdir -p ~/Documents && cd ~/Documents
git clone https://github.com/andre-reis-hub/wol-rpi-k8s.git
cd wol-rpi-k8s
```

## 3.2 StorageClass local (via Terraform ou kubectl)
```
kubectl apply -f k8s/storage/            # se tiver a StorageClass versionada
# ou aplicar a StorageClass local-storage manualmente (ver docs)
```

## 3.3 Criar pastas dos servicos no disco grande
```
for s in vault prometheus loki palworld abiotic-factor valheim containerd; do
  sudo mkdir -p /var/lib/rancher/$s
done
sudo chown 1000:1000 /var/lib/rancher/{palworld,abiotic-factor,valheim}
sudo chown 10001:10001 /var/lib/rancher/loki
```

Continua em GUIA-INSTALACAO-PARTE2.md (Vault, ArgoCD, monitoramento, jogos).
