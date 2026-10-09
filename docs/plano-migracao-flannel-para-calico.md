# Plano — migração Flannel → Calico v3.33.0 (node único)

> **Status: PLANO, ainda não executado.** Escrito em 2026-10-09, logo depois do
> upgrade do Kubernetes para 1.37.1 (ver `registro-upgrade-k8s-1.32-para-1.37.md`).
> Objetivo: ter NetworkPolicy com enforcement de verdade, para fechar o isolamento do
> namespace `kpack-builds`. Ao executar, preencher a seção "Registro da execução".

## O que foi verificado antes de escrever

| Item | Resultado |
|---|---|
| Calico `latest` (GitHub API) | `v3.33.0`, `prerelease: false` |
| Manifest da tag | `.../v3.33.0/manifests/canal.yaml` retorna 200 |
| Compatibilidade (doc oficial do Calico 3.33) | testado com Kubernetes 1.35, 1.36 e 1.37 |
| Kernel mínimo (doc) | 5.10; Ubuntu 24.04 atende |
| Flannel atual | `v0.28.5`, DaemonSet `kube-flannel-ds` no namespace `kube-flannel` |
| Backend do Flannel | `vxlan`, rede `10.244.0.0/16`, `EnableNFTables: false`, sem `DirectRouting` na config |
| Vault | selo `shamir` (**sem auto-unseal**) |
| PDBs no cluster | só `launchpad-db-primary` (min available 1, disrupções permitidas 0) |
| CNPG | Cluster `launchpad-db`, 1 instância, campo `spec.enablePDB` existe |
| Backups do CNPG | **nenhum** (`Backup`/`ScheduledBackup` vazios) |

## Caminho escolhido: migração oficial para Calico VXLAN

O guia oficial (`migration-from-flannel`) migra um cluster Flannel VXLAN ao vivo para
Calico VXLAN, com um controlador que atualiza os nodes um a um. **Não** é o Canal
(Calico só para policy + Flannel para rede) que tínhamos desenhado antes. O resultado
também aplica NetworkPolicy. Pré-requisitos da doc: Flannel VXLAN v0.9.1+, instalado como
DaemonSet com configuração no Kubernetes, `DirectRouting` desligado — todos atendidos.

URLs (todas na tag `v3.33.0`):

- `https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/flannel-migration/calico.yaml`
- `https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/flannel-migration/migration-job.yaml`

## Incertezas (não verificadas)

1. **O controlador expulsa pods do node?** O ClusterRole do job inclui `pods/eviction`
   e `pods/exec`, o que sugere que sim. A doc não afirma e o código do controlador não
   foi lido. Por isso o PDB do banco é desligado e o Vault é tratado como se fosse
   reiniciar.
2. **Queda de rede de pods.** A doc não trata de cluster com um node só nem diz o que
   acontece com pods em execução. Esperar uma interrupção curta de banco, Vault e sites.
3. **Migração a quente nunca foi testada neste cluster.** O rollback é manual e exige
   drain e reboot.

`kubectl` deve continuar funcionando durante a troca, porque o apiserver usa hostNetwork.

## Antes de começar (no dia)

- [ ] Jogos desligados; vigia em festim (já está).
- [ ] **Chaves de unseal do Vault à mão** (não colar em chat).
- [ ] Janela de 30–60 min com atenção total; sessão dentro do `tmux`.
- [ ] Backups novos no mesmo dia (o estado muda):
  - snapshot do etcd `pre-salto6` (mesmo método do registro do upgrade);
  - tar de `/etc/kubernetes`;
  - dump do banco: `kubectl -n launchpad exec launchpad-db-1 -c postgres -- pg_dump -U postgres -Fc launchpad > ~/launchpad-db-pre-salto6.dump`
    e conferir com `pg_restore --list`;
  - `scp` para o RPi e `chmod 600` em todos.
- [ ] Guardar o estado atual para comparar depois:
  - `kubectl get pods -A -o wide > ~/pods-pre-migracao.txt`
  - `ip -br link > ~/links-pre-migracao.txt`

## Execução

Um comando por vez, na ordem. Parar e investigar se qualquer passo não normalizar.

**1. Desligar o PDB do banco** (para o controlador não ficar preso nele):

```bash
kubectl -n launchpad patch cluster launchpad-db --type merge -p '{"spec":{"enablePDB":false}}'
kubectl -n launchpad get pdb      # deve ficar vazio
```

