import { Fragment, useCallback, useEffect, useState } from "react";
import type { MyProfile } from "./api";
import { labelStore } from "./catalog";
import { dreApi, type DreClassification, type DreLinesPage,
  type DrePreview, type DreRow } from "./dreApi";

type Props = { token: string; profile: MyProfile };

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmt = (v?: string | null) => v == null || v === "" ? null : brl.format(Number(v));
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

const COLUMN_LABEL: Record<string, string> = {
  COMPARTILHADO: "Compartilhado / não distribuído",
  UMA: "UMA total",
  TOTAL: "Total visível",
};
const colLabel = (c: string) => COLUMN_LABEL[c] ?? labelStore(c);

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
const BUCKET_LABEL: Record<string, string> = {
  despesa_comercial: "Despesas comerciais",
  despesa_operacional: "Despesas operacionais e pessoal",
  das_identificado: "DAS identificado",
  compra_revenda: "Compras para revenda",
  financiamento: "Financiamentos / amortizações",
  imobilizado: "Aquisição de imobilizado",
  a_classificar: "A classificar",
};

const STORE_ORDER = ["JOINVILLE", "TUBARAO", "ITAJAI"];
const orderColumns = (cols: string[]) => {
  const rank = (c: string) =>
    c === "COMPARTILHADO" ? 80
      : c === "UMA" || c === "TOTAL" ? 90
      : STORE_ORDER.indexOf(c) >= 0 ? STORE_ORDER.indexOf(c) : 50;
  return [...cols].sort((a, b) => rank(a) - rank(b) || cols.indexOf(a) - cols.indexOf(b));
};

const DESPESA_KEYS = ["despesa_comercial", "despesa_operacional", "das"];
const EXCLUDED_CALC = ["compra_revenda", "financiamento", "imobilizado"];
const EXCLUDED_INFO: Record<string, string> = {
  compra_revenda: "Mercadoria para revenda — não é despesa operacional nem CMV; controle próprio em Compras p/ revenda.",
  financiamento: "Parcelas sem segregação de juros e principal — fora do resultado operacional.",
  imobilizado: "Investimento em bens — fora do resultado; sem depreciação nesta etapa.",
  a_classificar: "Sem regra de classificação vigente — fora do saldo até validação gerencial.",
};
const fmtNum = (v: number | null) => v == null ? "—" : brl.format(v);

function Cell({ row, column }: { row: DreRow; column: string }) {
  const value = row.values[column];
  const pct = row.pct[column];
  if (value == null) {
    return <td className="fin-num dre-cell-empty" title="Sem dados no arquivo vigente — nunca zero automático">—</td>;
  }
  return <td className="fin-num">
    <span className="dre-value">{fmt(value)}</span>
    {pct != null && <small className="dre-pct">{pct}%</small>}
  </td>;
}

