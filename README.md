# Portal UMA

## Código operacional — módulos sem ERP (26/10/2026)

A aplicação **operacional** está em [`operacional/`](./operacional/), separada do
protótipo `index.html`, que permanece uma demonstração pública com dados fictícios.

A versão operacional usa **React/TypeScript + FastAPI + PostgreSQL** e já possui:
avaliações Google manuais por loja, insumos (entradas, retiradas e histórico),
clientes e ligações, checklist semanal, calendário WhatsApp anual sem repetição de
produtos, Instagram, treinamentos e autenticação local sem e-mail (senha provisória
individual e troca obrigatória no primeiro login). Inclui **anexos privados**
de imagens de Status/comprovantes e PDFs de treinamento, guardados no PostgreSQL.

**O código estar no GitHub não significa que o sistema esteja implantado.**
A hospedagem do backend, banco de produção, HTTPS e DNS do subdomínio
`portal.universodasmangueiras.com.br` ainda precisam ser configurados e
homologados antes de utilização pelas lojas. Não enviar dados reais à
demonstração pública nem inserir senhas no repositório.

Detalhes de instalação e segurança: [Implantação e acessos](./operacional/IMPLANTACAO-E-ACESSOS.md).


Protótipo demonstrativo de gestão comercial da **Universo das Mangueiras Automotivas (UMA)**.

## Versão disponível

**v5.1 — Fechamento Mensal interativo de 7 slides e até 20 minutos (demonstração)**, em `index.html`.

Inclui tela de login inicialmente vazia, visão geral, vendas, carteira de televendas, avaliações no Google, controle de insumos, checklist, metas diárias, assinatura demonstrativa de treinamentos, calendário de Status do WhatsApp e apresentações gerenciais em slides.

**Permissões fictícias:** Milena/Admin lança contagens mensais de avaliações, entrega de brindes, entradas de estoque, cadastro de materiais, metas e validação das tarefas. Vendedores apenas consultam as avaliações de sua loja, registram retiradas dos insumos da própria loja e acompanham tarefas e ligações.

### Como executar

1. Baixe `index.html` (ou clone o repositório).
2. Abra o arquivo diretamente em um navegador moderno; não há instalação de dependências.
3. Use um dos acessos **fictícios**:
   - Administração: `Admin` / `Admin` ou `Milena` / `Milena`;
   - Vendedores: `J1` / `J1`, `J2` / `J2`, `T1` / `T1`, `T2` / `T2`, `I1` / `I1`.

## Avisos importantes

- **Somente demonstração, com dados fictícios.** Não utilizar dados reais de clientes ou documentos comerciais sensíveis.
- **Não há backend ou autenticação segura.** Os logins são simulados em JavaScript e não protegem informações.
- As alterações são salvas no armazenamento local do navegador, **sem sincronização entre lojas ou computadores**.
- O portal **não está integrado ao ERP** e não comprova automaticamente compras, cupons ou premiações.
- As regras de premiação exibidas são hipóteses para validação com a gestão antes de uso operacional.
- **Repositório público:** não inclua dados de clientes, credenciais reais ou segredos.

## Atualização v5.1 — Fechamento Mensal (19/10/2026)

O Portal UMA mantém os módulos da v5. A tela **Fechamento Mensal**, no menu principal, foi atualizada sem reconstruir o sistema.

