import {Fragment,useCallback,useEffect,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {financeApi,type FinanceBatch,type FinanceOverview,type ObligationItem,
  type ObligationPage,type PaymentsPage,type PurchasesView} from "./financeApi";

type Props={token:string;profile:MyProfile};
type FinTab="overview"|"payables"|"payments"|"purchases";

const brl=new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"});
const fmt=(v?:string|null)=>v==null||v===""?"—":brl.format(Number(v));
const dmy=(iso?:string|null)=>iso?iso.slice(0,10).split("-").reverse().join("/"):"—";
const monthLabel=(m:string)=>m.slice(5,7)+"/"+m.slice(0,4);
const dtHora=(iso?:string|null)=>{
  if(!iso)return"—";
  const d=new Date(iso);
  return isNaN(+d)?"—":d.toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"});
};
const localToday=()=>{
  const d=new Date();
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),
    String(d.getDate()).padStart(2,"0")].join("-");
};
const shiftDays=(iso:string,delta:number)=>{
  const d=new Date(iso+"T12:00:00");
  d.setDate(d.getDate()+delta);
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),
    String(d.getDate()).padStart(2,"0")].join("-");
};
const monthNow=()=>localToday().slice(0,7);
const monthBounds=(m:string)=>({from:m+"-01",
  to:new Date(+m.slice(0,4),+m.slice(5,7),0).toISOString().slice(0,10)});

const FLAG_LABEL:Record<string,string>={
  vencido:"Vencido",hoje:"Vence hoje",a_vencer:"A vencer",quitado:"Quitado"};
const catLabel=(c:string)=>c==="compra_revenda"?"Compra p/ revenda":"Despesa";

type PayableFilters={store:string;status:string;category:string;supplier:string;
  due_from:string;due_to:string;sort:string;page:number};
type PaymentFilters={store:string;category:string;supplier:string;
  paid_from:string;paid_to:string;sort:string;page:number};

function Bars({data,empty,hint}:{data:{label:string;value:number;sub?:string}[];
  empty:string;hint?:string}){
  if(!data.length)return <p className="empty">{empty}</p>;
  const max=Math.max(...data.map(d=>d.value),0.01);
  return <div className="fin-bars">{hint&&<p className="fin-bars-hint">{hint}</p>}
    {data.map(d=><div className="fin-bar-row" key={d.label}>
      <span className="fin-bar-label" title={d.label}>{d.label}</span>
      <span className="fin-bar-track"><span className="fin-bar-fill"
        style={{width:Math.max(2,d.value/max*100)+"%"}}/></span>
      <span className="fin-bar-value">{brl.format(d.value)}{d.sub&&
        <small> · {d.sub}</small>}</span>
    </div>)}</div>;
}

function Pager({total,page,pageSize,onPage}:{total:number;page:number;
  pageSize:number;onPage:(p:number)=>void}){
  const pages=Math.max(1,Math.ceil(total/pageSize));
  if(total<=0)return null;
  return <div className="paging">
    <button className="btn-ghost" disabled={page<=1} onClick={()=>onPage(page-1)}>Anterior</button>
    <span>Página {page} de {pages} · {total} lançamentos</span>
    <button className="btn-ghost" disabled={page>=pages} onClick={()=>onPage(page+1)}>Próxima</button>
  </div>;
}

function StoreFilter({profile,value,onChange}:{profile:MyProfile;value:string;
  onChange:(v:string)=>void}){
  return <label>Loja
    <select value={value} onChange={e=>onChange(e.target.value)}>
      {profile.stores.length>1&&<option value="TODAS">Todas as lojas</option>}
      {profile.stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}
    </select></label>;
}

function FlagPill({flag}:{flag:string}){
  return <span className={"fin-flag fin-flag-"+flag}>{FLAG_LABEL[flag]??flag}</span>;
}

function LastImport({info}:{info?:{imported_at:string|null;file_name:string;
  row_count?:number}|null}){
  if(!info)return null;
  return <p className="fin-last-import">Última importação: <strong>{dtHora(info.imported_at)}</strong>
    {" · "}{info.file_name}{info.row_count!=null&&` · ${info.row_count} lançamentos`}</p>;
}

