import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from functools import wraps

import requests
import urllib3
import wakeonlan
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']

USERNAME = os.environ['USERNAME']
PASSWORD = os.environ['PASSWORD']
GUEST_USERNAME = os.environ.get('GUEST_USERNAME', '')
GUEST_PASSWORD = os.environ.get('GUEST_PASSWORD', '')

PC_MAC = os.environ['PC_MAC']
PC_LOCAL_IP = os.environ['PC_LOCAL_IP']
REGISTER_TOKEN = os.environ.get('REGISTER_TOKEN', '')
PC_SSH_USER = os.environ.get('PC_SSH_USER', 'andre-reis')

PUBLIC_HOST = os.environ.get('PUBLIC_HOST', PC_LOCAL_IP)
# Se AUTO_PUBLIC_IP=true, descobre o IP publico real automaticamente
AUTO_PUBLIC_IP = os.environ.get('AUTO_PUBLIC_IP', 'true').lower() == 'true'
_public_ip_cache = {'ip': None, 'ts': 0}
PUBLIC_IP_TTL = 300  # segundos (5 min) - evita consultar toda hora


def get_public_host():
    """Retorna o IP publico real. Descobre via servico externo (com cache de
    5 min) se AUTO_PUBLIC_IP=true; senao usa PUBLIC_HOST do .env."""
    import time as _t
    if not AUTO_PUBLIC_IP:
        return PUBLIC_HOST
    agora = _t.time()
    if _public_ip_cache['ip'] and (agora - _public_ip_cache['ts']) < PUBLIC_IP_TTL:
        return _public_ip_cache['ip']
    for url in ('https://api.ipify.org', 'https://ifconfig.me/ip', 'https://icanhazip.com'):
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                ip = r.text.strip()
                if ip:
                    _public_ip_cache['ip'] = ip
                    _public_ip_cache['ts'] = agora
                    return ip
        except Exception:
            continue
    # fallback: cache antigo ou PUBLIC_HOST
    return _public_ip_cache['ip'] or PUBLIC_HOST

K8S_API = os.environ.get('K8S_API', 'https://192.168.15.14:6443')
K8S_TOKEN = os.environ.get('K8S_TOKEN', '')
K8S_CA_CERT = os.environ.get('K8S_CA_CERT', '')

PALWORLD_API_URL = os.environ.get('PALWORLD_API_URL', '')
PALWORLD_API_USER = os.environ.get('PALWORLD_API_USER', 'admin')
PALWORLD_API_PASS = os.environ.get('PALWORLD_API_PASS', '')

LOKI_URL = os.environ.get('LOKI_URL', 'http://192.168.15.14:31100')
LOKI_WINDOW_HOURS = int(os.environ.get('LOKI_WINDOW_HOURS', '12'))
CHAT_LIMIT = int(os.environ.get('CHAT_LIMIT', '10'))

WAKING_TIMEOUT = 300
STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')

GAMES = {
    'palworld': {
        'nome': 'Palworld',
        'emoji': '🎮',
        'namespace': 'palworld',
        'deployment': 'palworld-server',
        'porta_conexao': 30211,
        'fonte_players': 'rest',
        'log_join': 'joined the server',
        'log_leave': 'left the server',
        'log_name_regex': r'(\w[\w .-]*) joined the server',
        'log_leave_name_regex': r'(\w[\w .-]*) left the server',
        'chat_filtro': r'\\[CHAT\\] <',
        'chat_regex': r'\[CHAT\]\s+<([^>]+)>\s+(.+)$',
    },
    'abiotic-factor': {
        'nome': 'Abiotic Factor',
        'emoji': '🧪',
        'namespace': 'abiotic-factor',
        'deployment': 'abiotic-factor-server',
        'porta_conexao': 7777,
        'so_ip': True,  # porta padrao (7777) -> no jogo basta o IP, copia so o IP
        'fonte_players': 'loki',
        'log_join': 'entered the facility',
        'log_leave': 'exited the facility',
        'log_name_regex': r'CHAT LOG:\s+(.+?) has entered the facility',
        'log_leave_name_regex': r'CHAT LOG:\s+(.+?) has exited the facility',
        'chat_filtro': 'CHAT LOG:',
        'chat_regex': r'CHAT LOG:\s+(\S+)\s+(.+)$',
    },
    'valheim': {
        'nome': 'Valheim',
        'emoji': '🛡️',
        'namespace': 'valheim',
        'deployment': 'valheim-server',
        'porta_conexao': 30456,
        'fonte_players': 'loki_valheim',
        'chat_filtro': None,
        'chat_regex': None,
    },
}

