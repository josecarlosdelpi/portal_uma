import { Fragment, useCallback, useEffect, useState } from "react";
import type { MyProfile } from "./api";
import { labelStore } from "./catalog";
import { cashflowApi, type CfPreview, type DreLinesPage } from "./cashflowApi";

type Props = { token: string; profile: MyProfile };
type PeriodKind = "month" | "quarter" | "semester" | "year" | "custom";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmt = (v?: string | null) => v == null || v === "" ? "—" : brl.format(Number(v));
const fmtNum = (v: number | null) => v == null ? "—" : brl.format(v);
const dmy = (iso?: string | null) => iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—";
const dtHora = (iso?: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(+d) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
};
const monthNow = () => {
  const d = new Date();
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0")].join("-");
};
const monthLabel = (m: string) => m.slice(5, 7) + "/" + m.slice(0, 4);
const lastDayOf = (ym: string) =>
  new Date(+ym.slice(0, 4), +ym.slice(5, 7), 0).toISOString().slice(0, 10);
const iso = (y: number, m: number, d: number) =>
  [y, String(m).padStart(2, "0"), String(d).padStart(2, "0")].join("-");

const COLUMN_LABEL: Record<string, string> = {
  COMPARTILHADO: "Compartilhado / não distribuído",
  UMA: "UMA total",
  TOTAL: "Total visível",
};
const colLabel = (c: string) => COLUMN_LABEL[c] ?? labelStore(c);

const STORE_ORDER = ["JOINVILLE", "TUBARAO", "ITAJAI"];
const orderColumns = (cols: string[]) => {
  const rank = (c: string) =>
    c === "COMPARTILHADO" ? 80
      : c === "UMA" || c === "TOTAL" ? 90
      : STORE_ORDER.indexOf(c) >= 0 ? STORE_ORDER.indexOf(c) : 50;
  return [...cols].sort((a, b) => rank(a) - rank(b) || cols.indexOf(a) - cols.indexOf(b));
};

const SOURCE_LABEL: Record<string, string> = {
  vendas: "Vendas.csv", devolucoes: "Devolucoes.csv", despesas: "Despesas.csv",
};
const AVAIL_LABEL: Record<string, string> = {
  current: "vigente", unavailable: "indisponível", missing: "nunca importado",
};
const RULE_LABEL: Record<string, string> = {
  barreira_categoria: "barreira: compra p/ revenda",
  excecao_fornecedor: "exceção por fornecedor",
  codigo_conta: "regra por código de conta",
  sem_regra: "sem regra — a classificar",
};
const STATE_LABEL: Record<string, string> = {
  current: "completo", partial: "parcial", missing: "sem dados",
  unavailable: "fonte indisponível",
};
const BALANCE_STATE_LABEL: Record<string, string> = {
  complete: "", partial: "parcial — somente registros disponíveis",
  unavailable: "não apurável",
};

const PERIOD_KIND_LABEL: Record<PeriodKind, string> = {
  month: "Mês", quarter: "Trimestre", semester: "Semestre",
  year: "Ano", custom: "Intervalo personalizado",
};

