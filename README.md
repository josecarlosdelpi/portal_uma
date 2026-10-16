# Portal UMA

Protótipo demonstrativo de gestão comercial da **Universo das Mangueiras Automotivas (UMA)**.

## Versão disponível

**v3 — Televendas (demonstração)**, em `index.html`.

Inclui tela de login, visão geral, vendas, cadastro e acompanhamento de clientes para televendas, registros de ligações e compras, indicadores demonstrativos de ativação e premiação, padrões/treinamentos e acompanhamento de ações gerenciais (GR).

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

## Próximos módulos em levantamento

Avaliações no Google, estoque de materiais de consumo e checklist semanal por loja. Dependem de esclarecimentos com a gestão, por isso ainda não estão implementados.

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
