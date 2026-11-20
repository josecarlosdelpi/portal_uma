#!/usr/bin/env bash
# Verificacao de saude: containers, API e banco.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.vps.yml --env-file .env"
$COMPOSE ps
echo ">> API interna"
$COMPOSE exec -T backend python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"
echo ">> banco"
$COMPOSE exec -T db pg_isready
