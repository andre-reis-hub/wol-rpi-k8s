# Post-mortem — Incidentes recentes (junho 2026)

Continuação do `post-mortem-2026-06-05.md`. Documenta os incidentes ocorridos
durante a expansão do projeto (Abiotic Factor, painel com RBAC, IP fixo, Loki).

---

## Incidente 14 — Acesso externo aos game servers falhava (regra com IP travado)

**Sintoma:** Amigos não conseguiam conectar no Palworld de fora. Testes de porta
davam "closed".

**Investigação (eliminação por camadas):**
- Firewall do Linux (ufw): inativo — descartado
- CGNAT: descartado (sessão PPPoE, IP WAN do roteador batia com o IP público)
- Kubernetes NodePort: correto (`iptables -t nat` mostrava `0.0.0.0/0` na 30211)
- Duas interfaces de rede (cabo + WiFi): descartado (WiFi down, rota única)

**Causa raiz:** Na aba "Redirecionar Portas" do roteador Vivo, o campo
**"IP Externo"** das regras estava travado num **IP público antigo**
(`177.196.137.162`). Como o IP residencial mudava periodicamente, qualquer
regra presa a um IP específico parava de funcionar quando o IP mudava.

**Solução:**
1. Deixar o campo "IP Externo" **vazio** (aceitar em qualquer IP da WAN).
   - `*` derruba o roteador (bug do firmware); vazio funciona.
2. Contratar **IP fixo** da Vivo (`179.246.145.230`) — elimina a mudança de IP.
3. Confirmado funcionando: primeiro com um site de teste na porta 5000 (RPi),
   depois com os próprios jogos.

**Lição:** Testes de porta UDP em sites são não-confiáveis (falso negativo). O
teste real é um amigo de outra rede, ou um servidor TCP simples
(`python3 -m http.server`) verificado via canyouseeme.org.

---

## Incidente 15 — Palworld "religava sozinho" após desligar pelo painel

**Sintoma:** Ao desligar um game server pelo painel (escala réplicas para 0),
o servidor voltava a ligar sozinho em segundos.

**Causa raiz:** As Applications do ArgoCD (palworld, abiotic-factor) tinham
auto-sync ativo. O deployment no Git tem `replicas: 1`. Quando o painel escalava
para 0, o ArgoCD detectava divergência com o Git e revertia para 1.

**Solução:** Adicionar `ignoreDifferences` no campo `/spec/replicas` de cada
Application, para o ArgoCD ignorar mudanças nesse campo:

```
kubectl patch application palworld -n argocd --type merge \
  -p '{"spec":{"ignoreDifferences":[{"group":"apps","kind":"Deployment","jsonPointers":["/spec/replicas"]}]}}'
```

Aplicado também para abiotic-factor. Assim o painel controla réplicas (0↔1)
livremente, e o ArgoCD continua gerenciando o resto do deployment.

**Lição:** Quando um controle externo (painel, HPA) gerencia réplicas, o GitOps
precisa abrir mão desse campo via ignoreDifferences. CLI do ArgoCD v3.4.3 não
tem flag direta para isso — usa-se kubectl patch na Application.

---

## Incidente 16 — Cluster inteiro fora do ar após reboot (disco trocou de nome)

**Gravidade:** ALTA — cluster 100% indisponível.

**Sintoma:** Após o i9 reiniciar, `kubectl` retornava
`connection refused` na porta 6443. Containerd e kubelet em loop de falha
(restart counter > 690).

**Investigação:**
- `journalctl -u kubelet`: erro `containerd.sock: no such file or directory`
- `journalctl`/status containerd: falha ao iniciar (status=1)
- `df -h /var/lib/rancher`: mostrava **11MB** em vez de 526GB!
- `lsblk`: o disco de 526GB tinha virado `nvme0n1p2`, e `nvme1n1p2`
  (que o fstab montava) era agora uma partição de 16MB.

**Causa raiz:** O `/etc/fstab` montava `/var/lib/rancher` por nome de
dispositivo (`/dev/nvme1n1p2`). Após o reboot, os discos NVMe trocaram de
ordem/nome (`nvme0n1` <-> `nvme1n1`), comum quando há mais de um NVMe. O fstab
montou a partição errada (16MB), o containerd não achou seus dados, e todo o
cluster caiu em cascata.

