# Post Mortem — Setup do Cluster Kubernetes
**Data:** 05–13 de Junho de 2026  
**Ambiente:** Ubuntu 24.04, i9 11ª geração, 32GB RAM, GTX 1660, dual SSD

---

## Resumo

Setup completo de um cluster Kubernetes single-node com Wake-on-LAN, painel de controle no Raspberry Pi Zero W, Vault com auto-unseal, ArgoCD GitOps, Prometheus + Grafana com dashboards versionados, GitHub Actions, Terraform e o primeiro game server (Palworld) com monitoramento integrado ao painel. Processo de ~8 dias com os incidentes documentados abaixo.

---

## Incidentes

### 1. IP do servidor mudou após reboot
**Severidade:** Alta — cluster inacessível  
O i9 estava com IP dinâmico. Após reboot, mudou de `.13` para `.14`, invalidando o certificado TLS do k8s.  
**Solução:** Reserva DHCP por MAC + `kubeadm reset` + `init` com IP correto.  
**Mitigação:** Fixar IPs antes de instalar o k8s.

### 2. Disco errado formatado
**Severidade:** Alta  
Confusão entre `nvme0n1` e `nvme1n1` formatou a Microsoft Reserved Partition.  
**Solução:** Corrigir fstab, montar disco correto.  
**Mitigação:** Sempre `lsblk` e `parted -l` antes de operar discos.

### 3. Swap ativo após reboot
**Severidade:** Média — kubelet não iniciou  
**Solução:** `swapoff -a` + comentar swap no fstab.  
**Mitigação:** Verificar `free -h` antes do `kubeadm init`.

### 4. Superblock corrompido no nvme1n1p2
**Severidade:** Média  
**Solução:** `mkfs.ext4 -F /dev/nvme1n1p2`.  
**Mitigação:** Não redimensionar NTFS com Windows ativo.

### 5. Containerd no disco principal (disk-pressure)
**Severidade:** Média  
Partição `/` de 29GB encheu com imagens.  
**Solução:** Mover containerd para disco secundário via symlink.  
**Mitigação:** Criar symlink antes do `kubeadm init`.

### 6. Vault dev mode — secrets perdidos
**Severidade:** Média  
Modo dev armazena em memória; reboot apagava tudo.  
**Solução:** Reinstalar com Raft + PV persistente.  
**Mitigação:** Nunca usar dev mode com dados reais.

### 7. Vault sealed após reboot
**Severidade:** Baixa  
**Solução:** Auto-unseal via systemd lendo chave de `/etc/vault/unseal-key`.  
**Mitigação:** Mitigado. Produção: AWS/GCP KMS.

### 8. ArgoCD — downtime em updates (Recreate)
**Severidade:** Baixa  
PV ReadWriteOnce não permite rolling update (~30s downtime).  
**Solução:** Aceito para homelab; auto-unseal recupera o Vault.  
**Mitigação:** NFS (ReadWriteMany) para zero downtime.

### 9. Prometheus PVC pendente — StorageClass inexistente
**Severidade:** Média  
`local-storage` era usada como string mas não existia como recurso.  
**Solução:** Criar StorageClass explícita + PV do Prometheus.  
**Mitigação:** Criar StorageClass como recurso antes de PVs que a referenciam.

### 10. GitHub Actions — PAT sem escopo workflow
**Severidade:** Baixa  
Push do workflow rejeitado por falta do escopo `workflow` no PAT.  
**Solução:** Novo PAT com `repo` + `workflow`.  
**Mitigação:** Incluir `workflow` ao gerar PATs para repos com CI/CD.

### 11. GitHub Actions — kubeconform validando Helm values
**Severidade:** Baixa  
`values.yaml` (sem `kind:`) falhava na validação.  
**Solução:** Excluir `values.yaml` do find do kubeconform.  
**Mitigação:** Manter Helm values fora da validação de manifestos.

### 12. Cooler/luzes ligados após shutdown (falso alarme)
**Severidade:** Nenhuma (comportamento esperado)  
Após `shutdown now`, cooler e RGB continuaram ligados, aparentando freeze. O log confirmou que o SO desligou corretamente (`Reached target poweroff.target`).  
**Causa:** O `DeepSx Enabled in S5` (necessário para WoL) mantém energia residual na placa, mantendo cooler/RGB ativos. É o que permite a NIC escutar o magic packet.  
**Solução:** Nenhuma necessária — WoL funciona normalmente. Confirmado ligando/desligando pelo painel.

### 13. Palworld REST API inacessível do RPi
**Severidade:** Baixa  
O painel não exibia métricas do Palworld. A REST API (porta 8212) era interna ao pod, sem NodePort.  
**Causa:** Service expunha só as portas de jogo (8211/27015), não a 8212 da API. Faltava também a env `REST_API_ENABLED=true`.  
**Solução:** Adicionar `containerPort: 8212` e env `REST_API_ENABLED`/`REST_API_PORT` no deployment, e NodePort `30212/TCP` no service.  
**Mitigação:** Ao integrar APIs de game servers ao painel, expor a porta da API como NodePort desde o início.

---

## Lições aprendidas

| Lição | Ação |
|-------|------|
| IP fixo é pré-requisito do k8s | Reservar DHCP antes de tudo |
| `swapoff` não persiste | Verificar `free -h` antes do init |
| Nomes de disco confundem | `lsblk` antes de qualquer operação |
| Partição `/` pequena | Mover containerd antes do init |
| Vault dev perde dados | Usar Raft desde o início |
| Vault sealed após reboot | Auto-unseal |
| ReadWriteOnce = downtime | Aceito em homelab, NFS p/ produção |
| StorageClass deve existir | Criar como recurso antes dos PVs |
| PAT precisa de workflow | Incluir escopo ao criar token |
| kubeconform vs Helm values | Excluir values.yaml |
| S5 mantém energia residual | Normal para WoL, não é freeze |
| API de game server | Expor porta como NodePort p/ painel |

---

## Estado final do ambiente

| Componente | Status | Detalhe |
|------------|--------|---------|
| Wake-on-LAN | ✅ | `enp5s0`, magic packet via RPi |
| RPi — painel Flask | ✅ | WoL + desligar remoto + status Palworld |
| Cloudflare Tunnel | ✅ | panel, grafana, argocd.areis-solution.com |
| Kubernetes v1.32.13 | ✅ | kubeadm, single-node |
| Vault | ✅ | Raft + auto-unseal |
| ArgoCD | ✅ | GitOps |
| Prometheus + Grafana | ✅ | StorageClass local-storage + dashboards versionados |
| GitHub Actions | ✅ | Valida manifestos a cada push |
| Terraform | ✅ | Gerencia StorageClass |
| Palworld | ✅ | PvE 8 players, REST API integrada ao painel |
| Desligamento remoto | ✅ | Botão no painel via SSH |
