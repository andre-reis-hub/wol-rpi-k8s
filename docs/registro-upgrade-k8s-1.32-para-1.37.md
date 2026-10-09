# Upgrade Kubernetes v1.32.13 → v1.37.1 (node único) — registro

> Concluído em **2026-10-09**, entre ~15:50 e ~18:50 (America/Sao_Paulo).
> Este documento substitui o `runbook-upgrade-k8s-1.32-para-1.37.md` (que era o
> **plano**, escrito antes do primeiro salto) com o que **de fato funcionou**.
> Onde algo é hipótese e não foi comprovado, está marcado como **(hipótese)**.

## Resultado

| Componente | Antes | Depois |
|---|---|---|
| Kubernetes (kubeadm/kubelet/kubectl) | 1.32.13 | **1.37.1** |
| etcd | 3.5.24 | **3.7.0** (versão de cluster e de storage migradas) |
| CoreDNS | 1.11.3 | **1.14.6** |
| containerd | 2.2.1 | 2.2.1 (inalterado) |

Estado final verificado:

- Node `andre-reis-hm570` em `Ready`, `v1.37.1`.
- `readyz` retornou `ok`; etcd com 0 restarts; kube-proxy `1/1 Running`, 0 restarts.
- Vault `Sealed: false` / `HA Mode: active`.
- launchpad `/healthz` → 200.
- Todos os releases Helm em `deployed`.
- `journalctl -u kubelet -p err --since "10 min ago"` → sem entradas.
- Únicos pods fora de `Running`: três pods antigos do `wol-backup` em `Error` (ver itens em aberto).

Cluster: 1 node (control-plane + workloads), kubeadm, Flannel (**sem** enforcement de
NetworkPolicy), Ubuntu 24.04, cgroup v2.

## Os cinco saltos

Um minor por vez — o kubeadm não permite pular.

| Salto | apply → kubelet | Versão | etcd | CoreDNS | Observações |
|---|---|---|---|---|---|
| 1.32 → 1.33 | 15:57 → 16:07 | 1.33.13 | 3.5.24 | 1.12.0 | Drain pulado (ver abaixo). A métrica `apiserver_requested_deprecated_apis` mostrou `v1 endpoints` — só aviso. |
| 1.33 → 1.34 | 16:42 → 16:48 | 1.34.12 | → 3.6.5 | 1.12.1 | `kubectl` recusou conexão por ~2 min após reiniciar o kubelet (static pods sendo recriados). |
| 1.34 → 1.35 | 17:13 → 17:18 | 1.35.9 | → 3.6.6 | 1.13.1 | Antes: confirmado `cgroup2fs` e containerd 2.2.1. |
| 1.35 → 1.36 | 17:48 → 17:54 | 1.36.5 | → 3.6.8 | 1.14.2 | kube-proxy reiniciou 2x com `too many open files`. Checados: kube-proxy mode `""`, 0 `gitRepo`, 0 `externalIPs`. |
| 1.36 → 1.37 | 18:42 → 18:46 | 1.37.1 | → 3.7.0 | 1.14.6 | kube-proxy com 0 restarts. |

## Procedimento que funcionou

Ordem de cada salto: **backups → repo apt do minor → kubeadm → `upgrade plan` →
`upgrade apply` → kubelet/kubectl → restart do kubelet → checagem de saúde.**

**Sem drain.** O PDB do CNPG `launchpad-db-primary` tem `ALLOWED DISRUPTIONS 0`
(min available 1) e, com um node só, não há para onde mover os pods — o drain
travaria. O plano original previa drain a cada salto; foi corrigido: `apply` direto.

Rodar o `apply` **dentro do tmux** (sessão SSH pelo celular pode cair).

`v1.XX` = minor alvo; `1.XX.Y` = patch visto no `apt-cache madison`.

```bash
# 1. Repo apt do minor alvo
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.XX/deb/ /" \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.XX/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg   # responder y se perguntar sobrescrever
sudo apt-get update

# 2. Patch disponível
apt-cache madison kubeadm | head -5

# 3. kubeadm
sudo apt-mark unhold kubeadm
sudo apt-get install -y kubeadm=1.XX.Y-1.1
sudo apt-mark hold kubeadm

# 4. Plano e apply (apply dentro do tmux)
sudo kubeadm upgrade plan
sudo kubeadm upgrade apply v1.XX.Y

# 5. kubelet e kubectl
sudo apt-mark unhold kubelet kubectl
sudo apt-get install -y kubelet=1.XX.Y-1.1 kubectl=1.XX.Y-1.1
sudo apt-mark hold kubelet kubectl
sudo systemctl daemon-reload
sudo systemctl restart kubelet
```

Rodar **um comando por vez**; colar vários de uma vez no terminal do celular engoliu
comandos mais de uma vez.

Depois do restart do kubelet, esperar o apiserver voltar (até ~2 min) antes de usar `kubectl`.

### Checagem de saúde (depois de CADA salto)

```bash
kubectl get nodes; kubectl get pods -A | grep -v -E 'Running|Completed'
kubectl -n vault exec vault-0 -- vault status | grep -E 'Sealed|HA Mode'
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.15.14:30080/healthz
kubectl -n kube-system get pods | grep kube-proxy
```

Observações:

- `vault status` **no host** falha (não há Vault em 127.0.0.1:8200) — usar `kubectl exec`.
- `vault-0` `Ready 1/1` **não** prova que está unsealed; conferir `Sealed: false`.

