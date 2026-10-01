# Runbook — Upgrade Kubernetes v1.32 → v1.37 (node único)

> Este arquivo nasceu como **plano**, escrito antes do primeiro salto. Conforme cada
> salto for executado, preenche a seção dele com data, saídas relevantes e qualquer
> surpresa — ele vira o registro final a ser commitado no `wol-rpi-k8s` no fim.

## Contexto e decisões tomadas

- Cluster: 1 node só (`andre-reis-hm570`), control-plane + workloads juntos.
- Estado de partida confirmado: `kubeadm/kubelet v1.32.13`, `containerd 2.2.1`,
  Ubuntu 24.04.5, `/etc/kubernetes` e `/var/lib/etcd` no padrão kubeadm.
- Alvo: `v1.37.1` (confirmado via `https://dl.k8s.io/release/stable.txt` — não usar
  `cdn.dl.k8s.io`, não resolve nesta rede).
- **Drain completo a cada salto** (decisão do André — aceita a janela de
  indisponibilidade de alguns minutos por salto, em troca de seguir o processo
  oficial à risca).
- Saltos obrigatórios, um minor por vez: `1.32 → 1.33 → 1.34 → 1.35 → 1.36 → 1.37`.
  O kubeadm não permite pular minor.
- Motivo de ter esperado: Calico atual (não a versão provisória 3.29.7 que tínhamos
  cotado para o 1.32) só entra **depois** do Kubernetes estar no alvo — ver seção
  final.
- Backups já confirmados antes de começar: backup automático dos jogos (`wol-backup`)
  rodando normalmente, ESO/Vault saudáveis, `kpack-builds` isolado por quota e
  Pod Security (não por rede ainda).

## Antes do salto 1 — rede de segurança (fazer uma vez só)

```bash
# snapshot do etcd — a rede de segurança real deste runbook inteiro
sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save ~/etcd-snapshot-pre-upgrade-$(date +%Y%m%d).db

# confirma que o snapshot é válido e tem tamanho razoável
sudo ETCDCTL_API=3 etcdctl --write-out=table \
  snapshot status ~/etcd-snapshot-pre-upgrade-$(date +%Y%m%d).db

# backup dos manifests estáticos e certs (rápido, sem etcdctl)
sudo tar czf ~/etc-kubernetes-pre-upgrade-$(date +%Y%m%d).tar.gz /etc/kubernetes
ls -lh ~/etcd-snapshot-pre-upgrade-*.db ~/etc-kubernetes-pre-upgrade-*.tar.gz
```

Guarda os dois arquivos fora do node também (scp pro RPi ou pro Termux) — se o disco
raiz tiver problema, o snapshot local não adianta.

## Procedimento genérico de cada salto (repete 5x)

Troca `<MINOR>` pelo alvo do salto (ex.: `1.33`, depois `1.34`, etc.) e `<NODE>` pelo
nome real do node (`andre-reis-hm570`).

```bash
# 1. Troca o repositório apt para o minor alvo
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v<MINOR>/deb/ /" \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list
curl -fsSL https://pkgs.k8s.io/core:/stable:/v<MINOR>/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
sudo apt-get update

# 2. Descobre o patch mais recente disponível desse minor (não cravar número)
apt-cache madison kubeadm | head -5

# 3. Atualiza o kubeadm primeiro
sudo apt-mark unhold kubeadm
sudo apt-get install -y kubeadm='<MINOR>.X-*'   # X = patch visto no passo 2
sudo apt-mark hold kubeadm
kubeadm version

# 4. Vê o plano antes de aplicar — lê a saída com atenção (APIs removidas etc.)
sudo kubeadm upgrade plan

# 5. Drain (único node — os pods ficam Pending até o uncordon do passo 8)
kubectl drain <NODE> --ignore-daemonsets --delete-emptydir-data --force

# 6. Aplica o upgrade do control plane
sudo kubeadm upgrade apply v<MINOR>.X

# 7. Atualiza kubelet e kubectl, reinicia o kubelet
sudo apt-mark unhold kubelet kubectl
sudo apt-get install -y kubelet='<MINOR>.X-*' kubectl='<MINOR>.X-*'
sudo apt-mark hold kubelet kubectl
sudo systemctl daemon-reload
sudo systemctl restart kubelet

# 8. Libera o node de novo
kubectl uncordon <NODE>
```

## Checagem de saúde — roda depois de CADA salto, antes de seguir pro próximo