**2. Instalar o Calico:**

```bash
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/flannel-migration/calico.yaml
kubectl -n kube-system get pods | grep -i calico
```

**3. Iniciar o controlador de migração** (dentro do tmux):

```bash
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/flannel-migration/migration-job.yaml
kubectl get jobs -n kube-system flannel-migration
kubectl logs -n kube-system -l k8s-app=flannel-migration-controller
```

Esperar `1/1` completions. O controlador pode ser reagendado enquanto o node é atualizado.

**4. Depois que o job completar:**

```bash
kubectl delete -f https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/flannel-migration/migration-job.yaml
```

## Verificação pós-migração

```bash
kubectl get nodes; kubectl get pods -A | grep -v -E 'Running|Completed'
kubectl -n vault exec vault-0 -- vault status | grep -E 'Sealed|HA Mode'
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.15.14:30080/healthz
kubectl -n kube-system get pods | grep kube-proxy
ip -br link          # esperado: interfaces cali*; cni0 ausente
```

- Se o Vault voltou selado: `kubectl -n vault exec -it vault-0 -- vault operator unseal`
  (repetir até atingir o limiar de chaves).
- Reativar o PDB do banco:

```bash
kubectl -n launchpad patch cluster launchpad-db --type merge -p '{"spec":{"enablePDB":true}}'
kubectl -n launchpad get pdb
```

### Teste de enforcement (o resultado que importa)

Num namespace descartável, subir um servidor e um cliente, confirmar que o curl funciona,
aplicar uma policy `deny-all` de ingress e confirmar que o curl **falha**. Em Flannel puro
o curl continuava retornando 200 (sem enforcement); com Calico deve dar timeout.

```bash
kubectl create ns np-test
kubectl -n np-test run web --image=nginx --port=80
kubectl -n np-test expose pod web --port=80
kubectl -n np-test run cli --image=curlimages/curl --restart=Never --command -- sleep 3600
kubectl -n np-test exec cli -- curl -s -m 3 -o /dev/null -w "%{http_code}\n" http://web      # esperado: 200
```

```bash
kubectl -n np-test apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
spec:
  podSelector: {}
  policyTypes: ["Ingress"]
EOF
kubectl -n np-test exec cli -- curl -s -m 3 -o /dev/null -w "%{http_code}\n" http://web      # esperado: 000 (timeout)
kubectl delete ns np-test
```

## Rollback (se algo der errado)

Do guia oficial, **com o namespace do nosso Flannel** (`kube-flannel`; a doc usa
`kube-system` no patch):

```bash
kubectl delete -f .../v3.33.0/manifests/flannel-migration/migration-job.yaml
kubectl delete -f .../v3.33.0/manifests/flannel-migration/calico.yaml
kubectl get nodes -l projectcalico.org/node-network-during-migration=calico
```

Para cada node listado: `kubectl drain <node>` (com o PDB do banco desligado),
`rm /etc/cni/net.d/10-calico.conflist`, reboot, depois:

```bash
kubectl label node <node> projectcalico.org/node-network-during-migration=flannel --overwrite
kubectl uncordon <node>
```

Com todos revertidos:

```bash
kubectl patch ds/kube-flannel-ds -n kube-flannel -p '{"spec": {"template": {"spec": {"nodeSelector": null}}}}'
kubectl label node --all projectcalico.org/node-network-during-migration-
```

Último recurso: restaurar o snapshot do etcd `pre-salto6` e o dump do banco.

## Depois da migração

1. Escrever a NetworkPolicy real do `kpack-builds`:
   - egress para DNS (`10.96.0.10:53`);
   - egress para internet **exceto** `192.168.15.0/24` e `10.244.0.0/16`;
   - ingress apenas do ingress controller.
2. Adicionar o `ScheduledBackup` do CNPG (**hoje o banco do launchpad não tem backup**),
   com destino fora do node, e testar um restore.
3. Conferir se o Flannel DaemonSet foi removido pelo controlador; se sobrar, apagar.

## Registro da execução

| Item | Resultado |
|---|---|
| Data/hora | |
| Controlador expulsou pods? | |
| Vault voltou selado? | |
| Tempo de indisponibilidade | |
| Teste `deny-all` | |
| Observações | |
