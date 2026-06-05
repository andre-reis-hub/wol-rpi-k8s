# wol-rpi-k8s

Painel de controle remoto hospedado num Raspberry Pi Zero W para ligar o PC via Wake-on-LAN, monitorar status e acessar serviços K8s remotamente.

## Infraestrutura

### Raspberry Pi Zero W (sempre ligado)
- **Função:** Gateway de baixo consumo, hospeda o painel web
- **OS:** Raspberry Pi OS Lite (32-bit, ARMv6)
- **IP local:** fixo via reserva DHCP no roteador (MAC: `b8:27:eb:c1:50:af`)

### PC Linux (acorda sob demanda)
- **Função:** Workload pesado, roda K8s e ferramentas de monitoramento
- **K8s:** k3s
- **Acionamento:** WoL magic packet enviado pelo Pi Zero

### Acesso Remoto
- **Exposição:** Cloudflare Tunnel (`cloudflared` no Pi Zero)
- **URL:** subdomínio Cloudflare (gratuito — requer domínio próprio na Cloudflare para URL persistente; alternativa: DuckDNS + Let's Encrypt)
- **HTTPS:** automático via Cloudflare

## Stack

### Pi Zero — Backend
- **Linguagem:** Python
- **Framework:** Flask
- **Frontend:** HTMX + Jinja2
- **Estado do PC:** JSON file
- **Autenticação:** sessão Flask, credenciais em `.env`

### PC Linux — Agente de boot
- **Implementação:** Script Python + systemd service
- **Dispara após:** `network-online.target`
- **Ações:**
  1. Consulta IP público via `api.ipify.org`
  2. Consulta NodePort services do K8s (`kubectl get services`)
  3. POST para Pi Zero com `{ ip, servicos: [{nome, porta}] }`

## Arquitetura

```
Internet
    │
Cloudflare Tunnel (HTTPS)
    │
Pi Zero W [Flask]
    ├── GET /               → Dashboard (status PC, links, botão WoL)
    ├── POST /wol           → Envia magic packet (requer login)
    └── POST /api/register  ← agente do PC registra IP e serviços

PC Linux [systemd: agente.py]
    ├── Consulta IP público (api.ipify.org)
    ├── Consulta K8s services (NodePort)
    └── POST → Pi Zero /api/register

K8s no PC [k3s]
    └── NodePort services (jogos, monitoramento)
        → Port forwarding no roteador
        → Links exibidos no dashboard
```

## Fluxo de uso

1. Usuário acessa `https://subdominio` (Cloudflare Tunnel)
2. Faz login
3. Vê status: **PC offline**
4. Clica em "Ligar PC" → Pi Zero envia WoL magic packet
5. Dashboard mostra **"Ligando..."** (polling a cada 5s)
6. PC boota → agente registra IP e serviços no Pi Zero
7. Dashboard atualiza: links dos serviços disponíveis

## Roadmap

| Etapa | Descrição |
|-------|-----------|
| 1 | Site base no Pi Zero (Flask + HTMX + login + status do PC) |
| 2 | Integração WoL (botão ligar + estado "ligando") |
| 3 | Cloudflare Tunnel (exposição segura à internet) |
| 4 | Agente leve no PC (systemd + registro de IP e serviços) |
| 5 | k3s no PC (setup inicial) |
| 6 | Ferramentas de monitoramento como pods K8s |
| 7 | Links dinâmicos de serviços no dashboard |

## Decisões

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Exposição à internet | Cloudflare Tunnel | Grátis, HTTPS automático, sem abrir portas no roteador |
| Autenticação | Flask session + `.env` | Um único usuário, sem overhead |
| Backend Pi Zero | Python + Flask | ARMv6 compatível, ecossistema simples |
| Frontend | HTMX + Jinja2 | Updates dinâmicos sem framework JS pesado |
| Estado persistido | JSON file | Sem banco de dados, suficiente para o escopo |
| IP fixo do Pi Zero | Reserva DHCP por MAC | Agente do PC precisa de endereço local estável |
| Agente no PC | Python + systemd | Nativo Linux, boot automático |
| IP público reportado | `api.ipify.org` | Fonte simples e autoritativa |
| Acesso a game servers | NodePort K8s + port forwarding no roteador | CGNAT descartado, IP público real confirmado |
| K8s no PC | k3s | Mais leve que K8s full, ideal para estudo |
| Estratégia de commits | Direto na main, um commit por funcionalidade | Histórico linear e legível |

## Pontos de atenção

- **IP do Pi Zero:** Fixar via reserva DHCP no roteador (MAC: `b8:27:eb:c1:50:af`) antes de subir o agente no PC
- **Port forwarding para jogos:** Configuração manual no roteador; pods expostos via NodePort (faixa 30000–32767)
- **CGNAT:** Descartado — IP público real confirmado
- **Segurança WoL:** Endpoint protegido por login — sem autenticação qualquer um poderia ligar o PC
- **Estado intermediário:** Entre WoL enviado e PC online leva 1–3 min; dashboard deve refletir isso
