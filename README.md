# wol-rpi-k8s

Homelab GitOps: painel de controle num Raspberry Pi Zero W para ligar um PC via
Wake-on-LAN sob demanda, rodar game servers em Kubernetes e acessar tudo
remotamente. O PC (i9) fica desligado e só acorda quando alguém vai jogar.

## Visão geral da arquitetura

```
Internet
    │
    ├── Cloudflare Tunnel (HTTPS) ──► serviços web (painel, Grafana, ArgoCD)
    │
    └── Port forward (UDP) ─────────► game servers (Palworld, Abiotic Factor)

Raspberry Pi Zero W (sempre ligado, ~1W)
    ├── Painel Flask (liga/desliga PC e jogos, status, jogadores online)
    ├── cloudflared (tunnel)
    └── consulta o cluster do i9 via API k8s (RBAC) + Loki + REST

PC i9 (acorda sob demanda via WoL)
    └── Kubernetes (kubeadm v1.32)
        ├── ArgoCD (GitOps)
        ├── Vault (secrets, auto-unseal)
        ├── Prometheus + Grafana + Loki (observabilidade)
        └── Game servers (Palworld, Abiotic Factor) via NodePort
```

## Infraestrutura física

### Raspberry Pi Zero W — gateway sempre ligado
- OS Raspberry Pi OS Lite 32-bit (ARMv6), 512MB RAM, ~1W
- IP fixo `192.168.15.12` (reserva DHCP, MAC `b8:27:eb:c1:50:af`)
- GUI desabilitada (`multi-user.target`) para liberar RAM
- Hospeda: painel Flask (systemd `wol-panel`), cloudflared

### PC i9 — servidor principal sob demanda
- i9 11ª geração (8c/16t), 32GB RAM, GTX 1660, Ubuntu 24.04
- IP fixo `192.168.15.14` (MAC `00:e0:4c:a6:00:3e`)
- Acorda via WoL (magic packet enviado pelo RPi), interface `enp5s0`
- Kubernetes kubeadm v1.32, Flannel CNI (`10.244.0.0/16`)

### Discos do i9 (montados por UUID no fstab — ver Incidente 16)
| Partição | UUID | Tamanho | Uso |
|----------|------|---------|-----|
| root `/` | f3940cf8-... | 29GB | Ubuntu |
| k8s | 639a06c7-4964-4f04-ba24-7ba0bb614887 | 526GB | `/var/lib/rancher` |
| games | 27c11386-... | 186GB | `/mnt/games` |

> CRÍTICO: montar SEMPRE por UUID. Nomes NVMe (`nvme0n1`/`nvme1n1`) trocam
> entre reboots e quebram a montagem. Ver post-mortem Incidente 16.

### Rede / acesso externo
- Domínio `areis-solution.com` (Cloudflare)
- IP público FIXO `179.246.145.230` (Vivo, contratado)
- Subdomínios via Cloudflare Tunnel (HTTP): `panel`, `grafana`, `argocd`
- Game servers via port forward UDP no roteador (campo "IP Externo" VAZIO)

## Componentes do cluster

### GitOps — ArgoCD
Applications (todas com auto-sync):
- `wol-infra` → Vault (k8s/vault)
- `palworld` → k8s/games/palworld (ignoreDifferences em /spec/replicas)
- `abiotic-factor` → k8s/games/abiotic-factor (idem)
- `loki` → chart Helm loki-stack (opcional, ver k8s/argocd-apps/loki-app.yaml)

> ignoreDifferences em /spec/replicas: permite o painel escalar 0↔1 sem o
> ArgoCD reverter. Ver post-mortem Incidente 15.

### Secrets — Vault
Raft storage, auto-unseal via systemd lendo /etc/vault/unseal-key.

### Observabilidade
- Prometheus + Grafana (kube-prometheus-stack)
- Loki + Promtail (agregação de logs, retenção 6 meses)
- Dashboards versionados via ConfigMap (label `grafana_dashboard: "1"`)
- Dashboard "Game Servers — Jogadores e Conexões (Loki)"

## Game servers

| Jogo | Imagem | Porta (NodePort) | Players | Monitoramento |
|------|--------|------------------|---------|---------------|
| Palworld | thijsvanloef/palworld-server-docker | 30211/UDP | 8 | REST API (30212) |
| Abiotic Factor | andrewsav/abiotic-factor (Wine) | 30777/UDP | 6 | Loki (logs) |

Cada jogo: namespace próprio, PV em `/var/lib/rancher/<jogo>`, secret de senha
fora do Git, Service NodePort, README. Padrão documentado em
`docs/como-adicionar-game-server.md`.

## Painel (site/)

Flask + HTMX no RPi (systemd `wol-panel`). Funções:
- Ligar PC (WoL) / desligar PC (SSH `shutdown`)
- Ligar/desligar cada game server (escala réplicas via API k8s, RBAC mínimo)
- Status do PC e de cada jogo
- Jogadores online: Palworld via REST API, Abiotic via Loki (anti-fantasma:
  só mostra se o servidor está ligado)
- Endereço de conexão de cada jogo com botão copiar
- Dois níveis de acesso: admin (liga+desliga) e convidado (só liga)

Controle dos jogos via ServiceAccount `panel-controller` (RBAC mínimo:
get/patch deployments+scale nos namespaces dos jogos). Ver k8s/rbac/.

## Documentação

- `docs/setup-completo.md` — do zero ao cluster
- `docs/checklist-k8s.md` — checklist de instalação
- `docs/como-adicionar-game-server.md` — guia para novos jogos
- `docs/post-mortem-2026-06-05.md` — incidentes 1–13
- `docs/post-mortem-2026-06-28.md` — incidentes 14–18 (IP travado, ArgoCD
  replicas, disco/UUID, A2S, Loki)

## Lições recorrentes

1. **Nunca dependa de identificadores mutáveis:** IP dinâmico (→ IP fixo),
   nome de disco NVMe (→ UUID no fstab). Os dois maiores incidentes do projeto.
2. **GitOps + controle externo de réplicas:** use ignoreDifferences.
3. **Monitoramento de jogadores:** logs (Loki) são universais; A2S e REST API
   são específicos e nem sempre disponíveis.
4. **Roteador Vivo:** campo "IP Externo" do port forward deve ficar VAZIO.