# Padroes que NAO sao chat de jogador (filtrar para nao poluir)
ABIOTIC_NAO_CHAT = ('has entered the facility', 'has exited the facility')


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'ip': None, 'services': [], 'last_seen': None, 'waking': False, 'waking_since': None}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def is_waking(state):
    if not state.get('waking') or not state.get('waking_since'):
        return False
    elapsed = (datetime.utcnow() - datetime.fromisoformat(state['waking_since'])).total_seconds()
    return elapsed < WAKING_TIMEOUT


def pc_online():
    result = subprocess.run(['ping', '-c', '1', '-W', '1', PC_LOCAL_IP], capture_output=True)
    return result.returncode == 0


def _k8s_headers():
    return {'Authorization': f'Bearer {K8S_TOKEN}'}


def _k8s_verify():
    return K8S_CA_CERT if K8S_CA_CERT and os.path.exists(K8S_CA_CERT) else False


def get_game_replicas(game):
    g = GAMES[game]
    try:
        url = f"{K8S_API}/apis/apps/v1/namespaces/{g['namespace']}/deployments/{g['deployment']}"
        r = requests.get(url, headers=_k8s_headers(), verify=_k8s_verify(), timeout=4)
        if r.status_code == 200:
            return r.json().get('spec', {}).get('replicas', 0)
    except Exception:
        pass
    return None


def scale_game(game, replicas):
    g = GAMES[game]
    try:
        url = f"{K8S_API}/apis/apps/v1/namespaces/{g['namespace']}/deployments/{g['deployment']}/scale"
        headers = _k8s_headers()
        headers['Content-Type'] = 'application/merge-patch+json'
        body = json.dumps({'spec': {'replicas': replicas}})
        r = requests.patch(url, headers=headers, data=body, verify=_k8s_verify(), timeout=6)
        return r.status_code in (200, 201)
    except Exception:
        return False