- **Apresentação de 7 slides em 20 minutos:** (1) abertura, 1 min; (2) resultado consolidado, 3 min; (3) as três lojas lado a lado, 5 min; (4) atividades comerciais, 3 min; (5) qualidade das rotinas, 2 min; (6) reconhecimentos, melhorias e avisos, 2 min; (7) prioridades do mês seguinte, 4 min.
- **Preparação administrativa:** mês/ano, mensagem de abertura, comentários para cada loja, oportunidades, reconhecimentos, melhorias, avisos gerais e recados por unidade. Salvar rascunho recupera os comentários do mês selecionado.
- **Prioridades de 3 a 5 ações:** responsável, loja, prazo e situação. Podem ser criadas ou vinculadas a ações existentes do módulo de acompanhamento gerencial, evitando duplicação de registros. A apresentação mostra pendências documentadas no fechamento do mês anterior.
- **Dados calculados na abertura:** faturamento, meta, atingimento, comparação com mês anterior e ano anterior quando existirem registros; atividades de televendas, avaliações Google, checklists, treinamentos, WhatsApp e Instagram. Itens não monitorados ficam marcados **Sem dados/Ainda não monitorado**; não se inventam zeros nem métricas de campanhas.
- **Modo apresentação:** proporção 16:9 para TV/projetor, tela cheia ao clicar **Iniciar apresentação**, setas ←/→, Esc para encerrar, botões de navegação, numeração e tempos sugeridos. Visual preta, branca e amarela, com a logo original.
- **Saída e histórico:** botões **Salvar rascunho**, **Pré-visualizar**, **Iniciar apresentação**, **Arquivar fechamento**, **Imprimir / PDF** (todos os 7 slides em páginas de paisagem) e **Exportar slides HTML**. Cada arquivo guarda os dados e comentários daquele momento; nova versão de um fechamento preserva a anterior no histórico. Arquivos históricos antigos com 8 slides permanecem consultáveis.
- **Sem ranking individual de vendedores e sem nota única que misture resultados comerciais e operacionais.** O Status WhatsApp é único para a UMA, não atribuído artificialmente às três lojas.

### Como testar

1. Entre com **Milena/Milena** ou **Admin/Admin** (credenciais de apresentação).
2. Abra **Fechamento Mensal** no menu e escolha um mês.
3. Escreva comentários e clique em **Salvar rascunho**.
4. Cadastre ou vincule 3–5 prioridades; use **Pré-visualizar** ou **Iniciar apresentação**.
5. Arquive o fechamento e teste a consulta, a impressão/PDF e a exportação HTML.

**Limitação fundamental:** todos os dados, comentários, ações e arquivos continuam sendo armazenados apenas no navegador, sem autenticação real nem ERP. A versão pública deve ser testada exclusivamente com dados fictícios; não inserir valores comerciais confidenciais, nomes de funcionários reais, informações pessoais ou documentos internos.

## Histórico: novidades da v5 — 16/10/2026

- **Visão Geral:** percentuais de metas comerciais (vendas, ligações, avaliações) separados dos operacionais (tarefas e Instagram). Cada indicador com meta válida tem peso igual dentro de seu grupo, limitado a 100% apenas no cálculo do indicador consolidado. O Status do WhatsApp, que é único para toda a UMA, é apresentado à parte; não é atribuído artificialmente a cada loja. Há seleção de mês ou semana e consulta a períodos anteriores.
- **Metas diárias:** meta mensal cadastrada pela Milena por unidade; contagem de segunda a sexta-feira com exclusões configuráveis de feriados/dias sem expediente por loja. A meta do dia corresponde ao valor restante dividido pelos dias de funcionamento restantes. Após o faturamento acumulado alcançar a meta mensal, os dias seguintes utilizam o valor mínimo diário configurado por loja, preservado entre meses. Vendedores consultam apenas a própria loja.
- **Fechamento na v5 (substituído na v5.1):** oito slides gerados a partir dos registros presentes no portal, incluindo vendas, avaliações, ligações, tarefas, WhatsApp e Instagram (quando cadastrados). Exibição em tela cheia, impressão/salvamento em PDF pelo navegador, exportação como HTML de slides e arquivamento local de um retrato por mês. **Não exporta PPTX nesta demonstração.**
- **Treinamentos:** procedimento, versão, colaborador/loja, responsável, data e horário, arquivo PDF pequeno opcional, desenho de assinatura na tela e comprovante imprimível. A assinatura e o documento ficam apenas no armazenamento local. **Não devem ser usados como comprovação jurídica ou com dados reais**.
- **Status WhatsApp:** calendário único de segunda a sexta, categorias de posts do planejamento utilizado pela UMA, controle de código de produto único dentro do ano, imagem da arte e evidência em JPG/PNG/WebP compactadas, confirmação de publicação, histórico e download. Apenas o administrador exclui registros. Dias sem publicação podem ser indicados pela Milena.
- **Instagram:** campos de contagem mensal de posts previstos e realizados por loja; lançamentos manuais da Milena para alimentar indicadores e slides, sem API.
- **Permissões demonstrativas:** perfil Milena/Admin vê todas as lojas; vendedor consulta a própria unidade e pode atualizar publicações do calendário único de WhatsApp. Os controles de acesso ocorrem apenas no navegador, sem proteção de servidor.

