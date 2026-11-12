import {useEffect, useMemo, useRef, useState} from "react";
import {
  api, uploadSalesFile, type MyProfile, type SalesBatch, type SalesDailyRow,
  type SalesSummary, type SalesSyncStatus, type SalesTopItem,
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

const STORE_COLORS: Record<string, string> = {
  JOINVILLE: "#0e757a", TUBARAO: "#b7a92d", ITAJAI: "#35566b",
};

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

function DailyChart({days}: {days: SalesDailyRow[]}) {
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
    return [...set].sort();
  }, [days]);
  if (byDate.length === 0) return <p className="empty">Nenhuma venda registrada no período.</p>;
  const max = Math.max(...byDate.map(([, v]) => Object.values(v).reduce((a, b) => a + b, 0)), 1);
  const barW = Math.max(14, Math.min(40, Math.floor(920 / byDate.length)));
  const width = byDate.length * barW;
  const height = 190;
  return <div>
    <div className="sales-legend">
      {stores.map(code => <span key={code} className="sales-legend-item">
        <i style={{background: STORE_COLORS[code] ?? "#607d8b"}}/>{labelStore(code)}</span>)}
    </div>
    <div className="sales-chart-wrap">
      <svg className="sales-chart" viewBox={`0 0 ${width} ${height + 26}`}
        role="img" aria-label="Faturamento diário por loja">
        {byDate.map(([iso, perStore], index) => {
          const total = Object.values(perStore).reduce((a, b) => a + b, 0);
          const barH = (total / max) * (height - 30);
          let offset = 0;
          return <g key={iso}>
            {stores.map(code => {
              const value = perStore[code] ?? 0;
              if (!value) return null;
              const h = (value / total) * barH;
              const y = height - 10 - offset - h;
              offset += h;
              return <rect key={code} x={index * barW + 2} y={y} width={barW - 4} height={h}
                rx={2} fill={STORE_COLORS[code] ?? "#607d8b"}>
                <title>{labelStore(code)} · {dayMonth(iso)} · {money(value)}</title>
              </rect>;
            })}
            {(index % Math.ceil(byDate.length / 15) === 0 || index === byDate.length - 1) &&
              <text x={index * barW + barW / 2} y={height + 18} textAnchor="middle"
                className="sales-chart-label">{dayMonth(iso)}</text>}
          </g>;
        })}
        <line x1={0} y1={height - 10} x2={width} y2={height - 10} stroke="#dbe5e9"/>
      </svg>
    </div>
  </div>;
}

function TopList({title, items, metric}: {title: string; items: SalesTopItem[]; metric: "revenue" | "quantity"}) {
  const max = Math.max(...items.map(i => Number(metric === "revenue" ? i.revenue : i.quantity)), 1);
  return <div className="sales-top">
    <h3>{title}</h3>
    {items.length === 0 && <p className="empty">Sem dados no período.</p>}
    {items.map((item, index) => {
      const value = Number(metric === "revenue" ? item.revenue : item.quantity);
      return <div className="sales-top-row" key={item.key + index}>
        <span className="sales-top-rank">{index + 1}</span>
        <span className="sales-top-name" title={item.key}>{item.key}</span>
        <span className="sales-top-bar"><i style={{width: (value / max * 100) + "%"}}/></span>
        <span className="sales-top-value">{metric === "revenue" ? money(item.revenue) : qty(item.quantity)}</span>
      </div>;
    })}
  </div>;
}

