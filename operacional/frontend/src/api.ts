/** All business information is fetched from the protected Python API. */
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export type MyProfile = {
  id: string;
  display_name: string;
  profile: "superadmin" | "administrator" | "seller" | "staff";
  stores: string[];
  features: { targets: boolean; overview: boolean; monthly_closing: boolean; reviews: boolean; supplies: boolean; telemarketing: boolean; checklist: boolean; daily_tasks: boolean; whatsapp_status: boolean; instagram: boolean; training: boolean; sales: boolean; finance: boolean };
};

export type PortalUser = {
  id: string;
  display_name: string;
  profile: "superadmin" | "administrator" | "seller" | "staff";
  active: boolean;
  username: string | null;
  must_change_password: boolean;
  group: { id: string; name: string } | null;
  stores: string[];
  store_scope: string[];
  overrides: Record<string, boolean>;
};

export type AccessInvitation = {
  id: string;
  email: string;
  display_name: string;
  profile: "administrator" | "seller";
  store_code: string | null;
  status: "prepared" | "sent" | "activated" | "cancelled" | "expired";
  revision: number;
  created_at: string;
  delivery: "not_configured";
};

export type PrepareAccessInput = {
  display_name: string;
  email: string;
  profile: "administrator" | "seller";
  store_code: string | null;
};

export type AccessGroup = {
  id: string;
  name: string;
  description: string;
  active: boolean;
  stores: string[];
  permissions: string[];
  member_count: number;
};

export type GroupDetail = AccessGroup & {
  members: Array<{ id: string; display_name: string; active: boolean }>;
};

export type PermissionCatalog = {
  modules: Array<{
    module: string;
    permissions: Array<{ code: string; kind: "view" | "edit" | "action"; requires_all_stores?: boolean }>;
  }>;
  stores: string[];
  profiles: string[];
  non_delegable: string[];
};

export type EffectivePermissions = {
  user_id: string;
  display_name: string;
  is_superadmin: boolean;
  profile: string;
  group: { id: string; name: string } | null;
  stores: string[];
  items: Array<{
    module: string;
    code: string;
    kind: string;
    requires_all_stores: boolean;
    group_default: boolean;
    override: boolean | null;
    stores: string[];
    effective: boolean;
  }>;
};

export type AccessDiffEntry = { code: string; stores: string[] };

export type AccessPreview = {
  user_id: string;
  group: { id: string; name: string } | null;
  stores: string[];
  store_scope: string[];
  before: Record<string, string[]>;
  after: Record<string, string[]>;
  granted: AccessDiffEntry[];
  revoked: AccessDiffEntry[];
};

export type ReassignmentPreview = {
  group: { id: string; name: string };
  target: { id: string; name: string };
  member_count: number;
  members: Array<{
    user_id: string;
    display_name: string;
    stores_before: string[];
    stores_after: string[];
    granted: AccessDiffEntry[];
    revoked: AccessDiffEntry[];
  }>;
};

