# Portal UMA

Protótipo demonstrativo de gestão comercial da **Universo das Mangueiras Automotivas (UMA)**.

## Versão disponível

**v4 — Televendas, avaliações Google, insumos e checklist (demonstração)**, em `index.html`.

Inclui tela de login com campos inicialmente vazios, visão geral, vendas, carteira de televendas, registros de ligações e compras, indicadores demonstrativos, acompanhamento das avaliações no Google **por loja**, controle do estoque de insumos **por unidade** e checklist semanal com metas de ligações obtidas dos registros de televendas, além de padrões/treinamentos e ações gerenciais (GR).

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
