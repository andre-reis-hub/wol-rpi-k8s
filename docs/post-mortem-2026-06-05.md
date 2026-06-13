# Post Mortem — Setup do Cluster Kubernetes
**Data:** 05–13 de Junho de 2026  
**Ambiente:** Ubuntu 24.04, i9 11ª geração, 32GB RAM, dual SSD

---

## Resumo

Setup completo de um cluster Kubernetes single-node com Wake-on-LAN, particionamento de disco secundário, painel de controle no Raspberry Pi Zero W, Vault com auto-unseal, ArgoCD GitOps, Prometheus + Grafana com dashboards versionados e GitHub Actions para validação de manifestos. O processo levou aproximadamente 8 dias com múltiplos incidentes documentados abaixo.

---

## Incidentes

### 1. IP do servidor mudou após reboot

**Severidade:** Alta  
**Impacto:** Cluster Kubernetes completamente inacessível

**O que aconteceu:**  
O servidor i9 estava com IP dinâmico via DHCP. Após um reboot, o IP mudou de `192.168.15.13` para `192.168.15.14`. O certificado TLS do Kubernetes havia sido gerado para o IP antigo, tornando toda comunicação com o API server impossível.

**Solução aplicada:**  
Reserva DHCP por MAC no roteador + `kubeadm reset` + `kubeadm init` com IP correto.

**Mitigação futura:**  
Sempre fixar IPs via reserva DHCP **antes** de instalar o k8s.

---

### 2. Disco errado formatado (`nvme0n1p2`)

**Severidade:** Alta  
**Impacto:** Microsoft Reserved Partition do Windows formatada (16MB)

**Solução aplicada:**  
Corrigido o `/etc/fstab` e montado o disco correto. A Microsoft Reserved Partition foi reformatada mas não afeta o Windows.

**Mitigação futura:**  
Sempre executar `lsblk` e `sudo parted -l` antes de qualquer operação de disco.

---

### 3. Swap ativo após reboot — kubelet recusou iniciar

**Severidade:** Média  
**Impacto:** kubelet não iniciou, `kubeadm init` falhou

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

**Solução aplicada:**  
Reinstalação com modo standalone + Raft storage + PersistentVolume no disco secundário.

**Mitigação futura:**  
Nunca usar modo dev em ambiente com dados reais. Usar Raft desde o início.

---

### 7. Vault sealed após reboot — intervenção manual necessária

**Severidade:** Baixa  
**Impacto:** Vault inacessível após cada reboot até unseal manual

**Solução aplicada:**  
Script de auto-unseal via systemd lendo a unseal key de arquivo protegido `/etc/vault/unseal-key`.

**Mitigação futura:**  
Já mitigado. Para produção, considerar AWS KMS ou Google Cloud KMS.

---

### 8. ArgoCD — downtime durante updates (Recreate strategy)

**Severidade:** Baixa  
**Impacto:** ~30 segundos de downtime do Vault durante deploys

**Causa raiz:**  
Single-node com PV local `ReadWriteOnce` não suporta dois pods simultâneos no mesmo volume.

**Solução aplicada:**  
Aceito para homelab. O auto-unseal garante que o Vault volta automaticamente após o deploy.

**Mitigação futura:**  
Para zero downtime: usar NFS (`ReadWriteMany`) ou dois discos com replicação. Fora do escopo atual.

---

### 9. Prometheus PVC pendente — StorageClass inexistente

**Severidade:** Média  
**Impacto:** Pod do Prometheus nunca foi criado, sem mensagem de erro óbvia

**O que aconteceu:**  
O Helm chart `kube-prometheus-stack` foi instalado referenciando `storageClassName: local-storage`, mas essa StorageClass nunca havia sido criada como recurso — apenas usada como string no PV manual do Vault. O Prometheus Operator reportou `storage class "local-storage" does not exist` apenas no `kubectl describe prometheus`, não no `get pods`.

