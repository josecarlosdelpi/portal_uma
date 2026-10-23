# Portal UMA — interface operacional

Aplicação **React + TypeScript + Vite** isolada do protótipo v5.1 na raiz.

## Escopo inicial

- Entrada com provedor OIDC compatível com Authorization Code + PKCE.
- Perfil e acesso inicial pela API Python autenticada.
- Console SuperAdmin: usuários, grupos de loja, permissão por indicador, exceções individuais (herdar/permitir/bloquear) e auditoria.
- Operações de alteração só são habilitadas após login seguro e confirmação de perfil na API.
- A criação de credenciais/convites no provedor fica pendente da escolha do serviço de autenticação.
- Nenhum dado real ou credencial de teste está embutido.

## Desenvolvimento local

1. Configure e inicie o backend seguindo o `../README.md`.
2. Copie `.env.example` para `.env.local`.
3. Insira `VITE_OIDC_AUTHORITY` e `VITE_OIDC_CLIENT_ID` **somente após configurar um provedor OIDC confiável**. Configurações Vite são públicas: nunca inserir senhas nem client secrets.
4. Execute `npm install`, `npm run test`, `npm run build` e `npm run dev`.

No Vite, o caminho `/api` aponta para o backend local em `http://127.0.0.1:8000`. Na implantação, é recomendado servir a API pelo mesmo domínio via proxy. Para servidores diferentes, configurar `VITE_API_BASE_URL` e CORS estrito no backend.

Se as variáveis OIDC não estiverem disponíveis, a interface exibirá uma tela informativa e **não oferecerá login falso**. Para funcionar com dados reais ainda faltam provisionamento inicial do SuperAdmin, testes completos de autenticação, backups, privacidade e publicação privada.

### UX das permissões

Os controles do frontend são somente interface. O backend sempre decide acesso. O vendedor só pode consultar sua loja; nem uma exceção individual pode autorizar escrita ou leitura cruzada. Um indicador liberado não torna visível o restante do módulo se a rota também exige permissão de abertura.

### Limitação do cadastro de usuários

A API já suporta cadastro seguro mediante um identificador `sub` existente no provedor de identidade. A tela administrativa não solicita identificadores técnicos ao usuário; o fluxo de convites por e-mail será integrado quando o fornecedor de autenticação for definido. Essa etapa não impede editar permissões dos usuários já provisionados.

## Metas diárias (incremento 4)

- Painel de metas por loja e competência, com alterações apenas por administrador operacional ou SuperAdmin.
- Vendedor só visualiza as metas se a permissão `targets.view` for concedida para a sua unidade.
- Meta mensal e mínimo diário separados, além de dias úteis excluídos manualmente por loja; alterações versionadas e auditadas no backend.
- A tabela diária mostra apenas a **distribuição-base orientativa**, não o faturamento real nem a meta dinâmica. Nenhum valor de vendas é fabricado.
- O cálculo dinâmico está preparado no backend, mas aguarda o histórico oficial do ERP para ativação.

## Incremento 5 — Visão Geral e Fechamento Mensal

- Dashboard com filtros de competência, escopo por loja e metas autorizadas. Faturamento, evolução e percentual não aparecem como zero nem como valor fictício.
- Fechamento mensal com rascunho versionado, comentários por loja, conquistas, melhorias, avisos e prioridades de 3 a 5 ações.
- Apresentação navegável de **7 slides, total 20 minutos** (1/3/5/3/2/2/4), com impressão e versão arquivada congelada.
- Apresentação **consolidada** só pode ser acessada pela gestão. Usuários vendedores não recebem dados de outras lojas, ainda que recebam permissões para consulta local.
- O provedor de autenticação OIDC e a base de vendas ainda estão pendentes. Arquivos atuais são identificados como **parciais — dados de vendas pendentes**.

## Módulos operacionais sem ERP (incremento 6)

- Avaliações Google: conferência **manual** de avaliações, faixas de 10 e 20, histórico e entrega coletiva não cumulativa.
- Materiais e insumos: catálogo, mínimos por loja, entradas, retiradas, saldo bloqueando negativo, histórico de movimentações.
- Televendas: carteira de clientes por loja, contato atribuído a vendedor ativo da unidade, anotações e retornos. **Não calcula compra, ativação ou comissão sem ERP.**
- Vendedores continuam como **consulta somente** de acordo com as permissões aprovadas; gravações exclusivamente pelos administradores até que haja aprovação específica de novo fluxo de participação.
- O visual usa agora o logotipo original embutido na v5.1 e o tema preto/dourado. A identidade foi reaproveitada sem modificar a demonstração pública.

## Incremento 7: outras rotinas

- Checklist semanal com metas de ligações contadas a partir do histórico de contatos, tarefas recorrentes/extraordinárias e validação administrativa; alterações criam versões para preservar o histórico.
- Calendário único de Status WhatsApp, seg–sex, códigos de produtos únicos por ano, estados de planejamento/arte pronta/publicação e dias sem postagem.
- Instagram manual, por loja e mês.
- Treinamentos: metadados de participação e prática por colaborador, com procedimentos sinalizados como rascunho. **Não persistir assinaturas, PDFs nem imagens até implantar armazenamento privado e autorizações adequadas.**
