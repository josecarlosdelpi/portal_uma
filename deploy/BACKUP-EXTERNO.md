# Backup externo — destino protegido fora da VPS

Os dumps locais (`deploy/backups/*.dump`) cobrem falhas de aplicacao e
restores rapidos, mas **nao protegem contra perda da VPS inteira**.
Copie-os para armazenamento externo — a escolha depende do seu provedor.

## Opcao A — Object storage S3-compativel (rclone)

```bash
# uma vez: configure o remote (Backblaze B2, Wasabi, AWS S3, Cloudflare R2)
rclone config create uma-backups s3 provider=Other \
  env_auth=false access_key_id=XXXX secret_access_key=YYYY \
  endpoint=https://s3.regiao.exemplo.com

# diario (cron do host ou systemd timer):
rclone sync /opt/portal_uma/deploy/backups uma-backups:portal-uma \
  --include 'portal_uma-*.dump' --include 'pre-*.dump' \
  --s3-upload-cutoff 0 --retries 3
```

Guarde as credenciais do remote em `/root/.config/rclone/rclone.conf`
(modo 600), fora do repositorio e fora dos containers.

## Opcao B — SSH/rsync para outro servidor ou NAS

```bash
rsync -a --delete-after /opt/portal_uma/deploy/backups/ \
  usuario@backup.exemplo:/backups/portal-uma/ \
  -e "ssh -i /root/.ssh/backup_ed25519 -o BatchMode=yes"
```

## Retencao e teste

- Retencao local: `BACKUP_RETENTION_DAYS` (padrao 14 dias) no `.env`.
- Retencao remota: politica de lifecycle/versioning do bucket ou
  rotacao no destino — configure conforme o provedor.
- **Teste o restore trimestralmente**: baixe um dump e rode
  `bash deploy/scripts/restore.sh <arquivo>` em ambiente descartavel
  (`PROJECT`+`HTTP_PORT`/`HTTPS_PORT` alternativos).

## O que NAO versionar / NAO expor

- `deploy/backups/*.dump` contem dados reais — nunca commitar nem enviar
  para destino publico.
- Credenciais do remote (rclone.conf, chaves SSH) fora do Git.
