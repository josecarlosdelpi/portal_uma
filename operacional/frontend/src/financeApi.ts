import {ApiError, request} from "./api";

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export type FinanceBatch = {
  id: string;
  domain: string;
  channel: string;
  file_name: string;
  sha256: string;
  row_count: number;
  coverage: string;
  period_start: string | null;
  period_end: string | null;
  status: "imported" | "failed";
  is_current: boolean;
  error_detail: string | null;
  quality_flag_count: number;
  imported_at: string | null;
  duration_ms: number;
};

export type FinanceQualityFlag = {row: number; code: string; detail: string};
export type FinanceBatchDetail = FinanceBatch & {quality_flags: FinanceQualityFlag[]};
export type FinanceBatchList = {items: FinanceBatch[]};

export type FinanceImportResult = {duplicated: boolean; batch: FinanceBatch};

export type FinanceSyncStatus = {
  file_key: string;
  last_status: string | null;
  last_check_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  last_applied: {imported_at: string | null; file_name: string;
    row_count: number} | null;
};

export type CategoryTotals = {
  open_amount: string; open_count: number;
  paid_month_amount: string; paid_month_count: number;
};

export type FinanceOverview = {
  as_of: string;
  month: string;
  has_data: boolean;
  last_import: {imported_at: string | null; file_name: string; row_count: number;
    period_start: string | null; period_end: string | null} | null;
  kpis: {
    open_amount: string; open_count: number;
    overdue_amount: string; overdue_count: number;
    due_7d_amount: string; due_7d_count: number;
    due_30d_amount: string; due_30d_count: number;
    paid_month_amount: string; paid_month_count: number;
  };
  monthly_due: Array<{month: string; amount: string; count: number}>;
  by_store: Array<{store_code: string; open_amount: string; open_count: number;
    paid_month_amount: string; paid_month_count: number}>;
  by_category: {compra_revenda?: CategoryTotals; despesa?: CategoryTotals};
};

export type ObligationItem = {
  id: string;
  supplier_name: string;
  supplier_doc: string | null;
  amount: string;
  due_date: string;
  paid_at: string | null;
  category: "despesa" | "compra_revenda";
  store_code: string;
  status: "aberto" | "pago";
  due_flag: "vencido" | "hoje" | "a_vencer" | "quitado";
  source_row: number;
};

export type ObligationPage = {
  items: ObligationItem[];
  total: number;
  sum_amount: string;
  page: number;
  page_size: number;
  has_data: boolean;
  by_month: Array<{month: string; amount: string; count: number}>;
  last_import?: {imported_at: string | null; file_name: string} | null;
};

export type PaymentsPage = ObligationPage & {
  by_store: Array<{store_code: string; amount: string; count: number}>;
  by_category: Record<string, {amount: string; count: number}>;
};

export type PurchasesView = {
  has_data: boolean;
  items: ObligationItem[];
  total: number;
  page: number;
  page_size: number;
  totals: {count: number; amount: string; paid_amount: string;
    paid_count: number; open_amount: string; open_count: number};
  by_store: Array<{store_code: string; amount: string; count: number}>;
  by_month: Array<{month: string; amount: string; count: number}>;
  top_suppliers: Array<{supplier_name: string; amount: string; count: number}>;
  last_import?: {imported_at: string | null; file_name: string} | null;
};

export type ObligationQuery = {
  store?: string; category?: string; status?: string; supplier?: string;
  due_from?: string; due_to?: string; sort?: string;
  page?: number; page_size?: number;
};

export type PaymentQuery = {
  store?: string; category?: string; supplier?: string;
  paid_from?: string; paid_to?: string; sort?: string;
  page?: number; page_size?: number;
};

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? "?" + text : "";
};

export const financeApi = {
  async importDespesas(token: string, file: File): Promise<FinanceImportResult> {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(baseUrl + "/api/v1/finance/import", {
      method: "POST", mode: "cors", cache: "no-store",
      headers: {Authorization: "Bearer " + token},
      body: form,
    });
    if (!response.ok) {
      let message = "Não foi possível importar o arquivo.";
      try {
        const body = await response.json();
        if (typeof body?.detail === "string" && body.detail) message = body.detail;
      } catch { /* resposta sem corpo json */ }
      throw new ApiError(response.status, message);
    }
    return response.json() as Promise<FinanceImportResult>;
  },

  sync: (token: string) =>
    request<FinanceSyncStatus>(token, "/api/v1/finance/sync"),

  batches: (token: string) =>
    request<FinanceBatchList>(token, "/api/v1/finance/batches"),

  batch: (token: string, id: string) =>
    request<FinanceBatchDetail>(token, "/api/v1/finance/batches/" + encodeURIComponent(id)),

  overview: (token: string, params: {store?: string; month?: string}) =>
    request<FinanceOverview>(token, "/api/v1/finance/overview" + qs(params)),

  obligations: (token: string, params: ObligationQuery) =>
    request<ObligationPage>(token, "/api/v1/finance/obligations" + qs(params)),

  payments: (token: string, params: PaymentQuery) =>
    request<PaymentsPage>(token, "/api/v1/finance/payments" + qs(params)),

  purchases: (token: string, params: {store?: string; supplier?: string;
    page?: number; page_size?: number}) =>
    request<PurchasesView>(token, "/api/v1/finance/purchases" + qs(params)),
};
