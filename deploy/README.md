# Portal UMA — Deploy em VPS Linux (producao)

Stack: Caddy (HTTPS automatico) -> Nginx (React) -> FastAPI -> PostgreSQL 16.
Somente as portas HTTP/HTTPS do Caddy sao publicas; banco e API nao tem
mapeamento de porta no host.

## Pre-requisitos

- Linux x86_64, Docker Engine + plugin `docker compose` (v2)
- 2 vCPU / 4 GB RAM / 40 GB disco (recomendado)
- Portas 80 e 443 liberadas; DNS do dominio apontando para a VPS

## Valores em `deploy/.env`

| Variavel | Origem |
|---|---|
| `DOMAIN` | dominio publico (ex.: portal.universodasmangueiras.com.br) |
| `POSTGRES_PASSWORD` | gerada no install (min. 16 chars; exemplo e rejeitado) |
| `GOOGLE_DRIVE_FOLDER_ID` | pasta do Drive com os CSVs do ERP |
| `DRIVE_SA_FILE` | JSON da conta de servico do Google (arquivo local) |
| `ENFORCE_SUPERADMIN_MFA` | `true` = enrolment TOTP obrigatorio no 1o acesso |
| `BACKUP_RETENTION_DAYS` | dias de retencao dos dumps (padrao 14) |

## Instalacao inicial (ordem testada)

```bash
cd deploy
cp .env.example .env
mkdir -p secrets && chmod 700 secrets
cp /caminho/uma-drive-sa.json secrets/
bash scripts/install.sh
```

`install.sh` valida `.env` (rejeita senha de exemplo/ausente/fraca),
sobe **somente o banco**, executa as migrations (`alembic upgrade head`)
e **depois** sobe backend/frontend/Caddy/backups — o sincronizador ERP
nunca roda contra um banco sem schema.

### Primeiro SuperAdmin (banco novo)

```bash
docker compose -p portal-uma -f deploy/docker-compose.vps.yml \
  --env-file deploy/.env exec backend \
  env UMA_CONFIRM_INITIAL_SUPERADMIN=I_UNDERSTAND_ONE_TIME \
      UMA_INITIAL_SUPERADMIN_USERNAME=seu.login \
      UMA_INITIAL_SUPERADMIN_NAME="Seu Nome" \
      python -m app.bootstrap_local
```

Com `ENFORCE_SUPERADMIN_MFA=true`: 1o login com senha temporaria gera
sessao limitada -> troca de senha -> **enrolment TOTP obrigatorio** ->
novo login com senha + codigo. Sem bypass possivel pela UI.

## Operacao

```bash
bash scripts/update.sh        # pull + backup + build + stop app + migrate + restart + health
bash scripts/migrate.sh       # backup -> stop backend -> upgrade head -> start
bash scripts/health.sh        # containers + API (com retry) + banco
bash scripts/restore.sh F.dump# restore controlado (valida, backup previo, confirmacao)
```

`update.sh` e `migrate.sh` **param o backend antes da migration** — a versao
antiga nao opera contra schema potencialmente mais novo. Se a migration
falhar: backend permanece parado, backup `pre-update-*.dump` preservado,
recupere com `restore.sh`.

`restore.sh` valida o dump (`pg_restore -l`), cria `pre-restore-*.dump`
do banco atual, encerra conexoes e faz DROP/CREATE em passos separados.
Falha nunca e reportada como sucesso.

## Migracao dos dados homologados (portal_uma_dev -> VPS)

```bash
# 1. na maquina atual (somente leitura)
docker compose -f operacional/docker-compose.yml exec -T db \
  pg_dump -Fc -U portal_dev portal_uma_dev > portal_uma_dev.dump

# 2. copie para deploy/backups/ na VPS e rode:
cd deploy
bash scripts/transfer-data.sh backups/portal_uma_dev.dump
```

Restaura o dump, aplica a migration pendente (`0029` sobre `0028`) e
imprime contagens para conferencia (usuarios, credenciais, clientes
televendas, categorias). Anexos de procedimentos e WhatsApp ficam no
proprio banco (`bytea`) — o dump ja os cobre.
**Nunca use dumps dos ambientes 8081/8082 (dados ficticios).**

## Backups

- Dump diario automatico (servico `pgbackups`, autenticacao via
  `PGPASSWORD` do ambiente — nada em linha de comando ou log).
- Todos os dumps (diarios + pre-update/pre-migrate/pre-restore) vao para
  `deploy/backups/` — localizacao unica, bind mount no host.
- Backup externo: ver `BACKUP-EXTERNO.md` (rclone/rsync + teste de restore).

## Seguranca aplicada e testada

- `APP_ENV=production`: `/docs`, `/redoc`, `openapi.json` retornam 404 no
  backend (pelo proxy caem no SPA e nao expoem a API).
- Somente HTTP/HTTPS publicas; Postgres/FastAPI sem porta no host.
- HSTS + headers de seguranca (Caddy + Nginx + backend).
- Rate limit por IP (20 tentativas/5min): usa `X-Real-IP` reescrito pelo
  nosso Nginx (`$remote_addr`) — **`X-Forwarded-For` forjado nao contorna**,
  testado ponta a ponta pelo proxy.
- `/health` executa `SELECT 1`: 200 com banco, 500 sem banco — o
  healthcheck do Compose reflete a disponibilidade real.
- MFA TOTP obrigatorio p/ SuperAdmin (enrolment, login, falha, desativacao
  e recuperacao testados). Recuperacao: `python -m app.recover_superadmin`
  com `UMA_CONFIRM_SUPERADMIN_RESET=I_UNDERSTAND_ONE_TIME` — gera senha
  temporaria, revoga sessoes e limpa o TOTP.

## Teste descartavel da stack (sem DNS/publico)

O mesmo compose roda isolado — testado nesta preparacao:

```bash
cp .env.example .env.test   # DOMAIN=localhost, HTTP_PORT=8180, HTTPS_PORT=8444
                            # ERP_SYNC_ENABLED=false (sem credencial Drive)
ENV_FILE=.env.test PROJECT=uma-vpstest bash scripts/install.sh
# Caddy emite certificado interno para 'localhost': https://localhost:8444
```

Validado nesta branch: boot ordenado, HTTPS, MFA completo, rate limit
anti-spoof, backup real (pg_dump TCP), restore real, restart, outage e
recuperacao de DB, abort de update em migration falha, isolamento de
portas e migracao do dump homologado com contagens preservadas.

## Pendencia conhecida

`Devolucoes.csv` malformado no Drive segue rejeitado pela validacao
(logs consultaveis) — corrigir na fonte, nao no codigo.