**Causa raiz:**  
PVs locais (`local`) não precisam de StorageClass registrada para funcionar isoladamente, mas o `volumeClaimTemplate` do Prometheus exige que a StorageClass exista como objeto no cluster.

**Solução aplicada:**  
```bash
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-storage
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
EOF
```
Seguido da criação do PV `prometheus-pv` apontando para `/var/lib/rancher/prometheus`.

**Mitigação futura:**  
Sempre criar a StorageClass como recurso explícito antes de qualquer PV que a referencie. Validar com `kubectl get storageclass`.

---

### 10. GitHub Actions — push rejeitado por falta de escopo `workflow`

**Severidade:** Baixa  
**Impacto:** Push do primeiro workflow do GitHub Actions rejeitado

**O que aconteceu:**  
```
remote: refusing to allow a Personal Access Token to create or update
workflow `.github/workflows/validate-k8s.yml` without `workflow` scope
```

**Causa raiz:**  
O PAT (classic) usado para push tinha apenas o escopo `repo`. GitHub exige o escopo adicional `workflow` especificamente para criar/alterar arquivos em `.github/workflows/`.

**Solução aplicada:**  
Gerado novo PAT com escopos `repo` + `workflow`, atualizado via `git remote set-url`.

**Mitigação futura:**  
Ao gerar PAT para repositórios que terão CI/CD, sempre incluir o escopo `workflow` desde o início.

---

### 11. GitHub Actions — kubeconform validando arquivo Helm values

**Severidade:** Baixa  
**Impacto:** Workflow falhando com `Process completed with exit code 123`

**O que aconteceu:**  
O `kubeconform` tentou validar `k8s/vault/values.yaml` (arquivo de configuração do Helm, sem campo `kind:`) como se fosse um manifesto Kubernetes, retornando `missing 'kind' key`.

**Causa raiz:**  
O `find` do workflow buscava todo `*.yaml` em `k8s/`, sem diferenciar manifestos k8s de arquivos de values do Helm.

**Solução aplicada:**  
```yaml
find k8s -name '*.yaml' -not -path '*/dashboards/*' -not -name 'values.yaml' | xargs kubeconform -summary -ignore-missing-schemas
```

**Mitigação futura:**  
Ao adicionar novos charts Helm, manter os arquivos `values.yaml` fora da validação kubeconform ou movê-los para uma pasta dedicada (ex: `k8s/helm-values/`).

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
| StorageClass deve existir como recurso | Criar explicitamente antes de PVs que a referenciam |
| PAT precisa de `workflow` para Actions | Incluir escopo desde a criação do token |
| kubeconform não diferencia Helm values | Excluir `values.yaml` da validação |

---

## Estado final do ambiente

| Componente | Status | Detalhe |
|------------|--------|---------|
| Wake-on-LAN | ✅ | `enp5s0`, magic packet via RPi |
| RPi Zero W — painel Flask | ✅ | `192.168.15.12:5000`, systemd |
| Cloudflare Tunnel | ✅ | `panel`, `grafana`, `argocd`.areis-solution.com |
| i9 — Ubuntu 24.04 | ✅ | IP fixo `192.168.15.14` |
| Kubernetes v1.32.13 | ✅ | kubeadm, single-node |
| CNI | ✅ | Flannel `10.244.0.0/16` |
| Helm v3.21.0 | ✅ | `/usr/local/bin/helm` |
| Disco secundário | ✅ | `nvme1n1p2` → `/var/lib/rancher` (526GB) |
| Vault | ✅ | Raft storage + auto-unseal |
| ArgoCD | ✅ | GitOps monitorando `k8s/vault/` |
| Prometheus + Grafana | ✅ | StorageClass `local-storage`, PV dedicado |
| Dashboards versionados | ✅ | ConfigMap com sidecar do Grafana |
| GitHub Actions | ✅ | Valida manifestos k8s a cada push |
| Agente | ✅ | Registra IP e serviços no painel |
| Terraform | ⏳ | Próximo passo |
