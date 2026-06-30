# Gerenciamento de segredos com Vault

Os segredos dos game servers (senhas) sao guardados no **Vault** e injetados
nos pods via **Vault Agent Injector**, em vez de `kubectl set env` manual ou
senha no Git. Assim o ArgoCD pode sincronizar sem apagar a senha.

## Arquitetura

```
Vault (KV v2 em wol/)
   └── wol/abiotic-factor { server-password: tico }
          │
          │ (policy: permite ler) + (role: liga ServiceAccount->policy)
          ▼
   Kubernetes auth (valida o ServiceAccount do pod)
          │
          ▼
   Vault Agent Injector (init container no pod)
          │ le o segredo e escreve em /vault/secrets/server-password
          ▼
   Container do jogo (wrapper monta o 'args' com a senha e inicia)
```

## Componentes configurados (uma vez)

1. **Secrets engine KV v2** montado em `wol/`
2. **Kubernetes auth** habilitado:
   ```
   vault auth enable kubernetes
   vault write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc:443
   ```
3. **Agent Injector** rodando no namespace vault (vault-agent-injector)

## Estrutura por jogo

Para cada jogo, 3 coisas no Vault + annotations no deployment:

### No Vault
- Secret: `wol/<jogo>` com a chave `server-password`
- Policy `<jogo>`: permite `read` em `wol/data/<jogo>` (KV v2 usa /data/ no path!)
- Role `<jogo>`: liga o ServiceAccount `<jogo>-sa` (namespace do jogo) a policy

### No deployment (annotations)
```yaml
annotations:
  vault.hashicorp.com/agent-inject: "true"
  vault.hashicorp.com/role: "<jogo>"
  vault.hashicorp.com/agent-inject-secret-server-password: "wol/data/<jogo>"
  vault.hashicorp.com/agent-inject-template-server-password: |
    {{- with secret "wol/data/<jogo>" -}}
    {{ index .Data.data "server-password" }}
    {{- end -}}
  vault.hashicorp.com/agent-pre-populate-only: "true"
spec:
  serviceAccountName: <jogo>-sa
```

> ATENCAO ao template: chave com hifen (server-password) DEVE usar
> `{{ index .Data.data "server-password" }}`. Usar `.Data.data.server-password`
> quebra com erro "bad character U+002D" (o hifen vira operador de subtracao
> no Go template). Ver post-mortem incidente 19.

### No container (wrapper)
O container le a senha do arquivo e monta o args antes de iniciar:
```yaml
command: ["/bin/bash", "-c"]
args:
  - |
    SENHA="$(cat /vault/secrets/server-password)"
    export args="... -ServerPassword=${SENHA}"
    exec /entrypoint.sh
```

## Adicionar segredo de um NOVO jogo

Use o script `scripts/add-game-secret.sh` (ver abaixo) ou manualmente:

```
export VT=<token-vault>   # token com permissao

# 1. Guardar a senha
kubectl exec -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault kv put wol/<jogo> server-password=<senha>"

# 2. Criar a policy
kubectl exec -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault policy write <jogo> - <<POL
path \"wol/data/<jogo>\" {
  capabilities = [\"read\"]
}
POL"

# 3. ServiceAccount + role
kubectl create serviceaccount <jogo>-sa -n <jogo>
kubectl exec -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault write auth/kubernetes/role/<jogo> \
  bound_service_account_names=<jogo>-sa \
  bound_service_account_namespaces=<jogo> \
  policies=<jogo> ttl=24h"
```

Depois adicionar as annotations + wrapper no deployment (ver acima).

## Verificacao / troubleshooting

```
# Senha injetada no pod?
kubectl exec -n <jogo> deployment/<deploy> -c <container> -- cat /vault/secrets/server-password

# Log do init container do Vault (erros de template/auth aparecem aqui)
kubectl logs -n <jogo> deployment/<deploy> -c vault-agent-init

# Vault unsealed?
kubectl exec -n vault vault-0 -- vault status
```

## Token do Vault

O token usado para administrar (criar policies/roles) e separado dos tokens
que os pods recebem (curtos, via role). Para operacoes administrativas, use um
token com permissao adequada. Tokens podem ser revogados/rotacionados:
```
vault token revoke <token>
```