## Snapshot do etcd em imagem distroless

O pod do etcd não tem `sh`, `cat` nem `sha256sum`, e o host não tem `etcdctl`.
Método que funcionou (trocar `N` pelo número do salto):

```bash
kubectl -n kube-system exec etcd-andre-reis-hm570 -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save /var/lib/etcd/pre-saltoN.db

sudo cp /var/lib/etcd/pre-saltoN.db ~/etcd-snapshot-pre-saltoN.db
sudo chown andre-reis:andre-reis ~/etcd-snapshot-pre-saltoN.db
ls -lh ~/etcd-snapshot-pre-saltoN.db     # esperado: dono andre-reis, ~36M
# SÓ DEPOIS de conferir o ls acima:
sudo rm /var/lib/etcd/pre-saltoN.db

sudo tar czf ~/etc-kubernetes-pre-saltoN.tar.gz /etc/kubernetes
scp ~/etcd-snapshot-pre-saltoN.db ~/etc-kubernetes-pre-saltoN.tar.gz andre@192.168.15.12:~/
```

Erros a evitar (todos aconteceram):

- **Nomes de arquivo baseados em data**: houve colisão de nome e o snapshot correto
  foi apagado; foi regenerado. Usar `pre-saltoN`, e **nunca `rm` antes de confirmar** a cópia.
- Colar vários comandos de uma vez no terminal do celular.
- Esquecer o `scp` para fora do node.

O tar de `/etc/kubernetes` cresceu a cada salto (34K → 28M → 56M → 85M → 114M) porque
o `kubeadm upgrade apply` acumula backups em `/etc/kubernetes/tmp`.

No RPi (`~`) ficaram: `etcd-snapshot-final.db`, `etc-kubernetes-pre-upgrade-20261007.tar.gz`
e os pares `pre-salto2..5` (~36M cada snapshot + 28/56/85/114M os tars). Podem ser
apagados depois de alguns dias estáveis.

## Salto 5 (etcd 3.6.8 → 3.7.0)

- O kubeadm 1.37 empurra o etcd direto de 3.6.8 para 3.7.0. O PR do Kubespray e o
  anúncio do etcd 3.7 recomendam passar antes por 3.6.11 ou superior; o problema exato
  **não foi confirmado**, e o kubeadm 1.36 só oferece 3.6.8. Risco aceito conscientemente.
- Checagens antes do apply, todas limpas: `kubeadm-flags.env` vazio; só os 4 manifests
  padrão; `scheduling.k8s.io` apenas com `priorityclasses`; nenhum `eventRecordQPS`.
- Depois do apply, o log do etcd mostrou a versão do cluster indo de 3.6 para 3.7 e
  storage version 3.7.0.
- **Sem rollback fácil:** o kubeadm não faz downgrade de minor. O caminho seria restaurar o
  snapshot `pre-salto5`.

## Itens em aberto

1. **`wol-backup` falha às vezes** com `/vault/secrets/restic-password` e
   `rclone-conf-b64` ausentes. Causa provável **(hipótese)**: a injeção do Vault Agent
   não aconteceu. Precisa de alerta (ex.: `kube_job_status_failed`) e/ou esperar o Vault
   antes do Job rodar.
2. **kube-proxy `too many open files`** no salto 4. Aumentamos `fs.inotify.max_user_instances`
   de 128 para 1024 (`/etc/sysctl.d/99-inotify.conf`). **(hipótese não comprovada)** — o
   salto 5 não repetiu o erro, mas isso não prova a causa.
3. **etcd loga `rejected connection ... EOF` a cada 30 s** em 127.0.0.1:2379. Origem
   desconhecida (já descartado: não são as probes; a atribuição ao restart do apiserver
   também foi retirada).
4. **Repo apt da HashiCorp** com aviso de GPG (`NO_PUBKEY FC9CA96ACA026560`).
5. **Grafana:** o 1.37 remove algumas métricas do kubelet/apiserver (ex.:
   `container_tasks_state`, `container_cpu_load_average_10s`). Verificar se algum painel
   do kube-prometheus ficou vazio.
6. **Rede:** só Flannel, então **não há enforcement de NetworkPolicy** (o teste `deny-all`
   retornou 200). O `kpack-builds` está isolado apenas por quota e PodSecurity.
   Próximo passo: descobrir o Calico atual na hora de instalar, confirmar suporte ao 1.37
   (política N-2) e repetir o teste de enforcement. **Não usar** o `~/canal-3.29.yaml`
   baixado antes (era para o 1.32).

## Depois: Calico/Canal e NetworkPolicy do `kpack-builds`

Plano (ainda **não executado**):

1. Descobrir a release atual do Calico no GitHub e confirmar na doc dela a faixa de
   Kubernetes suportada.
2. Estacionar o `kube-flannel-ds` (patch de nodeSelector, sem apagar), aplicar o manifest
   do canal da versão certa, reiniciar com os jogos desligados.
3. Validar: interfaces `cali*` existem e `cni0` sumiu; repetir o teste `deny-all` num
   namespace descartável; manter rollback.
4. Só então escrever a NetworkPolicy real do `kpack-builds`:
   - egress para DNS (`10.96.0.10:53`);
   - egress para internet **exceto** `192.168.15.0/24` e `10.244.0.0/16`;
   - ingress apenas do ingress controller.
