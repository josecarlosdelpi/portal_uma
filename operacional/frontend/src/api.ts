/** All business information is fetched from the protected Python API. */
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export type MyProfile = {
  id: string;
  display_name: string;
  profile: "superadmin" | "administrator" | "seller";
  stores: string[];
  features: { targets: boolean; overview: boolean; monthly_closing: boolean; reviews: boolean; supplies: boolean; telemarketing: boolean; checklist: boolean; daily_tasks: boolean; whatsapp_status: boolean; instagram: boolean; training: boolean };
};

export type PortalUser = {
  id: string;
  display_name: string;
  profile: "superadmin" | "administrator" | "seller";
  active: boolean;
  username: string | null;
  must_change_password: boolean;
  stores: string[];
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

export type StoreGroup = {
  id: string;
  store: string;
  name: string;
  active: boolean;
  permissions: string[];
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

export type DailyBase = { date: string; weekday: number; base_daily_target: string | null };

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
    status: "awaiting_official_import";
    monthly_revenue: null;
    attainment_percent: null;
    dynamic_day_plan: null;
  };
};


export type OverviewStore = {
  code: string;
  name: string;
  target: string | null;
  target_visibility: "allowed" | "restricted";
  revenue: null;
  attainment_percent: null;
  previous_month_change_percent: null;
  previous_year_change_percent: null;
};

export type OverviewSnapshot = {
  year: number;
  month: number;
  scope: "consolidated" | "store";
  stores: OverviewStore[];
  summary: {
    monthly_target: string | null;
    revenue: null;
    attainment_percent: null;
    previous_month_change_percent: null;
    previous_year_change_percent: null;
  };
  source: { sales_status: "awaiting_erp_integration"; sales_updated_at: null; message: string };
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
    code: string; name: string; target: string | null; revenue: null;
    attainment_percent: null; change_percent: null;
  }>;
  total_target: string | null;
  revenue: null;
  attainment_percent: null;
  previous_month_change_percent: null;
  previous_year_change_percent: null;
  source: {status: "awaiting_erp_integration"; sales_updated_at: null};
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
  profile: "administrator" | "seller"; stores: string[]; active: boolean;
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

  createLocalUser: (token: string, payload: {
    username: string; display_name: string; profile: "administrator" | "seller";
    store_code: string | null;
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
    request<StoreGroup[]>(token, adminPath + "/groups"),

  audit: (token: string, offset = 0, limit = 30) =>
    request<AuditPage>(token, adminPath + "/audit?offset=" + offset + "&limit=" + limit),

  saveGroup: (token: string, groupId: string, permissions: string[]) =>
    request<{ store: string; permissions: string[] }>(
      token, adminPath + "/groups/" + encodeURIComponent(groupId) + "/permissions",
      "PUT", { permissions },
    ),

  saveOverrides: (token: string, userId: string, permissions: Record<string, boolean | null>) =>
    request<{ user_id: string; overrides: Record<string, boolean> }>(
      token, adminPath + "/users/" + encodeURIComponent(userId) + "/overrides",
      "PUT", { permissions },
    ),

  setUserStore: (token: string, userId: string, storeCode: string) =>
    request<{ user_id: string; stores: string[] }>(
      token, adminPath + "/users/" + encodeURIComponent(userId) + "/store",
      "PUT", { store_code: storeCode },
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

};