```bash
kubectl get nodes -o wide                      # Ready, versão nova aparecendo
kubectl get pods -A | grep -v -E 'Running|Completed'   # vazio = bom sinal
kubectl get --raw /metrics | grep '^apiserver_requested_deprecated_apis'  # vazio = bom
kubectl -n launchpad get pods                   # launchpad voltou
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.15.14:30080/healthz  # 200
kubectl -n monitoring get pods                  # Grafana/Prometheus/Loki voltaram
kubectl -n vault get pods                       # Vault voltou
kubectl -n kpack-builds get pods                # kpack ok (se algum build em andamento)
helm list -A                                    # releases ainda deployed
```

Só avança pro próximo salto se essa lista vier limpa. Se algo não normalizar em
alguns minutos, para e investiga antes de continuar — não empilha salto em cima de
problema não resolvido.

### Registro de cada salto (preencher ao vivo)

| Salto | Data | Versão aplicada | Saúde pós-salto | Observações |
|---|---|---|---|---|
| 1.32 → 1.33 | | | | |
| 1.33 → 1.34 | | | | |
| 1.34 → 1.35 | | | | |
| 1.35 → 1.36 | | | | |
| 1.36 → 1.37 | | | | |

## Rollback (se um salto específico quebrar)

Não existe downgrade de minor via kubeadm. Se o cluster ficar instável depois de um
`kubeadm upgrade apply`:

```bash
# restaura os manifests estáticos e certs do backup do salto anterior
sudo systemctl stop kubelet
sudo tar xzf ~/etc-kubernetes-pre-upgrade-<data>.tar.gz -C /

# se precisar restaurar o estado do etcd também (último recurso)
sudo systemctl stop etcd 2>/dev/null || true
sudo ETCDCTL_API=3 etcdctl snapshot restore ~/etcd-snapshot-pre-upgrade-<data>.db \
  --data-dir /var/lib/etcd-restored
# depois: trocar o data-dir no manifest do etcd para /var/lib/etcd-restored e
# reiniciar — este passo é delicado, ler a documentação oficial de disaster
# recovery do etcd antes de rodar em produção real.

sudo systemctl start kubelet
```

Testar a restauração do snapshot (passo "`snapshot status`" acima) é o que dá
confiança de que, se precisar, o restore funciona — não espera precisar dele pra
descobrir que o arquivo está corrompido.

## Depois do 5º salto (cluster em v1.37.x) — ATUALIZAR o Calico, não usar o 3.29.7

O Canal `v3.29.7` que já baixamos (`~/canal-3.29.yaml`) foi escolhido só para
compatibilidade com o `v1.32` antigo — **não usar ele no cluster em 1.37**.

Antes de instalar qualquer coisa de rede, repetir a mesma checagem que fizemos para
o kpack: descobrir a versão real, não confiar em busca/memória.

```bash
# versão mais recente do Calico Open Source, direto do GitHub
curl -s https://api.github.com/repos/projectcalico/calico/releases/latest \
  | grep -E '"tag_name"|"html_url"'

# confirma na doc oficial dessa versão se v1.37 está na faixa suportada
# (Calico segue política N-2: cobre a versão atual do k8s + as duas anteriores —
# se a release mais nova do Calico ainda não cobrir 1.37, pode ser preciso
# esperar um patch novo do Calico sair, ou usar a build mais recente mesmo assim
# e validar com o teste de enforcement abaixo)
```

Depois de confirmada a versão, repete o procedimento de migração Flannel→Canal que
já está desenhado (parar o `kube-flannel` sem apagar, aplicar o canal.yaml da
versão certa, reboot, validar com `cali*` interfaces existindo e `cni0` sumindo,
e o teste de `NetworkPolicy deny-all` num namespace descartável).

## Depois de tudo — o que fica pro NetworkPolicy do kpack-builds

Só depois do Calico confirmado aplicando policy de verdade (o teste `deny-all`
bloqueando) é que a `NetworkPolicy` real do `kpack-builds` deve ser escrita — com:

- egress liberado para DNS (CoreDNS, `10.96.0.10:53`)
- egress liberado para internet (clonar repos, publicar imagens) — `0.0.0.0/0`
  **exceto** a faixa da LAN (`192.168.15.0/24`) e a faixa de pods do cluster
  (`10.244.0.0/16`), para impedir acesso lateral a Vault/launchpad-db/outros
  namespaces
- ingress só do Ingress controller, nada mais

Isso fecha a Fase 1 do kpack de verdade — hoje ela está isolada em recursos, não
em rede.
