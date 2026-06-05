import json
import os
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

STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'ip': None, 'services': [], 'last_seen': None}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def pc_online():
    result = subprocess.run(
        ['ping', '-c', '1', '-W', '1', PC_LOCAL_IP],
        capture_output=True,
    )
    return result.returncode == 0


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
    return render_template('dashboard.html')


@app.route('/status-fragment')
@login_required
def status_fragment():
    online = pc_online()
    state = load_state()
    return render_template('_status.html', online=online, state=state)


@app.route('/wol', methods=['POST'])
@login_required
def wol():
    wakeonlan.send_magic_packet(PC_MAC)
    return '<span class="wol-sent">Pacote WoL enviado. Aguardando PC ligar...</span>'


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    state = {
        'ip': data.get('ip'),
        'services': data.get('services', []),
        'last_seen': datetime.utcnow().isoformat(),
    }
    save_state(state)
    return {'ok': True}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