export function SalesPage({token, profile}: Props) {
  const stores = profile.stores;
  const [from, setFrom] = useState(firstOfMonth);
  const [to, setTo] = useState(todayIso);
  const [store, setStore] = useState<string>("");
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [days, setDays] = useState<SalesDailyRow[]>([]);
  const [products, setProducts] = useState<SalesTopItem[]>([]);
  const [sellers, setSellers] = useState<SalesTopItem[]>([]);
  const [customers, setCustomers] = useState<SalesTopItem[]>([]);
  const [status, setStatus] = useState<SalesSyncStatus | null>(null);
  const [batches, setBatches] = useState<SalesBatch[]>([]);
  const [metric, setMetric] = useState<"revenue" | "quantity">("revenue");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [kind, setKind] = useState<"vendas" | "devolucoes">("vendas");
  const [importing, setImporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const canImport = profile.profile !== "seller";

  const load = async (f = from, t = to, s = store) => {
    setLoading(true); setError("");
    try {
      const [sum, daily, prod, sell, cust, stat] = await Promise.all([
        api.salesSummary(token, f, t, s || undefined),
        api.salesDaily(token, f, t, s || undefined),
        api.salesTop(token, "products", f, t, s || undefined, 10),
        api.salesTop(token, "sellers", f, t, s || undefined, 10),
        api.salesTop(token, "customers", f, t, s || undefined, 10),
        api.salesStatus(token),
      ]);
      setSummary(sum); setDays(daily.days); setProducts(prod.items);
      setSellers(sell.items); setCustomers(cust.items); setStatus(stat);
      if (canImport) {
        const imp = await api.salesImports(token, 15);
        setBatches(imp.items);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível consultar as vendas.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [token, store]);

  const doImport = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { setError("Selecione o arquivo CSV do ERP."); return; }
    setImporting(true); setError(""); setMessage("");
    try {
      const result = await uploadSalesFile(token, kind, file);
      setMessage(result.batch.status === "DUPLICATE"
        ? "Este arquivo já havia sido importado — nada foi duplicado."
        : `Importação concluída: ${result.batch.rows_applied} linhas aplicadas.`);
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha na importação.");
    } finally {
      setImporting(false);
    }
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

    <div className="notice notice-amber" role="status">
      Os números abaixo são dados em fase de testes e ainda não foram reconciliados
      com os relatórios oficiais do ERP. Devoluções são exibidas separadamente e
      não são descontadas do faturamento.
    </div>
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {message && <div className="notice notice-success" role="status">{message}</div>}

    <section className="panel sales-sync">
      <div className="sales-sync-info">
        <strong>Google Drive · pasta DadosUMA</strong>
        <span>Vendas: {vendas?.last_applied_at
          ? "atualizado em " + dateTime(vendas.last_applied_at) + " (" + vendas.rows_applied + " linhas)"
          : "nenhum arquivo importado ainda"}</span>
        <span>Verificação automática: {status?.drive.enabled
          ? "a cada " + Math.round((status.drive.interval_seconds ?? 600) / 60) + " min"
          : "desativada (configure a conta de serviço)"}</span>
        {lastError && <span className="sales-sync-error">Última falha: {lastError}</span>}
      </div>
      {canImport && <button className="btn-secondary" type="button"
        disabled={syncing} onClick={() => void doSync()}>
        {syncing ? "Sincronizando…" : "Sincronizar agora"}</button>}
    </section>

    <div className="target-filters">
      <div className="form-row"><label htmlFor="sales-from">De</label>
        <input id="sales-from" type="date" value={from}
          onChange={e => setFrom(e.target.value)}/></div>
      <div className="form-row"><label htmlFor="sales-to">Até</label>
        <input id="sales-to" type="date" value={to}
          onChange={e => setTo(e.target.value)}/></div>
      {stores.length > 1 && <div className="form-row"><label htmlFor="sales-store">Loja</label>
        <select id="sales-store" value={store} onChange={e => setStore(e.target.value)}>
          <option value="">Todas as lojas</option>
          {stores.map(code => <option key={code} value={code}>{labelStore(code)}</option>)}
        </select></div>}
      <button className="btn-secondary" type="button" disabled={loading}
        onClick={() => void load()}>{loading ? "Atualizando…" : "Aplicar"}</button>
      <button className="btn-ghost" type="button"
        onClick={() => { setFrom(firstOfMonth()); setTo(todayIso()); }}>Este mês</button>
      <button className="btn-ghost" type="button"
        onClick={() => { setFrom(daysAgo(30)); setTo(todayIso()); }}>Últimos 30 dias</button>
    </div>

    {summary && <>
      <div className="overview-kpis">
        <div className="panel overview-kpi"><span>Faturamento do período</span>
          <strong>{money(summary.totals.revenue)}</strong>
          <small>{qty(summary.totals.quantity)} itens em {summary.totals.rows} linhas</small></div>
        <div className="panel overview-kpi"><span>Devoluções registradas</span>
          <strong>{money(summary.totals.returns_revenue)}</strong>
          <small>{summary.totals.returns_rows} linha(s) · exibidas separadamente</small></div>
        {summary.stores.map(item => <div className="panel overview-kpi" key={item.code}>
          <span>{labelStore(item.code)}</span>
          <strong>{item.revenue_visibility === "restricted" ? "Restrito" : money(item.revenue)}</strong>
          <small>{qty(item.quantity)} itens · {money(item.returns_revenue)} em devoluções</small></div>)}
      </div>

      <section className="panel">
        <div className="panel-head"><div><h2>Evolução diária do faturamento</h2>
          <p>Soma das linhas de venda por dia e loja. Barras empilhadas por unidade.</p></div></div>
        <DailyChart days={days}/>
      </section>

      <div className="columns-3">
        <section className="panel">
          <div className="panel-head"><div><h2>Produtos</h2>
            <p>Códigos do ERP sem descrição cadastrada.</p></div>
            <div className="tab-bar">
              <button className={metric === "revenue" ? "tab active" : "tab"}
                onClick={() => setMetric("revenue")}>Faturamento</button>
              <button className={metric === "quantity" ? "tab active" : "tab"}
                onClick={() => setMetric("quantity")}>Quantidade</button>
            </div></div>
          <TopList title="" items={products} metric={metric}/>
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Vendedores</h2>
            <p>Códigos do ERP; a identificação de nomes depende do cadastro oficial.</p></div></div>
          <TopList title="" items={sellers} metric="revenue"/>
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

    {canImport && <section className="panel">
      <div className="panel-head"><div><h2>Importação e histórico</h2>
        <p>Importação manual dos CSVs do ERP (mesmo caminho da sincronização automática).</p></div></div>
      <div className="sales-import">
        <select aria-label="Tipo de arquivo" value={kind}
          onChange={e => setKind(e.target.value as "vendas" | "devolucoes")} disabled={importing}>
          <option value="vendas">Vendas.csv</option>
          <option value="devolucoes">Devolucoes.csv</option>
        </select>
        <input ref={fileRef} type="file" accept=".csv,text/csv" disabled={importing}/>
        <button className="btn-primary" type="button" disabled={importing}
          onClick={() => void doImport()}>{importing ? "Importando…" : "Importar arquivo"}</button>
      </div>
      <div className="table-wrap"><table><thead><tr>
        <th>Data/hora</th><th>Tipo</th><th>Origem</th><th>Arquivo</th><th>Status</th>
        <th>Linhas</th><th>Período</th>
      </tr></thead><tbody>
        {batches.map(batch => <tr key={batch.id}>
          <td>{dateTime(batch.applied_at)}</td><td>{batch.kind}</td>
          <td>{batch.source === "DRIVE_SYNC" ? "Drive" : "Manual"}</td>
          <td>{batch.file_name}</td>
          <td><span className={"pill " + (batch.status === "APPLIED" ? "pill-green"
            : batch.status === "FAILED" ? "pill-red"
            : "pill-grey")}>{batch.status === "APPLIED" ? "Aplicado"
            : batch.status === "DUPLICATE" ? "Já importado"
            : batch.status === "FAILED" ? "Falhou" : batch.status}</span></td>
          <td>{batch.rows_applied}{batch.rows_rejected ? " (+" + batch.rows_rejected + " rejeitadas)" : ""}</td>
          <td>{batch.period_start && batch.period_end
            ? dayMonth(batch.period_start) + " – " + dayMonth(batch.period_end) : "—"}</td>
        </tr>)}
        {batches.length === 0 && <tr><td colSpan={7} className="empty">Nenhuma importação registrada.</td></tr>}
      </tbody></table></div>
    </section>}
  </div>;
}