def get_palworld_metrics():
    if not PALWORLD_API_URL:
        return None
    try:
        resp = requests.get(f'{PALWORLD_API_URL}/v1/api/metrics',
                            auth=(PALWORLD_API_USER, PALWORLD_API_PASS), timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_palworld_players():
    if not PALWORLD_API_URL:
        return []
    try:
        resp = requests.get(f'{PALWORLD_API_URL}/v1/api/players',
                            auth=(PALWORLD_API_USER, PALWORLD_API_PASS), timeout=3)
        if resp.status_code == 200:
            return [p.get('name', '?') for p in resp.json().get('players', [])]
    except Exception:
        pass
    return []


def _loki_query_range(logql, hours):
    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        params = {'query': logql, 'start': str(int(start.timestamp() * 1e9)),
                  'end': str(int(end.timestamp() * 1e9)), 'limit': '2000', 'direction': 'forward'}
        r = requests.get(f'{LOKI_URL}/loki/api/v1/query_range', params=params, timeout=5)
        if r.status_code == 200:
            return r.json().get('data', {}).get('result', [])
    except Exception:
        pass
    return None


def get_loki_players(game):
    g = GAMES[game]
    ns = g['namespace']
    logql = f'{{namespace="{ns}"}} |~ "{g["log_join"]}|{g["log_leave"]}"'
    result = _loki_query_range(logql, LOKI_WINDOW_HOURS)
    if result is None:
        return None
    eventos = []
    re_join = re.compile(g['log_name_regex'])
    re_leave = re.compile(g['log_leave_name_regex'])
    for stream in result:
        for ts, line in stream.get('values', []):
            mj = re_join.search(line)
            ml = re_leave.search(line)
            if mj:
                eventos.append((int(ts), mj.group(1).strip(), 'in'))
            elif ml:
                eventos.append((int(ts), ml.group(1).strip(), 'out'))
    eventos.sort(key=lambda e: e[0])
    estado = {}
    for ts, nome, tipo in eventos:
        estado[nome] = (tipo == 'in')
    return [nome for nome, online in estado.items() if online]


def get_loki_chat(game, limite=CHAT_LIMIT):
    """Ultimas N mensagens de chat do jogo via Loki."""
    g = GAMES[game]
    if not g.get('chat_filtro') or not g.get('chat_regex'):
        return []
    chat_re = re.compile(g['chat_regex'])
    ns = g['namespace']
    logql = f'{{namespace="{ns}"}} |~ "{g["chat_filtro"]}"'
    result = _loki_query_range(logql, LOKI_WINDOW_HOURS)
    if not result:
        return []
    msgs = []
    for stream in result:
        for ts, line in stream.get('values', []):
            m = chat_re.search(line)
            if not m:
                continue
            nome = m.group(1).strip()
            msg = m.group(2).strip()
            # Filtra linhas que nao sao chat real (ex: entered/exited do Abiotic)
            if game == 'abiotic-factor' and any(x in line for x in ABIOTIC_NAO_CHAT):
                continue
            msgs.append((int(ts), nome, msg))
    msgs.sort(key=lambda x: x[0])
    msgs = msgs[-limite:]
    return [{'nome': n, 'msg': msg} for _, n, msg in msgs]


def get_players(game, ligado):
    if not ligado:
        return [], True
    g = GAMES[game]
    if g['fonte_players'] == 'rest':
        return get_palworld_players(), True
    elif g['fonte_players'] == 'loki_valheim':
        nomes = get_valheim_players()
        if nomes is None:
            return [], False
        return nomes, True
    else:
        nomes = get_loki_players(game)
        if nomes is None:
            return [], False
        return nomes, True

def get_valheim_players():
    """Valheim: rastreia sessoes por SteamID.
    - 'Got connection SteamID X' abre sessao X
    - 'Got character ZDOID from Nome' associa Nome ao ultimo SteamID aberto
    - 'Closing socket X' fecha a sessao X
    Retorna lista de nomes online."""
    import re
    logql = ('{namespace="valheim"} |~ '
    '"Got connection SteamID|Got character ZDOID from|Closing socket"')
    result = _loki_query_range(logql, LOKI_WINDOW_HOURS)
    if result is None:
        return None
    re_sid   = re.compile(r'Got connection SteamID (\d+)')
    re_char  = re.compile(r'Got character ZDOID from (.+?) :')
    re_close = re.compile(r'Closing socket (\d+)')
    # Junta todas as linhas de todos os streams e ordena por timestamp
    eventos = []
    for stream in result:
        for ts, line in stream.get('values', []):
            eventos.append((int(ts), line))
    eventos.sort(key=lambda x: x[0])
    online = {}              # steamid -> nome
    last_open_no_name = None
    for ts, line in eventos:
        m_sid = re_sid.search(line)
        m_char = re_char.search(line)
        m_close = re_close.search(line)
        if m_sid:
            sid = m_sid.group(1)
            online[sid] = None
            last_open_no_name = sid
        elif m_char:
            nome = m_char.group(1).strip()
            if last_open_no_name:
                online[last_open_no_name] = nome
                last_open_no_name = None
        elif m_close:
            online.pop(m_close.group(1), None)
    return [n for n in online.values() if n]

def get_tunnel_url():
    return os.environ.get('TUNNEL_URL')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return '<p><strong class="status-offline">Acesso negado: apenas administrador.</strong></p>', 403
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if user == USERNAME and pw == PASSWORD:
            session['user'] = USERNAME
            session['role'] = 'admin'
            return redirect(url_for('dashboard'))
        if GUEST_USERNAME and user == GUEST_USERNAME and pw == GUEST_PASSWORD:
            session['user'] = GUEST_USERNAME
            session['role'] = 'guest'
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Credenciais inválidas')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    return render_template(
        'dashboard.html',
        games=GAMES,
        tunnel_url=get_tunnel_url(),
        grafana_base=os.environ.get('GRAFANA_BASE', 'https://grafana.areis-solution.com'),
        argocd_base=os.environ.get('ARGOCD_BASE', 'https://argocd.areis-solution.com'),
    )


@app.route('/status-fragment')
@login_required
def status_fragment():
    online = pc_online()
    state = load_state()
    waking = not online and is_waking(state)
    is_admin = session.get('role') == 'admin'
    return render_template('_status.html', online=online, waking=waking, state=state, is_admin=is_admin)


