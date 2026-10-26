# Homologacao local integrada do Portal UMA

Ambiente **somente para testes locais com dados ficticios**, separado do GitHub Pages e do site institucional.

## Requisitos
Docker e Docker Compose v2, porta local 5173 disponivel, acesso ao repositorio.

## Como iniciar
1. Acesse a branch `feat/homologacao-local-integrada`.
2. Entre em `operacional/homologacao`.
3. Copie `.env.example` para `.env` e defina `UMA_HML_DB_PASSWORD` com uma senha unica, aleatoria e forte, usando caracteres alfanumericos. Nunca compartilhe ou comite.
4. Execute:

```sh
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
docker compose -f compose.yaml exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

5. Apenas com banco de homologacao inicialmente vazio, crie o SuperAdmin:

```sh
docker compose -f compose.yaml exec -e UMA_INITIAL_SUPERADMIN_USERNAME=superadmin_hml -e UMA_INITIAL_SUPERADMIN_NAME=SuperAdmin_Homologacao -e UMA_CONFIRM_INITIAL_SUPERADMIN=I_UNDERSTAND_ONE_TIME api python -m app.bootstrap_local
```

A senha provisoria aparece somente uma vez no terminal: guarde-a privadamente, nao fotografe nem envie no chat. Acesse http://127.0.0.1:5173 e altere a senha no primeiro login.

## Checklist de homologacao
- Testar SuperAdmin, administrador e vendedor ficticios, permissoes por loja e auditoria.
- Criar, atribuir, concluir, reabrir, editar e excluir Tarefas Diarias. Conferir historico.
- Verificar bloqueio de leitura entre lojas e de escrita para vendedores.
- Conferir avaliacoes manuais, insumos, ligacoes, checklist, calendario WhatsApp, Instagram e treinamentos com anexos ficticios.
- Conferir Metas Diarias, Visao Geral e Fechamento Mensal de sete slides sem inventar dados do ERP.
- Verificar mensagens de erro, revisoes concorrentes e comportamento apos novo login.

## Limites de seguranca
A interface responde apenas no loopback 127.0.0.1:5173. API e PostgreSQL nao expoem portas no host. **Nao publicar este ambiente na internet**. Usa APP_ENV=development e nao substitui a homologacao de producao com HTTPS, MFA, backups e protecao de sessoes. O primeiro inicio baixa imagens e dependencias.

```sh
docker compose -f compose.yaml down
```

Para apagar irreversivelmente o banco de testes e volumes:

```sh
docker compose -f compose.yaml down -v
```

A ultima instrucao so deve ser usada se todos os dados puderem ser descartados.
