# Portal UMA — versão operacional (início)

> **Incremento atual (26/10/2026):** avaliações Google (conferência manual), catálogo e movimentação de insumos,
> carteira e ligações, checklist semanal, calendário WhatsApp/Instagram e treinamentos possuem API
> persistente e telas React. Anexos de artes, comprovantes e PDFs são protegidos e guardados no
> PostgreSQL, com limite de tamanho e auditoria (migração `0009`). Todos funcionam sem ERP.
> A operação das três lojas **ainda exige implantação privada do backend, banco e HTTPS**;
> a prévia do GitHub Pages continua usando dados fictícios.

> **Atualização vigente (23/10/2026):** a API e o frontend já possuem login local por nome de usuário, senha provisória individual, troca obrigatória, exclusão lógica, redefinição e provisionamento local do SuperAdmin. Esta versão **não está publicada com dados reais**. O texto dos incrementos anteriores abaixo permanece como histórico; consulte [Implantação e Acessos](./IMPLANTACAO-E-ACESSOS.md) para o estado atual.

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

**Implementado nesta ramificação:** modelos iniciais de usuários, lojas, grupos, permissões e auditoria; migrações versionadas para PostgreSQL (com grupos das três lojas); regras de autorização testáveis; API mínima que exige token válido e identidade previamente cadastrada; API administrativa exclusivamente de SuperAdmin para usuários, grupos, overrides, vínculo de loja, status de conta e consulta à auditoria; configuração de desenvolvimento local.

**Ainda NÃO implementado:** fluxo completo de login, criação segura do primeiro superadministrador, importador Excel, demais telas comerciais, integração da autenticação e migração visual completa dos módulos v5.1. A ausência desses itens **bloqueia a operação real**.

### Como testar o backend localmente (apenas ambiente de desenvolvimento)

Requer Python 3.12+ e Docker/Podman para PostgreSQL.

1. Na pasta `operacional`, inicie o PostgreSQL de desenvolvimento: `docker compose up -d db`.
2. Em `backend`, crie seu ambiente virtual, execute `pip install -e '.[dev]'` e copie `.env.example` para `.env`.
3. Execute `alembic upgrade head` para criar o esquema e as três lojas.
4. Execute `pytest` para validar os controles de acesso.
5. Execute `uvicorn app.main:app --reload` para testar `GET /health`.

As rotas `/api/v1/me` e `/api/v1/stores` exigem um JWT verificável e um usuário previamente cadastrado no banco. **Não existe login simulado nem senha padrão.** Sem configuração de identidade válida, o acesso falha de maneira segura.

Não exponha a porta do PostgreSQL em redes externas. Não inclua `.env`, credenciais, planilhas reais ou dados pessoais no GitHub.

### Como subir a stack completa com Docker (desenvolvimento)

Requer Docker Desktop (ou outro runtime compatível com Compose v2).

1. Na pasta `operacional`, execute `docker compose up -d --build`.
2. O backend roda as migrações Alembic automaticamente antes de iniciar o Uvicorn.
3. Endereços locais:
   - Frontend (nginx + build de produção): http://localhost:8080 — faz proxy de `/api` e `/health` para o backend;
   - API: http://localhost:8000 (`/health` para liveness);
   - PostgreSQL: `127.0.0.1:5439` (credenciais somente de desenvolvimento no compose).
4. Para parar: `docker compose down` (adicione `-v` para apagar também o volume do banco).

As portas publicadas ficam restritas a `127.0.0.1`. O usuário SuperAdmin e as contas locais seguem o provisionamento descrito em [Implantação e Acessos](./IMPLANTACAO-E-ACESSOS.md).

## Próximos incrementos

1. Escolher/implementar o provedor de autenticação e o provisionamento inicial seguro.
2. Validar a interface de configurações e de metas em um ambiente privado autenticado.
3. Reproduzir visualmente a experiência aprovada do protótipo na aplicação React.
4. Adaptar a importação Excel ao relatório real enviado pelo Jardel.
5. Migrar metas, indicadores e sete slides preservando as regras aprovadas.
6. Homologar backup, autorização, privacidade, testes e publicação antes de dados reais.

O `delpi-central` não é dependência, não deve ser modificado e não terá conexão com dados da UMA.

## Entrega de governança (incremento 2)

