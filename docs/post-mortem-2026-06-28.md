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