@app.route('/game-fragment/<game>')
@login_required
def game_fragment(game):
    if game not in GAMES:
        return '', 404
    g = GAMES[game]
    online = pc_online()
    replicas = get_game_replicas(game) if online else None
    ligado = bool(replicas) if replicas is not None else False
    players, fonte_ok = get_players(game, ligado) if online else ([], True)
    metrics = get_palworld_metrics() if (online and ligado and g['fonte_players'] == 'rest') else None
    chat = get_loki_chat(game)  # sempre, mesmo desligado (mostra historico)
    host = get_public_host()
    if g.get('so_ip'):
        endereco = host  # porta padrao: no jogo basta o IP
    else:
        endereco = f"{host}:{g['porta_conexao']}"
    is_admin = session.get('role') == 'admin'
    return render_template(
        '_game.html',
        game=game, g=g, online=online, ligado=ligado,
        players=players, fonte_ok=fonte_ok, metrics=metrics,
        endereco=endereco, is_admin=is_admin, chat=chat,
    )


@app.route('/game/<game>/start', methods=['POST'])
@login_required
def game_start(game):
    if game not in GAMES:
        return '', 404
    scale_game(game, 1)
    return game_fragment(game)


@app.route('/game/<game>/stop', methods=['POST'])
@login_required
@admin_required
def game_stop(game):
    if game not in GAMES:
        return '', 404
    scale_game(game, 0)
    return game_fragment(game)


@app.route('/wol', methods=['POST'])
@login_required
def wol():
    wakeonlan.send_magic_packet(PC_MAC)
    state = load_state()
    state['waking'] = True
    state['waking_since'] = datetime.utcnow().isoformat()
    save_state(state)
    return ''


