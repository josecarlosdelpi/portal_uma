/** Labels are UX only. Backend remains the exclusive authority for access. */
export const stores = {
  JOINVILLE: "Joinville",
  ITAJAI: "Itajaí",
  TUBARAO: "Tubarão",
} as const;
export type StoreCode = keyof typeof stores;

export type PermissionMeta = {
  code: string;
  name: string;
  kind: "view" | "edit" | "action";
  requiresAllStores?: boolean;
};

export type PermissionGroup = {
  module: string;
  title: string;
  help: string;
  permissions: ReadonlyArray<PermissionMeta>;
};

/** Catálogo espelha app.admin_service.PERMISSION_CATALOG — a autoridade é a API. */
export const permissionGroups: ReadonlyArray<PermissionGroup> = [
  {
    module: "overview",
    title: "Visão geral",
    help: "Painel com indicadores autorizados para a loja.",
    permissions: [
      { code: "overview.view", name: "Acessar visão geral", kind: "view" },
    ],
  },
  {
    module: "sales",
    title: "Vendas",
    help: "Permissões específicas evitam expor números não autorizados.",
    permissions: [
      { code: "sales.view", name: "Abrir módulo de vendas", kind: "view" },
      { code: "sales.revenue.view", name: "Ver faturamento", kind: "view" },
      { code: "sales.target.view", name: "Ver meta de vendas", kind: "view" },
      { code: "sales.attainment.view", name: "Ver atingimento da meta", kind: "view" },
      { code: "sales.previous_month.view", name: "Comparação com mês anterior", kind: "view" },
      { code: "sales.previous_year.view", name: "Comparação com ano anterior", kind: "view" },
      { code: "sales.import", name: "Importar vendas do ERP", kind: "action", requiresAllStores: true },
    ],
  },
  {
    module: "targets",
    title: "Metas diárias",
    help: "Consulta e manutenção das metas da loja.",
    permissions: [
      { code: "targets.view", name: "Ver metas diárias", kind: "view" },
      { code: "targets.edit", name: "Editar metas e calendário", kind: "edit" },
    ],
  },
  {
    module: "telemarketing",
    title: "Telemarketing",
    help: "Carteira de clientes e registros de contato.",
    permissions: [
      { code: "telemarketing.view", name: "Ver telemarketing", kind: "view" },
      { code: "telemarketing.edit", name: "Registrar contatos", kind: "edit" },
    ],
  },
  {
    module: "monthly_closing",
    title: "Fechamento mensal",
    help: "Consolida as três lojas: exige abrangência completa.",
    permissions: [
      { code: "monthly_closing.view", name: "Ver fechamento consolidado", kind: "view", requiresAllStores: true },
      { code: "monthly_closing.edit", name: "Editar fechamento", kind: "edit", requiresAllStores: true },
      { code: "monthly_closing.archive", name: "Arquivar versões do fechamento", kind: "action", requiresAllStores: true },
    ],
  },
  {
    module: "daily_tasks",
    title: "Tarefas diárias",
    help: "Rotina diária da loja.",
    permissions: [
      { code: "daily_tasks.view", name: "Ver tarefas diárias", kind: "view" },
      { code: "daily_tasks.edit", name: "Editar tarefas diárias", kind: "edit" },
    ],
  },
  {
    module: "checklist",
    title: "Checklist semanal",
    help: "Tarefas semanais e meta de ligações.",
    permissions: [
      { code: "checklist.view", name: "Ver checklist", kind: "view" },
      { code: "checklist.edit", name: "Editar checklist", kind: "edit" },
    ],
  },
  {
    module: "supplies",
    title: "Materiais e insumos",
    help: "Estoque de materiais da loja.",
    permissions: [
      { code: "supplies.view", name: "Ver insumos", kind: "view" },
      { code: "supplies.edit", name: "Movimentar insumos", kind: "edit" },
    ],
  },
  {
    module: "reviews",
    title: "Avaliações Google",
    help: "Registro mensal de avaliações.",
    permissions: [
      { code: "reviews.view", name: "Ver avaliações", kind: "view" },
      { code: "reviews.edit", name: "Editar avaliações", kind: "edit" },
    ],
  },
  {
    module: "whatsapp_status",
    title: "Status WhatsApp",
    help: "Calendário de postagens da loja.",
    permissions: [
      { code: "whatsapp_status.view", name: "Ver status WhatsApp", kind: "view" },
      { code: "whatsapp_status.edit", name: "Editar status WhatsApp", kind: "edit" },
    ],
  },
  {
    module: "instagram",
    title: "Instagram",
    help: "Metas mensais de publicações.",
    permissions: [
      { code: "instagram.view", name: "Ver Instagram", kind: "view" },
      { code: "instagram.edit", name: "Editar Instagram", kind: "edit" },
    ],
  },
  {
    module: "training",
    title: "Padrões e treinamentos",
    help: "Procedimentos, versões e registros de treinamento.",
    permissions: [
      { code: "training.view", name: "Ver treinamentos", kind: "view" },
      { code: "training.edit", name: "Editar padrões e treinamentos", kind: "edit" },
    ],
  },
  {
    module: "finance",
    title: "Financeiro",
    help: "Despesas e pagamentos importados do ERP. Nunca é concedido por padrão.",
    permissions: [
      { code: "finance.view", name: "Consultar módulo financeiro", kind: "view" },
    ],
  },
];

export const grantableCodes = permissionGroups.flatMap(
  (group) => group.permissions.map((permission) => permission.code),
);

export const permissionName = (code: string): string =>
  permissionGroups.flatMap((group) => group.permissions)
    .find((permission) => permission.code === code)?.name ?? code;

export function labelStore(code: string): string {
  return stores[code as StoreCode] ?? code;
}

export function accessDecision(
  inherited: boolean,
  override: boolean | undefined,
): "inherited" | "granted" | "denied" {
  if (override === true) return "granted";
  if (override === false) return "denied";
  return inherited ? "granted" : "denied";
}
