# 🚨 RUNBOOK — Disaster Recovery (perdi tudo, reconstruir do zero)

Documento de EMERGENCIA. Se o i9 morreu / disco perdido / cluster irrecuperavel,
siga esta ordem EXATA. Tempo estimado: 3-5h (maioria e espera).
RTO ~4h | RPO ~24h (backup diario)

## INVENTARIO — onde estao as chaves (confirme ANTES)
- [ ] Unseal key do Vault: ver Bitwarden
- [ ] Root token do Vault: ver Bitwarden (ou gera novo no init)
- [ ] Senha do restic (t******1n): ver Bitwarden — SEM ELA NAO HA RESTORE
- [ ] rclone client_id/secret: Google Cloud Console (projeto rclone-backup)
- [ ] Senha admin Grafana: secret monitoring-grafana (keys admin-user/password)
- [ ] Repo: github.com/andre-reis-hub/wol-rpi-k8s

## FASE 1 — Sistema base (ver GUIA-INSTALACAO-DO-ZERO.md + GUIA-PARTE0-LVM.md)
- [ ] Ubuntu Desktop 24.04, LVM root 150GB, hostname andre-reis-hm570
- [ ] IP fixo 192.168.15.14 + openssh-server
- [ ] Disco 526GB por UUID em /var/lib/rancher
- [ ] GRUB: nvidia.NVreg_EnableGpuFirmware=0 pcie_port_pm=off pcie_aspm.policy=performance
      (NAO usar pcie_aspm=off — tira video). Ver docs/operacao/gpu-d3cold-note.md
- [ ] swapoff -a + comentar no fstab

## FASE 2 — Kubernetes (ver GUIA-INSTALACAO-DO-ZERO.md FASE 2)
- [ ] modules + sysctl ; containerd data-root em /var/lib/rancher/containerd
- [ ] kubeadm/kubelet/kubectl v1.32 (hold)
- [ ] kubeadm init --pod-network-cidr=10.244.0.0/16 + kubeconfig + remover taint
- [ ] Flannel ; node Ready
- [ ] criar pastas /var/lib/rancher/{vault,prometheus,loki,palworld,abiotic-factor,valheim,containerd}
      + chown 1000:1000 nos saves, 10001:10001 no loki

## FASE 3 — Clone + infra
- [ ] git clone repo em ~/Documents/wol-rpi-k8s
- [ ] StorageClass/PVs ; ArgoCD ; kube-prometheus-stack + Loki
- [ ] metrics-server + patch --kubelet-insecure-tls (ver docs/operacao/metrics-server-note.md)
- [ ] Config do Grafana embed+login (ver docs/operacao/grafana-config.md)
- [ ] kubectl apply nos jogos (k8s/games/*) e RBAC (k8s/rbac/rbac.yaml)
- [ ] Dashboards extra (k8s/monitoring/dashboards-extra/): finops, gamer, recursos

## FASE 4 — Vault (ver vault-secrets.md)
- [ ] Helm install Vault + Agent Injector
- [ ] vault operator init -key-shares=1 -key-threshold=1  >>> ANOTAR key+token no Bitwarden <<<
- [ ] vault operator unseal <key>
- [ ] atualizar /etc/vault/unseal-key + restart vault-unseal.service (auto-unseal)
- [ ] VT=<root>: secrets enable -path=wol -version=2 kv ; auth enable kubernetes ;
      write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc:443
- [ ] add-game-secret.sh para palworld/abiotic-factor/valheim (senha ver Bitwarden)
- [ ] wol/backup (restic-password) + wol/rclone (rclone-conf-b64) + policy/role backup

## FASE 5 — Restore dos saves (ver GUIA-RESTORE.md)
- [ ] rclone config (client_id proprio) + autorizar
- [ ] export RESTIC_PASSWORD='<ver Bitwarden>'
- [ ] restic -o rclone.connections=1 -r rclone:gdrive:wol-backups snapshots
- [ ] restic -o rclone.connections=1 -r rclone:gdrive:wol-backups restore latest --target /tmp/restore
- [ ] cp -a /tmp/restore/data/*/ para /var/lib/rancher/* (jogos DESLIGADOS)
      + chown -R 1000:1000

## FASE 6 — Painel + rede
- [ ] RPi sobrevive (nao afetado). Atualizar K8S_TOKEN + k8s-ca.crt no .env (cluster novo)
- [ ] systemctl restart wol-panel
- [ ] cloudflared rodando (panel/grafana/argocd)
- [ ] port forwards: 30211 Palworld, 7777 Abiotic, 30456/30457 Valheim

## FASE 7 — Validacao
- [ ] nodes Ready ; pods Running ; Vault unsealed
- [ ] jogos ligam + aceitam senha ; saves restaurados (conferir mundo no jogo)
- [ ] backup manual dispara e completa ; Grafana+ArgoCD acessiveis
- [ ] painel: iframes carregam (embed) E login admin no Grafana funciona
- [ ] kubectl top nodes funciona (metrics-server)

## ORDEM RESUMIDA
1.Ubuntu+LVM+GRUB 2.k8s 3.clone+infra+metrics+grafana 4.Vault 5.restore 6.painel 7.validar
PRIORIDADE: a senha do restic. Sem ela nao ha restore. BITWARDEN!