function LinesDrill({ token, bucket, from, to, store, columns }:
  { token: string; bucket: string; from: string; to: string;
    store?: string; columns: number }) {
  const [page, setPage] = useState<DreLinesPage | null>(null);
  const [items, setItems] = useState<DreLinesPage["items"]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [next, setNext] = useState(1);

  const load = useCallback(async (pageNumber: number) => {
    setLoading(true); setError("");
    try {
      const res = await cashflowApi.lines(token, {
        bucket, date_from: from, date_to: to, store, page: pageNumber, page_size: 25 });
      setPage(res);
      setItems(prev => pageNumber === 1 ? res.items : [...prev, ...res.items]);
      setNext(pageNumber + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao detalhar o grupo.");
    } finally { setLoading(false); }
  }, [token, bucket, from, to, store]);

  useEffect(() => { setItems([]); void load(1); }, [load]);

  if (loading && !page) return <tr className="dre-drill"><td colSpan={columns}>Carregando pagamentos…</td></tr>;
  if (error) return <tr className="dre-drill"><td colSpan={columns}><span className="notice notice-error">{error}</span></td></tr>;
  if (page && !page.has_data) return <tr className="dre-drill"><td colSpan={columns}>Fonte de despesas indisponível.</td></tr>;
  return <tr className="dre-drill"><td colSpan={columns}>
    <div className="dre-drill-box">
      <table className="dre-drill-table">
        <thead><tr>
          <th>Pagamento</th><th>Vencimento</th><th>Fornecedor</th><th>Conta</th>
          <th>Loja ERP</th><th>Alocação</th><th>Regra aplicada</th><th className="fin-num">Valor</th>
        </tr></thead>
        <tbody>
          {items.map(item => <tr key={item.id}>
            <td>{dmy(item.paid_at)}</td>
            <td>{dmy(item.due_date)}</td>
            <td><strong>{item.supplier_name}</strong>
              {item.document_number && <small className="dre-doc"> doc {item.document_number}</small>}</td>
            <td>{item.account_code ?? "—"}{item.account_description &&
              <small className="dre-doc"> {item.account_description}</small>}</td>
            <td>{labelStore(item.store_code)}</td>
            <td>{item.allocation === "COMPARTILHADO" ? "Compartilhado" : labelStore(item.allocation)}
              {item.allocation_provisional && <small className="dre-doc"> provisória</small>}</td>
            <td>{RULE_LABEL[item.rule] ?? item.rule}
              {item.rule_note && <small className="dre-doc"> {item.rule_note}</small>}</td>
            <td className="fin-num">{fmt(item.amount)}</td>
          </tr>)}
        </tbody>
      </table>
      {page && items.length < page.total &&
        <button className="btn-ghost" disabled={loading}
          onClick={() => void load(next)}>
          {loading ? "Carregando…" : `Carregar mais (${items.length} de ${page.total})`}
        </button>}
    </div>
  </td></tr>;
}

export function CashflowPanel({ token, profile }: Props) {
  const [store, setStore] = useState("TODAS");
  const [kind, setKind] = useState<PeriodKind>("month");
  const [month, setMonth] = useState(monthNow);
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [quarter, setQuarter] = useState("1");
  const [semester, setSemester] = useState("1");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [data, setData] = useState<CfPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [openBucket, setOpenBucket] = useState<string | null>(null);

  const range = (): { from: string; to: string } | null => {
    const y = year;
    if (kind === "month") return { from: month + "-01", to: lastDayOf(month) };
    if (kind === "quarter") {
      const q = Number(quarter);
      return { from: iso(y, (q - 1) * 3 + 1, 1), to: lastDayOf(iso(y, q * 3, 1).slice(0, 7)) };
    }
    if (kind === "semester") {
      const s = Number(semester);
      return s === 1
        ? { from: iso(y, 1, 1), to: iso(y, 6, 30) }
        : { from: iso(y, 7, 1), to: iso(y, 12, 31) };
    }
    if (kind === "year") return { from: iso(y, 1, 1), to: iso(y, 12, 31) };
    if (!customFrom || !customTo) return null;
    return { from: customFrom, to: customTo };
  };

  const load = useCallback(async () => {
    const r = range();
    if (!r) { setData(null); return; }
    setLoading(true); setError(""); setOpenBucket(null);
    try {
      setData(await cashflowApi.preview(token, {
        date_from: r.from, date_to: r.to,
        store: store === "TODAS" ? undefined : store }));
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : "Falha ao apurar o fluxo de caixa.");
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, store, kind, month, year, quarter, semester, customFrom, customTo]);
  useEffect(() => { void load(); }, [load]);

  const columns = orderColumns(data?.columns ?? []);
  const totalCol = columns.length ? columns[columns.length - 1] : "";
  const storeCols = columns.filter(c => c !== "UMA" && c !== "TOTAL");
  const storeParam = store === "TODAS" ? undefined : store;
  const r = range();

  const sum = (key: "entries" | "exits" | "balance"): number | null => {
    const v = data?.summary[key][totalCol];
    return v == null ? null : Number(v);
  };
  const entriesV = sum("entries");
  const exitsV = sum("exits");
  const balanceV = sum("balance");
  const saldoState = data?.summary.balance_state?.[totalCol] ?? "unavailable";

  const summaryRow = (key: "entries" | "exits" | "balance", label: string, note?: string) =>
    <tr className={key === "balance" ? "dre-row-subtotal" : ""}>
      <td>{label}{note && <small className="dre-note">{note}</small>}</td>
      {columns.map(col => {
        const v = data?.summary[key][col];
        const st = key === "balance" ? data?.summary.balance_state?.[col] : undefined;
        return <td key={col} className={"fin-num" + (v == null ? " dre-cell-empty" : "")}>
          <span className="dre-value">{fmt(v)}</span>
          {key === "entries" && v == null &&
            <small className="dre-note dre-note-warn">sem dados de vendas</small>}
          {key === "exits" && v == null &&
            <small className="dre-note dre-note-warn">fonte indisponível</small>}
          {st && st !== "complete" &&
            <small className="dre-note dre-note-warn">{BALANCE_STATE_LABEL[st]}</small>}
        </td>;
      })}
    </tr>;

  return <div className="dre">
    {error && <div className="notice notice-error" role="alert">{error}
      <button className="fin-notice-close" onClick={() => setError("")} aria-label="Fechar">×</button></div>}

    <div className="routine-filters">
      <label>Loja
        <select value={store} onChange={e => setStore(e.target.value)}>
          {profile.stores.length > 1 && <option value="TODAS">Consolidado</option>}
          {profile.stores.map(code => <option key={code} value={code}>{labelStore(code)}</option>)}
        </select></label>
      <label>Período
        <select value={kind} onChange={e => setKind(e.target.value as PeriodKind)}>
          {(Object.keys(PERIOD_KIND_LABEL) as PeriodKind[]).map(k =>
            <option key={k} value={k}>{PERIOD_KIND_LABEL[k]}</option>)}
        </select></label>
      {kind === "month" &&
        <label>Mês<input type="month" min="2020-01" max="2100-12"
          value={month} onChange={e => setMonth(e.target.value)} /></label>}
      {kind === "quarter" && <>
        <label>Trimestre<select value={quarter} onChange={e => setQuarter(e.target.value)}>
          <option value="1">1º trimestre</option><option value="2">2º trimestre</option>
          <option value="3">3º trimestre</option><option value="4">4º trimestre</option>
        </select></label>
        <label>Ano<input type="number" min="2020" max="2100"
          value={year} onChange={e => setYear(Number(e.target.value))} /></label></>}
      {kind === "semester" && <>
        <label>Semestre<select value={semester} onChange={e => setSemester(e.target.value)}>
          <option value="1">1º semestre</option><option value="2">2º semestre</option>
        </select></label>
        <label>Ano<input type="number" min="2020" max="2100"
          value={year} onChange={e => setYear(Number(e.target.value))} /></label></>}
      {kind === "year" &&
        <label>Ano<input type="number" min="2020" max="2100"
          value={year} onChange={e => setYear(Number(e.target.value))} /></label>}
      {kind === "custom" && <>
        <label>De<input type="date" value={customFrom}
          onChange={e => setCustomFrom(e.target.value)} /></label>
        <label>Até<input type="date" value={customTo}
          onChange={e => setCustomTo(e.target.value)} /></label></>}
    </div>

    <p className="dre-disclaimer" role="note">
      {data?.disclaimer ?? "FLUXO DE CAIXA ESTIMADO — vendas registradas menos pagamentos efetivos; não é saldo bancário real"}
    </p>

    {loading && <p role="status">Apurando fluxo de caixa…</p>}
    {!loading && kind === "custom" && !r &&
      <p className="empty">Informe o intervalo de datas para apurar.</p>}

    {data && !loading && r && <>
      <div className="dre-kpis" aria-label="Resumo do período">
        <div className="panel dre-kpi"><span>Vendas registradas</span>
          <strong className={entriesV == null ? "dre-kpi-na" : ""}>{fmtNum(entriesV)}</strong>
          <small>{entriesV == null ? "sem dados de vendas no período"
            : `${data.sales_rows} venda(s) — entradas estimadas`}</small></div>
        <div className="panel dre-kpi"><span>Pagamentos realizados</span>
          <strong className={exitsV == null ? "dre-kpi-na" : ""}>{fmtNum(exitsV)}</strong>
          <small>{exitsV == null ? "fonte de despesas indisponível"
            : `${data.payment_rows} pagamento(s) efetivos`}</small></div>
        <div className={"panel dre-kpi" + (balanceV != null && balanceV < 0 ? " dre-kpi-neg" : "")}>
          <span>Saldo Financeiro Estimado</span>
          <strong className={balanceV == null ? "dre-kpi-na" : ""}>{fmtNum(balanceV)}</strong>
          <small className={saldoState !== "complete" ? "cf-warn" : ""}>
            {saldoState === "unavailable"
              ? "não apurável — dados insuficientes"
              : saldoState === "partial"
                ? "parcial — somente registros disponíveis · abertura R$ 0,00"
                : "abertura R$ 0,00 — não é saldo bancário"}</small></div>
      </div>
      <p className="dre-kpi-note">
        {data.entries_source.label} — indicadores da coluna “{colLabel(totalCol)}”,
        período {dmy(data.period.first)} a {dmy(data.period.last)}.</p>

      <div className="table-wrap"><table className="dre-table">
        <thead><tr>
          <th>Movimento</th>
          {columns.map(col => <th key={col} className="fin-num">{colLabel(col)}</th>)}
        </tr></thead>
        <tbody>
          {summaryRow("entries", "Vendas registradas (entradas estimadas)",
            "Não são recebimentos efetivos; prazos não presumidos.")}
          {summaryRow("exits", "Pagamentos realizados (saídas)",
            "Somente lançamentos pagos, pela data efetiva.")}
          {summaryRow("balance", "Saldo Financeiro Estimado",
            "Abertura R$ 0,00; não é saldo bancário real.")}
        </tbody>
      </table></div>

      {data.consolidated && columns.includes("COMPARTILHADO") &&
        <p className="dre-note dre-shared-memo">
          Pagamentos compartilhados entram no resultado UMA sem rateio entre as lojas,
          seguindo a atribuição do ERP — por isso a soma das lojas pode diferir do
          consolidado e a visão por loja não reflete o consumo econômico real de cada unidade.</p>}
      {!data.consolidated && data.shared_memo &&
        <p className="dre-note dre-shared-memo">
          Pagamentos compartilhados fora deste recorte: {fmt(data.shared_memo.amount)}
          {" "}({data.shared_memo.count} lançamento(s)) — compõem somente o consolidado UMA.</p>}

      {data.returns.state === "current" && data.returns.count > 0 &&
        <p className="dre-note dre-shared-memo">
          Devoluções registradas no período (informativo): {data.returns.count} —
          {storeCols.filter(c => data.returns.columns[c] != null).map(c =>
            ` ${colLabel(c)} ${fmt(data.returns.columns[c])}`).join(";")}.
          Nenhum reembolso presumido nem abatimento das entradas.</p>}

      <article className="panel cf-section">
        <div className="panel-head"><div>
          <h2>Evolução mensal</h2>
          <p>Entradas estimadas, saídas efetivas e saldo de cada mês — cada período começa do zero.</p>
        </div></div>
        <div className="table-wrap"><table className="dre-table">
          <thead><tr>
            <th>Mês</th><th className="fin-num">Entradas estimadas</th>
            <th className="fin-num">Pagamentos</th><th className="fin-num">Saldo do mês</th>
            <th>Cobertura vendas</th>
          </tr></thead>
          <tbody>
            {data.monthly.map(m => <tr key={m.month}>
              <td>{monthLabel(m.month)}</td>
              <td className={"fin-num" + (m.entries == null ? " dre-cell-empty" : "")}>{fmt(m.entries)}
                {m.sales_rows > 0 && <small className="dre-pct">{m.sales_rows} venda(s)</small>}</td>
              <td className={"fin-num" + (m.exits == null ? " dre-cell-empty" : "")}>{fmt(m.exits)}
                {m.payment_rows > 0 && <small className="dre-pct">{m.payment_rows} pagamento(s)</small>}</td>
              <td className={"fin-num" + (m.balance == null ? " dre-cell-empty" : "")}>
                <strong>{fmt(m.balance)}</strong>
                {m.balance_state !== "complete" &&
                  <small className="dre-note dre-note-warn">
                    {m.balance_state === "unavailable" ? "não apurável" : "parcial"}</small>}</td>
              <td>{STATE_LABEL[m.vendas_state] ?? m.vendas_state}
                {m.vendas_state !== "current" &&
                  <small className="dre-note dre-note-warn">período não comparável a um mês completo</small>}</td>
            </tr>)}
          </tbody>
        </table></div>
      </article>

      <article className="panel cf-section">
        <div className="panel-head"><div>
          <h2>Composição dos pagamentos</h2>
          <p>Saídas efetivas por categoria financeira — inclui compras p/ revenda,
            financiamentos e imobilizado pagos no período.</p>
        </div></div>
        <div className="table-wrap"><table className="dre-table dre-excl-table">
          <thead><tr>
            <th>Categoria</th>
            {storeCols.map(col => <th key={col} className="fin-num">{colLabel(col)}</th>)}
            <th className="fin-num">Total</th><th className="fin-num">Pagamentos</th>
          </tr></thead>
          <tbody>
            {data.payments.map(group => <Fragment key={group.bucket}>
              <tr>
                <td><button className="dre-expand" onClick={() =>
                    setOpenBucket(openBucket === group.bucket ? null : group.bucket)}>
                  {openBucket === group.bucket ? "▾" : "▸"} {group.label}</button></td>
                {storeCols.map(col =>
                  <td key={col} className={"fin-num" + (group.columns[col] == null ? " dre-cell-empty" : "")}>
                    {fmt(group.columns[col])}</td>)}
                <td className="fin-num"><strong>{fmt(group.amount)}</strong></td>
                <td className="fin-num">{group.count}</td>
              </tr>
              {openBucket === group.bucket && <LinesDrill
                token={token} bucket={group.bucket} from={r.from} to={r.to}
                store={storeParam} columns={storeCols.length + 3} />}
            </Fragment>)}
          </tbody>
        </table></div>
      </article>

      <article className="panel dre-tech">
        <div className="panel-head"><div>
          <h2>Fontes, validações e metodologia</h2>
          <p>Situação dos arquivos vigentes, pendências e premissas da apuração.</p>
        </div></div>
        <div className="dre-sources">
          {(["vendas", "devolucoes", "despesas"] as const).map(srcKind => {
            const src = data.sources[srcKind];
            return <div key={srcKind}
              className={"dre-source" + (src.availability !== "current" ? " dre-source-warn" : "")}>
              <strong>{SOURCE_LABEL[srcKind]}</strong>
              <span>{AVAIL_LABEL[src.availability] ?? src.availability}</span>
              {src.last_import && <small>
                importado {dtHora(src.last_import.imported_at)}
                {src.last_import.period_start && ` · ${dmy(src.last_import.period_start)} a ${dmy(src.last_import.period_end)}`}
              </small>}
            </div>;
          })}
        </div>
        {data.warnings.length > 0 && <ul className="dre-warnings">
          {data.warnings.map((w, i) => <li key={i}>{w.message}</li>)}
        </ul>}
        <ul className="cf-methodology">
          <li><strong>{data.entries_source.label}.</strong> {data.entries_source.note}</li>
          {data.methodology.map((m, i) => <li key={i}>{m}</li>)}
        </ul>
      </article>
    </>}
  </div>;
}
