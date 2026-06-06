# Post Mortem — Setup do Cluster Kubernetes
**Data:** 05–06 de Junho de 2026  
**Ambiente:** Ubuntu 24.04, i9 11ª geração, 32GB RAM, dual SSD

---

## Resumo

Setup completo de um cluster Kubernetes single-node com Wake-on-LAN, particionamento de disco secundário e painel de controle no Raspberry Pi Zero W. O processo levou aproximadamente 1 dia com múltiplos incidentes que foram resolvidos e documentados abaixo.

---

## Incidentes

### 1. IP do servidor mudou após reboot

**Severidade:** Alta  
**Impacto:** Cluster Kubernetes completamente inacessível

**O que aconteceu:**  
O servidor i9 estava com IP dinâmico via DHCP. Após um reboot, o IP mudou de `192.168.15.13` para `192.168.15.14`. O certificado TLS do Kubernetes havia sido gerado para o IP antigo, tornando toda comunicação com o API server impossível.

**Causa raiz:**  
Ausência de reserva DHCP por MAC antes da instalação do k8s. O kubeadm embute o IP do servidor nos certificados TLS no momento do `init` — qualquer mudança de IP invalida os certificados.

**Solução aplicada:**  
- Reserva DHCP por MAC no roteador para o i9 (`00:e0:4c:a6:00:3e` → `192.168.15.14`)
- Reserva DHCP por MAC para o RPi Zero (`b8:27:eb:c1:50:af` → `192.168.15.12`)
- `kubeadm reset` + `kubeadm init` com `--apiserver-advertise-address=192.168.15.14`

**Mitigação futura:**  
Sempre fixar IPs via reserva DHCP **antes** de instalar o k8s. Verificar com `ip addr` que o IP está correto antes do `kubeadm init`.

---

### 2. Disco errado formatado (`nvme0n1p2`)

**Severidade:** Alta  
**Impacto:** Microsoft Reserved Partition do Windows formatada (16MB — sem perda de dados do usuário)

**O que aconteceu:**  
O servidor tem dois SSDs: `nvme0n1` (256GB — Windows/Ubuntu) e `nvme1n1` (1TB — dados). A partição para o Kubernetes deveria ser criada em `nvme1n1p2`, mas os comandos foram executados em `nvme0n1p2` por confusão entre os dispositivos.

**Causa raiz:**  
Não verificar o `lsblk` completo antes de executar comandos de disco. Os nomes `nvme0n1` e `nvme1n1` são visualmente similares e fáceis de confundir.

**Solução aplicada:**  
- Corrigido o `/etc/fstab` de `nvme0n1p2` para `nvme1n1p2`
- Montado o disco correto em `/var/lib/rancher`
- A Microsoft Reserved Partition foi reformatada mas não afeta o funcionamento do Windows

**Mitigação futura:**  
Sempre executar `lsblk` e `sudo parted -l` antes de qualquer operação de disco. Anotar explicitamente qual dispositivo é qual antes de começar.

```bash
# Identificar discos antes de qualquer operação
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,LABEL
sudo parted -l
```

---

### 3. Swap ativo após reboot — kubelet recusou iniciar

**Severidade:** Média  
**Impacto:** kubelet não iniciou, `kubeadm init` falhou na fase de health check

**O que aconteceu:**  
O comando `swapoff -a` foi executado mas o `/etc/fstab` não foi corretamente modificado. Após o reboot, o swap voltou a ser ativado automaticamente. O kubelet do Kubernetes recusa iniciar com swap ativo.

**Causa raiz:**  
O `swapoff -a` desativa o swap apenas na sessão atual — não persiste após reboot. A edição do `fstab` na primeira tentativa não comentou corretamente a linha do swap.

**Solução aplicada:**  
```bash
sudo swapoff -a
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
free -h  # verificar Swap: 0B
```

**Mitigação futura:**  
Sempre verificar `free -h` mostrando `Swap: 0B` antes de executar o `kubeadm init`. Incluir essa verificação no checklist.

