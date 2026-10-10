# Tentativa de migração Flannel → Calico (2026-10-10) — registro e plano revisado

> **Resultado: a migração oficial NÃO funciona em cluster de um node só. Foi revertida.**
> Cluster restaurado ao estado anterior (Flannel como rede). Este documento substitui
> `plano-migracao-flannel-para-calico.md` (que descrevia o caminho que falhou) e traz o
> plano revisado (Canal), **ainda não executado**.

## O que foi tentado

Migração ao vivo do guia oficial do Calico v3.33.0 (`flannel-migration/calico.yaml` +
`migration-job.yaml`). Pré-requisitos atendidos: Flannel v0.28.5, backend VXLAN,
DaemonSet, sem DirectRouting, pod CIDR `10.244.0.0/16`.

## Linha do tempo (horário de Brasília)

| Hora | Evento |
|---|---|
| 12:25 | PDB do banco desligado (`spec.enablePDB: false` no Cluster do CNPG). |
| 12:34 | `calico.yaml` aplicado. Sem erros; `calico-node` com 0 pods (só roda em node com o label de migração, confirmado no arquivo). |
| 12:36 | `migration-job.yaml` aplicado. O controlador marcou o node (`node-flannel-migration-in-progress=true`), bloqueou-o e esvaziou-o. **Expulsou também o próprio pod.** |
| 12:36–12:51 | Pod substituto do controlador `Pending` (`1 node(s) were unschedulable`). Vault, banco, launchpad, Prometheus etc. `Pending`. |
| 12:45 | Diagnóstico: labels do node (`in-progress=true`, `network-during-migration=flannel`) e evento `FailedScheduling`. |
| 12:49 | Job apagado (o Flannel seguia `1/1 Running`). |
| 12:51 | `kubectl uncordon`; pods voltaram sozinhos. |
| 12:54 | `vault-0` voltou **selado**; `sudo systemctl restart vault-unseal.service` abriu (`Sealed false`, `HA Mode active`). `healthz` do launchpad 200. |
| 12:56 | PDB do banco reativado; `nodeSelector` do `kube-flannel-ds` removido (`null`). |
| 12:58 | Labels de migração removidos do node. |
| 13:00 | Objetos do Calico e do controlador removidos; 0 pods e 0 CRDs de Calico. |

Indisponibilidade de aplicações: ~12:36 a ~12:54 (cerca de 18 min). **Sem perda de dados.**

## Por que falhou (verificado no código v3.33.0)

- `Run` do controlador reinicia **sempre do começo**; o estado é lido dos labels do node.
- `setupCalicoNetworkForNode` executa, nesta ordem: label `in-progress`, **`Drain`**,
  label `network=none`, remoção do Flannel (pod `remove-flannel`), deleção dos pods sem
  hostNetwork, label `network=calico`, espera do `calico-node`, verificação do `vxlan.calico`,
  **`Uncordon`**, remoção do label `in-progress`.
- O `Drain` roda incondicionalmente e expulsa o pod do controlador (um pod de Job). O pod
  substituto só tolera `CriticalAddonsOnly` (não o bloqueio de node), então não agenda.
- Em cluster com vários nodes o substituto vai para outro node e retoma. Com **um node só**
  não há outro, e liberar o node manualmente reiniciaria o ciclo (novo `Drain`).
- A doc oficial não trata de cluster de um node. Os migradores de IPAM e de rede ficam em
  `kube-controllers/pkg/controllers/flannelmigration/`.

## Lições

1. `kubectl get pods -A | grep -v -E 'Running|Completed'` **esconde** pods `Running` com `0/1`
   (ex.: Vault selado). Usar também `grep -E ' 0/[0-9]+ '`.
2. O `vault-unseal.service` é de execução única no boot; **funciona** como recuperação
   manual depois de um reinício do pod (`sudo systemctl restart vault-unseal.service`).
3. Ao testar com um componente que reage a si mesmo (esvazia o node), pensar no que acontece
   quando ele se expulsa.
4. Manter o PDB desligado só durante a janela e reativar logo depois.
5. Ler o código do componente antes da janela, não durante.

