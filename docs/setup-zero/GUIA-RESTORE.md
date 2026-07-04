# GUIA DE RESTORE — como recuperar saves de um backup

Este e o guia que FALTOU no incidente da perda de dados. Com o backup restic
no Google Drive, recuperar um save e simples.

## Pre-requisitos
- rclone configurado (remote gdrive) - ver GUIA-BACKUP.md Parte A
- restic instalado
- A senha do restic (do Vault wol/backup ou do seu Bitwarden)

## 1. Configurar acesso ao repositorio
```
export RESTIC_PASSWORD='<senha-do-restic>'
REPO="rclone:gdrive:wol-backups"
```

## 2. Listar os backups disponiveis
```
restic -r "$REPO" snapshots
```
Mostra data/hora e ID de cada snapshot. Ex:
```
ID        Time                 Tags
a1b2c3d4  2026-07-02 03:00:00  auto-20260702
e5f6g7h8  2026-07-01 03:00:00  auto-20260701
```

## 3. Ver o que tem num snapshot (opcional)
```
restic -r "$REPO" ls a1b2c3d4
```

## 4. Restaurar um snapshot para uma pasta temporaria
```
restic -r "$REPO" restore a1b2c3d4 --target /tmp/restore
```
Os arquivos aparecem em /tmp/restore/data/palworld, etc.

## 5. Restaurar apenas UM jogo (ex: so o Valheim)
```
restic -r "$REPO" restore a1b2c3d4 --target /tmp/restore --include /data/valheim
```

## 6. Colocar os saves de volta no lugar
```
# Pare o servidor do jogo antes (evita sobrescrever com o jogo rodando)
kubectl scale deployment/valheim-server -n valheim --replicas=0

# Copie os saves restaurados de volta
sudo cp -a /tmp/restore/data/valheim/* /var/lib/rancher/valheim/
sudo chown -R 1000:1000 /var/lib/rancher/valheim

# Religue o servidor
kubectl scale deployment/valheim-server -n valheim --replicas=1
```

## 7. Restaurar os segredos do Vault (se necessario)
Os JSONs exportados estao em /tmp/restore/tmp/vault-export/.
```
export VT=<token-vault>
# Exemplo: restaurar a senha do palworld
cat /tmp/restore/tmp/vault-export/palworld.json
# reinserir com: vault kv put wol/palworld server-password=<valor-do-json>
```

## TESTE DE RESTORE (faca isso 1x por mes!)

A licao mais importante: um backup so vale se voce JA TESTOU restaurar.
Uma vez por mes, restaure um snapshot para /tmp e confira que os arquivos
estao la. Nao espere um desastre para descobrir que o backup estava quebrado.

```
restic -r "$REPO" restore latest --target /tmp/teste-restore
ls -la /tmp/teste-restore/data/*/
rm -rf /tmp/teste-restore
```

## IMPORTANTE — parametro obrigatorio no i9

Ao restaurar/listar do i9, use SEMPRE `-o rclone.connections=1`, senao o restic
da timeout com o Google Drive:

restic -o rclone.connections=1 -r rclone:gdrive:wol-backups snapshots
restic -o rclone.connections=1 -r rclone:gdrive:wol-backups restore latest --target /tmp/restore
Descoberto no incidente 21 (recuperacao). Sem esse parametro:
"context deadline exceeded".