---

### 4. Superblock corrompido no `nvme1n1p2`

**Severidade:** Média  
**Impacto:** Disco secundário inacessível após reboot, dados do containerd perdidos, cluster precisou ser reiniciado do zero

**O que aconteceu:**  
Após redimensionar a partição NTFS de 954GB para 450GB e criar uma nova partição ext4 adjacente, o superblock da partição ext4 ficou corrompido. Na tentativa de montar o disco após reboot, o `mount` retornou erro de superblock inválido.

**Causa raiz:**  
Provável corrupção durante a operação de redimensionamento do NTFS com `parted`. O NTFS foi redimensionado sem que o Windows tivesse verificado/liberado o filesystem antes — o `parted` fez o resize diretamente.

**Solução aplicada:**  
```bash
sudo mkfs.ext4 -F /dev/nvme1n1p2  # reformatar
sudo mount /dev/nvme1n1p2 /var/lib/rancher
```

**Mitigação futura:**  
- Antes de redimensionar partições NTFS, inicializar o Windows e usar o Disk Management para liberar o filesystem
- Após criar partição ext4, verificar com `fsck` antes de usar
- Não armazenar dados críticos no disco secundário sem backup

---

### 5. Containerd usando disco principal (disk-pressure no k8s)

**Severidade:** Média  
**Impacto:** Pods não agendados — node em estado `disk-pressure`

**O que aconteceu:**  
O containerd por padrão armazena imagens em `/var/lib/containerd`, que fica na partição `/` do Ubuntu (29GB). Após o `kubeadm init` baixar as imagens do control plane (~2GB), a partição chegou a 87% de uso, acionando o mecanismo de disk-pressure do Kubernetes que impediu o agendamento de novos pods, incluindo o CoreDNS.

**Causa raiz:**  
Partição `/` pequena (29GB) combinada com o caminho padrão do containerd. O disco secundário foi montado em `/var/lib/rancher` mas o containerd não foi reconfigurado para usá-lo antes do `kubeadm init`.

**Solução aplicada:**  
```bash
sudo systemctl stop kubelet containerd
sudo mkdir -p /var/lib/rancher/containerd/data
sudo mv /var/lib/containerd /var/lib/rancher/containerd/data
sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd
sudo systemctl start containerd kubelet
```

**Mitigação futura:**  
Criar o symlink **antes** do `kubeadm init`. Ver checklist de instalação.

---

## Lições aprendidas

| Lição | Ação |
|-------|------|
| IP fixo é pré-requisito do k8s | Reservar DHCP antes de tudo |
| `swapoff` não persiste | Sempre verificar `free -h` antes do `kubeadm init` |
| Nomes de disco são confusos | Usar `lsblk` e anotar antes de qualquer operação |
| Partição `/` pequena não serve para k8s | Mover containerd para disco grande antes do init |
| Resize de NTFS é arriscado | Preferir particionar espaço não alocado |
| Certificados k8s são atrelados ao IP | IP fixo é obrigatório, não opcional |

---

## Estado final do ambiente

| Componente | Status | Detalhe |
|------------|--------|---------|
| Wake-on-LAN | ✅ | `enp5s0`, magic packet via RPi |
| RPi Zero W — painel Flask | ✅ | `192.168.15.12:5000`, systemd |
| i9 — Ubuntu 24.04 | ✅ | IP fixo `192.168.15.14` |
| Kubernetes v1.32.13 | ✅ | kubeadm, single-node |
| CNI | ✅ | Flannel `10.244.0.0/16` |
| Helm v3.21.0 | ✅ | `/usr/local/bin/helm` |
| Disco secundário | ✅ | `nvme1n1p2` → `/var/lib/rancher` (526GB) |
| Containerd | ✅ | Symlink para disco secundário |
| Vault | ⏳ | Próximo passo |
| ArgoCD | ⏳ | Próximo passo |
