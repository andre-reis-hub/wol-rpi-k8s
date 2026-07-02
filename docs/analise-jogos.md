# Análise da lista de jogos — viabilidade no wol-rpi-k8s

Critérios: servidor dedicado Linux nativo (mais leve que Wine), imagem Docker
madura, consumo de RAM, e monitoramento (logs de chat/players para o Loki).

| Jogo | Servidor | Imagem sugerida | Portas | RAM | Dificuldade |
|------|----------|-----------------|--------|-----|-------------|
| **Valheim** | Linux nativo ✅ | `ghcr.io/community-valheim-tools/valheim-server` | 2456-2457/UDP | ~4GB | ⭐ Fácil (RECOMENDADO 1º) |
| **Terraria** | Linux nativo ✅ | `ryshe/terraria` | 7777/TCP | ~1-2GB | ⭐ Fácil (leve!) |
| **Necesse** | Linux nativo ✅ | `brammys/necesse-server` | 14159/UDP | ~2GB | ⭐ Fácil (leve!) |
| **Project Zomboid** | Linux nativo ✅ | `afey/zomboid` | 16261-16262/UDP | ~4-8GB | ⭐⭐ Médio |
| **V Rising** | Windows/Wine ⚠️ | `trueosiris/vrising` | 9876-9877/UDP | ~6GB | ⭐⭐ Médio (Wine, como Abiotic) |
| **Enshrouded** | Windows/Wine ⚠️ | `mornedhels/enshrouded-server` | 15637/UDP | ~8-16GB | ⭐⭐⭐ Pesado (Wine + RAM) |
| **Sons of the Forest** | Windows/Wine ⚠️ | `jammsen/sons-of-the-forest` | 8766+27016+9700/UDP | ~8-12GB | ⭐⭐⭐ Pesado |
| **Windrose** | ❓ | — | — | — | Não identifiquei servidor dedicado público; confirmar o nome/loja do jogo |

## Recomendações

1. **Valheim primeiro** — Linux nativo, imagem madura com backups automáticos,
   logs claros de conexão (bom para Loki), comunidade gigante.
2. **Terraria e Necesse** — super leves, podem rodar JUNTO com outros sem pesar.
3. **V Rising** — quando quiser, segue o padrão Wine que você já domina (Abiotic).
4. **Enshrouded / Sons of the Forest** — deixar por último: Wine + muita RAM.
   Rodando junto com Palworld+Abiotic pode passar dos 32GB.

## Capacidade do i9 (32GB) — colocação FinOps

Rodando simultâneos (estimativa de RAM):
- Palworld (8-16) + Abiotic (6-12) = já ocupa 14-28GB
- +Valheim (4) cabe se Palworld estiver moderado
- +Terraria/Necesse (1-2) cabem quase sempre
- Enshrouded/SotF: rodar SOZINHOS ou com jogos leves

**Estratégia**: com o painel liga/desliga, ligar só o que vai jogar.
O monitoramento FinOps (abaixo) mostra o custo disso em R$.

Padrões de log p/ Loki (chat/join) devem ser confirmados no primeiro boot de
cada jogo (ver docs/como-adicionar-game-server.md).
