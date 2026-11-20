# Portal UMA — Deploy em VPS Linux (producao)

Stack: Caddy (HTTPS automatico) -> Nginx (React) -> FastAPI -> PostgreSQL 16.
Somente as portas **80/443** sao publicas; banco e API ficam na rede interna.

## Pre-requisitos na VPS

- Linux x86_64 com Docker Engine + plugin `docker compose` (v2)
- 2 vCPU / 4 GB RAM / 40 GB disco (minimo recomendado)
- Portas 80 e 443 liberadas no firewall para a internet
- DNS do dominio apontando para o IP da VPS (A/AAAA)

## Valores que voce precisa informar em `deploy/.env`

| Variavel | Origem |
|---|---|
| `DOMAIN` | dominio publico (ex.: portal.universodasmangueiras.com.br) |
| `POSTGRES_PASSWORD` | gerada automaticamente no install |
| `GOOGLE_DRIVE_FOLDER_ID` | pasta do Drive com os CSVs do ERP |
| `DRIVE_SA_FILE` | JSON da conta de servico do Google (arquivo local) |
| `BACKUP_RETENTION_DAYS` | dias de retencao dos dumps (padrao 14) |

## Instalacao inicial

```bash
cd deploy
cp .env.example .env          # revise DOMAIN e GOOGLE_DRIVE_FOLDER_ID
mkdir -p secrets && chmod 700 secrets
cp /caminho/uma-drive-sa.json secrets/   # credencial do Drive (nunca versionar)
bash scripts/install.sh       # build + up + migrations explicitas
```

O script gera a senha do banco, sobe a stack e roda `alembic upgrade head`
uma unica vez, de forma explicita — **o backend nao migra no boot**.

## Migracao dos dados existentes (portal_uma_dev -> VPS)

```bash
# 1. no ambiente atual, gere um dump verificavel
docker exec portal_uma_db pg_dump -Fc -U <user> portal_uma_dev > portal_uma_dev.dump

# 2. copie o dump para a VPS (scp) para deploy/backups/

# 3. na VPS, restore controlado (o script pede confirmacao)
cd deploy && bash scripts/restore.sh backups/portal_uma_dev.dump
```

Preserva: usuarios, permissoes, clientes, contatos, categorias,
classificacoes financeiras, historicos do ERP e anexos.
Nao copie dumps dos ambientes 8081/8082 (dados ficticios).

## Operacao do dia a dia

```bash
bash scripts/update.sh        # pull + backup + build + migrate + restart + health
bash scripts/migrate.sh       # so a migration (backup automatico antes)
bash scripts/health.sh        # status dos containers + API + banco
bash scripts/restore.sh F.dump# restore controlado
```

## Backups

- Dump **diario** automatico via servico `pgbackups` no volume `backups`.
- Retencao configuravel (`BACKUP_RETENTION_DAYS`, padrao 14 dias).
- **Copie os .dump para armazenamento externo** (ex.: `rsync`/`rclone`) —
  o volume local nao substitui backup fora da VPS.
- Restore testado: `pg_restore` em banco novo valida integridade.

## Seguranca aplicada

- `APP_ENV=production` desativa `/docs`, `/redoc` e `openapi.json`.
- Somente 80/443 publicas; PostgreSQL e FastAPI nao tem porta exposta.
- HSTS + headers de seguranca no Caddy e no Nginx.
- Rate limit de login por IP (20 tentativas / 5 min) alem do bloqueio por usuario.
- **MFA (TOTP) para SuperAdmin** — ative em Configuracoes > Usuarios apos o 1o acesso.
- Tokens de sessao somente em `sessionStorage` (nunca `localStorage`/cookie).
- Segredos via `.env` (modo 600) e arquivo montado read-only — fora de Git, imagens e logs.

## Recuperacao de conta SuperAdmin

Se o SuperAdmin perder o acesso, use o script de recuperacao dentro do
container (gera senha temporaria + revoga sessoes + limpa o MFA):

```bash
docker compose -f deploy/docker-compose.vps.yml --env-file deploy/.env \
  exec backend python -m app.recover_superadmin
```

## Atualizar a partir do GitHub

`scripts/update.sh` faz `git pull --ff-only`, **backup pre-migration**,
rebuild, migration explicita e restart — com abort se a migration falhar.

## Pendencia conhecida

`Devolucoes.csv` malformado no Drive continua rejeitado (log consultavel via
`docker compose logs backend`) — validacao intencional, corrija na fonte.
