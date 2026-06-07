import json
import os
import re
import subprocess
from datetime import datetime
from functools import wraps

import wakeonlan
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']

USERNAME = os.environ['USERNAME']
PASSWORD = os.environ['PASSWORD']
PC_MAC = os.environ['PC_MAC']
PC_LOCAL_IP = os.environ['PC_LOCAL_IP']
REGISTER_TOKEN = os.environ.get('REGISTER_TOKEN', '')

WAKING_TIMEOUT = 300

STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')


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
    result = subprocess.run(
        ['ping', '-c', '1', '-W', '1', PC_LOCAL_IP],
        capture_output=True,
    )
    return result.returncode == 0


def get_tunnel_url():
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'wol-tunnel', '--no-pager', '-o', 'cat'],
            capture_output=True, text=True, timeout=5
        )
        matches = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', result.stdout)
        if matches:
            return matches[-1]
    except Exception:
        pass
    return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == USERNAME and request.form['password'] == PASSWORD:
            session['user'] = USERNAME
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
    tunnel_url = get_tunnel_url()
    return render_template('dashboard.html', tunnel_url=tunnel_url)


@app.route('/status-fragment')
@login_required
def status_fragment():
    online = pc_online()
    state = load_state()
    waking = not online and is_waking(state)
    return render_template('_status.html', online=online, waking=waking, state=state)


@app.route('/wol', methods=['POST'])
@login_required
def wol():
    wakeonlan.send_magic_packet(PC_MAC)
    state = load_state()
    state['waking'] = True
    state['waking_since'] = datetime.utcnow().isoformat()
    save_state(state)
    return ''


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
    app.run(host='0.0.0.0', port=5000)
