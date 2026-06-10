# Post Mortem — Setup do Cluster Kubernetes
**Data:** 05–09 de Junho de 2026  
**Ambiente:** Ubuntu 24.04, i9 11ª geração, 32GB RAM, dual SSD

---

## Resumo

Setup completo de um cluster Kubernetes single-node com Wake-on-LAN, particionamento de disco secundário, painel de controle no Raspberry Pi Zero W, Vault com auto-unseal e ArgoCD GitOps. O processo levou aproximadamente 4 dias com múltiplos incidentes documentados abaixo.

---

## Incidentes

### 1. IP do servidor mudou após reboot

**Severidade:** Alta  
**Impacto:** Cluster Kubernetes completamente inacessível

**O que aconteceu:**  
O servidor i9 estava com IP dinâmico via DHCP. Após um reboot, o IP mudou de `192.168.15.13` para `192.168.15.14`. O certificado TLS do Kubernetes havia sido gerado para o IP antigo, tornando toda comunicação com o API server impossível.

**Causa raiz:**  
Ausência de reserva DHCP por MAC antes da instalação do k8s.

**Solução aplicada:**  
Reserva DHCP por MAC no roteador + `kubeadm reset` + `kubeadm init` com IP correto.

**Mitigação futura:**  
Sempre fixar IPs via reserva DHCP **antes** de instalar o k8s.

---

### 2. Disco errado formatado (`nvme0n1p2`)

**Severidade:** Alta  
**Impacto:** Microsoft Reserved Partition do Windows formatada (16MB)

**O que aconteceu:**  
O servidor tem dois SSDs: `nvme0n1` (256GB) e `nvme1n1` (1TB). Comandos executados em `nvme0n1p2` por confusão entre os dispositivos.

**Causa raiz:**  
Não verificar o `lsblk` completo antes de executar comandos de disco.

**Solução aplicada:**  
Corrigido o `/etc/fstab` e montado o disco correto. A Microsoft Reserved Partition foi reformatada mas não afeta o Windows.

**Mitigação futura:**  
Sempre executar `lsblk` e `sudo parted -l` antes de qualquer operação de disco.

---

### 3. Swap ativo após reboot — kubelet recusou iniciar

**Severidade:** Média  
**Impacto:** kubelet não iniciou, `kubeadm init` falhou

**O que aconteceu:**  
O `swapoff -a` foi executado mas o `/etc/fstab` não foi corretamente modificado. Após reboot, swap voltou ativo.

**Solução aplicada:**  
```bash
sudo swapoff -a
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
```

**Mitigação futura:**  
Sempre verificar `free -h` mostrando `Swap: 0B` antes do `kubeadm init`.

---

### 4. Superblock corrompido no `nvme1n1p2`

**Severidade:** Média  
**Impacto:** Disco secundário inacessível, dados do containerd perdidos

**O que aconteceu:**  
Após redimensionar a partição NTFS, o superblock da nova partição ext4 ficou corrompido.

**Solução aplicada:**  
```bash
sudo mkfs.ext4 -F /dev/nvme1n1p2
```

**Mitigação futura:**  
Usar `fsck` após criar partição ext4. Não redimensionar NTFS com Windows ativo.

---

### 5. Containerd usando disco principal (disk-pressure)

**Severidade:** Média  
**Impacto:** Pods não agendados — node em `disk-pressure`

**O que aconteceu:**  
Containerd armazena imagens em `/var/lib/containerd` (partição `/` de 29GB). Após baixar imagens do control plane, chegou a 87% de uso.

**Solução aplicada:**  
```bash
sudo systemctl stop kubelet containerd
sudo mv /var/lib/containerd /var/lib/rancher/containerd/data
sudo ln -s /var/lib/rancher/containerd/data /var/lib/containerd
sudo systemctl start containerd kubelet
```

**Mitigação futura:**  
Criar symlink **antes** do `kubeadm init`.

---

### 6. Vault em modo dev — secrets perdidos no reboot

**Severidade:** Média  
**Impacto:** Todos os secrets perdidos após restart do pod vault-0

**O que aconteceu:**  
Vault instalado com `dev.enabled=true` armazena secrets em memória. Ao reiniciar o pod, todos os secrets eram apagados.

**Solução aplicada:**  
Reinstalação com modo standalone + Raft storage + PersistentVolume no disco secundário.

**Mitigação futura:**  
Nunca usar modo dev em ambiente com dados reais. Usar Raft desde o início.

---

### 7. Vault sealed após reboot — intervenção manual necessária

**Severidade:** Baixa  
**Impacto:** Vault inacessível após cada reboot até unseal manual

**O que aconteceu:**  
Comportamento esperado do Vault — após restart do pod, fica em estado sealed por segurança.

**Solução aplicada:**  
Script de auto-unseal via systemd lendo a unseal key de arquivo protegido `/etc/vault/unseal-key`.

**Mitigação futura:**  
Já mitigado. Para produção, considerar AWS KMS ou Google Cloud KMS.

---

### 8. ArgoCD — downtime durante updates (Recreate strategy)

**Severidade:** Baixa  
**Impacto:** ~30 segundos de downtime do Vault durante deploys

**O que aconteceu:**  
O PersistentVolume do Vault usa `ReadWriteOnce` — apenas um pod pode montar por vez. O ArgoCD não consegue fazer rolling update, usando Recreate: mata o pod antigo antes de subir o novo.

**Causa raiz:**  
Single-node com PV local `ReadWriteOnce` não suporta dois pods simultâneos no mesmo volume.

**Solução aplicada:**  
Aceito para homelab. O auto-unseal garante que o Vault volta automaticamente após o deploy.

**Mitigação futura:**  
Para zero downtime: usar NFS (`ReadWriteMany`) ou dois discos com replicação. Fora do escopo atual.

---

## Lições aprendidas

| Lição | Ação |
|-------|------|
| IP fixo é pré-requisito do k8s | Reservar DHCP antes de tudo |
| `swapoff` não persiste | Verificar `free -h` antes do `kubeadm init` |
| Nomes de disco são confusos | Usar `lsblk` e anotar antes de qualquer operação |
| Partição `/` pequena não serve para k8s | Mover containerd antes do init |
| Vault dev mode perde dados | Usar Raft desde o início |
| Vault sealed após reboot | Configurar auto-unseal |
| ReadWriteOnce causa downtime | Aceito para homelab, NFS para produção |

---

## Estado final do ambiente

| Componente | Status | Detalhe |
|------------|--------|---------|
| Wake-on-LAN | ✅ | `enp5s0`, magic packet via RPi |
| RPi Zero W — painel Flask | ✅ | `192.168.15.12:5000`, systemd |
| Cloudflare Tunnel | ✅ | `panel.areis-solution.com`, `argocd.areis-solution.com` |
| i9 — Ubuntu 24.04 | ✅ | IP fixo `192.168.15.14` |
| Kubernetes v1.32.13 | ✅ | kubeadm, single-node |
| CNI | ✅ | Flannel `10.244.0.0/16` |
| Helm v3.21.0 | ✅ | `/usr/local/bin/helm` |
| Disco secundário | ✅ | `nvme1n1p2` → `/var/lib/rancher` (526GB) |
| Vault | ✅ | Raft storage + auto-unseal |
| ArgoCD | ✅ | GitOps monitorando `k8s/vault/` |
| Agente | ✅ | Registra IP e serviços no painel |
| Prometheus + Grafana | ⏳ | Próximo passo |
| GitHub Actions | ⏳ | Próximo passo |
| Terraform | ⏳ | Próximo passo |
