import { request } from "./api";

export type ExpCategory = {
  id: string; name: string; active: boolean; created_at: string;
};

export type ExpSupplier = {
  supplier_key: string; label: string;
  doc: string | null; name: string; rows: number;
};

export type ExpRule = {
  id: string; supplier_key: string; supplier_label: string;
  store_code: string | null; scope: string;
  category_id: string; category_name: string; active: boolean;
};

export type ExpWarning = { code: string; message: string };

export type ExpByCategory = {
  category_id: string | null; name: string;
  total: string; pct: string; rows: number;
};

export type ExpByStore = {
  store: string; total: string;
  categories: { name: string; total: string; pct: string }[];
};

export type ExpExcludedNature = {
  bucket: string; label: string; total: string; rows: number;
};

export type ExpAnalysis = {
  availability: string;
  warnings: ExpWarning[];
  orphan_classifications: number;
  totals: {
    paid_total: string; classified: string; unclassified: string;
    classified_pct: string | null;
    payment_rows: number; unclassified_rows: number;
  } | null;
  by_category: ExpByCategory[];
  by_store: ExpByStore[];
  shared_memo: { amount: string; rows: number } | null;
  excluded_natures: ExpExcludedNature[];
  pending_nature: string | null;
  methodology: string[];
};

export type ExpLine = {
  fingerprint: string;
  supplier_name: string; supplier_doc: string | null;
  store_code: string;
  paid_at: string;
  document_number: string | null; installment_number: string | null;
  amount: string;
  nature: string; nature_label: string; eligible: boolean;
  category_id: string | null; category_name: string | null;
  origin: "manual" | "rule_store" | "rule_general" | "none" | string;
};

export type ExpLinesPage = {
  items: ExpLine[]; total: number; page: number; page_size: number;
  orphan_classifications: number; availability?: string;
  categories: ExpCategory[];
};

export type ExpSetResult = {
  fingerprint: string;
  category_id: string | null; category_name?: string;
  origin: string; rows: number;
};

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? "?" + text : "";
};

export const expensesApi = {
  categories: (token: string) =>
    request<{ items: ExpCategory[] }>(token, "/api/v1/expenses/categories"),
  createCategory: (token: string, name: string) =>
    request<ExpCategory>(token, "/api/v1/expenses/categories", "POST", { name }),
  updateCategory: (token: string, id: string,
                   body: { name?: string; active?: boolean }) =>
    request<ExpCategory>(token, "/api/v1/expenses/categories/" + id, "PATCH", body),

  suppliers: (token: string, q: string) =>
    request<{ items: ExpSupplier[] }>(token,
      "/api/v1/expenses/suppliers" + qs({ q })),

  rules: (token: string) =>
    request<{ items: ExpRule[] }>(token, "/api/v1/expenses/supplier-rules"),
  createRule: (token: string, body: { supplier_key: string;
    supplier_label: string; store_code?: string | null; category_id: string }) =>
    request<{ id: string }>(token, "/api/v1/expenses/supplier-rules", "POST", body),
  updateRule: (token: string, id: string,
               body: { category_id?: string; active?: boolean }) =>
    request<{ id: string }>(token, "/api/v1/expenses/supplier-rules/" + id,
      "PATCH", body),

  analysis: (token: string, params: { date_from: string; date_to: string;
    store?: string; category_id?: string; situation?: string;
    supplier?: string }) =>
    request<ExpAnalysis>(token, "/api/v1/expenses/analysis" + qs(params)),

  lines: (token: string, params: { date_from: string; date_to: string;
    store?: string; category_id?: string; situation?: string;
    supplier?: string; page?: number; page_size?: number }) =>
    request<ExpLinesPage>(token, "/api/v1/expenses/lines" + qs(params)),

  setCategory: (token: string, fingerprint: string,
                category_id: string | null) =>
    request<ExpSetResult>(token,
      "/api/v1/expenses/lines/" + fingerprint + "/category",
      "PUT", { category_id }),
};
