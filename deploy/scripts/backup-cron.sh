#!/bin/sh
# Loop interno do servico pgbackups: dump diario + retencao.
set -eu
RETENTION_DAYS="${RETENTION_DAYS:-14}"
while :; do
  TS=$(date +%Y%m%d-%H%M%S)
  OUT="/backups/portal_uma-${TS}.dump"
  if pg_dump -Fc -h db -U "$POSTGRES_USER" "$POSTGRES_DB" > "$OUT.tmp" 2>/dev/null; then
    mv "$OUT.tmp" "$OUT"
    echo "[backup] gravado $OUT"
  else
    rm -f "$OUT.tmp"
    echo "[backup] FALHOU em $TS" >&2
  fi
  find /backups -name 'portal_uma-*.dump' -mtime "+${RETENTION_DAYS}" -delete
  # proxima execucao em ~24h
  sleep 86400
done
