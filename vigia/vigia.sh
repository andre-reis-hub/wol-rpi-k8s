#!/usr/bin/env bash
# =====================================================================
# VIGIA DE ÓCIO — desliga o i9 quando o ambiente fica sem uso.
# MODO ATUAL: DRY-RUN TOTAL (festim). Não escala, não desliga. Só loga.
# Roda no i9 via timer systemd (a cada 2min).
# Consulta o Prometheus através do pod game-exporter (tem Python e fala
# com o prometheus-operated pelo DNS interno do cluster).
# =====================================================================
set -uo pipefail

IDLE_MINUTES="${IDLE_MINUTES:-20}"
BOOT_GRACE_MINUTES="${BOOT_GRACE_MINUTES:-15}"
STATE_FILE="${STATE_FILE:-$HOME/.vigia/idle-since}"
EXPORTER_NS="${EXPORTER_NS:-monitoring}"
PROM_URL="${PROM_URL:-http://prometheus-operated.monitoring.svc:9090}"
LOG_TAG="vigia"
DRY_RUN="${DRY_RUN:-true}"   # <<< festim. NUNCA mude sem calibrar.

log() { logger -t "$LOG_TAG" "$*"; echo "[$(date '+%H:%M:%S')] $*"; }

mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null

# --- 1. Carência pós-boot ---
uptime_s=$(awk '{print int($1)}' /proc/uptime)
grace_s=$(( BOOT_GRACE_MINUTES * 60 ))
if (( uptime_s < grace_s )); then
  log "carência pós-boot (${uptime_s}s < ${grace_s}s) — não avalia."
  rm -f "$STATE_FILE"
  exit 0
fi

# --- 2. Consulta o Prometheus VIA game-exporter (Python garantido) ---
prom_val() {
  local query="$1"
  kubectl -n "$EXPORTER_NS" exec deploy/game-exporter -- python -c "
import urllib.request, json, sys
try:
    u = '$PROM_URL/api/v1/query?query=' + urllib.parse.quote('''$query''')
    d = json.load(urllib.request.urlopen(u, timeout=5))
    r = d['data']['result']
    print(r[0]['value'][1] if r else '0')
except Exception:
    print('ERR')
" 2>/dev/null || echo "ERR"
}

# --- 3. Coleta os SINAIS DE USO ---
jogadores=$(prom_val 'sum(game_players_online)')
deteccao_falhou=$(prom_val 'sum(game_detection_ok<1)')
ssh_sessions=$(who 2>/dev/null | grep -c .)
k8s_jobs_ativos=$(kubectl get jobs -A --no-headers 2>/dev/null \
                  | awk '{if ($3 !~ /1\/1|Complete/) print}' | grep -c .)

# --- 4. Decide "em uso" ---
usado="não"; motivos=()
num() { echo "${1:-0}" | grep -Eq '^[0-9]+([.][0-9]+)?$' && echo "$1" || echo "0"; }

if [[ "$jogadores" == "ERR" || "$deteccao_falhou" == "ERR" ]]; then
  usado="sim"; motivos+=("prometheus-inacessível(falha-segura)")
elif (( $(echo "$(num "$deteccao_falhou") > 0" | bc -l) )); then
  usado="sim"; motivos+=("detecção-cega(falha-segura)")
fi
(( $(echo "$(num "$jogadores") > 0" | bc -l) )) && { usado="sim"; motivos+=("jogadores=$jogadores"); }
(( ssh_sessions > 0 ))    && { usado="sim"; motivos+=("ssh=$ssh_sessions"); }
(( k8s_jobs_ativos > 0 )) && { usado="sim"; motivos+=("jobs=$k8s_jobs_ativos"); }

# --- 5. Rastreia ócio contínuo ---
now=$(date +%s)
if [[ "$usado" == "sim" ]]; then
  log "EM USO: ${motivos[*]} — zera contador."
  rm -f "$STATE_FILE"; exit 0
fi
if [[ -f "$STATE_FILE" ]]; then idle_since=$(cat "$STATE_FILE"); else idle_since=$now; echo "$now" > "$STATE_FILE"; fi
idle_min=$(( (now - idle_since) / 60 ))
log "OCIOSO há ${idle_min}min (jogadores=${jogadores}, ssh=${ssh_sessions}, jobs=${k8s_jobs_ativos})."

# --- 6. Passou do limite? (festim) ---
if (( idle_min >= IDLE_MINUTES )); then
  if [[ "$DRY_RUN" == "true" ]]; then
    log "🔫 FESTIM: DESLIGARIA o i9 agora (ocioso ${idle_min}min >= ${IDLE_MINUTES}min)."
    log "🔫 FESTIM: escalaria jogos p/ 0 (saves) ANTES de desligar."
  else
    log "escalando jogos p/ 0 (saves)..."
    for ns in palworld abiotic-factor valheim; do
      kubectl -n "$ns" scale deploy --all --replicas=0 2>/dev/null
    done
    sleep 45
    log "poweroff agora."
    sudo /usr/sbin/poweroff
  fi
fi
