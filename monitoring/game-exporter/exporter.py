import os
import re
import time
from datetime import datetime, timedelta

import requests
import urllib3
from prometheus_client import start_http_server, Gauge

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SA_DIR = '/var/run/secrets/kubernetes.io/serviceaccount'
K8S_API = os.environ.get('K8S_API', 'https://kubernetes.default.svc')
K8S_CA_CERT = os.environ.get('K8S_CA_CERT', f'{SA_DIR}/ca.crt')
LOKI_URL = os.environ.get('LOKI_URL', 'http://loki.monitoring.svc:3100')
LOKI_WINDOW_HOURS = int(os.environ.get('LOKI_WINDOW_HOURS', '12'))
PALWORLD_API_URL = os.environ.get('PALWORLD_API_URL', '')
PALWORLD_API_USER = os.environ.get('PALWORLD_API_USER', 'admin')
PALWORLD_API_PASS = os.environ.get('PALWORLD_API_PASS', '')
SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL', '30'))
EXPORTER_PORT = int(os.environ.get('EXPORTER_PORT', '9109'))

GAMES = {
    'palworld': {
        'namespace': 'palworld', 'deployment': 'palworld-server',
        'fonte_players': 'rest',
        'log_join': 'joined the server', 'log_leave': 'left the server',
        'log_name_regex': r'(\w[\w .-]*) joined the server',
        'log_leave_name_regex': r'(\w[\w .-]*) left the server',
    },
    'abiotic-factor': {
        'namespace': 'abiotic-factor', 'deployment': 'abiotic-factor-server',
        'fonte_players': 'loki',
        'log_join': 'entered the facility', 'log_leave': 'exited the facility',
        'log_name_regex': r'CHAT LOG:\s+(.+?) has entered the facility',
        'log_leave_name_regex': r'CHAT LOG:\s+(.+?) has exited the facility',
    },
    'valheim': {
        'namespace': 'valheim', 'deployment': 'valheim-server',
        'fonte_players': 'loki_valheim',
    },
}

def _read_token():
    t = os.environ.get('K8S_TOKEN', '')
    if t:
        return t
    try:
        with open(f'{SA_DIR}/token') as f:
            return f.read().strip()
    except Exception:
        return ''

def _headers():
    return {'Authorization': f'Bearer {_read_token()}'}

def _verify():
    return K8S_CA_CERT if os.path.exists(K8S_CA_CERT) else False

def get_replicas(game):
    g = GAMES[game]
    try:
        url = f"{K8S_API}/apis/apps/v1/namespaces/{g['namespace']}/deployments/{g['deployment']}"
        r = requests.get(url, headers=_headers(), verify=_verify(), timeout=4)
        if r.status_code == 200:
            return r.json().get('spec', {}).get('replicas', 0)
    except Exception:
        pass
    return None

def _loki_range(logql, hours):
    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        params = {'query': logql, 'start': str(int(start.timestamp() * 1e9)),
                  'end': str(int(end.timestamp() * 1e9)), 'limit': '2000', 'direction': 'forward'}
        r = requests.get(f'{LOKI_URL}/loki/api/v1/query_range', params=params, timeout=6)
        if r.status_code == 200:
            return r.json().get('data', {}).get('result', [])
    except Exception:
        pass
    return None

def palworld_players():
    if not PALWORLD_API_URL:
        return None
    try:
        r = requests.get(f'{PALWORLD_API_URL}/v1/api/players',
                         auth=(PALWORLD_API_USER, PALWORLD_API_PASS), timeout=4)
        if r.status_code == 200:
            return [p.get('name', '?') for p in r.json().get('players', [])]
    except Exception:
        pass
    return None

def loki_players(game):
    g = GAMES[game]
    logql = f'{{namespace="{g["namespace"]}"}} |~ "{g["log_join"]}|{g["log_leave"]}"'
    res = _loki_range(logql, LOKI_WINDOW_HOURS)
    if res is None:
        return None
    rj = re.compile(g['log_name_regex'])
    rl = re.compile(g['log_leave_name_regex'])
    ev = []
    for s in res:
        for ts, line in s.get('values', []):
            mj = rj.search(line)
            ml = rl.search(line)
            if mj:
                ev.append((int(ts), mj.group(1).strip(), 'in'))
            elif ml:
                ev.append((int(ts), ml.group(1).strip(), 'out'))
    ev.sort(key=lambda e: e[0])
    st = {}
    for _, nome, tipo in ev:
        st[nome] = (tipo == 'in')
    return [n for n, on in st.items() if on]

def valheim_players():
    logql = ('{namespace="valheim"} |~ '
             '"Got connection SteamID|Got character ZDOID from|Closing socket"')
    res = _loki_range(logql, LOKI_WINDOW_HOURS)
    if res is None:
        return None
    r_sid = re.compile(r'Got connection SteamID (\d+)')
    r_char = re.compile(r'Got character ZDOID from (.+?) :')
    r_close = re.compile(r'Closing socket (\d+)')
    ev = []
    for s in res:
        for ts, line in s.get('values', []):
            ev.append((int(ts), line))
    ev.sort(key=lambda x: x[0])
    online = {}
    last = None
    for _, line in ev:
        a = r_sid.search(line)
        b = r_char.search(line)
        c = r_close.search(line)
        if a:
            online[a.group(1)] = None
            last = a.group(1)
        elif b:
            if last:
                online[last] = b.group(1).strip()
                last = None
        elif c:
            online.pop(c.group(1), None)
    return [n for n in online.values() if n]

def players_for(game):
    """Retorna (qtd, ok). ok=False = detecção falhou (NÃO confiar no zero)."""
    g = GAMES[game]
    if g['fonte_players'] == 'rest':
        p = palworld_players()
    elif g['fonte_players'] == 'loki_valheim':
        p = valheim_players()
    else:
        p = loki_players(game)
    if p is None:
        return 0, False
    return len(p), True

m_players = Gauge('game_players_online', 'Jogadores online por jogo', ['game'])
m_up = Gauge('game_server_up', 'Servidor ligado (replicas>0)', ['game'])
m_ok = Gauge('game_detection_ok', 'Deteccao funcionou (1) ou falhou (0)', ['game'])

def collect():
    for game in GAMES:
        rep = get_replicas(game)
        up = 1 if (rep or 0) > 0 else 0
        m_up.labels(game=game).set(up)
        if up:
            qtd, ok = players_for(game)
            m_players.labels(game=game).set(qtd)
            m_ok.labels(game=game).set(1 if ok else 0)
        else:
            m_players.labels(game=game).set(0)
            m_ok.labels(game=game).set(1)

if __name__ == '__main__':
    start_http_server(EXPORTER_PORT)
    print(f'game-exporter ouvindo em :{EXPORTER_PORT}')
    while True:
        try:
            collect()
        except Exception as e:
            print('erro na coleta:', e)
        time.sleep(SCRAPE_INTERVAL)