@app.route('/shutdown', methods=['POST'])
@login_required
@admin_required
def shutdown():
    try:
        result = subprocess.run(
            ['ssh', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=no',
             f'{PC_SSH_USER}@{PC_LOCAL_IP}', 'sudo shutdown now'],
            capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return '<p><strong class="status-waking">⏻ Comando de desligamento enviado.</strong></p>'
        return f'<p><strong class="status-offline">Erro ao desligar: {result.stderr[:100]}</strong></p>'
    except Exception as e:
        return f'<p><strong class="status-offline">Erro: {str(e)[:100]}</strong></p>'


@app.route('/api/register', methods=['POST'])
def register():
    if REGISTER_TOKEN:
        auth = request.headers.get('Authorization', '')
        if auth != f'Bearer {REGISTER_TOKEN}':
            return {'error': 'unauthorized'}, 401
    data = request.get_json(silent=True) or {}
    state = {'ip': data.get('ip'), 'services': data.get('services', []),
             'last_seen': datetime.utcnow().isoformat(), 'waking': False, 'waking_since': None}
    save_state(state)
    return {'ok': True}


@app.route('/backup/start', methods=['POST'])
@login_required
@admin_required
def backup_start():
    import json as _json
    nome = f"backup-manual-{int(datetime.utcnow().timestamp())}"
    url_cj = f"{K8S_API}/apis/batch/v1/namespaces/backup/cronjobs/wol-backup"
    r = requests.get(url_cj, headers=_k8s_headers(), verify=_k8s_verify(), timeout=5)
    if r.status_code != 200:
        return '<p><strong class="status-offline">Erro ao ler CronJob.</strong></p>'
    job_spec = r.json()['spec']['jobTemplate']['spec']
    body = {"apiVersion": "batch/v1", "kind": "Job",
            "metadata": {"name": nome, "namespace": "backup"}, "spec": job_spec}
    url_job = f"{K8S_API}/apis/batch/v1/namespaces/backup/jobs"
    headers = _k8s_headers(); headers['Content-Type'] = 'application/json'
    r2 = requests.post(url_job, headers=headers, data=_json.dumps(body),
                       verify=_k8s_verify(), timeout=8)
    if r2.status_code in (200, 201):
        return ('<p><strong class="status-online">✅ Backup iniciado!</strong></p>'
                '<div hx-get="/backup/status" hx-trigger="load, every 10s" hx-swap="innerHTML"></div>')
    return f'<p><strong class="status-offline">Erro ao criar job: {r2.status_code}</strong></p>'


@app.route('/backup/status')
@login_required
def backup_status():
    url = f"{K8S_API}/apis/batch/v1/namespaces/backup/jobs"
    r = requests.get(url, headers=_k8s_headers(), verify=_k8s_verify(), timeout=5)
    if r.status_code != 200:
        return '<p><small>Status indisponivel.</small></p>'
    jobs = r.json().get('items', [])
    jobs.sort(key=lambda j: j['metadata'].get('creationTimestamp', ''), reverse=True)
    linhas = []
    for j in jobs[:3]:
        nome = j['metadata']['name']
        st = j.get('status', {})
        if st.get('succeeded'): estado = '✅ Concluido'
        elif st.get('active'): estado = '⏳ Rodando...'
        elif st.get('failed'): estado = '❌ Falhou'
        else: estado = '… Iniciando'
        linhas.append(f'<li>{nome}: {estado}</li>')
    return '<ul style="font-size:0.85rem;">' + ''.join(linhas) + '</ul>'

# =====================================================================
# ROTAS DE BACKUP/RESTORE/RESET POR JOGO
# Inserir estas rotas no app.py (antes do if __name__ == '__main__')
# =====================================================================

def _criar_job_ops(nome, script_key, env_extra):
    """Cria um Job na namespace backup que roda um dos scripts de
    backup-ops-scripts, com as credenciais do Vault injetadas e os
    volumes dos saves montados. env_extra: dict de variaveis (JOGO, etc)."""
    import json as _json
    env_list = [{"name": k, "value": v} for k, v in env_extra.items()]
    body = {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": nome, "namespace": "backup"},
        "spec": {
            "backoffLimit": 1,
            "template": {
                "metadata": {"annotations": {
                    "vault.hashicorp.com/agent-inject": "true",
                    "vault.hashicorp.com/role": "backup",
                    "vault.hashicorp.com/agent-inject-secret-restic-password": "wol/data/backup",
                    "vault.hashicorp.com/agent-inject-template-restic-password":
                        '{{- with secret "wol/data/backup" -}}\n{{ index .Data.data "restic-password" }}\n{{- end -}}',
                    "vault.hashicorp.com/agent-inject-secret-rclone-conf-b64": "wol/data/rclone",
                    "vault.hashicorp.com/agent-inject-template-rclone-conf-b64":
                        '{{- with secret "wol/data/rclone" -}}\n{{ index .Data.data "rclone-conf-b64" }}\n{{- end -}}',
                    "vault.hashicorp.com/agent-pre-populate-only": "true",
                }},
                "spec": {
                    "serviceAccountName": "backup-sa",
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": "ops",
                        "image": "restic/restic:latest",
                        "command": ["/bin/sh", "-c"],
                        "args": [f"apk add --no-cache rclone bash coreutils >/dev/null 2>&1 || true; bash /scripts/{script_key}"],
                        "env": env_list,
                        "volumeMounts": [
                            {"name": "scripts", "mountPath": "/scripts"},
                            {"name": "palworld", "mountPath": "/data/palworld"},
                            {"name": "abiotic", "mountPath": "/data/abiotic-factor"},
                            {"name": "valheim", "mountPath": "/data/valheim"},
                        ],
                    }],
                    "volumes": [
                        {"name": "scripts", "configMap": {"name": "backup-ops-scripts", "defaultMode": 493}},
                        {"name": "palworld", "hostPath": {"path": "/var/lib/rancher/palworld", "type": "DirectoryOrCreate"}},
                        {"name": "abiotic", "hostPath": {"path": "/var/lib/rancher/abiotic-factor", "type": "DirectoryOrCreate"}},
                        {"name": "valheim", "hostPath": {"path": "/var/lib/rancher/valheim", "type": "DirectoryOrCreate"}},
                    ],
                },
            },
        },
    }
    url = f"{K8S_API}/apis/batch/v1/namespaces/backup/jobs"
    headers = _k8s_headers(); headers['Content-Type'] = 'application/json'
    r = requests.post(url, headers=headers, data=_json.dumps(body), verify=_k8s_verify(), timeout=8)
    return r.status_code in (200, 201)


