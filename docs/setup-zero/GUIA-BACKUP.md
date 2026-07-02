# Sistema de Backup — saves dos jogos + Vault para Google Drive

Backup INCREMENTAL (so a diferenca) com restic, enviado ao Google Drive via
rclone, cifrado. Diario automatico (CronJob) + botao manual no painel.
Retencao: 7 dias.

## Por que restic + rclone

- restic: backup incremental (so blocos que mudaram), dedup, compressao,
  criptografia, snapshots (restaurar "de N dias atras")
- rclone: conecta o restic ao Google Drive (OAuth)
- Resultado: backups pequenos, cifrados, versionados, na sua conta Drive

## O que e salvo

- /var/lib/rancher/palworld     (saves Palworld)
- /var/lib/rancher/abiotic-factor (saves Abiotic)
- /var/lib/rancher/valheim      (mundos Valheim)
- Vault: export dos segredos (KV wol/*) — ver secao Vault abaixo

====================================================================
PARTE A — Configurar o rclone com Google Drive (UMA VEZ, interativo)
====================================================================

Isso e feito no i9, uma vez. Gera um token OAuth do Drive.

## A.1 Instalar rclone e restic
```
sudo apt install -y rclone restic
```

## A.2 Configurar o remote do Drive
```
rclone config
```
Responda:
- n (new remote)
- name> gdrive
- Storage> drive   (Google Drive)
- client_id> (deixe vazio - ENTER; opcionalmente crie um no Google Cloud
  Console para nao usar o compartilhado, mais rapido)
- client_secret> (vazio - ENTER)
- scope> 1 (Full access) ou 3 (drive.file - so arquivos criados pelo rclone;
  RECOMENDADO por seguranca: 3)
- root_folder_id> (vazio)
- service_account_file> (vazio)
- Edit advanced config> n
- Use auto config> Y (abre o navegador para autorizar) 
  -> se estiver headless/SSH, use N e siga o link manualmente
- Autorize na conta Google
- Configure this as a team drive> n
- y (confirma)
- q (quit config)

## A.3 Testar
```
rclone mkdir gdrive:wol-backups
rclone lsd gdrive:
```
> Deve listar a pasta wol-backups no seu Drive.

## A.4 Pegar o conteudo do rclone.conf (vai para o Vault)
```
cat ~/.config/rclone/rclone.conf
```
Guarde esse conteudo - vamos por no Vault na Parte B.

====================================================================
PARTE B — Guardar credenciais no Vault
====================================================================

O CronJob precisa do rclone.conf e da senha do restic. Guardamos no Vault
(mesma estrutura KV wol/ que voce ja usa).

```
export VT=<token-vault>

# Senha de criptografia do restic (ESCOLHA uma forte e GUARDE no Bitwarden!)
# Sem ela, os backups NAO podem ser restaurados.
kubectl exec -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault kv put wol/backup \
  restic-password='ESCOLHA_SENHA_FORTE_AQUI'"

# O rclone.conf inteiro (cole o conteudo do cat da Parte A.4)
# Use um arquivo temporario para nao quebrar com aspas:
kubectl exec -i -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault kv put wol/rclone rclone-conf=@-" < ~/.config/rclone/rclone.conf
```

> A senha do restic e CRITICA: sem ela nao ha restore. Guarde no Bitwarden.

====================================================================
PARTE C — Aplicar o CronJob e o backup manual
====================================================================

Os manifestos estao em k8s/backup/ (ver arquivos gerados):
- cronjob-backup.yaml   (diario 3h)
- rbac-backup.yaml      (ServiceAccount + acesso ao Vault)
- backup-script ConfigMap (o script que roda)

```
# criar SA e role no Vault para o backup ler wol/backup e wol/rclone
kubectl apply -f k8s/backup/namespace.yaml
export VT=<token-vault>
# policy que le os secrets de backup
kubectl exec -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault policy write backup - <<POL
path \"wol/data/backup\" { capabilities = [\"read\"] }
path \"wol/data/rclone\" { capabilities = [\"read\"] }
path \"wol/data/palworld\" { capabilities = [\"read\"] }
path \"wol/data/abiotic-factor\" { capabilities = [\"read\"] }
path \"wol/data/valheim\" { capabilities = [\"read\"] }
POL"
kubectl create serviceaccount backup-sa -n backup
kubectl exec -n vault vault-0 -- sh -c "VAULT_TOKEN=$VT vault write auth/kubernetes/role/backup \
  bound_service_account_names=backup-sa \
  bound_service_account_namespaces=backup \
  policies=backup ttl=1h"

kubectl apply -f k8s/backup/
```

## Testar o backup manual JA
```
kubectl create job -n backup backup-manual-teste --from=cronjob/wol-backup
kubectl logs -n backup job/backup-manual-teste -f
```

====================================================================
PARTE D — RESTORE (o que faltou desta vez!)
====================================================================

Ver GUIA-RESTORE.md. Resumo:
```
# listar snapshots
restic -r rclone:gdrive:wol-backups snapshots
# restaurar um snapshot para uma pasta
restic -r rclone:gdrive:wol-backups restore <snapshot-id> --target /tmp/restore
# copiar os saves de volta para o disco do jogo
```

## Vault no backup
O script tambem exporta os segredos do Vault (KV wol/*) e inclui no backup,
para nao perder as senhas dos jogos num desastre.