function ItemTable({items,axis}:{items:ObligationItem[];axis:"due"|"paid"}){
  if(!items.length)return <p className="empty">Nenhum lançamento encontrado com esses filtros.</p>;
  let lastMonth="";
  const grouped=axis==="due";
  return <div className="table-wrap"><table>
    <thead><tr>
      <th>Fornecedor</th><th>Loja</th><th>Categoria</th>
      <th>{axis==="due"?"Vencimento":"Pagamento"}</th>
      <th>{axis==="due"?"Pagamento":"Vencimento"}</th>
      <th>Situação</th><th className="fin-num">Valor</th>
    </tr></thead>
    <tbody>
      {items.map(item=>{
        const axisDate=axis==="due"?item.due_date:item.paid_at??"";
        const monthKey=axisDate.slice(0,7);
        const head=grouped&&monthKey!==lastMonth?(lastMonth=monthKey,
          <tr className="fin-group-row" key={"g"+item.id}><td colSpan={7}>{monthLabel(monthKey)}</td></tr>):null;
        return <Fragment key={item.id}>{head}
          <tr>
            <td><strong>{item.supplier_name}</strong>
              {item.supplier_doc&&<div className="mono fin-doc">{item.supplier_doc}</div>}</td>
            <td>{labelStore(item.store_code)}</td>
            <td>{catLabel(item.category)}</td>
            <td>{dmy(axis==="due"?item.due_date:item.paid_at)}</td>
            <td>{dmy(axis==="due"?item.paid_at:item.due_date)}</td>
            <td>{item.status==="pago"?<span className="pill pill-green">Pago</span>:
              <FlagPill flag={item.due_flag}/>}</td>
            <td className="fin-num">{fmt(item.amount)}</td>
          </tr></Fragment>;
      })}
    </tbody></table></div>;
}

