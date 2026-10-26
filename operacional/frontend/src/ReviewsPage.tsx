import {useCallback,useEffect,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {operationsApi,type ReviewRow,type ReviewSnapshot} from "./operationsApi";

type Props={token:string;profile:MyProfile};
const initialMonth=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");};
const today=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
const tierName=(tier:ReviewRow["tier"])=>tier==="maior"?"Brinde maior":tier==="simbolico"?"Brinde simbólico":tier==="nenhum"?"Sem brinde":"Sem dados";

export function ReviewsPage({token,profile}:Props){
  const [period,setPeriod]=useState(initialMonth);
  const [data,setData]=useState<ReviewSnapshot|null>(null);
  const [store,setStore]=useState(profile.stores[0]??"");
  const [count,setCount]=useState("0");
  const [checked,setChecked]=useState(today);
  const [delivered,setDelivered]=useState("");
  const [note,setNote]=useState("");
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [year,month]=period.split("-").map(Number);
  const canWrite=profile.profile!=="seller";
  const refresh=useCallback(async()=>{
    setLoading(true);setError("");
    try{setData(await operationsApi.reviews(token,year,month));}
    catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível consultar.");}
    finally{setLoading(false);}
  },[token,year,month]);
  useEffect(()=>{if(year&&month)void refresh();},[refresh,year,month]);
  const current=data?.stores.find(row=>row.store_code===store);
  useEffect(()=>{
    const row=data?.stores.find(r=>r.store_code===store);
    setCount(String(row?.count??0));setChecked(row?.checked_on??today());
    setDelivered(row?.delivered_on??"");setNote(row?.note??"");
  },[data,store]);

  async function save(){
    if(!current)return;
    setWorking(true);setError("");setMessage("");
    try{
      await operationsApi.saveReview(token,store,year,month,{
        count:Number(count),checked_on:checked,delivered_on:delivered||null,
        note,expected_revision:current.revision
      });
      await refresh();setMessage("Conferência Google registrada e auditada.");
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível salvar.");}
    finally{setWorking(false);}
  }

  const reviewSum=data?.stores.reduce((sum,row)=>sum+(row.count??0),0)??0;
  return <section>
    <div className="page-header"><div><div className="eyebrow">VISIBILIDADE DIGITAL</div>
      <h1>Avaliações no Google</h1>
      <p>Conferência mensal por loja e acompanhamento da premiação coletiva, sem acumular brindes.</p></div></div>
    <div className="notice notice-amber">A quantidade é conferida e informada manualmente pela gestão.
      Ainda não existe ligação automática com o Google.</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters">
      <label>Mês de referência<input type="month" min="2020-01" max="2100-12"
        value={period} onChange={e=>setPeriod(e.target.value)}/></label>
      <span className="chip">10 avaliações: brinde simbólico · 20: somente um brinde maior</span>
    </div>
    {loading?<p>Carregando avaliações…</p>:data&&<>
      <div className="routine-kpis">
        <div className="panel"><span>Avaliações conferidas</span><strong>{
          data.stores.every(r=>r.count!==null)?reviewSum:"Parcial"
        }</strong><small>Somente lojas com permissão para consulta</small></div>
        <div className="panel"><span>Lojas com brinde simbólico</span><strong>{
          data.stores.filter(r=>r.tier==="simbolico").length
        }</strong><small>Entre 10 e 19 avaliações</small></div>
        <div className="panel"><span>Lojas com brinde maior</span><strong>{
          data.stores.filter(r=>r.tier==="maior").length
        }</strong><small>20 ou mais avaliações</small></div>
      </div>
      <div className="routine-storecards">
        {data.stores.map(row=><article className="panel" key={row.store_code}>
          <h2>{labelStore(row.store_code)}</h2>
          <strong className="routine-big">{row.count===null?"Sem dados":row.count+" avaliações"}</strong>
          <div className="routine-meta">Premiação: <b>{tierName(row.tier)}</b></div>
          <div className="routine-meta">Entrega: <b>{row.delivered_on??"Pendente / não aplicável"}</b></div>
          <small>{row.checked_on?"Conferido em "+row.checked_on:"Ainda não conferido"}</small>
        </article>)}
      </div>
      {canWrite&&<article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Conferência mensal</h2>
          <p>Os valores são conferidos pela gestão antes de registrar.</p></div></div>
        <div className="routine-form-grid">
          <label>Unidade<select value={store} onChange={e=>setStore(e.target.value)}>
            {data.stores.map(row=><option value={row.store_code} key={row.store_code}>{labelStore(row.store_code)}</option>)}
          </select></label>
          <label>Avaliações no mês<input type="number" min={0} max={9999} step={1}
            value={count} onChange={e=>setCount(e.target.value)}/></label>
          <label>Data da conferência<input type="date" value={checked} onChange={e=>setChecked(e.target.value)}/></label>
          <label>Data de entrega (opcional)<input type="date" value={delivered}
            onChange={e=>setDelivered(e.target.value)}/></label>
          <label className="routine-wide">Observação<input type="text" maxLength={200}
            value={note} onChange={e=>setNote(e.target.value)}/></label>
        </div>
        <p className="small-note">Ao mudar a faixa de premiação, confirme novamente a entrega. Não existe prêmio cumulativo.</p>
        <button className="btn-primary" disabled={working||!store||!checked||count===""||
          Number(count)<0||Number(count)>9999||!Number.isInteger(Number(count))}
          onClick={()=>void save()}>Salvar conferência</button>
      </article>}
    </>}
  </section>;
}
