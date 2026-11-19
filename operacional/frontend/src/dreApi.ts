import { request } from "./api";

export type DreSource = {
  availability: "current" | "unavailable" | "missing";
  last_import: { imported_at: string | null; file_name: string;
    row_count: number; period_start: string | null;
    period_end: string | null } | null;
  last_status: string | null;
  last_check_at?: string | null;
  sync_status?: string | null;
};

export type DreRow = {
  key: string;
  label: string;
  kind: "input" | "subtotal" | "memo";
  bucket?: string;
  expandable?: boolean;
  state?: string;
  note?: string;
  values: Record<string, string | null>;
  pct: Record<string, string | null>;
};

export type DreExcludedGroup = {
  bucket: string;
  label: string;
  amount: string | null;
  count: number;
  expandable: boolean;
  columns: Record<string, string | null>;
};

export type DreWarning = { code: string; message: string };

export type DrePreview = {
  disclaimer: string;
  basis: string;
  rounding_policy: string;
  period: { month: string; mode: string; first: string; last: string };
  columns: string[];
  consolidated: boolean;
  store_states: Record<string, string>;
  despesas_coverage: string;
  rows: DreRow[];
  excluded: DreExcludedGroup[];
  shared_memo: { amount: string; count: number } | null;
  sales_quality: Record<string, { rows: number; zero_cost_rows: number }>;
  warnings: DreWarning[];
  sources: { vendas: DreSource; devolucoes: DreSource; despesas: DreSource };
  rules_origin: "default" | "db";
};

export type DreLine = {
  id: string;
  supplier_name: string;
  account_code: string | null;
  account_description: string | null;
  store_code: string;
  allocation: string;
  allocation_provisional: boolean;
  due_date: string;
  paid_at: string | null;
  status: string;
  amount: string;
  rule: string;
  rule_note: string | null;
  document_number: string | null;
  source_row: number;
};

export type DreLinesPage = {
  items: DreLine[];
  total: number;
  sum_amount?: string;
  page: number;
  page_size: number;
  has_data: boolean;
  data_state: string;
};

export type DreClassification = {
  disclaimer: string;
  rules_origin: "default" | "db";
  editable: boolean;
  rules: Array<{ account_code: string | null; supplier_pattern: string | null;
    bucket: string; allocation: string; note: string }>;
  accounts: Array<{
    account_code: string | null;
    account_description: string | null;
    count: number;
    amount: string;
    dominant_bucket: string;
    dominant_amount: string;
    dominant_count: number;
    mixed: boolean;
    buckets: Record<string, { count: number; amount: string }>;
    category_flags: string[];
  }>;
  data_state: string;
  last_import: DreSource["last_import"];
  bucket_labels: Record<string, string>;
};

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? "?" + text : "";
};

export const dreApi = {
  preview: (token: string, params: { month?: string; mode?: string; store?: string }) =>
    request<DrePreview>(token, "/api/v1/dre/preview" + qs(params)),

  lines: (token: string, params: { bucket: string; month?: string; mode?: string;
    store?: string; page?: number; page_size?: number }) =>
    request<DreLinesPage>(token, "/api/v1/dre/lines" + qs(params)),

  classification: (token: string) =>
    request<DreClassification>(token, "/api/v1/dre/classification"),
};