As rotas `/api/v1/admin/*` exigem autenticação OIDC válida e perfil SuperAdmin ativo no banco. Há endpoints para listar e provisionar contas associadas a identidades já existentes no provedor, designar a loja única de um vendedor, conceder leitura de módulos/indicadores por grupo, permitir ou negar leitura por usuário, ativar ou suspender contas e consultar os registros de auditoria.

A API **não cria credenciais**, **não atribui a ninguém a condição de SuperAdmin** e **não cadastra usuários automaticamente a partir de um token**. O cadastro inicial seguro da conta SuperAdmin e o provedor de identidade ainda precisam ser definidos antes de qualquer ambiente real. Os dados de auditoria são persistidos no servidor, com operações administrativas registradas na mesma transação; retenção, backups e política de acesso ao banco serão homologados antes da produção.

Nenhum nome, e-mail ou dado pessoal real foi incluído no seed; somente os três nomes de lojas e grupos. O módulo de auditoria ainda não cobre importações, metas ou outros módulos não implementados. Não expor o banco ou a API publicamente enquanto a autenticação e a infraestrutura final não forem testadas.

## Metas operacionais (incremento 4)

A estrutura PostgreSQL inclui metas mensais por unidade, configurações de mínimo diário por loja e dias de fechamento por competência. Vendedores só consultam a própria unidade quando o SuperAdmin concede `targets.view`, enquanto administradores e SuperAdmin podem gravar alterações auditadas. O controle de revisões rejeita gravações sobre dados desatualizados.

A interface React passa a oferecer **Metas diárias**, com cadastro por loja e mês, calendário de segunda a sexta, exceções de dias sem expediente e prévia financeira distribuída exatamente em centavos. **Faturamento realizado, atingimento e meta dinâmica continuam sem dados até uma importação validada do ERP**. Não são calculados a partir de registros fictícios.

A implantação exige aplicar as migrações Alembic (agora também 0003), configurar um provedor OIDC e homologar acesso/backup antes de utilizar valores comerciais reais. O `delpi-central` não participa do desenvolvimento ou da execução.

## Incremento 5 — Dashboard e fechamento mensal

Foram adicionados `/api/v1/overview/{year}/{month}` e `/api/v1/monthly-closing/...`, com escopo por loja, ausência explícita de fonte de faturamento e versão auditada dos rascunhos. A migração `0004` adiciona tabelas de rascunho e snapshots imutáveis de fechamento. A edição e o arquivamento exigem perfil de gestão autenticado e a apresentação consolidada não pode ser acessada diretamente por vendedores.

A interface React inclui Visão Geral, editor mensal, prioridades, apresentação de sete slides (até vinte minutos) e histórico de arquivos. Ainda é necessário integrar as informações comerciais oficiais e configurar as contas do provedor de identidade antes de uso com dados reais.


## Provisionamento da primeira conta SuperAdmin

Não existe usuário ou senha padrão. O procedimento futuro será feito por um operador técnico com acesso administrativo ao banco:

1. Configurar o provedor de identidade OIDC (emissor, público/audiência e endpoint HTTPS JWKS).
2. Criar a conta do responsável nesse provedor com autenticação forte e obter seu identificador **sub**. Nunca usar senha ou token pessoal como identificador.
3. Fornecer ao processo técnico, somente durante essa operação, as variáveis `UMA_INITIAL_SUPERADMIN_SUBJECT`, `UMA_INITIAL_SUPERADMIN_NAME` e `UMA_CONFIRM_INITIAL_SUPERADMIN=I_UNDERSTAND_ONE_TIME`.
4. Executar `python -m app.bootstrap` com o banco protegido, sem publicar variáveis, senhas ou identificadores no repositório.
5. A rotina registra uma auditoria e recusa novas execuções se já houver SuperAdmin; não promove contas existentes nem cria senha.

**Não execute esse provisionamento na demonstração estática e não habilite login real antes da homologação do serviço de identidade.** O DELPI Central permanece totalmente fora deste fluxo.

## Módulos não dependentes do ERP (incremento 6)

A migração 0005 adiciona acompanhamento manual das avaliações Google, estoque de insumos próprio por loja (catálogo, saldos e livro de movimentações) e carteira/registro de ligações com nome do vendedor e próximas tentativas. As informações são separadas dos dados comerciais oficiais do ERP, possuem isolamento por loja, validação no servidor e auditoria.

A equipe comercial **não recebe** permissão de escrita por esse incremento: preservamos a política inicialmente aprovada de vendedor somente leitura. Liberação de lançamentos pelos funcionários exigirá um fluxo próprio de autorização por ação, sem lhes dar permissão irrestrita para alterar cadastros ou outros usuários.

