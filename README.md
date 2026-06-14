# wol-rpi-k8s

Infraestrutura de game server doméstico com Wake-on-LAN, Kubernetes e painel de controle remoto. O servidor principal (i9) fica desligado e acorda sob demanda via Raspberry Pi Zero W — sempre ligado com consumo mínimo (~1W).

## Arquitetura

```
Internet
    │
Cloudflare Tunnel (HTTPS)
    ├── panel.areis-solution.com    → Flask painel (RPi Zero W)
    ├── grafana.areis-solution.com  → Grafana (i9 / k8s)
    └── argocd.areis-solution.com   → ArgoCD (i9 / k8s)

Raspberry Pi Zero W [sempre ligado — 192.168.15.12]
    ├── Flask painel (WoL, desligar, status Palworld, links)
    └── Cloudflare Tunnel (gateway de acesso)

PC Linux i9 [acorda sob demanda — 192.168.15.14]
    └── Kubernetes
          ├── Vault       (secrets — Raft + auto-unseal)
          ├── ArgoCD      (GitOps)
          ├── Prometheus  (métricas)
          ├── Grafana     (dashboards versionados)
          └── Game servers
                └── Palworld (PvE, REST API → painel)
```

## Fluxo de uso

```
1. Acessa panel.areis-solution.com e faz login
2. Clica "Ligar PC" → RPi envia WoL magic packet
3. i9 boota (~1-3 min), Vault faz auto-unseal
4. Agente registra IP público e serviços no painel
5. Painel mostra status do Palworld (jogadores, FPS, uptime)
6. Joga! Para encerrar, clica "Desligar PC" no painel
```

---

## Infraestrutura

### Raspberry Pi Zero W (sempre ligado)
- Gateway leve — painel web + WoL + Cloudflare Tunnel + desligar remoto
- Raspberry Pi OS Lite (32-bit, ARMv6), ~1W
- IP fixo `192.168.15.12` (MAC `b8:27:eb:c1:50:af`)

### PC Linux i9 (acorda sob demanda)
- Intel Core i9 11ª geração, 32GB RAM, NVIDIA GTX 1660
- Ubuntu 24.04 LTS, IP fixo `192.168.15.14` (MAC `00:e0:4c:a6:00:3e`)
- Kubernetes kubeadm v1.32

### Discos
| Disco | Tamanho | Uso |
|-------|---------|-----|
| `nvme0n1p3` | 206GB | Windows (dual boot) |
| `nvme0n1p6` | 29GB | Ubuntu `/` |
| `nvme1n1p1` | 450GB | Jogos Windows (NTFS) |
| `nvme1n1p2` | 526GB | Kubernetes — `/var/lib/rancher` |

> Containerd, Vault, Prometheus e game servers usam o disco secundário
> via symlink/PV. StorageClass `local-storage` (provisioner manual).

---

## Stack

### Raspberry Pi Zero W
| Componente | Função |
|-----------|--------|
| Flask + HTMX + Jinja2 | Painel web |
| wakeonlan | Magic packet |
| requests | Consulta REST API do Palworld |
| SSH | Desligamento remoto do i9 |
| cloudflared | Tunnel (multi-hostname) |

### Kubernetes (i9)
| Componente | Função |
|-----------|--------|
| kubeadm v1.32 | Cluster |
| Flannel | CNI (`10.244.0.0/16`) |
| Helm v3 | Charts |
| Vault (Raft) | Secrets + auto-unseal |
| ArgoCD | GitOps |
| kube-prometheus-stack | Prometheus + Grafana + AlertManager |
| GitHub Actions | Validação de manifestos (kubeconform) |
| Terraform | StorageClass (IaC) |

### Acesso externo (mesmo tunnel)
| Subdomínio | Serviço |
|-----------|---------|
| `panel.areis-solution.com` | Painel Flask (RPi) |
| `grafana.areis-solution.com` | Grafana |
| `argocd.areis-solution.com` | ArgoCD |

---

## Game Servers

| Jogo | Modo | Portas (NodePort) | Status |
|------|------|-------------------|--------|
| Palworld | PvE, 8 players | 30211/UDP (jogo), 30015/UDP (query), 30212/TCP (API) | ✅ |

O painel exibe em tempo real: jogadores online, FPS do servidor, dias no
mundo e uptime — via REST API do Palworld.

Para adicionar novos jogos, veja [docs/como-adicionar-game-server.md](docs/como-adicionar-game-server.md).

---

## Roadmap

| Etapa | Descrição | Status |
|-------|-----------|--------|
| 1 | Painel Flask (WoL + login + status) | ✅ |
| 2 | Integração WoL | ✅ |
| 3 | Cloudflare Tunnel + domínio | ✅ |
| 4 | Agente no i9 | ✅ |
| 5 | Kubernetes + Helm | ✅ |
| 6 | Vault (Raft + auto-unseal) | ✅ |
| 7 | ArgoCD (GitOps) | ✅ |
| 8 | Prometheus + Grafana + dashboards | ✅ |
| 9 | GitHub Actions | ✅ |
| 10 | Terraform | ✅ |
| 11 | Painel: status de serviços + desligar remoto | ✅ |
| 12 | Primeiro game server (Palworld) + monitoramento | ✅ |

---

## Decisões

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Gateway sempre ligado | RPi Zero W | ~1W, suficiente para Flask + WoL + tunnel |
| Pesado no i9, leve no RPi | ArgoCD/Prometheus/Grafana no i9 | RPi Zero W (512MB, ARMv6) não suporta |
| Kubernetes | kubeadm v1.32 | 32GB RAM, próximo do mercado |
| Exposição | Cloudflare Tunnel | Grátis, HTTPS, sem abrir portas |
| Secrets | Vault Raft + auto-unseal | Persistente, self-hosted |
| GitOps | ArgoCD | Padrão de mercado |
| Monitoramento | kube-prometheus-stack | Tudo em um chart |
| Dashboards | ConfigMap + sidecar | Versionado, aplicado via ArgoCD |
| CI | kubeconform (GitHub Actions) | Valida antes do deploy |
| IaC | Terraform | Fácil migração para AWS |
| Desligamento | Botão no painel via SSH | Manual e seguro (vs auto-shutdown arriscado) |
| Game server isolamento | Namespace por jogo | Organização e limites por jogo |
| Monitoramento de jogo | REST API → painel | Visibilidade de players sem entrar no servidor |

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/setup-completo.md](docs/setup-completo.md) | Guia do zero ao cluster |
| [docs/checklist-k8s.md](docs/checklist-k8s.md) | Checklist k8s + Vault + ArgoCD |
| [docs/como-adicionar-game-server.md](docs/como-adicionar-game-server.md) | Como subir um novo jogo |
| [docs/post-mortem-2026-06-05.md](docs/post-mortem-2026-06-05.md) | Incidentes e lições |

---

## Pontos de atenção

- **IPs fixos:** reservar DHCP por MAC antes de instalar k8s
- **Swap:** desabilitado — verificar `free -h` antes do init
- **Disco:** containerd/Vault/Prometheus/games no disco secundário
- **Vault:** Raft + auto-unseal — secrets persistem após reboot
- **ArgoCD + RWO:** updates causam ~30s downtime (aceitável)
- **GPU NVIDIA:** mitigação de freezes via `nvidia.NVreg_EnableGpuFirmware=0`
- **S5/WoL:** cooler e RGB podem ficar ligados após shutdown (normal)
- **NodePort:** range válido 30000-32767
- **Boot time:** WoL → online leva 1–3 min
