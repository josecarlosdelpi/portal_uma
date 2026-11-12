import {useEffect, useMemo, useRef, useState} from "react";
import {
  api, type MyProfile, type SalesDailyRow, type SalesSummary,
  type SalesSyncStatus, type SalesTopItem, type UserPreferences,
} from "./api";
import {labelStore} from "./catalog";

type Props = {token: string; profile: MyProfile};

const money = (value: string | number | null | undefined) =>
  value === null || value === undefined ? "Sem dados" :
  new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(Number(value));
const qty = (value: string | null | undefined) =>
  value === null || value === undefined ? "0" :
  new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 2}).format(Number(value));
const dateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR") : "Nunca sincronizado";
const dayMonth = (iso: string) => iso.slice(8, 10) + "/" + iso.slice(5, 7);

const DEFAULT_COLORS: Record<string, string> = {
  JOINVILLE: "#0e757a", TUBARAO: "#b7a92d", ITAJAI: "#35566b",
};
const STORE_ORDER = ["JOINVILLE", "TUBARAO", "ITAJAI"];
const MONTH_NAMES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

const firstOfMonth = () => {
  const now = new Date();
  return now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-01";
};
const todayIso = () => {
  const now = new Date();
  return now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") +
    "-" + String(now.getDate()).padStart(2, "0");
};
const daysAgo = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
    "-" + String(d.getDate()).padStart(2, "0");
};
const monthRange = (year: number, month: number): [string, string] => {
  const mm = String(month).padStart(2, "0");
  const last = String(new Date(year, month, 0).getDate()).padStart(2, "0");
  return [`${year}-${mm}-01`, `${year}-${mm}-${last}`];
};

