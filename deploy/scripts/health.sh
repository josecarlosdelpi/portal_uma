#!/usr/bin/env bash
# Verificacao de saude: containers, API e banco.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-portal-uma}"
COMPOSE="docker compose -p ${PROJECT} -f docker-compose.vps.yml --env-file "${ENV_FILE:-.env}""
$COMPOSE ps
echo ">> API interna"
ok=""
for i in $(seq 1 30); do
  if $COMPOSE exec -T backend python -c \
      "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')" \
      >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[ -n "$ok" ] || { echo "!! backend sem resposta apos 60s"; exit 1; }
echo "API respondendo (health OK)"
echo ">> banco"
$COMPOSE exec -T db pg_isready
