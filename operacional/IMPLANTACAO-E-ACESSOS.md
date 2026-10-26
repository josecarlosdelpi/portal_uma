# Portal UMA — implantação e gestão de acessos (situação atual)

**Situação:** implementação e testes em andamento; **nenhum acesso de funcionário foi ativado em produção**. O protótipo v5.1 e o repositório DELPI Central não são alterados.

## 1. Diagnóstico da Locaweb

Captura do painel em 23/10/2026:
- Plano **Hospedagem I Linux**, sistema **Rocky Linux 8**, **PHP 8.3**.
- Módulos **Domínios**, **Banco de dados**, **Arquivos e acesso FTP**, **Configurações** (SSH/Git), e-mail.
- **WAF ativo**. Campo de SSL mostra **DNS Pendente** — checar configuração antes de mudar registros.
- **Backup: Ativar** — não tratar essa opção como proteção já configurada.
- Domínio `universodasmangueiras.com.br` atende o site atual; propor `portal.universodasmangueiras.com.br` sem modificar a raiz.

Contrato `contrato-hospedagem.pdf` fornecido pelo cliente:
- Cláusula 1.1.2.2 (página 4): prevê PHP, MySQL, PostgreSQL e SQL Server **genericamente** para hospedagens Linux I/II/III, mas a ficha (página 2) deixa os recursos específicos subordinados à contratação efetiva. **Não garante PostgreSQL no contrato específico**.
- Cláusula 5.3.1 (página 8): proíbe instalar programas no servidor compartilhado. Logo **não presumir hospedagem de serviço Python/FastAPI sempre ativo**.
- Cláusulas 6.7 e 6.7.1 (página 14): cópias mantidas **apenas sete dias**, em intervalos de até sete dias, sem substituir backup independente e testado.
- Cláusula 15 (página 21): cancelamento pode eliminar os arquivos irreversivelmente.
- O contrato de hospedagem fala sobre a senha de **administração da Locaweb**, diferente das senhas dos usuários do Portal UMA.

### Arquitetura recomendada

1. Preservar o site institucional, a demonstração v5.1 e a configuração de domínio enquanto há dúvidas técnicas.
2. Conferir no painel **Banco de dados** os tipos disponíveis e limites do plano, sem copiar credenciais.
3. Conferir **Domínios** para criação de subdomínio com pasta própria e **SSL/DNS** para HTTPS.
4. Avaliar publicar o **frontend estático** React compilado em pasta/subdomínio da Locaweb.
5. Hospedar **FastAPI e PostgreSQL** em infraestrutura compatível, preferencialmente gerenciada, se o compartilhado não comportar.
6. Homologar antes de produção: HTTPS, política de acesso, backup independente e restauração testada, logs, recuperação de conta, rate limiting, MFA do SuperAdmin e proteção de dados pessoais.
7. Sem mudanças de DNS, contratos, servidores ou publicação de credenciais sem autorização.

## 2. Acessos SEM E-MAIL — fluxo vigente

**Novo fluxo, solicitado em 23/10/2026:** o SuperAdmin cadastra nome, **nome de usuário** (sem e-mail), perfil e loja. O Portal UMA gera **senha provisória ALEATÓRIA, INDIVIDUAL, exibida uma única vez**; validade inicial de 72 horas. A primeira sessão fica limitada à troca obrigatória de senha. Não existe senha global igual para todos.

- Username de 3 a 40 caracteres: letras sem acento, números, ponto, sublinhado e hífen. Não exigir e-mail.
- Senha pessoal de no mínimo 12 caracteres, nunca igual à provisória; não permite acesso aos módulos antes da troca.
- Senhas são protegidas por hash **Argon2id** com salt automático; nunca armazenadas, registradas na auditoria ou consultáveis em texto aberto.
- Sessões geram tokens criptograficamente aleatórios; o PostgreSQL armazena **somente hashes** dos tokens.
- Bloqueio temporário após cinco tentativas erradas; sessões de troca de senha duram 15 minutos e sessões normais 12 horas.
- O SuperAdmin pode redefinir a senha provisória e invalidar sessões anteriores.
- **Excluir usuário** revoga o acesso, encerra sessões, remove o colaborador da lista de contas administráveis, mas preserva a identidade e os dados históricos para auditoria (**exclusão lógica**, não exclusão física de informações comerciais). Não é possível excluir o SuperAdmin.
- Um administrador operacional pode trabalhar nas três lojas, mas não administrar contas; vendedor fica limitado à sua única loja e leitura aprovada.
- Criação do primeiro SuperAdmin não está disponível por rota HTTP. O procedimento privado abaixo verifica ausência de outro SuperAdmin.
- O fluxo OIDC anterior fica compatível como alternativa, mas não é obrigatório para cadastrar colaboradores por login local; o antigo pré-cadastro por e-mail não é usado na interface.
- A prévia estática do GitHub Pages **não envia nem valida senhas reais**. Nunca inserir informações verdadeiras nela.

