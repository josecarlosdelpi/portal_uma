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
