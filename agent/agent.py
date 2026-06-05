#!/usr/bin/env python3
import json
import logging
import os
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

PANEL_URL = os.environ['PANEL_URL']
REGISTER_TOKEN = os.environ['REGISTER_TOKEN']
INTERVAL = int(os.environ.get('INTERVAL', '60'))
KUBECONFIG = os.environ.get('KUBECONFIG', os.path.expanduser('~/.kube/config'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def get_public_ip():
    try:
        r = requests.get('https://api.ipify.org', timeout=5)
        return r.text.strip()
    except Exception as e:
        log.warning(f'Falha ao obter IP público: {e}')
        return None


def get_k8s_services():
    try:
        env = {**os.environ, 'KUBECONFIG': KUBECONFIG}
        result = subprocess.run(
            ['kubectl', 'get', 'services', '-A', '-o', 'json'],
            capture_output=True, text=True, timeout=10, env=env,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        services = []
        for item in data.get('items', []):
            if item['spec'].get('type') != 'NodePort':
                continue
            labels = item['metadata'].get('labels', {})
            nome = (
                labels.get('app.kubernetes.io/name') or
                labels.get('app') or
                item['metadata']['name']
            ).capitalize()
            for port in item['spec'].get('ports', []):
                node_port = port.get('nodePort')
                if node_port:
                    services.append({'nome': nome, 'porta': node_port})
        return services
    except FileNotFoundError:
        log.info('kubectl não encontrado — K8s ainda não configurado')
        return []
    except Exception as e:
        log.warning(f'Falha ao consultar K8s: {e}')
        return []


def register(ip, services):
    payload = {'ip': ip, 'services': services}
    headers = {'Authorization': f'Bearer {REGISTER_TOKEN}'}
    try:
        r = requests.post(
            f'{PANEL_URL}/api/register',
            json=payload,
            headers=headers,
            timeout=5,
        )
        r.raise_for_status()
        log.info(f'Registrado: ip={ip}, serviços={len(services)}')
    except Exception as e:
        log.warning(f'Falha ao registrar no painel: {e}')


def main():
    log.info('Agente WoL iniciado')
    while True:
        ip = get_public_ip()
        services = get_k8s_services()
        if ip:
            register(ip, services)
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