**Solução:** Montar por **UUID** (imutável), em vez de nome de dispositivo:

```
sudo umount /var/lib/rancher
sudo sed -i 's|/dev/nvme1n1p2 /var/lib/rancher|UUID=639a06c7-4964-4f04-ba24-7ba0bb614887 /var/lib/rancher|' /etc/fstab
sudo systemctl daemon-reload
sudo mount /var/lib/rancher       # confirmado: 526G, dados intactos
sudo systemctl restart containerd
sudo systemctl restart kubelet
```

Dados estavam todos preservados (só estava montado o disco errado).

**Limpeza pós-incidente:** Durante as horas com o disco errado, os controllers
recriaram dezenas de pods órfãos (ContainerStatusUnknown/Error). Limpos com:

```
kubectl delete pods -n <ns> --field-selector status.phase!=Running
```

**Lição (a mais importante do projeto):** SEMPRE montar discos por UUID no
fstab, nunca por /dev/nvmeXnYpZ. Nomes de dispositivo NVMe não são estáveis
entre reboots. Faz par com o Incidente 1 (IP mudou) — a lição comum é "nunca
dependa de identificadores que podem mudar" (nome de disco, IP dinâmico).

---

## Incidente 17 — A2S (Steam Query) não funcionou para monitorar jogadores

**Sintoma:** Tentativa de mostrar jogadores online via protocolo Steam A2S
(python-a2s) dava timeout nos dois jogos (portas de query 30015 e 30016).

**Causa raiz:** Nenhum dos dois servidores expõe A2S de forma acessível nesse
setup (Palworld não ativa A2S por padrão; Abiotic via Wine/EOS não responde
A2S externamente de forma confiável).

**Solução:** Abordagem híbrida:
- **Palworld:** REST API nativa (porta 30212) — já dava players, FPS, dias.
- **Abiotic Factor:** **Loki** — lê os logs do pod, que registram
  "X has entered/exited the facility".
- Anti-fantasma: o painel só mostra jogadores se o deployment tem réplica > 0
  (servidor ligado). Evita mostrar jogador "online" após o servidor desligar
  (que não loga a saída).

python-a2s foi removido do projeto.

**Lição:** Logs (via Loki) são a fonte universal de monitoramento de jogadores
— funcionam para qualquer servidor que logue conexões, independente de ter
REST API ou A2S. Mais robusto que protocolos específicos.

---

## Incidente 18 — loki-0 travado em ContainerCreating (pasta no disco errado)

**Sintoma:** Após instalar o Loki, o pod `loki-0` ficava em ContainerCreating.
`describe`: `MountVolume... path "/var/lib/rancher/loki" does not exist`.

**Causa raiz:** A pasta `/var/lib/rancher/loki` foi criada ANTES da correção do
Incidente 16 (quando o disco de 16MB estava montado). Após corrigir a montagem
para o disco certo (526GB), a pasta não existia mais nele.

**Solução:** Recriar a pasta no disco correto:
```
sudo mkdir -p /var/lib/rancher/loki
sudo chown 10001:10001 /var/lib/rancher/loki
```
O pod montou e ficou Running em seguida.

**Lição:** Após corrigir uma montagem de disco, recriar qualquer diretório que
tenha sido criado enquanto o disco errado estava montado.
## Incidente 19 — Senha do Abiotic sumia ao sincronizar o ArgoCD

**Sintoma:** O servidor Abiotic Factor ficava acessivel SEM senha de tempos em
tempos. Qualquer um conseguia entrar.

**Causa raiz:** A senha era adicionada via `kubectl set env` (fora do Git,
porque o repo e publico). O deployment no Git NAO tinha a senha. Toda vez que o
ArgoCD sincronizava (manual ou ao corrigir um "out of sync"), ele aplicava o
estado do Git e apagava a senha do `args`. O servidor reiniciava aberto.

**Solucao:** Migrar a senha para o **Vault** (Vault Agent Injector). Agora a
senha vive no Vault (KV `wol/abiotic-factor`), e um init container a injeta em
`/vault/secrets/server-password` a cada start do pod. Um wrapper no container le
o arquivo e monta o `args`. Assim:
- A senha nunca esta no Git nem depende de `kubectl set env`
- O ArgoCD pode sincronizar a vontade (o Vault reinjeta sempre)