## Incremento 7: outras rotinas operacionais

A migração 0006 prepara as tabelas de checklist semanal, metas de ligações, Status WhatsApp global da empresa, controle manual do Instagram e registros de treinamento. Mantemos segregação de lojas, auditoria e o limite de vendedores à consulta somente. Sem integração automática com o Google, WhatsApp ou Instagram; anexos e assinatura digital aguardam armazenamento privado homologado.

## Incremento 8 — acessos e convites preparados

A migração `0007` cria `access_invitations` para pré-cadastrar colaboradores pelo SuperAdmin, com e-mail normalizado, perfil, loja, revisão e auditoria. O cadastro pendente **não é uma conta**: nenhum token, senha ou e-mail é emitido. O acesso somente será ativado após integração da identidade OIDC com correspondência verificada. Cancelamento preserva auditoria; a conta ativada só pode ser desativada por segurança. O SuperAdmin permanece único e não é criado por convites.


Para detalhes específicos da infraestrutura Locaweb e da política de convites, consulte [Implantação e acessos](./IMPLANTACAO-E-ACESSOS.md).

## Incremento 9 — anexos operacionais privados

Foi implementado o armazenamento de **arquivos pequenos dentro do PostgreSQL**, sem pasta
pública, sem URLs abertas e sem depender do ERP: uma arte e um comprovante de publicação por
data no calendário compartilhado; um PDF por participação em treinamento. Não há assinatura
eletrônica implícita e o Google/WhatsApp/Instagram continuam sem APIs oficiais conectadas.
O registro de avaliações Google é por conferência **manual**, não por leitura automática.

- Somente JPG/PNG/WebP até **3 MB** para artes/comprovantes; somente PDF até **5 MB**
  para treinamento. O backend valida o conteúdo e a extensão, além do tamanho.
- Cada download exige autenticação e o acesso correspondente (calendário global ou
  loja do treinamento). Criação, substituição e exclusão exigem perfil de gestão.
- O nome original, o SHA-256, o tamanho, a revisão e as operações de upload/exclusão
  ficam registrados na auditoria, **sem armazenar conteúdo binário no log**.
- O calendário impede repetição de código de produto durante o mesmo ano; o histórico
  de publicações e o vínculo dos anexos são separados do ERP.
- Exclusão do planejamento do WhatsApp também exclui os anexos daquela data.
- As respostas dos arquivos são `no-store`, `nosniff` e sempre indicam download.
- **Capacidade/custo:** os arquivos ocupam espaço do PostgreSQL. Antes de operar em
  produção, contratar/configurar armazenamento e backups apropriados e testar uma
  restauração; revisar o uso do banco e migrar para armazenamento de objetos se necessário.
- Configurar no gateway/proxy HTTPS também um limite global para uploads, além do
  limite verificado na API.

Módulos desenvolvidos não significam sistema já colocado no ar: não há conta real,
servidor de aplicação nem banco operacional publicados em `portal.universodasmangueiras.com.br`.
A escolha do provedor e do TLS permanecerá independente do código.


## Incremento 10 — tarefas diárias e prévia SuperAdmin completa (26/10/2026)

O módulo `daily_tasks` foi criado independentemente do checklist semanal.
Permite registrar tarefa por data e loja, prioridade (baixa/normal/alta),
responsável opcional vinculado à loja, status (pendente/em andamento/concluída),
reabrir, editar e excluir logicamente. Todas as alterações relevantes são
auditadas, com controle de revisões para evitar sobrescrita de trabalho de
outro administrador. Administradores podem alterar; vendedores consultam
somente a própria loja quando recebem `daily_tasks.view`.

- Migração: `operacional/backend/migrations/versions/0010_daily_tasks.py`.
- API: `GET/POST/PUT/DELETE /api/v1/daily-tasks/...`.
- Frontend: `DailyTasksPage.tsx`, com filtro por loja e data e resumo de pendências.
- Demonstração estática: `preview-operacional/superadmin.html`, unificando
  todas as áreas operacionais, administrativas e o fechamento mensal de 7 slides.
  Todas as interações da prévia usam dados fictícios, sem sincronização ou login.

**A prévia não é a implantação do banco operacional.** A publicação do sistema
real continuará condicionada a backend, PostgreSQL, HTTPS, DNS e backups.