# ---- Backup de um jogo especifico ----
@app.route('/backup/game/<game>', methods=['POST'])
@login_required
@admin_required
def backup_game(game):
    if game not in GAMES:
        return '', 404
    ns = GAMES[game]['namespace']
    nome = f"bkp-{ns}-{int(datetime.utcnow().timestamp())}"
    ok = _criar_job_ops(nome, "backup-game.sh", {"JOGO": ns})
    if ok:
        return (f'<p><strong class="status-online">✅ Backup de {GAMES[game]["nome"]} iniciado!</strong></p>'
                '<div hx-get="/backup/status" hx-trigger="load, every 10s" hx-swap="innerHTML"></div>')
    return '<p><strong class="status-offline">Erro ao iniciar backup.</strong></p>'


# ---- Reset de um jogo (backup automatico + apaga save) ----
@app.route('/backup/reset/<game>', methods=['POST'])
@login_required
@admin_required
def reset_game(game):
    if game not in GAMES:
        return '', 404
    ns = GAMES[game]['namespace']
    # Desliga o servidor antes (nao pode apagar save com jogo rodando)
    scale_game(game, 0)
    nome = f"reset-{ns}-{int(datetime.utcnow().timestamp())}"
    ok = _criar_job_ops(nome, "reset-game.sh", {"JOGO": ns})
    if ok:
        return (f'<p><strong class="status-online">✅ Reset de {GAMES[game]["nome"]} iniciado!</strong></p>'
                '<p><small>Backup de seguranca feito + save apagado. '
                'Ligue o servidor para criar o mundo novo.</small></p>'
                '<div hx-get="/backup/status" hx-trigger="load, every 10s" hx-swap="innerHTML"></div>')
    return '<p><strong class="status-offline">Erro ao resetar.</strong></p>'


# ---- Restore: listar snapshots disponiveis de um jogo ----
# Como listar snapshots exige rodar restic, usamos um Job que grava o
# resultado num ConfigMap OU consultamos via um Job de listagem.
# Abordagem simples: o painel dispara um job de listagem que escreve a
# saida nos logs, e o painel le os logs.
@app.route('/backup/list/<game>')
@login_required
@admin_required
def backup_list(game):
    if game not in GAMES:
        return '', 404
    ns = GAMES[game]['namespace']
    # Dispara um job efemero que lista os snapshots em JSON nos logs
    import json as _json
    nome = f"list-{ns}-{int(datetime.utcnow().timestamp())}"
    script = (
        'export RESTIC_PASSWORD="$(cat /vault/secrets/restic-password)"; '
        'mkdir -p ~/.config/rclone; '
        'base64 -d /vault/secrets/rclone-conf-b64 > ~/.config/rclone/rclone.conf; '
        'apk add --no-cache rclone >/dev/null 2>&1 || true; '
        f'restic -o rclone.connections=1 -r rclone:gdrive:wol-backups snapshots '
        f'--tag manual-{ns} --tag pre-reset-{ns} --tag auto-$(date +%Y%m%d) --json 2>/dev/null || '
        f'restic -o rclone.connections=1 -r rclone:gdrive:wol-backups snapshots --json'
    )
    # (a listagem completa e filtrada no painel)
    body = {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": nome, "namespace": "backup"},
        "spec": {"backoffLimit": 0, "ttlSecondsAfterFinished": 120,
            "template": {"metadata": {"annotations": {
                    "vault.hashicorp.com/agent-inject": "true",
                    "vault.hashicorp.com/role": "backup",
                    "vault.hashicorp.com/agent-inject-secret-restic-password": "wol/data/backup",
                    "vault.hashicorp.com/agent-inject-template-restic-password":
                        '{{- with secret "wol/data/backup" -}}\n{{ index .Data.data "restic-password" }}\n{{- end -}}',
                    "vault.hashicorp.com/agent-inject-secret-rclone-conf-b64": "wol/data/rclone",
                    "vault.hashicorp.com/agent-inject-template-rclone-conf-b64":
                        '{{- with secret "wol/data/rclone" -}}\n{{ index .Data.data "rclone-conf-b64" }}\n{{- end -}}',
                    "vault.hashicorp.com/agent-pre-populate-only": "true"}},
                "spec": {"serviceAccountName": "backup-sa", "restartPolicy": "Never",
                    "containers": [{"name": "list", "image": "restic/restic:latest",
                        "command": ["/bin/sh", "-c"], "args": [script]}]}}}}
    url = f"{K8S_API}/apis/batch/v1/namespaces/backup/jobs"
    headers = _k8s_headers(); headers['Content-Type'] = 'application/json'
    requests.post(url, headers=headers, data=_json.dumps(body), verify=_k8s_verify(), timeout=8)
    # Retorna um placeholder que faz polling do resultado
    return (f'<p><small>Buscando backups de {GAMES[game]["nome"]}...</small></p>'
            f'<div hx-get="/backup/list-result/{game}/{nome}" hx-trigger="load delay:6s, every 5s" hx-swap="innerHTML"></div>')