Procedimento completo em `docs/vault-secrets.md`.

**Pegadinha encontrada (template Vault):** o primeiro deploy falhou com
`bad character U+002D '-'` no init container. Causa: o nome da chave
`server-password` tem hifen, e no Go template `.Data.data.server-password` o
hifen vira operador de subtracao. Corrigido usando:
`{{ index .Data.data "server-password" }}`.

**Licao:** Para segredos em repo publico, Vault (ou similar) e a solucao certa
— nao `kubectl set env` manual (fragil, some no sync) nem senha no Git
(inseguro). Mais um caso da licao recorrente: nao depender de estado manual
fora do controle declarativo.

---

## Nota tecnica — hostNetwork no Abiotic Factor (jogar no mesmo host)

**Contexto:** O Abiotic usa EOS (Epic Online Services). Quando o cliente do jogo
roda na MESMA maquina fisica que hospeda o servidor (o i9), a conexao dava
ConnectionTimeout apos 15s (o roteamento EOS nao fechava com cliente+servidor
no mesmo host + rede isolada do k8s). Colegas em outras redes conectavam normal.
O Palworld (Steam networking) nao tem esse problema.

**Solucao:** `hostNetwork: true` no deployment do Abiotic. O pod passa a usar a
rede do host diretamente, eliminando a traducao que quebrava a conexao local.

**Impacto:** As portas mudaram de NodePort (30777/30016) para portas diretas no
host (7777/27015). Ajustes feitos:
- Port forward no roteador: 7777/UDP -> 192.168.15.14
- Painel (app.py): porta_conexao do Abiotic = 7777
- Endereco de conexao: 179.246.145.230:7777 (externo) ou 192.168.15.14:7777 (local)

**Licao:** Jogos com EOS podem exigir hostNetwork para funcionar com
cliente+servidor no mesmo host. Steam networking (Palworld) e mais flexivel.

---

## Incidente 20 — Disk-pressure derruba o cluster (root pequeno)

**Sintoma:** Grafana, ArgoCD, Prometheus e Loki cairam juntos. Centenas de pods
em Evicted/Unknown. Cluster instavel por horas.

**Causa raiz:** Root (/) de 29GB chegou a 90%. O kubelet ativa DiskPressure
acima de ~85% e despeja pods. Controllers recriavam, eram despejados de novo =
ciclo vicioso. O que enchia: imagens de container + snapd (revisoes antigas).

**Solucao imediata:** journalctl --vacuum-size=100M, apt clean, remover snaps
antigos, kubectl delete pods com status != Running.

**Solucao definitiva:** Root de 29GB -> 75GB (depois 150GB com LVM). Containerd
data-root movido para o disco de 526GB via symlink.

**Licao:** Root >= 100GB para node k8s. Monitorar disco (dashboard FinOps mostra).

---

## Incidente 21 — Perda de dados por rm -rf em disco montado + backup

**Sintoma:** `rm -rf /var/lib/rancher/*` apagou saves dos jogos, storage do
Vault, Prometheus, Loki e containerd (disco de 526GB).

**Causa raiz:** O `umount /var/lib/rancher` FALHOU silenciosamente (kubelet/
containerd seguravam o disco), mas o rm-rf rodou mesmo assim, no disco montado.
Agravante: NAO havia backup.

**Recuperacao:** etcd (em /var/lib/etcd, disco root, intacto) preservou a
estrutura do cluster. Recriar pastas + corrigir symlink orfao do containerd
restaurou o cluster. Vault reinicializado do zero (init + reconfig KV/auth/
policies/roles via add-game-secret.sh).

**Solucao definitiva:** Backup restic+rclone -> Google Drive (cifrado,
incremental, retencao 7 dias, CronJob diario 3h, credenciais no Vault).
Restore TESTADO. Ver GUIA-BACKUP.md e GUIA-RESTORE.md.

**Licoes:**
1. NUNCA rm -rf em path de disco sem confirmar umount (mount | grep depois).
2. Backup nao e opcional; sem restore testado nao esta pronto.
3. Restore no i9 exige -o rclone.connections=1 (senao timeout).
4. Auto-unseal: apos re-init do Vault, atualizar /etc/vault/unseal-key.
