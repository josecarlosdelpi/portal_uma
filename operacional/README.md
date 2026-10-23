# Portal UMA — versão operacional (início)

Este diretório contém a evolução operacional do Portal UMA. O protótipo **v5.1**, em `/index.html`, permanece intacto e é exclusivamente demonstrativo.

## Diretrizes aprovadas

- Sistema independente do DELPI Central, usando apenas seus padrões como referência.
- Backend Python/FastAPI, PostgreSQL e frontend React/TypeScript/Vite.
- Apenas um backend modular no início; sem necessidade de microsserviços.
- Nove usuários planejados: um superadministrador, três administradores operacionais e cinco vendedores somente leitura.
- Vendedores restritos à loja, aos módulos e aos indicadores autorizados pelo superadministrador.
- Excel será a primeira origem de dados comerciais; o layout da planilha depende do relatório do ERP.
- Infraestrutura de produção e provedor de identidade ainda serão escolhidos.
- Não realizar deploy público ou carregar dados comerciais reais antes de autenticação, autorização e backups homologados.

## Situação deste incremento

**Implementado nesta ramificação:** modelos iniciais de usuários, lojas, grupos, permissões e auditoria; migração versionada para PostgreSQL; regras de autorização testáveis; API mínima que exige token válido e identidade previamente cadastrada; configuração de desenvolvimento local.

**Ainda NÃO implementado:** fluxo completo de login, criação segura do primeiro superadministrador, painel de administração, importador Excel, telas comerciais e migração visual dos módulos v5.1. A ausência desses itens **bloqueia a operação real**.

### Como testar o backend localmente (apenas ambiente de desenvolvimento)

Requer Python 3.12+ e Docker/Podman para PostgreSQL.

1. Na pasta `operacional`, inicie o PostgreSQL de desenvolvimento: `docker compose up -d db`.
2. Em `backend`, crie seu ambiente virtual, execute `pip install -e '.[dev]'` e copie `.env.example` para `.env`.
3. Execute `alembic upgrade head` para criar o esquema e as três lojas.
4. Execute `pytest` para validar os controles de acesso.
5. Execute `uvicorn app.main:app --reload` para testar `GET /health`.

As rotas `/api/v1/me` e `/api/v1/stores` exigem um JWT verificável e um usuário previamente cadastrado no banco. **Não existe login simulado nem senha padrão.** Sem configuração de identidade válida, o acesso falha de maneira segura.

Não exponha a porta do PostgreSQL em redes externas. Não inclua `.env`, credenciais, planilhas reais ou dados pessoais no GitHub.

## Próximos incrementos

1. Escolher/implementar o provedor de autenticação e o provisionamento inicial seguro.
2. Criar a interface de configuração de usuários, grupos, permissões e auditoria.
3. Reproduzir visualmente a experiência aprovada do protótipo na aplicação React.
4. Adaptar a importação Excel ao relatório real enviado pelo Jardel.
5. Migrar metas, indicadores e sete slides preservando as regras aprovadas.
6. Homologar backup, autorização, privacidade, testes e publicação antes de dados reais.

O `delpi-central` não é dependência, não deve ser modificado e não terá conexão com dados da UMA.