**Fontes do cálculo demonstrativo:** vendas já cadastradas na aba Vendas deste navegador; ligações já cadastradas no módulo de televendas; checklist e avaliações registrados nos módulos v4. Não há sincronização com ERP, Google ou outras máquinas. As metas de abertura e os produtos **DEMO-** são exemplos fictícios, não representam dados comerciais da UMA.

### Avisos de implantação

- **GitHub Pages hospeda apenas a demonstração estática.** Todo conteúdo novo é armazenado por navegador em localStorage, não é compartilhado entre computadores, pode ser apagado pelo usuário e tem espaço limitado. Anexos numerosos podem exceder esse limite.
- Não anexar fotografias, dados de clientes, documentos internos, assinaturas reais, credenciais ou informações privadas. Para um uso real, serão indispensáveis login seguro, permissões no servidor, armazenamento de arquivos e banco centralizado com backup e adequação à LGPD.
- **Assinaturas não são juridicamente validadas** pelo protótipo; o histórico local não comprova autoria nem integridade para fins trabalhistas.
- A consulta automática às avaliações do Google continua pendente de estudo de integração e autorização.
- A metodologia de metas diárias foi inspirada exclusivamente na aba **"Meta do dia"** da planilha fornecida, com correção consciente de datas e referências inconsistentes.

## Módulos v4 — implementação demonstrativa

- **Google:** contabilização mensal **manual** pela Milena, por loja; 10 avaliações significam um brinde simbólico para cada vendedor da loja, 20 avaliações significam **somente** um brinde maior por vendedor. Registro de data da entrega e histórico por mês. **Sem integração automática com o Google.**
- **Insumos:** saldos e mínimos distintos por loja; apenas Milena/Admin registra entradas e configura materiais; funcionários registram retiradas. Alertas quando `saldo <= mínimo`; sem transferência entre unidades.
- **Checklist:** tarefas semanais recorrentes ou pontuais, histórico por semana, mudanças preservando versões passadas de rotinas recorrentes; somente Milena/Admin valida a conclusão. Metas numéricas de ligações por loja e semana com totais calculados a partir da carteira de televendas, mas conclusão sujeita à validação da Milena.

Dados e perfis são fictícios, com persistência **somente no navegador local**.

## Próximos passos

Validar com a Milena os formulários e regras, conferir possibilidade de integração oficial com Google Business Profile e definir backend, autenticação e banco de dados antes de qualquer utilização operacional.

## Estratégia de evolução

Desenvolver de forma incremental, preservando o que já funciona no HTML atual. Antes de publicar uma versão para uso real, serão necessários autenticação segura, permissões no servidor, armazenamento centralizado, cópias de segurança e cuidados de privacidade.

## Publicação da demonstração com GitHub Pages

Este repositório já contém `index.html` e `.nojekyll`, preparados para hospedagem estática.

Para ativar o GitHub Pages, um administrador do repositório deve abrir [Settings → Pages](https://github.com/josecarlosdelpi/portal_uma/settings/pages) e escolher:

- **Source:** `Deploy from a branch`
- **Branch:** `main`
- **Folder:** `/(root)`
- Clicar em **Save**.

Após a implantação pelo GitHub, o endereço previsto será:

**https://josecarlosdelpi.github.io/portal_uma/**

A ativação em Settings é obrigatória. Ter os arquivos no GitHub não significa que o site já está no ar. A atualização do `index.html` no branch `main` será publicada automaticamente após habilitar o Pages.

**Atenção:** trata-se de uma demonstração pública sem autenticação real. Nunca preencher com dados reais de clientes, documentos, valores sensíveis ou senhas.
