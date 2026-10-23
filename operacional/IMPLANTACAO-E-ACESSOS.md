# Portal UMA — decisão de infraestrutura e gestão de acessos

## 1. Estado atual

- O contrato mostrado pelo responsável é **Hospedagem I – Linux** na Locaweb, vinculada ao domínio `universodasmangueiras.com.br`.
- O screenshot de faturamento **não demonstra** suporte a processo Python/FastAPI permanente nem confirma disponibilidade de PostgreSQL nesse contrato.
- A documentação comercial pública de Hospedagem I destaca bancos MySQL; PostgreSQL aparece em níveis superiores. Conferir a contratação específica antes de assumir disponibilidade.
- O Portal UMA usa React/TypeScript/Vite, API Python/FastAPI e PostgreSQL. A prévia do GitHub Pages é estática e **não é um ambiente de produção**.

## 2. Implantação segura proposta

1. Manter o site institucional e o `index.html` da v5.1 sem alterações.
2. Verificar no painel o subdomínio `portal.universodasmangueiras.com.br` e a possibilidade de apontá-lo a uma pasta independente, sem mudar o DNS principal.
3. Verificar HTTPS para esse subdomínio (o SSL DV atual pode não incluí-lo; consultar Let's Encrypt do painel).
4. Publicar somente a **compilação estática** do frontend na hospedagem compartilhada **se a compatibilidade e o HTTPS forem confirmados**.
5. Hospedar backend FastAPI e PostgreSQL em serviço adequado, **preferencialmente gerenciado**, caso o plano compartilhado não suporte essa arquitetura. Não usar o PostgreSQL compartilhado a partir de backend externo sem confirmação das regras da Locaweb.
6. Definir o provedor de identidade OIDC, configurar MFA do SuperAdmin, teste de recuperação, backups, permissões, logs e HTTPS antes de dados reais.
7. Só mudar DNS, contratar serviços e integrar dados reais depois de homologação explícita. Nunca colocar credenciais, `.env`, informações reais de funcionários ou planilhas no GitHub Pages.

## 3. Acessos do Portal UMA

### Implementado na ramificação operacional

- Um SuperAdmin exclusivo, provisionado tecnicamente por identidade OIDC **verificada** e com auditoria; não existe senha padrão.
- Perfis operacionais `administrator` (todas as três lojas, sem governança) e `seller` (uma única loja e consulta somente).
- Criação de **pré-cadastro** por nome, e-mail, perfil e loja em `access_invitations`.
- Cancelamento e reabertura de pré-cadastro, sem apagar histórico; verificação de revisão para evitar alterações concorrentes.
- Administração de contas já provisionadas: suspender/reativar, mover vendedor de loja, permissões individuais, por grupo e auditoria.
- Os rascunhos de convite têm status **prepared**, `delivery=not_configured`; não enviam email, não emitem tokens nem geram senha.

### Integração necessária para contas funcionarem

O serviço OIDC escolhido deverá assumir envio de convites, senha e recuperação; confirmar endereço individual, identidade, emissor e público do token; vincular `sub` verificado ao perfil pré-cadastrado **sem conceder privilégios pelo e-mail não verificado**; aplicar MFA ao SuperAdmin e preservar auditoria de ativações e suspensões. Contas canceladas não podem ser ativadas; convites devem expirar e ter uso único.

Não automatizar inclusão de contas por simples indicação de nome ou e-mail. O SuperAdmin continua único e nunca é criado pelo fluxo de convite. Contas já ativadas devem ser suspensas/desativadas, não apagadas fisicamente, para preservar trilhas de auditoria.

## 4. Informações que faltam da Locaweb

No painel **Hospedagem de Sites → Administrar site**, coletar apenas capturas de telas **sem senhas**:

- Aba de **Configurações / Informações técnicas**, se houver, indicando tipo de hospedagem e tecnologias suportadas.
- Aba de **Banco de dados**, especialmente tipos de bancos permitidos (não compartilhar usuários, senhas, endereços completos ou detalhes sensíveis de conexão).
- Aba **Domínios / Subdomínios**, para ver se existe opção de pasta independente.
- Aba **SSL / Certificados**, para verificar se o subdomínio pode ter HTTPS.

Se o painel não esclarecer: perguntar ao suporte se **Hospedagem I Linux** permite servir arquivos HTML/JS de uma aplicação React, criar subdomínio com pasta própria, usar HTTPS e executar continuamente um servidor Python ASGI/FastAPI. Confirmar também se inclui PostgreSQL. Nenhuma senha, chave, token ou acesso administrativo deve ser compartilhado no chat.
