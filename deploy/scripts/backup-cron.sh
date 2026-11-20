#!/bin/sh
# Loop do servico pgbackups: dump diario via TCP autenticado + retencao.
# PGPASSWORD vem do ambiente do servico (deploy/.env); nada em CLI/log.
set -u
RETENTION_DAYS="${RETENTION_DAYS:-14}"

run_backup() {
  TS=$(date +%Y%m%d-%H%M%S)
  OUT="/backups/portal_uma-${TS}.dump"
  if pg_dump -Fc -h db -U "$POSTGRES_USER" "$POSTGRES_DB" > "$OUT.tmp" 2>/tmp/dump.err; then
    if [ -s "$OUT.tmp" ]; then
      mv "$OUT.tmp" "$OUT"
      echo "[backup] gravado $OUT ($(wc -c < "$OUT") bytes)"
      return 0
    fi
  fi
  rm -f "$OUT.tmp"
  echo "[backup] FALHOU em $TS: $(tail -1 /tmp/dump.err)" >&2
  return 1
}

# primeiro dump logo no arranque (valida a configuracao cedo)
run_backup || true
while :; do
  sleep 86400
  run_backup || true
  find /backups -name 'portal_uma-*.dump' -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
done
