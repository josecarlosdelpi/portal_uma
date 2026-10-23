/** All business information is fetched from the protected Python API. */
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export type MyProfile = {
  id: string;
  display_name: string;
  profile: "superadmin" | "administrator" | "seller";
  stores: string[];
  features: { targets: boolean };
};

export type PortalUser = {
  id: string;
  display_name: string;
  profile: "superadmin" | "administrator" | "seller";
  active: boolean;
  stores: string[];
  overrides: Record<string, boolean>;
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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
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

const adminPath = "/api/v1/admin";

export const api = {
  me: (token: string, signal?: AbortSignal) =>
    request<MyProfile>(token, "/api/v1/me", "GET", undefined, signal),

  users: (token: string) =>
    request<PortalUser[]>(token, adminPath + "/users"),

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
};