### Como preparar o primeiro SuperAdmin (somente manutenção privada)

Requer PostgreSQL já implantado, migração `0008`, ambiente protegido e HTTPS para login real. Não executar em GitHub Actions nem compartilhar a saída do terminal.

```bash
cd operacional/backend
alembic upgrade head
export UMA_INITIAL_SUPERADMIN_USERNAME='substituir-por-login-escolhido'
export UMA_INITIAL_SUPERADMIN_NAME='Nome do SuperAdmin'
export UMA_CONFIRM_INITIAL_SUPERADMIN='I_UNDERSTAND_ONE_TIME'
python -m app.bootstrap_local
```

O comando cria exatamente um SuperAdmin e exibe sua senha inicial somente uma vez. Em caso de perda/expiração, **recuperação exclusivamente por operador autorizado com acesso administrativo ao banco**, usando `python -m app.recover_superadmin` e variáveis `UMA_SUPERADMIN_USERNAME` / `UMA_CONFIRM_SUPERADMIN_RESET=I_UNDERSTAND_ONE_TIME`. A recuperação revoga sessões antigas. Recomenda-se guardar logs de operações sem senhas.

### Antes da publicação real

Obrigatório configurar infraestrutura, HTTPS, backup, autenticação forte (especialmente **MFA do SuperAdmin**), fluxo de recuperação privado, testes contra força bruta por IP/proxy e autorização por loja. Armazenar tokens e credenciais de modo protegido; avaliar cookies HttpOnly seguros com proteção CSRF para a implantação final. O modo atual de sessão do frontend usa armazenamento por aba e requer revisão em homologação.

## 3. Perguntas pendentes à Locaweb

No painel (sem publicar segredos): verificar **Banco de dados** (MySQL/PostgreSQL disponíveis), **Domínios** (subdomínio/pasta), **Certificado SSL** (causa de DNS Pendente), **Configurações** (possibilidades de arquivos estáticos e restrições de execução). Pedir ao suporte por escrito: “Hospedagem I Linux permite hospedar uma interface React estática em subdomínio com HTTPS? Há suporte a processo contínuo Python ASGI/FastAPI ou somente PHP? Quais bancos e limitações estão incluídos?”.


## 5. Módulos sem ERP — anexos (migração 0009)

As rotinas podem ser alimentadas manualmente sem integração ao ERP: avaliações Google,
insumos, clientes e ligações, checklist, planejamento WhatsApp e Instagram, treinamentos.

A API oferece upload, download e exclusão de **artes e evidências de publicação**
(JPEG/PNG/WebP até 3 MB por arquivo) e de documentos de treinamento (PDF até 5 MB).
Os bytes são armazenados em **tabelas privadas PostgreSQL**, não no GitHub Pages,
na pasta da Locaweb ou em links públicos; a permissão é verificada a cada chamada.
O controle de acesso exige administrador ou SuperAdmin para alteração; vendedores
mantêm consulta somente por loja, conforme aprovação anterior.

Backups PostgreSQL com os anexos precisam de **restauração testada** e retenção adequada.
Configurar limites de upload também no proxy e monitorar consumo de disco.
Os PDFs de treinamentos **não são assinaturas digitais**; autenticação forte e
termos adequados são requisito para futura assinatura. O Google e os serviços
de publicação seguem com conferência e registro manual.

As rotas ficam em `app/attachments_routes.py`; controles de formato, tamanho,
escopo, auditoria e revisões em `app/attachments_service.py`.