function LinesDrill({ token, bucket, month, mode, store, columns }:
  { token: string; bucket: string; month: string; mode: string;
    store?: string; columns: number }) {
  const [page, setPage] = useState<DreLinesPage | null>(null);
  const [items, setItems] = useState<DreLinesPage["items"]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [next, setNext] = useState(1);

  const load = useCallback(async (pageNumber: number) => {
    setLoading(true); setError("");
    try {
      const res = await dreApi.lines(token, {
        bucket, month, mode, store, page: pageNumber, page_size: 25 });
      setPage(res);
      setItems(prev => pageNumber === 1 ? res.items : [...prev, ...res.items]);
      setNext(pageNumber + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao detalhar o grupo.");
    } finally { setLoading(false); }
  }, [token, bucket, month, mode, store]);

  useEffect(() => { setItems([]); void load(1); }, [load]);

  if (loading && !page) return <tr className="dre-drill"><td colSpan={columns}>Carregando lançamentos…</td></tr>;
  if (error) return <tr className="dre-drill"><td colSpan={columns}><span className="notice notice-error">{error}</span></td></tr>;
  if (page && !page.has_data) return <tr className="dre-drill"><td colSpan={columns}>Fonte de despesas indisponível.</td></tr>;
  return <tr className="dre-drill"><td colSpan={columns}>
    <div className="dre-drill-box">
      <table className="dre-drill-table">
        <thead><tr>
          <th>Vencimento</th><th>Fornecedor</th><th>Conta</th><th>Loja ERP</th>
          <th>Alocação</th><th>Situação</th><th>Regra aplicada</th><th className="fin-num">Valor</th>
        </tr></thead>
        <tbody>
          {items.map(item => <tr key={item.id}>
            <td>{dmy(item.due_date)}</td>
            <td><strong>{item.supplier_name}</strong>
              {item.document_number && <small className="dre-doc"> doc {item.document_number}</small>}</td>
            <td>{item.account_code ?? "—"}{item.account_description &&
              <small className="dre-doc"> {item.account_description}</small>}</td>
            <td>{labelStore(item.store_code)}</td>
            <td>{item.allocation === "COMPARTILHADO" ? "Compartilhado" : labelStore(item.allocation)}
              {item.allocation_provisional && <small className="dre-doc"> provisória</small>}</td>
            <td>{item.status === "pago" ? "Pago" : "Aberto"}</td>
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

export function DrePanel({ token, profile }: Props) {
  const [view, setView] = useState<"preview" | "regras">("preview");
  const [month, setMonth] = useState(monthNow);
  const [mode, setMode] = useState<"month" | "ytd">("month");
  const [store, setStore] = useState("TODAS");
  const [data, setData] = useState<DrePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [openBucket, setOpenBucket] = useState<string | null>(null);
  const [rules, setRules] = useState<DreClassification | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(""); setOpenRow(null); setOpenBucket(null);
    try {
      setData(await dreApi.preview(token, {
        month, mode, store: store === "TODAS" ? undefined : store }));
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : "Falha ao apurar a DRE.");
    } finally { setLoading(false); }
  }, [token, month, mode, store]);
  useEffect(() => { if (view === "preview") void load(); }, [view, load]);

  useEffect(() => {
    if (view !== "regras") return;
    void dreApi.classification(token).then(setRules)
      .catch(cause => setError(cause instanceof Error ? cause.message : "Falha ao consultar a classificação."));
  }, [view, token]);

  const columns = orderColumns(data?.columns ?? []);
  const storeCols = columns.filter(c => c !== "UMA" && c !== "TOTAL");
  const totalCol = columns.length ? columns[columns.length - 1] : "";
  const storeParam = store === "TODAS" ? undefined : store;

  const rowNum = (key: string): number | null => {
    const v = data?.rows.find(r => r.key === key)?.values[totalCol];
    return v == null ? null : Number(v);
  };
  const receitaV = rowNum("receita");
  const margemV = rowNum("margem");
  const saldoV = rowNum("saldo");
  const despParts = DESPESA_KEYS.map(rowNum);
  const despV = despParts.every(v => v == null) ? null
    : despParts.reduce<number>((a, v) => a + (v ?? 0), 0);
  const sharedInResult = data ? DESPESA_KEYS.reduce<number>((a, key) => {
    const v = data.rows.find(r => r.key === key)?.values["COMPARTILHADO"];
    return a + (v == null ? 0 : Number(v));
  }, 0) : 0;

  const ExcludedTable = ({ buckets }: { buckets: string[] }) => {
    const groups = (data?.excluded ?? []).filter(g => buckets.includes(g.bucket));
    if (!groups.length) return <p className="empty">Nenhum lançamento neste grupo no período.</p>;
    return <div className="table-wrap"><table className="dre-table dre-excl-table">
      <thead><tr>
        <th>Grupo / justificativa</th>
        {storeCols.map(col => <th key={col} className="fin-num">{colLabel(col)}</th>)}
        <th className="fin-num">Total</th><th className="fin-num">Lançamentos</th>
      </tr></thead>
      <tbody>
        {groups.map(group => <Fragment key={group.bucket}>
          <tr>
            <td><button className="dre-expand" onClick={() =>
                setOpenBucket(openBucket === group.bucket ? null : group.bucket)}>
              {openBucket === group.bucket ? "▾" : "▸"} {group.label}</button>
              {EXCLUDED_INFO[group.bucket] &&
                <small className="dre-note">{EXCLUDED_INFO[group.bucket]}</small>}</td>
            {storeCols.map(col =>
              <td key={col} className="fin-num">
                {group.columns[col] != null ? fmt(group.columns[col]) : "—"}</td>)}
            <td className="fin-num"><strong>{group.amount != null ? fmt(group.amount) : "—"}</strong></td>
            <td className="fin-num">{group.count}</td>
          </tr>
          {openBucket === group.bucket && <LinesDrill
            token={token} bucket={group.bucket} month={month} mode={mode}
            store={storeParam} columns={storeCols.length + 3} />}
        </Fragment>)}
      </tbody>
    </table></div>;
  };

  return <div className="dre">
    <div className="tabs" role="tablist" aria-label="DRE gerencial">
      <button role="tab" aria-selected={view === "preview"}
        className={"tab" + (view === "preview" ? " active" : "")}
        onClick={() => setView("preview")}>Prévia mensal</button>
      <button role="tab" aria-selected={view === "regras"}
        className={"tab" + (view === "regras" ? " active" : "")}
        onClick={() => setView("regras")}>Classificação DRE</button>
    </div>

    {error && <div className="notice notice-error" role="alert">{error}
      <button className="fin-notice-close" onClick={() => setError("")} aria-label="Fechar">×</button></div>}

    {view === "preview" && <>
      <div className="routine-filters">
        <label>Loja
          <select value={store} onChange={e => setStore(e.target.value)}>
            {profile.stores.length > 1 && <option value="TODAS">Consolidado</option>}
            {profile.stores.map(code => <option key={code} value={code}>{labelStore(code)}</option>)}
          </select></label>
        <label>Mês<input type="month" min="2020-01" max="2100-12"
          value={month} onChange={e => setMonth(e.target.value)} /></label>
        <label>Visão<select value={mode} onChange={e => setMode(e.target.value as "month" | "ytd")}>
          <option value="month">Mês</option>
          <option value="ytd">Acumulado até o mês</option>
        </select></label>
      </div>

      <p className="dre-disclaimer" role="note">
        {data?.disclaimer ?? "DRE GERENCIAL PRELIMINAR — valores em validação; não representa lucro definitivo"}
      </p>

      {loading && <p role="status">Apurando prévia…</p>}

      {data && !loading && <>
        <div className="dre-kpis" aria-label="Indicadores do período">
          <div className="panel dre-kpi"><span>Receita registrada</span>
            <strong className={receitaV == null ? "dre-kpi-na" : ""}>{fmtNum(receitaV)}</strong>
            <small>{receitaV == null ? "indisponível neste período" : "arquivo vigente de vendas"}</small></div>
          <div className="panel dre-kpi"><span>Margem bruta preliminar</span>
            <strong className={margemV == null ? "dre-kpi-na" : ""}>{fmtNum(margemV)}</strong>
            <small>receita − CMV · antes de devoluções</small></div>
          <div className="panel dre-kpi"><span>Despesas consideradas</span>
            <strong className={despV == null ? "dre-kpi-na" : ""}>{fmtNum(despV)}</strong>
            <small>comerciais + operacionais + DAS</small></div>
          <div className={"panel dre-kpi" + (saldoV != null && saldoV < 0 ? " dre-kpi-neg" : "")}>
            <span>Saldo gerencial parcial</span>
            <strong className={saldoV == null ? "dre-kpi-na" : ""}>{fmtNum(saldoV)}</strong>
            <small>não é lucro líquido</small></div>
        </div>
        <p className="dre-kpi-note">Indicadores da coluna “{colLabel(totalCol)}”
          {data.period.mode === "ytd" ? " — acumulado no ano" : ""}.</p>

        <div className="table-wrap"><table className="dre-table">
          <thead><tr>
            <th>Linha</th>
            {columns.map(col => <th key={col} className="fin-num">{colLabel(col)}</th>)}
          </tr></thead>
          <tbody>
            {data.rows.map(row => <Fragment key={row.key}>
              <tr className={"dre-row-" + row.kind + (row.state === "unavailable" ? " dre-row-warn" : "")}>
                <td>
                  {row.expandable
                    ? <button className="dre-expand" onClick={() =>
                        setOpenRow(openRow === row.key ? null : row.key)}>
                        {openRow === row.key ? "▾" : "▸"} {row.label}</button>
                    : row.label}
                  {row.note && <small className="dre-note">{row.note}</small>}
                  {row.state === "unavailable" &&
                    <small className="dre-note dre-note-warn">Fonte indisponível — aguardando correção.</small>}
                  {row.state === "missing" &&
                    <small className="dre-note dre-note-warn">Arquivo nunca importado.</small>}
                </td>
                {columns.map(col => <Cell key={col} row={row} column={col} />)}
              </tr>
              {openRow === row.key && row.bucket && <LinesDrill
                token={token} bucket={row.bucket} month={month} mode={mode}
                store={storeParam} columns={columns.length + 1} />}
            </Fragment>)}
          </tbody>
        </table></div>

        {data.consolidated && columns.includes("COMPARTILHADO") &&
          <p className="dre-note dre-shared-memo">
            Despesas compartilhadas{sharedInResult ? ` (${brl.format(sharedInResult)})` : ""} entram
            no resultado UMA e não são rateadas entre as lojas — por isso a soma das colunas
            das lojas pode diferir do total consolidado.</p>}
        {!data.consolidated && data.shared_memo &&
          <p className="dre-note dre-shared-memo">
            Despesas compartilhadas fora deste recorte: {fmt(data.shared_memo.amount)}
            {" "}({data.shared_memo.count} lançamento(s)) — compõem somente o resultado UMA
            consolidado, sem rateio entre as lojas.</p>}

        <article className="panel dre-excluded">
          <div className="panel-head"><div>
            <h2>Lançamentos não considerados no resultado</h2>
            <p>Valores fora do saldo gerencial parcial — sempre visíveis, nunca somados.</p>
          </div></div>
          <div className="dre-excl-sub">
            <h3>Excluídos do cálculo</h3>
            <p>Não são despesas operacionais do período — a natureza do lançamento o exclui do resultado.</p>
            <ExcludedTable buckets={EXCLUDED_CALC} />
          </div>
          <div className="dre-excl-sub">
            <h3>Pendentes de classificação</h3>
            <p>Lançamentos ainda sem destino definido — ficam fora do saldo até a validação gerencial.</p>
            <ExcludedTable buckets={(data.excluded ?? [])
              .filter(g => !EXCLUDED_CALC.includes(g.bucket)).map(g => g.bucket)} />
          </div>
        </article>

        <article className="panel dre-tech">
          <div className="panel-head"><div>
            <h2>Fontes, validações e metodologia</h2>
            <p>Situação dos arquivos vigentes, pendências de validação e premissas da apuração.</p>
          </div></div>
          <div className="dre-sources">
            {(["vendas", "devolucoes", "despesas"] as const).map(kind => {
              const src = data.sources[kind];
              return <div key={kind}
                className={"dre-source" + (src.availability !== "current" ? " dre-source-warn" : "")}>
                <strong>{SOURCE_LABEL[kind]}</strong>
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
          <p className="dre-basis">Base: {data.basis} · Arredondamento: {data.rounding_policy}</p>
        </article>
      </>}
    </>}

    {view === "regras" && <>
      {!rules && <p role="status">Carregando classificação…</p>}
      {rules && <>
        <p className="dre-basis">
          Mapeamento {rules.rules_origin === "db" ? "da tabela de regras" : "embutido (semente da diretriz)"}
          {" "}— somente leitura nesta etapa; a edição com auditoria será liberada ao SuperAdmin na próxima fase.</p>
        <article className="panel">
          <div className="panel-head"><div>
            <h2>Classificação por conta no arquivo vigente</h2>
            <p>Bucket dominante por código de conta do snapshot de Despesas.csv.</p>
          </div></div>
          {!rules.accounts.length && <p className="empty">Sem obrigações vigentes para resumir.</p>}
          {rules.accounts.length > 0 && <div className="table-wrap"><table className="dre-table">
            <thead><tr>
              <th>Conta</th><th>Descrição</th><th>Classificação dominante</th>
              <th className="fin-num">Lançamentos</th><th className="fin-num">Valor</th><th>Observação</th>
            </tr></thead>
            <tbody>
              {rules.accounts.map(acc => <tr key={acc.account_code ?? "sem-conta"}>
                <td>{acc.account_code ?? "—"}</td>
                <td>{acc.account_description ?? ""}</td>
                <td>{BUCKET_LABEL[acc.dominant_bucket] ?? acc.dominant_bucket}
                  {acc.mixed && <small className="dre-note dre-note-warn"> conta mista</small>}</td>
                <td className="fin-num">{acc.count}</td>
                <td className="fin-num">{fmt(acc.amount)}</td>
                <td>{acc.mixed
                  ? Object.entries(acc.buckets).map(([b, v]) =>
                      <small key={b} className="dre-doc">
                        {BUCKET_LABEL[b] ?? b}: {fmt(v.amount)} ({v.count})</small>)
                  : acc.category_flags.includes("compra_revenda") ? "categoria compra p/ revenda" : ""}</td>
              </tr>)}
            </tbody>
          </table></div>}
        </article>
        <article className="panel">
          <div className="panel-head"><div>
            <h2>Regras vigentes</h2>
            <p>Precedência: barreira de compra p/ revenda → exceção por fornecedor → código de conta → a classificar.</p>
          </div></div>
          <div className="table-wrap"><table className="dre-table">
            <thead><tr><th>Conta</th><th>Fornecedor contém</th><th>Destino</th><th>Alocação</th><th>Nota</th></tr></thead>
            <tbody>
              {rules.rules.map((rule, i) => <tr key={i}>
                <td>{rule.account_code ?? "qualquer"}</td>
                <td>{rule.supplier_pattern ?? "—"}</td>
                <td>{BUCKET_LABEL[rule.bucket] ?? rule.bucket}</td>
                <td>{rule.allocation === "shared" ? "compartilhado" :
                  rule.allocation === "pending_review" ? "revisão pendente" : "loja do ERP"}</td>
                <td>{rule.note}</td>
              </tr>)}
            </tbody>
          </table></div>
        </article>
      </>}
    </>}
  </div>;
}
