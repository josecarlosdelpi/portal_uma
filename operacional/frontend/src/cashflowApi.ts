import { request } from "./api";
import type { DreSource, DreLinesPage } from "./dreApi";

export type { DreSource, DreLinesPage };

export type CfBalanceState =
  "complete" | "partial" | "unavailable" | "payments_only";

export type CfSummary = {
  entries: Record<string, string | null>;
  exits: Record<string, string | null>;
  balance: Record<string, string | null>;
  balance_state: Record<string, CfBalanceState>;
};

export type CfMonthly = {
  month: string;
  entries: string | null;
  exits: string | null;
  balance: string | null;
  balance_state: CfBalanceState;
  vendas_state: string;
  sales_rows: number;
  payment_rows: number;
};

export type CfPaymentGroup = {
  bucket: string;
  label: string;
  columns: Record<string, string | null>;
  amount: string | null;
  count: number;
  expandable: boolean;
};

export type CfPreview = {
  disclaimer: string;
  opening_balance: string;
  entries_source: { kind: string; label: string; note: string; replaceable: boolean };
  period: { first: string; last: string; months: string[] };
  columns: string[];
  consolidated: boolean;
  store_states: Record<string, string>;
  sales_overall: string;
  summary: CfSummary;
  sales_rows: number;
  payment_rows: number;
  monthly: CfMonthly[];
  payments: CfPaymentGroup[];
  returns: { state: string; columns: Record<string, string>; count: number };
  payments_coverage: string;
  shared_memo: { amount: string; count: number } | null;
  warnings: { code: string; message: string }[];
  sources: { vendas: DreSource; devolucoes: DreSource; despesas: DreSource };
  methodology: string[];
};

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? "?" + text : "";
};

export const cashflowApi = {
  preview: (token: string, params: { date_from: string; date_to: string; store?: string }) =>
    request<CfPreview>(token, "/api/v1/cashflow/preview" + qs(params)),

  lines: (token: string, params: { bucket: string; date_from: string;
    date_to: string; store?: string; page?: number; page_size?: number }) =>
    request<DreLinesPage>(token, "/api/v1/cashflow/lines" + qs(params)),
};