export type AuditEvent = {
  id: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type AuditPage = { items: AuditEvent[]; limit: number; offset: number };
export type UserPreferences = {
  sidebar_pinned: boolean; favorites: string[];
  store_colors?: Record<string, string>;
};

export type DailyBase = { date: string; weekday: number; base_daily_target: string | null };

export type DynamicDayPlan = { date: string; daily_target: string | null; sales_before: string };
export type DailySale = { date: string; revenue: string };

export type TargetSnapshot = {
  store_code: string;
  year: number;
  month: number;
  target: { amount: string | null; revision: number; updated_at: string | null };
  minimum: { amount: string | null; revision: number };
  days_off: string[];
  working_day_count: number;
  base_plan: DailyBase[];
  sales: {
    status: "awaiting_official_import" | "pilot_unverified";
    monthly_revenue: string | null;
    attainment_percent: string | null;
    dynamic_day_plan: DynamicDayPlan[] | null;
    daily_sales: DailySale[];
  };
};


export type OverviewStore = {
  code: string;
  name: string;
  target: string | null;
  target_visibility: "allowed" | "restricted";
  revenue: string | null;
  attainment_percent: string | null;
  previous_month_change_percent: string | null;
  previous_year_change_percent: string | null;
};

export type OverviewSnapshot = {
  year: number;
  month: number;
  scope: "consolidated" | "store";
  stores: OverviewStore[];
  summary: {
    monthly_target: string | null;
    revenue: string | null;
    attainment_percent: string | null;
    previous_month_change_percent: string | null;
    previous_year_change_percent: string | null;
  };
  source: { sales_status: string; sales_updated_at: string | null; message: string };
};

export type ClosingPriority = {
  id: string; what: string; owner: string;
  scope: "all" | "JOINVILLE" | "TUBARAO" | "ITAJAI";
  due: string; status: "pendente" | "andamento" | "concluida";
};

export type ClosingNotes = { JOINVILLE: string; TUBARAO: string; ITAJAI: string };

export type ClosingDraft = {
  opening: string;
  stores: ClosingNotes;
  opportunities: string;
  wins: string;
  improvements: string;
  notices: string;
  notes: ClosingNotes;
  priorities: ClosingPriority[];
};

export type ClosingData = {
  stores: Array<{
    code: string; name: string; target: string | null; revenue: string | null;
    attainment_percent: string | null; change_percent: string | null;
  }>;
  total_target: string | null;
  revenue: string | null;
  attainment_percent: string | null;
  previous_month_change_percent: string | null;
  previous_year_change_percent: string | null;
  source: {status: string; sales_updated_at: string | null};
};

export type ClosingSnapshot = {
  period: string;
  draft: ClosingDraft;
  data: ClosingData;
  previous_pending: ClosingPriority[];
  durations: number[];
  state: "partial_sales_pending";
  source: string;
};

export type ClosingView = {
  year: number; month: number; draft: ClosingDraft; revision: number;
  updated_at: string | null; data: ClosingData;
  previous_pending: ClosingPriority[];
  last_archive: {id: string; version: number; created_at: string} | null;
  durations: number[];
  sales_data_complete: false;
};

export type ClosingArchiveRef = {
  id: string; version: number; state: string; created_at: string;
};
export type ClosingArchive = ClosingArchiveRef & {snapshot: ClosingSnapshot};

// ---- Integracao ERP — Vendas e Devolucoes (piloto) ----

export type SalesBatch = {
  id: string; kind: "VENDAS" | "DEVOLUCOES"; source: "MANUAL_UPLOAD" | "DRIVE_SYNC";
  status: "RECEIVED" | "APPLIED" | "DUPLICATE" | "FAILED";
  file_name: string; rows_total: number; rows_applied: number; rows_rejected: number;
  period_start: string | null; period_end: string | null;
  error_summary: {errors: string[]; warnings: string[]} | null;
  applied_at: string | null;
};

export type SalesSyncStatus = {
  kinds: Array<{
    kind: "VENDAS" | "DEVOLUCOES"; last_applied_at: string | null;
    file_name: string | null; rows_applied: number;
    period_start: string | null; period_end: string | null;
  }>;
  drive: {
    enabled: boolean; interval_seconds: number;
    files: Array<{
      file_key: string; file_name: string | null;
      last_check_at: string | null; last_sync_at: string | null;
      remote_modified_at: string | null; last_status: string;
      last_error: string | null; consecutive_failures: number;
    }>;
  };
};

export type SalesStoreSummary = {
  code: string; revenue: string | null; revenue_visibility: "allowed" | "restricted";
  quantity: string; rows: number;
  returns_revenue: string | null; returns_quantity: string; returns_rows: number;
};

export type SalesSummary = {
  from: string; to: string;
  stores: SalesStoreSummary[];
  totals: {
    revenue: string; quantity: string; rows: number;
    returns_revenue: string; returns_quantity: string; returns_rows: number;
  };
};

export type SalesDailyRow = {
  date: string; store_code: string;
  revenue: string; quantity: string;
  returns_revenue: string; returns_quantity: string;
};

export type SalesTopItem = {
  key: string; customer_cnpj: string | null;
  revenue: string; quantity: string; rows: number; stores: string[];
};

export type SalesTopResult = {
  dimension: "products" | "sellers" | "customers";
  from: string; to: string; items: SalesTopItem[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(
  token: string, route: string,
  method = "GET", body?: unknown, signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(baseUrl + route, {
    method,
    mode: "cors",
    cache: "no-store",
    signal,
    headers: {
      Authorization: "Bearer " + token,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    let message = "Erro ao acessar o Portal UMA.";
    if (response.status === 401) message = "Sessão expirada ou inválida. Entre novamente.";
    if (response.status === 403) message = "Acesso não permitido para esta conta.";
    if (response.status === 503) message = "Serviço de autenticação indisponível ou não configurado.";
    if (response.status === 409) message = "Os dados foram alterados ou já existem. Atualize a página.";
    if (response.status === 422) message = "Revise as informações antes de salvar.";
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}


export type LocalLoginResult = {
  access_token: string; token_type: "bearer"; expires_at: string;
  must_change_password: boolean; display_name: string;
  profile: "superadmin" | "administrator" | "seller";
};
export type LocalCreateAccount = {
  id: string; display_name: string; username: string;
  profile: "administrator" | "seller" | "staff";
  group: { id: string; name: string } | null;
  stores: string[]; active: boolean;
  temporary_password: string; temporary_valid_hours: number;
  must_change_password: true;
};
export type LocalResetPassword = {
  user_id: string; username: string;
  temporary_password: string; temporary_valid_hours: number;
  must_change_password: true;
};

export async function localLogin(username: string, password: string): Promise<LocalLoginResult> {
  const response = await fetch(baseUrl + "/api/v1/local-auth/login", {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw new ApiError(
    response.status,
    response.status === 401 ? "Usuário ou senha inválidos, expirados ou temporariamente bloqueados." :
      "Não foi possível entrar. Verifique a conexão.",
  );
  return response.json() as Promise<LocalLoginResult>;
}
export function localChangePassword(token: string, newPassword: string) {
  return request<LocalLoginResult>(
    token, "/api/v1/local-auth/change-password", "POST", { new_password: newPassword },
  );
}
export function localLogout(token: string) {
  return request<{ signed_out: boolean }>(token, "/api/v1/local-auth/logout", "POST");
}

const adminPath = "/api/v1/admin";

export const api = {
  me: (token: string, signal?: AbortSignal) =>
    request<MyProfile>(token, "/api/v1/me", "GET", undefined, signal),

  preferences: (token: string) =>
    request<UserPreferences>(token, "/api/v1/me/preferences"),
  savePreferences: (token: string, body: UserPreferences) =>
    request<UserPreferences>(token, "/api/v1/me/preferences", "PUT", body),

  createLocalUser: (token: string, payload: {
    username: string; display_name: string;
    profile: "administrator" | "seller" | "staff";
    group_id: string; store_codes?: string[];
  }) => request<LocalCreateAccount>(token, adminPath + "/local-users", "POST", payload),

  resetLocalPassword: (token: string, userId: string) =>
    request<LocalResetPassword>(
      token, adminPath + "/users/" + encodeURIComponent(userId) + "/reset-password", "POST",
    ),

  deleteUser: (token: string, userId: string) =>
    request<{ user_id: string; deleted: boolean }>(
      token, adminPath + "/users/" + encodeURIComponent(userId), "DELETE",
    ),

  users: (token: string) =>
    request<PortalUser[]>(token, adminPath + "/users"),

  invitations: (token: string) =>
    request<AccessInvitation[]>(token, adminPath + "/invitations"),

  prepareInvitation: (token: string, payload: PrepareAccessInput) =>
    request<AccessInvitation>(token, adminPath + "/invitations", "POST", payload),

  cancelInvitation: (token: string, invitationId: string, expectedRevision: number) =>
    request<AccessInvitation>(
      token, adminPath + "/invitations/" + encodeURIComponent(invitationId),
      "DELETE", { expected_revision: expectedRevision },
    ),

  groups: (token: string) =>
    request<AccessGroup[]>(token, adminPath + "/groups"),

  groupDetail: (token: string, groupId: string) =>
    request<GroupDetail>(token, adminPath + "/groups/" + encodeURIComponent(groupId)),

  catalog: (token: string) =>
    request<PermissionCatalog>(token, adminPath + "/catalog"),

  createGroup: (token: string, payload: {
    name: string; description: string; store_codes: string[]; permissions: string[];
  }) => request<AccessGroup>(token, adminPath + "/groups", "POST", payload),

  updateGroup: (token: string, groupId: string, payload: {
    name: string; description: string; store_codes: string[]; permissions: string[];
  }) => request<AccessGroup & { members_affected: number }>(
    token, adminPath + "/groups/" + encodeURIComponent(groupId), "PUT", payload),

  duplicateGroup: (token: string, groupId: string, name: string) =>
    request<AccessGroup>(
      token, adminPath + "/groups/" + encodeURIComponent(groupId) + "/duplicate",
      "POST", { name },
    ),

  setGroupActive: (token: string, groupId: string, active: boolean) =>
    request<AccessGroup>(
      token, adminPath + "/groups/" + encodeURIComponent(groupId) + "/active",
      "PATCH", { active },
    ),

  deleteGroup: (token: string, groupId: string, reassignTo?: string) =>
    request<{ deleted: boolean; members_moved: number }>(
      token, adminPath + "/groups/" + encodeURIComponent(groupId) +
        (reassignTo ? "?reassign_to=" + encodeURIComponent(reassignTo) : ""),
      "DELETE",
    ),

  audit: (token: string, offset = 0, limit = 30) =>
    request<AuditPage>(token, adminPath + "/audit?offset=" + offset + "&limit=" + limit),

  updateUserAccess: (token: string, userId: string, payload: {
    profile?: string; group_id?: string; store_codes?: string[] | null;
  }) => request<{ user_id: string; profile: string; group: { id: string; name: string } | null;
    stores: string[]; store_scope: string[] }>(
    token, adminPath + "/users/" + encodeURIComponent(userId) + "/access",
    "PUT", payload,
  ),

  previewUserAccess: (token: string, userId: string, payload: {
    group_id: string; store_codes?: string[];
  }) => request<AccessPreview>(
    token, adminPath + "/users/" + encodeURIComponent(userId) + "/access-preview",
    "POST", payload,
  ),

  reassignmentPreview: (token: string, groupId: string, reassignTo: string) =>
    request<ReassignmentPreview>(
      token, adminPath + "/groups/" + encodeURIComponent(groupId) +
        "/reassignment-preview?reassign_to=" + encodeURIComponent(reassignTo),
    ),

  effectivePermissions: (token: string, userId: string) =>
    request<EffectivePermissions>(
      token, adminPath + "/users/" + encodeURIComponent(userId) + "/effective",
    ),

  saveOverrides: (token: string, userId: string, permissions: Record<string, boolean | null>) =>
    request<{ user_id: string; overrides: Record<string, boolean> }>(
      token, adminPath + "/users/" + encodeURIComponent(userId) + "/overrides",
      "PUT", { permissions },
    ),

  setActive: (token: string, userId: string, active: boolean) =>
    request<{ user_id: string; active: boolean }>(
      token, adminPath + "/users/" + encodeURIComponent(userId) + "/active",
      "PATCH", { active },
    ),

  target: (token: string, store: string, year: number, month: number) =>
    request<TargetSnapshot>(token, "/api/v1/targets/" + encodeURIComponent(store) + "/" + year + "/" + month),

  saveTargetGoal: (token: string, store: string, year: number, month: number,
                   amount: string, expectedRevision: number) =>
    request<TargetSnapshot>(token, "/api/v1/targets/" + encodeURIComponent(store) + "/" + year + "/" + month + "/goal",
      "PUT", { amount, expected_revision: expectedRevision }),

  saveTargetMinimum: (token: string, store: string, amount: string, expectedRevision: number) =>
    request<{ store_code: string; amount: string; revision: number }>(
      token, "/api/v1/targets/" + encodeURIComponent(store) + "/minimum",
      "PUT", { amount, expected_revision: expectedRevision }),

  saveTargetCalendar: (token: string, store: string, year: number, month: number,
                       daysOff: string[], expectedRevision: number) =>
    request<TargetSnapshot>(token, "/api/v1/targets/" + encodeURIComponent(store) + "/" + year + "/" + month + "/calendar",
      "PUT", { days_off: daysOff, expected_revision: expectedRevision }),
  overview: (token: string, year: number, month: number) =>
    request<OverviewSnapshot>(token, "/api/v1/overview/" + year + "/" + month),

  closing: (token: string, year: number, month: number) =>
    request<ClosingView>(token, "/api/v1/monthly-closing/" + year + "/" + month),

  saveClosing: (token: string, year: number, month: number,
                draft: ClosingDraft, expected_revision: number) =>
    request<ClosingView>(token, "/api/v1/monthly-closing/" + year + "/" + month,
      "PUT", {draft, expected_revision}),

  archiveClosing: (token: string, year: number, month: number, expected_revision: number) =>
    request<ClosingArchive>(token, "/api/v1/monthly-closing/" + year + "/" + month + "/archives",
      "POST", {expected_revision}),

  closingArchives: (token: string, year: number, month: number) =>
    request<ClosingArchiveRef[]>(token, "/api/v1/monthly-closing/" + year + "/" + month + "/archives"),

  closingArchive: (token: string, year: number, month: number, id: string) =>
    request<ClosingArchive>(token, "/api/v1/monthly-closing/" + year + "/" + month +
      "/archives/" + encodeURIComponent(id)),

  salesStatus: (token: string) =>
    request<SalesSyncStatus>(token, "/api/v1/sales/status"),

  salesImports: (token: string, limit = 30) =>
    request<{items: SalesBatch[]}>(token, "/api/v1/sales/imports?limit=" + limit),

  salesSummary: (token: string, from: string, to: string, store?: string) =>
    request<SalesSummary>(token, "/api/v1/sales/summary?from=" + from + "&to=" + to +
      (store ? "&store=" + encodeURIComponent(store) : "")),

  salesDaily: (token: string, from: string, to: string, store?: string) =>
    request<{from: string; to: string; days: SalesDailyRow[]}>(
      token, "/api/v1/sales/daily?from=" + from + "&to=" + to +
      (store ? "&store=" + encodeURIComponent(store) : "")),

  salesTop: (token: string, dimension: "products" | "sellers" | "customers",
             from: string, to: string, store?: string, limit = 10,
             sort?: "revenue" | "quantity") =>
    request<SalesTopResult>(token, "/api/v1/sales/top/" + dimension +
      "?from=" + from + "&to=" + to + "&limit=" + limit +
      (sort ? "&sort=" + sort : "") +
      (store ? "&store=" + encodeURIComponent(store) : "")),

  triggerSalesSync: (token: string) =>
    request<{results: Array<{file_key: string; status: string; last_error: string | null}>}>(
      token, "/api/v1/sales/sync", "POST"),

};

export async function uploadSalesFile(
  token: string, kind: "vendas" | "devolucoes", file: File,
): Promise<{batch: SalesBatch}> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(baseUrl + "/api/v1/sales/imports/" + kind, {
    method: "POST", mode: "cors", cache: "no-store",
    headers: {Authorization: "Bearer " + token}, body: form,
  });
  if (!response.ok) {
    let message = "Não foi possível importar o arquivo.";
    try {
      const detail = await response.json();
      const first = detail?.detail?.batch?.error_summary?.errors?.[0];
      if (typeof first === "string") message = first;
      else if (typeof detail?.detail?.message === "string") message = detail.detail.message;
    } catch { /* resposta sem corpo JSON */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<{batch: SalesBatch}>;
}
