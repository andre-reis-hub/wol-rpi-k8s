#!/usr/bin/env bash
# add-game-secret.sh - configura o segredo (senha) de um game server no Vault
#
# Uso:
#   export VT=<token-vault-admin>
#   ./add-game-secret.sh <jogo> <senha>
#
# Exemplo:
#   ./add-game-secret.sh valheim minhaSenha123
#
# O <jogo> deve ser o nome do namespace do jogo (ex: palworld, abiotic-factor).
# Cria: secret KV, policy, ServiceAccount <jogo>-sa e role no Kubernetes auth.

set -euo pipefail

JOGO="${1:-}"
SENHA="${2:-}"

if [[ -z "$JOGO" || -z "$SENHA" ]]; then
  echo "Uso: $0 <jogo> <senha>"
  echo "Lembre de exportar VT com um token do Vault antes."
  exit 1
fi

if [[ -z "${VT:-}" ]]; then
  echo "ERRO: variavel VT (token do Vault) nao definida."
  echo "Rode: export VT=<seu-token-vault>"
  exit 1
fi

VPOD="vault-0"
VNS="vault"

echo "==> 1/4 Guardando a senha em wol/$JOGO ..."
kubectl exec -n "$VNS" "$VPOD" -- sh -c \
  "VAULT_TOKEN=$VT vault kv put wol/$JOGO server-password=$SENHA"

echo "==> 2/4 Criando policy '$JOGO' ..."
kubectl exec -n "$VNS" "$VPOD" -- sh -c "VAULT_TOKEN=$VT vault policy write $JOGO - <<POL
path \"wol/data/$JOGO\" {
  capabilities = [\"read\"]
}
POL"

echo "==> 3/4 Criando ServiceAccount '$JOGO-sa' no namespace '$JOGO' ..."
kubectl create serviceaccount "$JOGO-sa" -n "$JOGO" --dry-run=client -o yaml | kubectl apply -f -

echo "==> 4/4 Criando role '$JOGO' no Kubernetes auth ..."
kubectl exec -n "$VNS" "$VPOD" -- sh -c "VAULT_TOKEN=$VT vault write auth/kubernetes/role/$JOGO \
  bound_service_account_names=$JOGO-sa \
  bound_service_account_namespaces=$JOGO \
  policies=$JOGO ttl=24h"

echo ""
echo "PRONTO! Agora adicione no deployment de $JOGO:"
echo "  - serviceAccountName: $JOGO-sa"
echo "  - as annotations do Vault Agent (ver docs/vault-secrets.md)"
echo "  - o wrapper que le /vault/secrets/server-password e monta o args"