function DailyChart({days, colors}: {days: SalesDailyRow[]; colors: Record<string, string>}) {
  const byDate = useMemo(() => {
    const map = new Map<string, Record<string, number>>();
    for (const row of days) {
      const entry = map.get(row.date) ?? {};
      entry[row.store_code] = (entry[row.store_code] ?? 0) + Number(row.revenue);
      map.set(row.date, entry);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [days]);
  const stores = useMemo(() => {
    const set = new Set<string>();
    for (const row of days) set.add(row.store_code);
    return [...set].sort((a, b) =>
      (STORE_ORDER.indexOf(a) === -1 ? 99 : STORE_ORDER.indexOf(a)) -
      (STORE_ORDER.indexOf(b) === -1 ? 99 : STORE_ORDER.indexOf(b)));
  }, [days]);
  if (byDate.length === 0) return <p className="empty">Nenhuma venda registrada no período.</p>;
  const max = Math.max(...byDate.map(([, v]) => Object.values(v).reduce((a, b) => a + b, 0)), 1);
  // Largura fixa do viewBox: barras ocupam o espaco proporcionalmente e os
  // rotulos mantem o mesmo tamanho visual para qualquer quantidade de dias.
  const W = 1000;
  const H = 190;
  const barW = W / byDate.length;
  const gap = Math.min(8, barW * 0.14);
  const labelEvery = Math.max(1, Math.ceil(byDate.length / 18));
  return <div>
    <div className="sales-legend">
      {stores.map(code => <span key={code} className="sales-legend-item">
        <i style={{background: colors[code] ?? "#607d8b"}}/>{labelStore(code)}</span>)}
    </div>
    <div className="sales-chart-wrap">
      <svg className="sales-chart" viewBox={`0 0 ${W} ${H + 30}`}
        preserveAspectRatio="xMidYMid meet"
        role="img" aria-label="Faturamento diário por loja">
        {byDate.map(([iso, perStore], index) => {
          const total = Object.values(perStore).reduce((a, b) => a + b, 0);
          const barH = (total / max) * (H - 30);
          let offset = 0;
          return <g key={iso}>
            {stores.map(code => {
              const value = perStore[code] ?? 0;
              if (!value) return null;
              const h = (value / total) * barH;
              const y = H - 10 - offset - h;
              offset += h;
              return <rect key={code} x={index * barW + gap / 2} y={y}
                width={Math.max(1, barW - gap)} height={h}
                rx={Math.min(3, (barW - gap) / 3)} fill={colors[code] ?? "#607d8b"}>
                <title>{labelStore(code)} · {dayMonth(iso)} · {money(value)}</title>
              </rect>;
            })}
            {(index % labelEvery === 0 || index === byDate.length - 1) &&
              <text x={index * barW + barW / 2} y={H + 18} textAnchor="middle"
                className="sales-chart-label">{dayMonth(iso)}</text>}
          </g>;
        })}
        <line x1={0} y1={H - 10} x2={W} y2={H - 10} stroke="#dbe5e9"/>
      </svg>
    </div>
  </div>;
}

function TopList({items, metric, secondary}: {
  items: SalesTopItem[]; metric: "revenue" | "quantity";
  secondary?: (item: SalesTopItem) => string;
}) {
  const max = Math.max(...items.map(i => Number(metric === "revenue" ? i.revenue : i.quantity)), 1);
  return <div className="sales-top">
    {items.length === 0 && <p className="empty">Sem dados no período.</p>}
    {items.map((item, index) => {
      const value = Number(metric === "revenue" ? item.revenue : item.quantity);
      return <div className="sales-top-row" key={item.key + index}>
        <span className="sales-top-rank">{index + 1}</span>
        <span className="sales-top-name" title={item.key}>{item.key}</span>
        <span className="sales-top-bar"><i style={{width: (value / max * 100) + "%"}}/></span>
        <span className="sales-top-value">
          {metric === "revenue" ? money(item.revenue) : qty(item.quantity)}
          {secondary && <small className="sales-top-secondary">{secondary(item)}</small>}
        </span>
      </div>;
    })}
  </div>;
}

export function SalesPage({token, profile}: Props) {
  const stores = profile.stores;
  const now = new Date();
  const [mode, setMode] = useState<"month" | "range">("month");
  const [selYear, setSelYear] = useState(now.getFullYear());
  const [selMonth, setSelMonth] = useState(now.getMonth() + 1);
  const [from, setFrom] = useState(firstOfMonth);
  const [to, setTo] = useState(todayIso);
  const [store, setStore] = useState<string>("");
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [days, setDays] = useState<SalesDailyRow[]>([]);
  const [products, setProducts] = useState<SalesTopItem[]>([]);
  const [sellers, setSellers] = useState<SalesTopItem[]>([]);
  const [customers, setCustomers] = useState<SalesTopItem[]>([]);
  const [status, setStatus] = useState<SalesSyncStatus | null>(null);
  const [metric, setMetric] = useState<"revenue" | "quantity">("revenue");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [colors, setColors] = useState<Record<string, string>>({...DEFAULT_COLORS});
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canSync = profile.profile !== "seller";

  const yearOptions = useMemo(() => {
    const current = new Date().getFullYear();
    const years: number[] = [];
    for (let y = current - 3; y <= current + 1; y += 1) years.push(y);
    if (!years.includes(selYear)) years.push(selYear);
    return years.sort((a, b) => a - b);
  }, [selYear]);

  const load = async (f = from, t = to, s = store, m = metric) => {
    setLoading(true); setError("");
    try {
      const [sum, daily, prod, sell, cust, stat] = await Promise.all([
        api.salesSummary(token, f, t, s || undefined),
        api.salesDaily(token, f, t, s || undefined),
        api.salesTop(token, "products", f, t, s || undefined, 10, m),
        api.salesTop(token, "sellers", f, t, s || undefined, 10),
        api.salesTop(token, "customers", f, t, s || undefined, 10),
        api.salesStatus(token),
      ]);
      setSummary(sum); setDays(daily.days); setProducts(prod.items);
      setSellers(sell.items); setCustomers(cust.items); setStatus(stat);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível consultar as vendas.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [token, store]);
  useEffect(() => {
    void api.preferences(token).then(p => {
      setPrefs(p);
      setColors({...DEFAULT_COLORS, ...(p.store_colors ?? {})});
    }).catch(() => undefined);
  }, [token]);

  const applyMonth = (year: number, month: number) => {
    const [f, t] = monthRange(year, month);
    setSelYear(year); setSelMonth(month); setFrom(f); setTo(t);
    void load(f, t);
  };
  const shiftMonth = (delta: number) => {
    const base = new Date(selYear, selMonth - 1 + delta, 1);
    applyMonth(base.getFullYear(), base.getMonth() + 1);
  };
  const switchMode = (next: "month" | "range") => {
    setMode(next);
    if (next === "month") {
      const parsed = /^(\d{4})-(\d{2})-\d{2}$/.exec(from);
      applyMonth(
        parsed ? Number(parsed[1]) : now.getFullYear(),
        parsed ? Number(parsed[2]) : now.getMonth() + 1,
      );
    }
  };

  const toggleMetric = (next: "revenue" | "quantity") => {
    setMetric(next);
    void api.salesTop(token, "products", from, to, store || undefined, 10, next)
      .then(r => setProducts(r.items))
      .catch(() => undefined);
  };

  const persistColors = (next: Record<string, string>) => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      void api.savePreferences(token, {
        sidebar_pinned: prefs?.sidebar_pinned ?? true,
        favorites: prefs?.favorites ?? [],
        store_colors: next,
      }).then(saved => setPrefs(saved)).catch(() => undefined);
    }, 500);
  };
  const changeColor = (code: string, value: string) => {
    const next = {...colors, [code]: value};
    setColors(next);
    persistColors(next);
  };
  const resetColors = () => {
    setColors({...DEFAULT_COLORS});
    persistColors({});
  };

  const doSync = async () => {
    setSyncing(true); setError(""); setMessage("");
    try {
      const result = await api.triggerSalesSync(token);
      const failed = result.results.filter(r => r.status === "FAILED");
      const applied = result.results.filter(r => r.status === "OK");
      setMessage(failed.length ? `Sincronização com falhas em ${failed.length} arquivo(s).`
        : applied.length ? "Sincronização concluída." : "Nenhuma alteração encontrada no Drive.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao sincronizar com o Drive.");
    } finally {
      setSyncing(false);
    }
  };

  const vendas = status?.kinds.find(k => k.kind === "VENDAS");
  const driveFiles = status?.drive.files ?? [];
  const lastError = driveFiles.find(f => f.last_error)?.last_error;
  const orderedStores = summary
    ? [...summary.stores].sort((a, b) =>
        (STORE_ORDER.indexOf(a.code) === -1 ? 99 : STORE_ORDER.indexOf(a.code)) -
        (STORE_ORDER.indexOf(b.code) === -1 ? 99 : STORE_ORDER.indexOf(b.code)))
    : [];

  if (!profile.features.sales) {
    return <section className="panel"><h2>Vendas não disponíveis</h2>
      <p>Seu perfil não possui permissão para consultar este módulo.</p></section>;
  }

  return <div className="sales-page">
    <div className="page-header"><div>
      <div className="eyebrow">COMERCIAL · PILOTO ERP</div>
      <h1>Vendas e devoluções</h1>
      <p>{profile.profile === "seller"
        ? "Resultados da sua loja vindos do ERP, em fase de testes."
        : "Indicadores comerciais das três lojas, sincronizados do ERP."}</p>
    </div></div>

    {error && <div className="notice notice-error" role="alert">{error}</div>}

    <div className="target-filters sales-filters">
      <div className="sales-mode-tabs" role="group" aria-label="Modo de filtro">
        <button type="button" className={mode === "month" ? "tab active" : "tab"}
          onClick={() => switchMode("month")}>Mês</button>
        <button type="button" className={mode === "range" ? "tab active" : "tab"}
          onClick={() => switchMode("range")}>Período personalizado</button>
      </div>

      {mode === "month" ? <>
        <div className="sales-month-nav">
          <button type="button" className="btn-ghost sales-arrow" aria-label="Mês anterior"
            onClick={() => shiftMonth(-1)}>‹</button>
          <div className="form-row"><label htmlFor="sales-month">Mês</label>
            <select id="sales-month" value={selMonth}
              onChange={e => applyMonth(selYear, Number(e.target.value))}>
              {MONTH_NAMES.map((name, i) =>
                <option key={name} value={i + 1}>{name}</option>)}
            </select></div>
          <div className="form-row"><label htmlFor="sales-year">Ano</label>
            <select id="sales-year" value={selYear}
              onChange={e => applyMonth(Number(e.target.value), selMonth)}>
              {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
            </select></div>
          <button type="button" className="btn-ghost sales-arrow" aria-label="Próximo mês"
            onClick={() => shiftMonth(1)}>›</button>
        </div>
      </> : <>
        <div className="form-row"><label htmlFor="sales-from">De</label>
          <input id="sales-from" type="date" value={from}
            onChange={e => setFrom(e.target.value)}/></div>
        <div className="form-row"><label htmlFor="sales-to">Até</label>
          <input id="sales-to" type="date" value={to}
            onChange={e => setTo(e.target.value)}/></div>
        <button className="btn-secondary" type="button" disabled={loading}
          onClick={() => void load()}>{loading ? "Atualizando…" : "Aplicar"}</button>
        <button className="btn-ghost" type="button"
          onClick={() => { setMode("month"); applyMonth(now.getFullYear(), now.getMonth() + 1); }}>
          Este mês</button>
        <button className="btn-ghost" type="button"
          onClick={() => { setFrom(daysAgo(30)); setTo(todayIso()); void load(daysAgo(30), todayIso()); }}>
          Últimos 30 dias</button>
      </>}

      {stores.length > 1 && <div className="form-row"><label htmlFor="sales-store">Loja</label>
        <select id="sales-store" value={store} onChange={e => setStore(e.target.value)}>
          <option value="">Todas as lojas</option>
          {stores.map(code => <option key={code} value={code}>{labelStore(code)}</option>)}
        </select></div>}
    </div>

    {summary && <>
      <div className="overview-kpis">
        <div className="panel overview-kpi"><span>Faturamento do período</span>
          <strong>{money(summary.totals.revenue)}</strong>
          <small>{qty(summary.totals.quantity)} itens em {summary.totals.rows} linhas</small></div>
        {orderedStores.map(item => <div className="panel overview-kpi" key={item.code}>
          <span>{labelStore(item.code)}</span>
          <strong>{item.revenue_visibility === "restricted" ? "Restrito" : money(item.revenue)}</strong>
          <small>{qty(item.quantity)} itens · {money(item.returns_revenue)} em devoluções</small></div>)}
        <div className="panel overview-kpi"><span>Devoluções registradas</span>
          <strong>{money(summary.totals.returns_revenue)}</strong>
          <small>{summary.totals.returns_rows} linha(s) · exibidas separadamente</small></div>
      </div>

      <section className="panel">
        <div className="panel-head sales-panel-head"><div><h2>Evolução diária do faturamento</h2>
          <p>Soma das linhas de venda por dia e loja. Barras empilhadas por unidade.</p></div>
          <details className="sales-colors">
            <summary>Personalizar cores</summary>
            <div className="sales-colors-body">
              {Object.keys(DEFAULT_COLORS).filter(code => stores.includes(code)).map(code =>
                <label key={code} className="sales-color-line">
                  <input type="color" value={colors[code] ?? DEFAULT_COLORS[code]}
                    onChange={e => changeColor(code, e.target.value)}
                    aria-label={"Cor da loja " + labelStore(code)}/>
                  <span>{labelStore(code)}</span>
                </label>)}
              <button type="button" className="btn-ghost sales-color-reset"
                onClick={resetColors}>Restaurar padrão</button>
            </div>
          </details>
        </div>
        <DailyChart days={days} colors={colors}/>
      </section>

      <div className="columns-3">
        <section className="panel">
          <div className="panel-head sales-panel-head"><div><h2>Produtos</h2>
            <p>Códigos do ERP sem descrição cadastrada.</p></div>
            <div className="tab-bar sales-tab-bar">
              <button className={metric === "revenue" ? "tab tab-sm active" : "tab tab-sm"}
                onClick={() => toggleMetric("revenue")}>Faturamento</button>
              <button className={metric === "quantity" ? "tab tab-sm active" : "tab tab-sm"}
                onClick={() => toggleMetric("quantity")}>Quantidade</button>
            </div></div>
          <TopList items={products} metric={metric}
            secondary={item => metric === "revenue" ? qty(item.quantity) : money(item.revenue)}/>
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Vendedores</h2>
            <p>Códigos do ERP; a identificação de nomes depende do cadastro oficial.</p></div></div>
          <TopList items={sellers} metric="revenue"/>
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Clientes</h2>
            <p>Razão informada pelo ERP; CNPJ visível apenas à administração.</p></div></div>
          <div className="sales-top">
            {customers.length === 0 && <p className="empty">Sem dados no período.</p>}
            {customers.map((item, index) => <div className="sales-top-row" key={item.key + index}>
              <span className="sales-top-rank">{index + 1}</span>
              <span className="sales-top-name" title={item.customer_cnpj ?? item.key}>
                {item.key}{item.customer_cnpj ? <small className="sales-cnpj"> · {item.customer_cnpj}</small> : null}</span>
              <span className="sales-top-value">{money(item.revenue)}</span>
            </div>)}
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head"><div><h2>Devoluções por dia e loja</h2>
          <p>Registradas pelo ERP, sem abatimento automático do faturamento.</p></div></div>
        <div className="table-wrap"><table><thead><tr>
          <th>Data</th><th>Loja</th><th>Quantidade</th><th>Valor devolvido</th>
        </tr></thead><tbody>
          {days.filter(d => Number(d.returns_quantity) > 0).map(d =>
            <tr key={d.date + d.store_code}>
              <td>{dayMonth(d.date)}</td><td>{labelStore(d.store_code)}</td>
              <td>{qty(d.returns_quantity)}</td><td>{money(d.returns_revenue)}</td>
            </tr>)}
          {days.every(d => Number(d.returns_quantity) === 0) &&
            <tr><td colSpan={4} className="empty">Nenhuma devolução no período.</td></tr>}
        </tbody></table></div>
      </section>
    </>}

    <section className="panel sales-foot">
      <div className="sales-foot-grid">
        <div className="sales-foot-block">
          <strong>Dados em fase de testes</strong>
          <span>Números ainda não reconciliados com os relatórios oficiais do ERP.
            Devoluções são exibidas separadamente e não descontadas do faturamento.</span>
        </div>
        <div className="sales-foot-block">
          <strong>Google Drive · pasta DadosUMA</strong>
          <span>Vendas: {vendas?.last_applied_at
            ? "atualizado em " + dateTime(vendas.last_applied_at) + " (" + vendas.rows_applied + " linhas)"
            : "nenhum arquivo importado ainda"}</span>
          <span>Verificação automática: {status?.drive.enabled
            ? "a cada " + Math.round((status.drive.interval_seconds ?? 600) / 60) + " min"
            : "desativada (configure a conta de serviço)"}</span>
          {lastError && <span className="sales-sync-error">Última falha: {lastError}</span>}
        </div>
        <div className="sales-foot-actions">
          {message && <span className={"sales-foot-msg" +
            (message.includes("falha") ? " sales-sync-error" : "")}>{message}</span>}
          {canSync && <button className="btn-secondary" type="button"
            disabled={syncing} onClick={() => void doSync()}>
            {syncing ? "Sincronizando…" : "Sincronizar agora"}</button>}
        </div>
      </div>
    </section>
  </div>;
}
