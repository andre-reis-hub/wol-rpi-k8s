import json
import os
import re
import subprocess
from datetime import datetime
from functools import wraps

import requests
import urllib3
import wakeonlan
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

try:
    import a2s
    A2S_AVAILABLE = True
except ImportError:
    A2S_AVAILABLE = False

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

K8S_API = os.environ.get('K8S_API', 'https://192.168.15.14:6443')
K8S_TOKEN = os.environ.get('K8S_TOKEN', '')
K8S_CA_CERT = os.environ.get('K8S_CA_CERT', '')

WAKING_TIMEOUT = 300
STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')

# Catalogo de jogos. query_host/query_port usados para A2S (Steam Query).
# A query e feita no IP LOCAL do i9 (o RPi esta na mesma rede).
GAMES = {
    'palworld': {
        'nome': 'Palworld',
        'emoji': '🎮',
        'namespace': 'palworld',
        'deployment': 'palworld-server',
        'porta_conexao': 30211,
        'query_port': 30015,
    },
    'abiotic-factor': {
        'nome': 'Abiotic Factor',
        'emoji': '🧪',
        'namespace': 'abiotic-factor',
        'deployment': 'abiotic-factor-server',
        'porta_conexao': 30777,
        'query_port': 30016,
    },
}


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


def get_a2s_info(game):
    """Consulta Steam Query (A2S) na porta de query do jogo.
    Retorna dict com players/max_players/server_name ou None."""
    if not A2S_AVAILABLE:
        return None
    g = GAMES[game]
    try:
        addr = (PC_LOCAL_IP, g['query_port'])
        info = a2s.info(addr, timeout=3)
        return {
            'players': info.player_count,
            'max_players': info.max_players,
            'server_name': info.server_name,
        }
    except Exception:
        return None


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
    return render_template('dashboard.html', games=GAMES, tunnel_url=get_tunnel_url())


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
    info = get_a2s_info(game) if (online and ligado) else None
    endereco = f"{PUBLIC_HOST}:{g['porta_conexao']}"
    is_admin = session.get('role') == 'admin'
    return render_template(
        '_game.html',
        game=game, g=g, online=online, ligado=ligado,
        info=info, endereco=endereco, is_admin=is_admin,
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
            capture_output=True, text=True, timeout=10,
        )
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
    state = {
        'ip': data.get('ip'),
        'services': data.get('services', []),
        'last_seen': datetime.utcnow().isoformat(),
        'waking': False,
        'waking_since': None,
    }
    save_state(state)
    return {'ok': True}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
