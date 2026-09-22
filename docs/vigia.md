# Vigia de ócio — auto-shutdown do i9

Documento do vigia: o que é, como decide, e **como promover de festim (dry-run)
para bala de verdade** quando a pontaria estiver boa.

## O que é

O vigia desliga o i9 quando o ambiente fica sem uso, pra economizar energia.
É o par natural da campainha: a campainha **liga** o i9 sob demanda, o vigia
**desliga** quando ninguém usa.

- Roda **no i9**, via timer systemd, a cada 2 minutos.
- Consulta o Prometheus (através do pod `game-exporter`) + checagens locais.
- Arquivos: `vigia/vigia.sh`, `vigia/vigia.service`, `vigia/vigia.timer`
  (no repo `wol-rpi-k8s`).

## Estado atual: FESTIM (dry-run total)

O vigia está com `DRY_RUN=true`. Ele faz **toda** a lógica — coleta sinais,
decide "desligaria agora" — mas **não desliga nada, não escala nada**. Só loga.

Isso é de propósito: um mecanismo que desliga infraestrutura nasce em festim,
e só ganha "bala de verdade" depois de dias provando que a pontaria está certa.

Ver as decisões (i9):
```bash
journalctl -t vigia -n 50 --no-pager   # histórico
journalctl -t vigia -f                 # ao vivo
```

## Como o vigia decide

A regra é: **desliga SE nenhum sinal de uso estiver ativo, por 20min contínuos.**

Sinais de uso (qualquer um = "em uso", zera o contador de ócio):
- **jogadores online** — `sum(game_players_online)` via Prometheus
- **alguém logado** — `who` (sessões SSH no i9)
- **job k8s ativo** — algum Job rodando (ex: backup)
- **detecção cega (falha-segura)** — se `game_detection_ok` de algum jogo é 0,
  ou o Prometheus está inacessível, assume **OCUPADO** (não confia no zero)

Regras extras:
- **Carência pós-boot: 15min** — não avalia nos primeiros 15min de uptime.
  Protege contra desligar "na cara" logo que o i9 liga (alguém ligou por um motivo).
- **Servidor ligado e VAZIO não conta como uso** — é justamente o que queremos
  desligar (ninguém jogando, servidor à toa).

## A falha-segura (por que o vigia é seguro mesmo com bugs)

O `game_detection_ok` é a chave: quando a detecção de jogadores **falha** (Loki fora,
REST API do Palworld fora, Prometheus inacessível), o exporter marca `0`, e o vigia
**assume ocupado**. Ele erra pro lado seguro — nunca desliga baseado em informação
duvidosa. Já vimos isso funcionar em campo (o Palworld quebrado marcou detection_ok=0
e o vigia não desligou).

## Dependência importante

O vigia lê jogadores **através do game-exporter**. Se o exporter estiver desligado
(scale 0), o vigia fica cego → cai na falha-segura → **nunca desliga o i9**. Por isso
NÃO existe botão de desligar o exporter no painel (foi removido de propósito).

---

## BALA DE VERDADE — como promover (quando a pontaria estiver boa)

**Pré-requisito:** alguns dias de `journalctl -t vigia` mostrando:
- "EM USO" sempre que você estava mexendo/jogando/com job
- "OCIOSO há Xmin" subindo quando ninguém usava
- "🔫 FESTIM: DESLIGARIA" aparecendo SÓ após 20min de ócio real, NUNCA com uso

Se isso se confirmou por uns dias, promove **em etapas** (não tudo de uma vez):

### Etapa A — liberar só o scale (desliga servidores vazios, NÃO o i9 ainda)

Primeiro deixa o vigia realmente escalar os jogos pra 0 (dispara os saves), mas
ainda SEM `poweroff`. Observa mais uns dias: os saves estão sendo feitos? Os
servidores certos são desligados?

No `vigia.sh`, na seção de bala de verdade, mantenha o `poweroff` comentado e deixe
só o loop de `kubectl scale` ativo. (Ou adicione uma flag `SCALE_ONLY=true`.)

### Etapa B — liberar o poweroff (vigia completo)

Depois que o scale provar que funciona, libera o `poweroff`:

1. **Trocar DRY_RUN pra false** no `vigia.sh`:
   ```bash
   DRY_RUN="${DRY_RUN:-false}"
   ```

2. **O sudoers cirúrgico** — o vigia roda como você, mas `poweroff` precisa de root.
   Adicione uma regra que permite SÓ o poweroff sem senha (nada mais). No i9:
   ```bash
   echo 'andre-reis ALL=(root) NOPASSWD: /usr/sbin/poweroff' | sudo tee /etc/sudoers.d/vigia
   sudo chmod 440 /etc/sudoers.d/vigia
   sudo visudo -c   # valida a sintaxe
   ```

3. **Redeploy do vigia** e observar o primeiro desligamento real de perto.

### A sequência de shutdown (decisão B, já no código)

Quando o vigia decide desligar (bala real), ele:
1. Escala os jogos pra 0 (`kubectl scale deploy --all --replicas=0` nos namespaces
   dos jogos) → isso dispara os saves dos mundos
2. Espera ~45s pros saves terminarem
3. `sudo /usr/sbin/poweroff`

Escalar antes de desligar é o que garante que os saves são feitos graciosamente,
em vez de derrubar a máquina no meio.

---

## Sinais futuros (extensível)

O vigia foi desenhado pra a lista de sinais **crescer**. Quando você instrumentar:
- acessos ao launchpad (quem está usando a plataforma)
- acessos aos sites que criar no ambiente

...cada um vira uma métrica no Prometheus, e entra na query do vigia como mais um
sinal de uso. O vigia soma tudo e pergunta "deu zero por 20min?". Adicionar um sinal
novo = expor a métrica + somar ela no `vigia.sh`. O vigia em si quase não muda.

## Configuração (variáveis no vigia.sh)

| Variável | Default | O quê |
|----------|---------|-------|
| `IDLE_MINUTES` | 20 | ócio contínuo pra desligar |
| `BOOT_GRACE_MINUTES` | 15 | carência pós-boot |
| `DRY_RUN` | true | **festim** — nunca mude sem calibrar |
| `EXPORTER_NS` | monitoring | namespace do game-exporter |
| `PROM_URL` | prometheus-operated.monitoring.svc:9090 | Prometheus interno |

O timer roda a cada 2min (`vigia.timer`, `OnUnitActiveSec=2min`).
