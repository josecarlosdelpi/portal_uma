/** Labels are UX only. Backend remains the exclusive authority for access. */
export const stores = {
  JOINVILLE: "Joinville",
  ITAJAI: "Itajaí",
  TUBARAO: "Tubarão",
} as const;
export type StoreCode = keyof typeof stores;

export type PermissionGroup = {
  title: string;
  help: string;
  permissions: ReadonlyArray<{ code: string; name: string; detail?: string }>;
};

export const permissionGroups: ReadonlyArray<PermissionGroup> = [
  {
    title: "Visão geral",
    help: "Painel com indicadores autorizados para a loja.",
    permissions: [{ code: "overview.view", name: "Acessar visão geral" }],
  },
  {
    title: "Vendas",
    help: "Permissões específicas evitam expor números não autorizados.",
    permissions: [
      { code: "sales.view", name: "Abrir módulo de vendas" },
      { code: "sales.revenue.view", name: "Ver faturamento" },
      { code: "sales.target.view", name: "Ver meta de vendas" },
      { code: "sales.attainment.view", name: "Ver atingimento da meta" },
      { code: "sales.previous_month.view", name: "Comparação com mês anterior" },
      { code: "sales.previous_year.view", name: "Comparação com ano anterior" },
    ],
  },
  {
    title: "Gestão comercial",
    help: "Consultas e apresentação gerencial.",
    permissions: [
      { code: "targets.view", name: "Metas diárias" },
      { code: "monthly_closing.view", name: "Fechamento mensal" },
      { code: "telemarketing.view", name: "Televendas" },
    ],
  },
  {
    title: "Rotinas e comunicação",
    help: "Somente visualização para vendedores nesta primeira fase.",
    permissions: [
      { code: "reviews.view", name: "Avaliações Google" },
      { code: "supplies.view", name: "Insumos" },
      { code: "checklist.view", name: "Checklist" },
      { code: "training.view", name: "Treinamentos" },
      { code: "whatsapp_status.view", name: "Status WhatsApp" },
      { code: "instagram.view", name: "Instagram" },
    ],
  },
];

export const readPermissionCodes = permissionGroups.flatMap(
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