## Plano revisado: Canal (Flannel para a rede, Calico só para a política)

**Status: não executado.** É o caminho documentado do Calico para clusters Flannel
(`canal.yaml` da tag `v3.33.0`). Não usa controlador de migração e **não faz drain**:
a rede continua Flannel VXLAN e o Calico (Felix) aplica as NetworkPolicy.

### Premissas a confirmar (não verificadas)

- Se pods já existentes passam a ser filtrados sem reiniciar, ou só depois de recriados.
- O nome do arquivo CNI que o Canal grava e se o `10-flannel.conflist` antigo conflita.
- Que o Canal reaproveita a mesma sub-rede do node (o Flannel usa `node.spec.podCIDR`).
- Que o kube-controller-manager tem `--allocate-node-cidrs=true` e `--cluster-cidr`.

### Antes (no dia)

- [ ] Jogos desligados, tmux aberto, chaves do Vault à mão, backups novos (etcd, tar de `/etc/kubernetes`, dump do banco).
- [ ] `sudo grep -E 'cluster-cidr|allocate-node-cidrs' /etc/kubernetes/manifests/kube-controller-manager.yaml`
- [ ] **Backup dos objetos do Flannel** (para o rollback):
  `kubectl -n kube-flannel get ds,cm,sa -o yaml > ~/flannel-objetos-backup.yaml`
  e `kubectl get clusterrole,clusterrolebinding -o yaml | grep -i flannel` para conferir os RBAC.
- [ ] `ls /etc/cni/net.d` e `ip -br link` guardados.
- [ ] Baixar `canal.yaml` da `v3.33.0` para arquivo local e inspecionar
  (`grep -n -E 'kind: DaemonSet|image:|10.244|CNI_CONF_NAME|FELIX_|Backend'`).
  Comparar rede/porta/VNI com o `kube-flannel-cfg` atual (`10.244.0.0/16`, vxlan, `EnableNFTables: false`).

### Execução (a definir em detalhe depois da inspeção)

1. Apagar o DaemonSet do Flannel (os pods existentes mantêm a rede).
2. Aplicar o `canal.yaml` local; esperar o pod do `canal` ficar pronto.
3. Conferir `ip -br link` (interface `flannel.1`), `ls /etc/cni/net.d` e o `healthz` do launchpad.
4. Teste de enforcement com `deny-all` num namespace descartável.
5. Se pods antigos não forem filtrados: reiniciar por namespace ou reiniciar o i9 com jogos desligados.

### Rollback

Apagar o Canal, reaplicar `~/flannel-objetos-backup.yaml`, remover o conflist do Canal de `/etc/cni/net.d`.

### Alternativa mais leve

`kube-router` só no modo firewall (NetworkPolicy), sem roteamento nem service proxy, sem CRDs.
Menor pegada, mas não é o Calico.

## Estado de partida desta tentativa (referência)

- Flannel v0.28.5 (VXLAN, `10.244.0.0/16`), Kubernetes 1.37.1, Vault shamir (threshold 1).
- Injeção do Vault Agent verificada **funcionando** em Job manual (`teste-injecao-1`) hoje às 11:37;
  repetir após qualquer mudança de rede.

## Em aberto (independentes da rede)

1. **`wol-backup` falha de forma intermitente**: o webhook do injetor recebe a requisição,
   não registra erro, e o pod às vezes sai sem init container (annotations corretas, `failurePolicy: Ignore`
   global). Não depende do Vault estar aberto (falhou com ele aberto há 3 h). Causa raiz desconhecida.
   Mitigação: alerta de Job falhado; qualquer `failurePolicy: Fail` precisa ser restrito ao namespace `backup`.
2. **Banco do launchpad sem backup** (nenhum `Backup`/`ScheduledBackup` no CNPG). Prioridade alta.
3. `RUNBOOK-DR.md` desatualizado (k8s 1.32, Flannel; não cobre launchpad, CNPG, ESO, kpack, vigia).
4. Jobs `wol-backup` falhados antigos ainda no cluster (o vigia já foi enganado por um Job fantasma).