export function FinancePage({token,profile}:Props){
  const isSuperAdmin=profile.profile==="superadmin";
  const firstStore=profile.stores.length===1?profile.stores[0]:"TODAS";

  const [tab,setTab]=useState<FinTab>("overview");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [importing,setImporting]=useState(false);
  const [file,setFile]=useState<File|null>(null);
  const [batches,setBatches]=useState<FinanceBatch[]|null>(null);
  const [showBatches,setShowBatches]=useState(false);
  const [batchFlags,setBatchFlags]=useState<{id:string;flags:{row:number;code:string;detail:string}[]}|null>(null);

  const [ovStore,setOvStore]=useState(firstStore);
  const [ovMonth,setOvMonth]=useState(monthNow);
  const [overview,setOverview]=useState<FinanceOverview|null>(null);
  const [ovLoading,setOvLoading]=useState(false);

  const blankPayable:PayableFilters={store:firstStore,status:"",category:"",
    supplier:"",due_from:"",due_to:"",sort:"due_date",page:1};
  const [pf,setPf]=useState<PayableFilters>(blankPayable);
  const [payables,setPayables]=useState<ObligationPage|null>(null);
  const [pfLoading,setPfLoading]=useState(false);

  const blankPayments:PaymentFilters={store:firstStore,category:"",supplier:"",
    paid_from:"",paid_to:"",sort:"-paid_at",page:1};
  const [ym,setYm]=useState<PaymentFilters>(blankPayments);
  const [payments,setPayments]=useState<PaymentsPage|null>(null);
  const [ymLoading,setYmLoading]=useState(false);

  const [pcStore,setPcStore]=useState(firstStore);
  const [pcSupplier,setPcSupplier]=useState("");
  const [pcPage,setPcPage]=useState(1);
  const [purchases,setPurchases]=useState<PurchasesView|null>(null);
  const [pcLoading,setPcLoading]=useState(false);

  const [debouncedPfSupplier,setDebouncedPfSupplier]=useState("");
  const [debouncedYmSupplier,setDebouncedYmSupplier]=useState("");
  const [debouncedPcSupplier,setDebouncedPcSupplier]=useState("");
  useEffect(()=>{const t=setTimeout(()=>setDebouncedPfSupplier(pf.supplier),350);return()=>clearTimeout(t);},[pf.supplier]);
  useEffect(()=>{const t=setTimeout(()=>setDebouncedYmSupplier(ym.supplier),350);return()=>clearTimeout(t);},[ym.supplier]);
  useEffect(()=>{const t=setTimeout(()=>setDebouncedPcSupplier(pcSupplier),350);return()=>clearTimeout(t);},[pcSupplier]);
  useEffect(()=>{setPf(p=>({...p,page:1}));},[debouncedPfSupplier]);
  useEffect(()=>{setYm(p=>({...p,page:1}));},[debouncedYmSupplier]);
  useEffect(()=>{setPcPage(1);},[debouncedPcSupplier]);

  const refreshBatches=useCallback(async()=>{
    try{setBatches((await financeApi.batches(token)).items);}
    catch{setBatches([]);}
  },[token]);

  const loadOverview=useCallback(async()=>{
    setOvLoading(true);
    try{setOverview(await financeApi.overview(token,{store:ovStore==="TODAS"?undefined:ovStore,month:ovMonth}));}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao consultar a visão geral.");}
    finally{setOvLoading(false);}
  },[token,ovStore,ovMonth]);
  useEffect(()=>{if(tab==="overview")void loadOverview();},[tab,loadOverview]);

  const loadPayables=useCallback(async()=>{
    setPfLoading(true);
    try{setPayables(await financeApi.obligations(token,{
      store:pf.store==="TODAS"?undefined:pf.store,category:pf.category||undefined,
      status:pf.status||undefined,supplier:debouncedPfSupplier||undefined,
      due_from:pf.due_from||undefined,due_to:pf.due_to||undefined,
      sort:pf.sort,page:pf.page,page_size:25}));}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao consultar contas a pagar.");}
    finally{setPfLoading(false);}
  },[token,pf,debouncedPfSupplier]);
  useEffect(()=>{if(tab==="payables")void loadPayables();},[tab,loadPayables]);

  const loadPayments=useCallback(async()=>{
    setYmLoading(true);
    try{setPayments(await financeApi.payments(token,{
      store:ym.store==="TODAS"?undefined:ym.store,category:ym.category||undefined,
      supplier:debouncedYmSupplier||undefined,
      paid_from:ym.paid_from||undefined,paid_to:ym.paid_to||undefined,
      sort:ym.sort,page:ym.page,page_size:25}));}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao consultar pagamentos.");}
    finally{setYmLoading(false);}
  },[token,ym,debouncedYmSupplier]);
  useEffect(()=>{if(tab==="payments")void loadPayments();},[tab,loadPayments]);

  const loadPurchases=useCallback(async()=>{
    setPcLoading(true);
    try{setPurchases(await financeApi.purchases(token,{
      store:pcStore==="TODAS"?undefined:pcStore,
      supplier:debouncedPcSupplier||undefined,page:pcPage,page_size:25}));}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao consultar compras.");}
    finally{setPcLoading(false);}
  },[token,pcStore,debouncedPcSupplier,pcPage]);
  useEffect(()=>{if(tab==="purchases")void loadPurchases();},[tab,loadPurchases]);

  useEffect(()=>{void refreshBatches();},[refreshBatches]);

  async function doImport(){
    if(!file)return;
    setImporting(true);setError("");setNotice("");
    try{
      const res=await financeApi.importDespesas(token,file);
      setNotice(res.duplicated
        ?"Arquivo já importado anteriormente — nenhum lançamento duplicado."
        :`Importação concluída: ${res.batch.row_count} lançamentos`+
          (res.batch.quality_flag_count?` · ${res.batch.quality_flag_count} avisos de qualidade`:""));
      setFile(null);
      await Promise.all([refreshBatches(),loadOverview(),loadPayables(),loadPayments(),loadPurchases()]);
    }catch(cause){
      setError(cause instanceof Error?cause.message:"Falha ao importar.");
      void refreshBatches();
    }finally{setImporting(false);}
  }

  async function showFlags(batch:FinanceBatch){
    try{
      const detail=await financeApi.batch(token,batch.id);
      setBatchFlags({id:batch.id,flags:detail.quality_flags??[]});
    }catch{setBatchFlags({id:batch.id,flags:[]});}
  }

  function drill(kind:"open"|"overdue"|"due7"|"due30"|"paid"){
    const today=overview?.as_of??localToday();
    if(kind==="paid"){
      const b=monthBounds(ovMonth);
      setYm({...blankPayments,store:ovStore,paid_from:b.from,paid_to:b.to});
      setTab("payments");return;
    }
    const base:PayableFilters={...blankPayable,store:ovStore,status:"aberto"};
    if(kind==="overdue")base.due_to=shiftDays(today,-1);
    if(kind==="due7"){base.due_from=today;base.due_to=shiftDays(today,7);}
    if(kind==="due30"){base.due_from=today;base.due_to=shiftDays(today,30);}
    setPf(base);setDebouncedPfSupplier("");setTab("payables");
  }

  const k=overview?.kpis;
  return <section>
    <div className="page-header"><div>
      <div className="eyebrow">ERP — DESPESAS E PAGAMENTOS</div>
      <h1>Financeiro</h1>
      <p>Compromissos por vencimento e pagamentos por data efetiva, separados entre
        compras para revenda e despesas operacionais. Sem cálculo de CMV ou margem nesta etapa.</p>
    </div></div>

    {error&&<div className="notice notice-error" role="alert">{error}
      <button className="fin-notice-close" onClick={()=>setError("")} aria-label="Fechar">×</button></div>}
    {notice&&<div className="notice notice-success" role="status">{notice}</div>}

    {isSuperAdmin&&<article className="panel fin-import">
      <div className="panel-head"><div>
        <h2>Importação do ERP</h2>
        <p>Envie o arquivo <strong>Despesas.csv</strong> exportado do ERP. Reenviar o mesmo
          arquivo não duplica lançamentos; versões anteriores ficam preservadas para auditoria.</p>
      </div></div>
      <div className="fin-import-row">
        <input type="file" accept=".csv,text/csv" aria-label="Arquivo Despesas.csv"
          onChange={e=>setFile(e.target.files?.[0]??null)}/>
        <button className="btn-primary" disabled={!file||importing} onClick={()=>void doImport()}>
          {importing?"Importando…":"Importar Despesas.csv"}</button>
        <button className="btn-ghost" onClick={()=>{setShowBatches(s=>!s);if(!showBatches)void refreshBatches();}}>
          {showBatches?"Ocultar histórico":"Histórico de importações"}</button>
      </div>
      {showBatches&&<div className="fin-batches">
        {!batches?.length&&<p className="empty">Nenhuma importação registrada ainda.</p>}
        {batches?.map(b=><div className={"fin-batch"+(b.is_current?" current":"")+(b.status==="failed"?" failed":"")} key={b.id}>
          <div className="fin-batch-main">
            <strong>{b.file_name}</strong>
            <span>{dtHora(b.imported_at)} · {b.channel==="manual"?"manual":"drive"} · {b.row_count} lançamentos
              {b.period_start&&` · ${dmy(b.period_start)} a ${dmy(b.period_end)}`}</span>
            {b.error_detail&&<span className="fin-batch-error">{b.error_detail}</span>}
            {batchFlags?.id===b.id&&<div className="fin-flags">
              {!batchFlags.flags.length&&<small>Sem avisos de qualidade registrados.</small>}
              {batchFlags.flags.map((f,i)=><small key={i}>Linha {f.row}: {f.detail} <em>({f.code})</em></small>)}
              {b.quality_flag_count>batchFlags.flags.length&&
                <small>… e mais {b.quality_flag_count-batchFlags.flags.length} avisos.</small>}
            </div>}
          </div>
          <div className="fin-batch-side">
            {b.status==="failed"?<span className="fin-flag fin-flag-vencido">Falhou</span>:
              b.is_current?<span className="pill pill-green">Vigente</span>:<span className="pill pill-grey">Histórico</span>}
            {b.quality_flag_count>0&&<button className="btn-ghost" onClick={()=>void showFlags(b)}>
              {b.quality_flag_count} avisos</button>}
          </div>
        </div>)}
      </div>}
    </article>}

    <div className="tabs" role="tablist" aria-label="Módulo financeiro">
      <button role="tab" aria-selected={tab==="overview"} className={"tab"+(tab==="overview"?" active":"")}
        onClick={()=>setTab("overview")}>Visão geral</button>
      <button role="tab" aria-selected={tab==="payables"} className={"tab"+(tab==="payables"?" active":"")}
        onClick={()=>setTab("payables")}>Contas a pagar</button>
      <button role="tab" aria-selected={tab==="payments"} className={"tab"+(tab==="payments"?" active":"")}
        onClick={()=>setTab("payments")}>Pagamentos</button>
      <button role="tab" aria-selected={tab==="purchases"} className={"tab"+(tab==="purchases"?" active":"")}
        onClick={()=>setTab("purchases")}>Compras p/ revenda</button>
    </div>

    {tab==="overview"&&<>
      <div className="routine-filters">
        <StoreFilter profile={profile} value={ovStore} onChange={setOvStore}/>
        <label>Mês dos pagamentos<input type="month" min="2020-01" max="2100-12"
          value={ovMonth} onChange={e=>setOvMonth(e.target.value)}/></label>
      </div>
      {ovLoading&&<p role="status">Carregando indicadores…</p>}
      {overview&&!ovLoading&&<>
        <LastImport info={overview.last_import}/>
        {!overview.has_data?<p className="empty">Nenhum lançamento importado ainda.
          {isSuperAdmin?" Importe o Despesas.csv para visualizar os indicadores.":""}</p>:<>
        <div className="fin-kpis">
          <button className="panel fin-kpi" onClick={()=>drill("open")}>
            <span>Contas em aberto</span><strong>{fmt(k?.open_amount)}</strong>
            <small>{k?.open_count} lançamentos · por vencimento</small></button>
          <button className="panel fin-kpi fin-kpi-danger" onClick={()=>drill("overdue")}>
            <span>Vencidas</span><strong>{fmt(k?.overdue_amount)}</strong>
            <small>{k?.overdue_count} em atraso</small></button>
          <button className="panel fin-kpi" onClick={()=>drill("due7")}>
            <span>Vencem em 7 dias</span><strong>{fmt(k?.due_7d_amount)}</strong>
            <small>{k?.due_7d_count} compromissos</small></button>
          <button className="panel fin-kpi" onClick={()=>drill("due30")}>
            <span>Vencem em 30 dias</span><strong>{fmt(k?.due_30d_amount)}</strong>
            <small>{k?.due_30d_count} compromissos</small></button>
          <button className="panel fin-kpi fin-kpi-paid" onClick={()=>drill("paid")}>
            <span>Pagos em {monthLabel(ovMonth)}</span><strong>{fmt(k?.paid_month_amount)}</strong>
            <small>{k?.paid_month_count} pagamentos efetivos</small></button>
        </div>
        <div className="fin-split">
          <article className="panel"><div className="panel-head"><div>
            <h2>Compromissos em aberto por mês</h2><p>Somatório por data de vencimento.</p></div></div>
            <Bars data={(overview.monthly_due??[]).map(m=>({label:monthLabel(m.month),
              value:Number(m.amount),sub:m.count+" lanç."}))}
              empty="Nenhum compromisso em aberto."/>
          </article>
          <article className="panel"><div className="panel-head"><div>
            <h2>Por loja</h2><p>Em aberto (vencimento) e pago no mês selecionado.</p></div></div>
            {(overview.by_store??[]).map(s=><div className="fin-store-line" key={s.store_code}>
              <div className="fin-store-name">{labelStore(s.store_code)}</div>
              <div className="fin-store-vals">
                <span>Em aberto <strong>{fmt(s.open_amount)}</strong> ({s.open_count})</span>
                <span>Pago em {monthLabel(ovMonth)} <strong>{fmt(s.paid_month_amount)}</strong> ({s.paid_month_count})</span>
              </div></div>)}
          </article>
        </div>
        <div className="fin-split">
          {(["compra_revenda","despesa"] as const).map(cat=>{
            const c=overview.by_category?.[cat];
            return <article className="panel" key={cat}><div className="panel-head"><div>
              <h2>{catLabel(cat)}</h2>
              <p>{cat==="compra_revenda"?"Compras de mercadoria — não é despesa operacional nem CMV."
                :"Despesas operacionais registradas no ERP."}</p></div></div>
              <div className="fin-cat-vals">
                <div><span>Em aberto</span><strong>{fmt(c?.open_amount)}</strong>
                  <small>{c?.open_count??0} lançamentos</small></div>
                <div><span>Pago em {monthLabel(ovMonth)}</span><strong>{fmt(c?.paid_month_amount)}</strong>
                  <small>{c?.paid_month_count??0} pagamentos</small></div>
              </div></article>;
          })}
        </div></>}
      </>}
    </>}

    {tab==="payables"&&<>
      <div className="routine-filters">
        <StoreFilter profile={profile} value={pf.store}
          onChange={v=>setPf({...pf,store:v,page:1})}/>
        <label>Situação<select value={pf.status} onChange={e=>setPf({...pf,status:e.target.value,page:1})}>
          <option value="">Todas</option><option value="aberto">Aberto</option><option value="pago">Pago</option>
        </select></label>
        <label>Categoria<select value={pf.category} onChange={e=>setPf({...pf,category:e.target.value,page:1})}>
          <option value="">Todas</option><option value="despesa">Despesa</option>
          <option value="compra_revenda">Compra p/ revenda</option>
        </select></label>
        <label>Fornecedor<input type="search" placeholder="Buscar por nome"
          value={pf.supplier} onChange={e=>setPf({...pf,supplier:e.target.value})}/></label>
        <label>Vencimento de<input type="date" value={pf.due_from}
          onChange={e=>setPf({...pf,due_from:e.target.value,page:1})}/></label>
        <label>até<input type="date" value={pf.due_to}
          onChange={e=>setPf({...pf,due_to:e.target.value,page:1})}/></label>
        <label>Ordenar<select value={pf.sort} onChange={e=>setPf({...pf,sort:e.target.value,page:1})}>
          <option value="due_date">Vencimento ↑</option><option value="-due_date">Vencimento ↓</option>
          <option value="-amount">Maior valor</option><option value="amount">Menor valor</option>
          <option value="supplier_name">Fornecedor A–Z</option>
        </select></label>
        <button className="btn-ghost" onClick={()=>{setPf(blankPayable);setDebouncedPfSupplier("");}}>Limpar</button>
      </div>
      {payables?.last_import&&<LastImport info={payables.last_import}/>}
      {pfLoading&&<p role="status">Carregando compromissos…</p>}
      {payables&&!pfLoading&&<>
        <div className="fin-total-line">Total filtrado: <strong>{fmt(payables.sum_amount)}</strong>
          {" · "}{payables.total} lançamentos · eixo: <strong>data de vencimento</strong></div>
        <ItemTable items={payables.items} axis="due"/>
        <Pager total={payables.total} page={payables.page} pageSize={payables.page_size}
          onPage={p=>setPf({...pf,page:p})}/>
      </>}
    </>}

    {tab==="payments"&&<>
      <div className="routine-filters">
        <StoreFilter profile={profile} value={ym.store}
          onChange={v=>setYm({...ym,store:v,page:1})}/>
        <label>Categoria<select value={ym.category} onChange={e=>setYm({...ym,category:e.target.value,page:1})}>
          <option value="">Todas</option><option value="despesa">Despesa</option>
          <option value="compra_revenda">Compra p/ revenda</option>
        </select></label>
        <label>Fornecedor<input type="search" placeholder="Buscar por nome"
          value={ym.supplier} onChange={e=>setYm({...ym,supplier:e.target.value})}/></label>
        <label>Pagamento de<input type="date" value={ym.paid_from}
          onChange={e=>setYm({...ym,paid_from:e.target.value,page:1})}/></label>
        <label>até<input type="date" value={ym.paid_to}
          onChange={e=>setYm({...ym,paid_to:e.target.value,page:1})}/></label>
        <label>Ordenar<select value={ym.sort} onChange={e=>setYm({...ym,sort:e.target.value,page:1})}>
          <option value="-paid_at">Pagamento ↓</option><option value="paid_at">Pagamento ↑</option>
          <option value="-amount">Maior valor</option><option value="amount">Menor valor</option>
          <option value="supplier_name">Fornecedor A–Z</option>
        </select></label>
        <button className="btn-ghost" onClick={()=>{setYm(blankPayments);setDebouncedYmSupplier("");}}>Limpar</button>
      </div>
      {payments?.last_import&&<LastImport info={payments.last_import}/>}
      {ymLoading&&<p role="status">Carregando pagamentos…</p>}
      {payments&&!ymLoading&&<>
        <div className="routine-kpis">
          <div className="panel"><span>Total pago no período</span>
            <strong>{fmt(payments.sum_amount)}</strong><small>{payments.total} pagamentos efetivos</small></div>
          <div className="panel"><span>Compras p/ revenda</span>
            <strong>{fmt(payments.by_category?.["compra_revenda"]?.amount)}</strong>
            <small>{payments.by_category?.["compra_revenda"]?.count??0} pagamentos</small></div>
          <div className="panel"><span>Despesas</span>
            <strong>{fmt(payments.by_category?.["despesa"]?.amount)}</strong>
            <small>{payments.by_category?.["despesa"]?.count??0} pagamentos</small></div>
        </div>
        <div className="fin-split">
          <article className="panel"><div className="panel-head"><div>
            <h2>Evolução mensal</h2><p>Somatório por data efetiva de pagamento.</p></div></div>
            <Bars data={(payments.by_month??[]).map(m=>({label:monthLabel(m.month),
              value:Number(m.amount),sub:m.count+" pag."}))} empty="Nenhum pagamento no período."/>
          </article>
          <article className="panel"><div className="panel-head"><div>
            <h2>Por loja</h2><p>Pagamentos efetivos no recorte atual.</p></div></div>
            <Bars data={(payments.by_store??[]).map(s=>({label:labelStore(s.store_code),
              value:Number(s.amount),sub:s.count+" pag."}))} empty="Nenhum pagamento no período."/>
          </article>
        </div>
        <ItemTable items={payments.items} axis="paid"/>
        <Pager total={payments.total} page={payments.page} pageSize={payments.page_size}
          onPage={p=>setYm({...ym,page:p})}/>
      </>}
    </>}

    {tab==="purchases"&&<>
      <div className="routine-filters">
        <StoreFilter profile={profile} value={pcStore} onChange={v=>{setPcStore(v);setPcPage(1);}}/>
        <label>Fornecedor<input type="search" placeholder="Buscar por nome"
          value={pcSupplier} onChange={e=>setPcSupplier(e.target.value)}/></label>
      </div>
      {purchases?.last_import&&<LastImport info={purchases.last_import}/>}
      {pcLoading&&<p role="status">Carregando compras…</p>}
      {purchases&&!pcLoading&&<>
        {!purchases.has_data?<p className="empty">Nenhuma compra para revenda registrada.</p>:<>
        <div className="notice notice-amber fin-note">Registros financeiros de compras de mercadoria
          no arquivo do ERP — não representam necessariamente o volume econômico adquirido nem o CMV.</div>
        <div className="routine-kpis">
          <div className="panel"><span>Total registrado</span>
            <strong>{fmt(purchases.totals.amount)}</strong><small>{purchases.totals.count} lançamentos</small></div>
          <div className="panel"><span>Já pagos</span>
            <strong>{fmt(purchases.totals.paid_amount)}</strong><small>{purchases.totals.paid_count} pagamentos</small></div>
          <div className="panel"><span>Em aberto</span>
            <strong>{fmt(purchases.totals.open_amount)}</strong><small>{purchases.totals.open_count} compromissos</small></div>
        </div>
        <div className="fin-split">
          <article className="panel"><div className="panel-head"><div>
            <h2>Principais fornecedores</h2><p>Por valor total registrado.</p></div></div>
            <Bars data={(purchases.top_suppliers??[]).map(s=>({label:s.supplier_name,
              value:Number(s.amount),sub:s.count+" lanç."}))} empty="Sem fornecedores."/>
          </article>
          <article className="panel"><div className="panel-head"><div>
            <h2>Compromissos por mês</h2><p>Eixo vencimento, todas as situações.</p></div></div>
            <Bars data={(purchases.by_month??[]).map(m=>({label:monthLabel(m.month),
              value:Number(m.amount),sub:m.count+" lanç."}))} empty="Sem compromissos."/>
          </article>
        </div>
        <article className="panel"><div className="panel-head"><div>
          <h2>Por loja</h2><p>Valor total de compras para revenda.</p></div></div>
          <Bars data={(purchases.by_store??[]).map(s=>({label:labelStore(s.store_code),
            value:Number(s.amount),sub:s.count+" lanç."}))} empty="Sem compras."/>
        </article>
        <ItemTable items={purchases.items} axis="due"/>
        <Pager total={purchases.total} page={purchases.page} pageSize={purchases.page_size}
          onPage={setPcPage}/>
      </>}
      </>}
    </>}
  </section>;
}