@app.route('/backup/list-result/<game>/<jobname>')
@login_required
@admin_required
def backup_list_result(game, jobname):
    import json as _json
    ns = GAMES[game]['namespace']
    # Le os logs do pod do job de listagem
    url_pods = f"{K8S_API}/api/v1/namespaces/backup/pods?labelSelector=job-name={jobname}"
    r = requests.get(url_pods, headers=_k8s_headers(), verify=_k8s_verify(), timeout=5)
    if r.status_code != 200 or not r.json().get('items'):
        return '<p><small>Ainda buscando...</small></p>'
    pod = r.json()['items'][0]['metadata']['name']
    url_log = f"{K8S_API}/api/v1/namespaces/backup/pods/{pod}/log?container=list"
    rl = requests.get(url_log, headers=_k8s_headers(), verify=_k8s_verify(), timeout=5)
    if rl.status_code != 200 or not rl.text.strip():
        return '<p><small>Ainda buscando...</small></p>'
    # Parse do JSON do restic
    try:
        linha = [l for l in rl.text.splitlines() if l.strip().startswith('[')]
        snaps = _json.loads(linha[-1]) if linha else []
    except Exception:
        return '<p><small>Ainda processando...</small></p>'
    # Filtra snapshots que contem este jogo
    itens = []
    for s in snaps:
        paths = s.get('paths', [])
        if any(f"/data/{ns}" in p for p in paths):
            sid = s.get('short_id', s.get('id', '')[:8])
            tempo = s.get('time', '')[:19].replace('T', ' ')
            tags = ', '.join(s.get('tags', []))
            itens.append((sid, tempo, tags))
    if not itens:
        return '<p><small>Nenhum backup encontrado para este jogo.</small></p>'
    linhas = []
    for sid, tempo, tags in itens[-15:][::-1]:
        linhas.append(
            f'<tr><td>{tempo}</td><td><small>{tags}</small></td>'
            f'<td><form hx-post="/backup/restore/{game}/{sid}" hx-target="#backup-ops-box" '
            f'hx-swap="innerHTML" hx-confirm="Restaurar {GAMES[game]["nome"]} do backup de {tempo}? '
            f'O save atual sera substituido.">'
            f'<button class="outline" style="padding:0.1rem 0.5rem;margin:0;">Restaurar</button>'
            f'</form></td></tr>')
    return ('<table style="font-size:0.82rem;"><thead><tr><th>Data/Hora</th><th>Tag</th><th></th></tr></thead>'
            '<tbody>' + ''.join(linhas) + '</tbody></table>')


# ---- Restore de um jogo a partir de um snapshot ----
@app.route('/backup/restore/<game>/<snapshot>', methods=['POST'])
@login_required
@admin_required
def restore_game(game, snapshot):
    if game not in GAMES:
        return '', 404
    ns = GAMES[game]['namespace']
    # Desliga o servidor antes de restaurar
    scale_game(game, 0)
    nome = f"restore-{ns}-{int(datetime.utcnow().timestamp())}"
    ok = _criar_job_ops(nome, "restore-game.sh", {"JOGO": ns, "SNAPSHOT_ID": snapshot})
    if ok:
        return (f'<p><strong class="status-online">✅ Restore de {GAMES[game]["nome"]} iniciado!</strong></p>'
                f'<p><small>Restaurando snapshot {snapshot}. '
                'Ligue o servidor quando concluir.</small></p>'
                '<div hx-get="/backup/status" hx-trigger="load, every 10s" hx-swap="innerHTML"></div>')
    return '<p><strong class="status-offline">Erro ao restaurar.</strong></p>'
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
