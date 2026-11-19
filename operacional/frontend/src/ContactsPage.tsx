import {useCallback,useEffect,useMemo,useState} from "react";
import type {MyProfile} from "./api";
import {request} from "./api";
import {labelStore} from "./catalog";
import {ConfirmDialog} from "./ConfirmDialog";
import {
  operationsApi,type ClientDetail,type ClientFilters,type ClientInput,
  type ClientPage,type ClientRow,type ClientWarning,type ContactMetrics,
  type ContactRow,type FollowupPage,type ImportPreview,type TeamMember,
} from "./operationsApi";

type Props={token:string;profile:MyProfile};
const initialMonth=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");};
const today=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
const outcomeName=(value:string)=>({
  apresentacao:"Apresentação + WhatsApp",sem_resposta:"Não atendeu",
  whatsapp:"Contato via WhatsApp",outro:"Contato realizado"
}[value as "apresentacao"|"sem_resposta"|"whatsapp"|"outro"]??value);
const channelName=(value:string)=>({ligacao:"Ligação",whatsapp:"WhatsApp"}[value]??value);
const statusName=(value:string|null)=>({
  ativo:"Ativo",inativo:"Inativo",prospect:"Prospect"
}[value??""]??"Sem status");
const originName=(value:string)=>({
  google:"Pesquisa no Google",inativo60:"Inativos 60 dias",inativo90:"Inativos 90 dias",
  carteira:"Carteira anterior",planilha:"Planilha importada",indicacao:"Indicação",outro:"Outro"
}[value]??value);
const warningName=(code:string)=>({
  nome_duplicado:"Nome já cadastrado",telefone_duplicado:"Telefone já cadastrado",
  sem_tag:"Sem classificação (tag)",dados_incompletos:"Dados incompletos",
  data_inconsistente:"Data fora do período esperado",
  aniversario_nao_reconhecido:"Aniversário não reconhecido",
  data_contato_nao_reconhecida:"Data de contato não reconhecida",
  status_desconhecido:"Status não reconhecido",
  duplicado_no_arquivo:"Possível duplicidade dentro do arquivo",
}[code]??code);

type Tab="carteira"|"contatos"|"retornos"|"indicadores"|"importar"|"admin";

type PendingWarnings={warnings:ClientWarning[];proceed:()=>void};

const emptyForm={
  name:"",phone:"",cellphone:"",city:"",contact_person:"",
  birthday_day:"",birthday_month:"",status:"",tag:"",
  last_contact_on:"",last_purchase_on:"",erp_code:"",origin:"google",notes:"",
};

export function ContactsPage({token,profile}:Props){
  const [store,setStore]=useState(profile.stores[0]??"");
  const [period,setPeriod]=useState(initialMonth);
  const [tab,setTab]=useState<Tab>("carteira");
  const [canWrite,setCanWrite]=useState(false);
  const [canAdmin,setCanAdmin]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [pending,setPending]=useState<PendingWarnings|null>(null);
  const [year,month]=period.split("-").map(Number);

  const checkAccess=useCallback(async(permission:string)=>{
    try{
      await request(token,`/api/v1/access/${store}/${permission}`);
      return true;
    }catch{return false;}
  },[token,store]);
  useEffect(()=>{
    setCanWrite(false);setCanAdmin(false);
    if(!store)return;
    void checkAccess("telemarketing.edit").then(setCanWrite);
    void checkAccess("telemarketing.admin").then(setCanAdmin);
  },[checkAccess,store]);

  async function perform(action:()=>Promise<unknown>,
                         success:string|((r:unknown)=>string)){
    setWorking(true);setError("");setMessage("");
    try{
      const result=await action();
      const text=typeof success==="function"?success(result):success;
      if(text)setMessage(text);
    }
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao salvar.");}
    finally{setWorking(false);}
  }
  function askWarnings(warnings:ClientWarning[],proceed:()=>void){
    setPending({warnings,proceed});
  }

  return <section>
    <div className="page-header"><div><div className="eyebrow">PROCESSO COMERCIAL</div>
      <h1>Televendas e ligações</h1>
      <p>Carteira comercial por loja, com histórico de contatos, retornos e indicadores.</p>
    </div></div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters">
      <label>Loja<select value={store} onChange={e=>setStore(e.target.value)}>
        {profile.stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}</select></label>
      <label>Mês de referência<input type="month" min="2020-01" max="2100-12"
        value={period} onChange={e=>setPeriod(e.target.value)}/></label>
      <span className="chip">Histórico compartilhado pela unidade</span>
    </div>
    <div className="tabs" role="tablist">
      {([["carteira","Carteira"],["contatos","Cadastro e contatos"],
         ["retornos","Retornos"],["indicadores","Indicadores"]] as [Tab,string][])
        .map(([key,label])=><button key={key} role="tab"
          className={"tab"+(tab===key?" active":"")}
          onClick={()=>setTab(key)}>{label}</button>)}
      {canAdmin&&<button role="tab" className={"tab"+(tab==="importar"?" active":"")}
        onClick={()=>setTab("importar")}>Importar planilha</button>}
      {canAdmin&&<button role="tab" className={"tab"+(tab==="admin"?" active":"")}
        onClick={()=>setTab("admin")}>Administração</button>}
    </div>
    {tab==="carteira"&&<CarteiraTab token={token} store={store} canWrite={canWrite}
      working={working} setError={setError} askWarnings={askWarnings}
      perform={perform}/>}
    {tab==="contatos"&&<ContatosTab token={token} store={store} year={year} month={month}
      period={period} canWrite={canWrite} working={working} perform={perform}
      setError={setError} askWarnings={askWarnings}/>}
    {tab==="retornos"&&<RetornosTab token={token} store={store} canWrite={canWrite}
      perform={perform} working={working}/>}
    {tab==="indicadores"&&<IndicadoresTab token={token} store={store} year={year}
      month={month} setError={setError}/>}
    {tab==="importar"&&canAdmin&&<ImportarTab token={token} store={store}
      perform={perform} working={working} askWarnings={askWarnings}/>}
    {tab==="admin"&&canAdmin&&<AdminTab token={token} store={store}
      perform={perform} working={working}/>}
    {pending&&<ConfirmDialog title="Revisar antes de salvar"
      confirmLabel="Salvar mesmo assim" cancelLabel="Voltar e revisar"
      danger={false} busy={working}
      onConfirm={()=>{const run=pending.proceed;setPending(null);run();}}
      onCancel={()=>setPending(null)}>
      <ul style={{textAlign:"left",fontSize:12,color:"#795b30"}}>
        {pending.warnings.map((w,index)=><li key={index}><strong>{warningName(w.code)}:</strong> {w.message}</li>)}
      </ul>
      <p className="small-note">As confirmações ficam registradas na auditoria.</p>
    </ConfirmDialog>}
  </section>;
}

/* ---------------- Carteira ---------------- */

function CarteiraTab({token,store,canWrite,working,setError,askWarnings,perform}:{
  token:string;store:string;canWrite:boolean;working:boolean;
  setError:(v:string)=>void;
  askWarnings:(w:ClientWarning[],proceed:()=>void)=>void;
  perform:(a:()=>Promise<unknown>,s:string|((r:unknown)=>string))=>Promise<void>;
}){
  const [filters,setFilters]=useState({q:"",city:"",status:"",tag:"",phone:"",inactive:""});
  const [options,setOptions]=useState<ClientFilters>({cities:[],statuses:[],tags:[]});
  const [page,setPage]=useState(1);
  const [data,setData]=useState<ClientPage|null>(null);
  const [loading,setLoading]=useState(false);
  const [detail,setDetail]=useState<ClientDetail|null>(null);

  const load=useCallback(async(pageNumber:number)=>{
    if(!store)return;
    setLoading(true);setError("");
    try{
      const [rows,opts]=await Promise.all([
        operationsApi.clients(token,store,{...filters,page:pageNumber,page_size:50}),
        operationsApi.clientFilters(token,store),
      ]);
      setData(rows);setOptions(opts);setPage(pageNumber);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível carregar a carteira.");}
    finally{setLoading(false);}
  },[token,store,filters,setError]);
  useEffect(()=>{void load(1);},[store]);
  // Recarrega filtros do servidor apenas por acao do usuario; busca textual com atraso.
  useEffect(()=>{
    const timer=setTimeout(()=>void load(1),400);
    return ()=>clearTimeout(timer);
  },[filters.q,filters.phone]);

  const pages=data?Math.max(1,Math.ceil(data.total/data.page_size)):1;
  async function openDetail(id:string){
    try{setDetail(await operationsApi.clientDetail(token,store,id));}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao abrir a ficha.");}
  }
  return <>
    <div className="routine-filters">
      <label>Buscar<input value={filters.q} placeholder="Empresa ou pessoa"
        onChange={e=>setFilters(f=>({...f,q:e.target.value}))}/></label>
      <label>Telefone/celular<input value={filters.phone} placeholder="Somente números"
        onChange={e=>setFilters(f=>({...f,phone:e.target.value}))}/></label>
      <label>Cidade<select value={filters.city}
        onChange={e=>setFilters(f=>({...f,city:e.target.value}))}>
        <option value="">Todas</option>
        {options.cities.map(city=><option key={city} value={city}>{city}</option>)}</select></label>
      <label>Status<select value={filters.status}
        onChange={e=>setFilters(f=>({...f,status:e.target.value}))}>
        <option value="">Todos</option>
        {options.statuses.map(s=><option key={s} value={s}>{statusName(s)}</option>)}</select></label>
      <label>Tag<select value={filters.tag}
        onChange={e=>setFilters(f=>({...f,tag:e.target.value}))}>
        <option value="">Todas</option>
        {options.tags.map(tag=><option key={tag} value={tag}>{tag}</option>)}</select></label>
      <label>Inatividade<select value={filters.inactive}
        onChange={e=>setFilters(f=>({...f,inactive:e.target.value}))}>
        <option value="">Todos</option>
        <option value="sim">Inativos por compras</option>
        <option value="nao">Dentro do prazo</option></select></label>
      <button className="btn-secondary" onClick={()=>void load(1)}>Filtrar</button>
      <button className="btn-secondary" disabled={working}
        onClick={()=>void perform(()=>operationsApi.exportClients(
          token,store,"csv",filters),"Carteira exportada em CSV.")}>
        Exportar CSV</button>
      <button className="btn-secondary" disabled={working}
        onClick={()=>void perform(()=>operationsApi.exportClients(
          token,store,"xlsx",filters),"Carteira exportada em Excel.")}>
        Exportar Excel</button>
    </div>
    <article className="panel routine-form-panel">
      <div className="panel-head"><div><h2>Carteira da loja</h2>
        <p>{data?`${data.total} cliente(s) — página ${page} de ${pages}`:"Carregando…"}</p></div></div>
      {loading&&<p role="status">Consultando carteira…</p>}
      {!loading&&data&&<>
        <div className="table-wrap"><table><thead><tr>
          <th>Empresa</th><th>Cidade</th><th>Telefone</th><th>Celular</th>
          <th>Contato</th><th>Status</th><th>Tag</th><th>Últ. contato</th>
          <th>Últ. compra</th></tr></thead>
          <tbody>{data.items.map(c=><tr key={c.id}
            onClick={()=>void openDetail(c.id)}
            style={{cursor:"pointer"}}>
            <td>{c.name}</td><td>{c.city??"—"}</td><td>{c.phone??"—"}</td>
            <td>{c.cellphone??"—"}</td><td>{c.contact_person??"—"}</td>
            <td><span className={"pill "+(c.status==="ativo"?"pill-green":"pill-grey")}>
              {statusName(c.status)}</span>
              {c.inactive_by_purchases&&<span className="pill pill-grey"
                style={{marginLeft:4}}>Inativo p/ compras</span>}</td>
            <td>{c.tag??"—"}</td><td>{c.last_contact_on??"—"}</td>
            <td>{c.last_purchase_on??"Sem dados"}</td></tr>)}</tbody></table></div>
        {data.items.length===0&&<p className="empty">Nenhum cliente encontrado com estes filtros.</p>}
        <div className="paging">
          <button className="btn-secondary" disabled={page<=1}
            onClick={()=>void load(page-1)}>Anterior</button>
          <span>{data.total} registros</span>
          <button className="btn-secondary" disabled={page>=pages}
            onClick={()=>void load(page+1)}>Próxima</button>
        </div>
      </>}
    </article>
    {detail&&<ClientFicha token={token} store={store} detail={detail}
      canWrite={canWrite} working={working} options={options}
      askWarnings={askWarnings}
      onSaved={async()=>{
        setDetail(await operationsApi.clientDetail(token,store,detail.id));
        await load(page);
      }}
      onMoreHistory={async()=>{
        const next=detail.history.page+1;
        const more=await operationsApi.clientDetail(token,store,detail.id,next);
        setDetail(prev=>prev?{...prev,history:{...more.history,
          items:[...prev.history.items,...more.history.items]}}:prev);
      }}
      onClose={()=>setDetail(null)} perform={perform}/>}
  </>;
}

/* ---------------- Ficha do cliente ---------------- */

function ClientFicha({token,store,detail,canWrite,working,options,askWarnings,onSaved,onMoreHistory,onClose,perform}:{
  token:string;store:string;detail:ClientDetail;canWrite:boolean;working:boolean;
  options:ClientFilters;
  askWarnings:(w:ClientWarning[],proceed:()=>void)=>void;
  onSaved:()=>Promise<void>;onMoreHistory:()=>Promise<void>;onClose:()=>void;
  perform:(a:()=>Promise<unknown>,s:string|((r:unknown)=>string))=>Promise<void>;
}){
  const [editing,setEditing]=useState(false);
  const [form,setForm]=useState({...emptyForm});
  useEffect(()=>{
    setForm({
      name:detail.name,phone:detail.phone??"",cellphone:detail.cellphone??"",
      city:detail.city??"",contact_person:detail.contact_person??"",
      birthday_day:detail.birthday_day?String(detail.birthday_day):"",
      birthday_month:detail.birthday_month?String(detail.birthday_month):"",
      status:detail.status??"",tag:detail.tag??"",
      last_contact_on:detail.last_contact_on??"",
      last_purchase_on:detail.last_purchase_on??"",
      erp_code:detail.erp_code??"",origin:detail.origin,notes:detail.notes??"",
    });
  },[detail]);
  const field=(key:keyof typeof form)=>({
    value:form[key],
    onChange:(e:{target:{value:string}})=>setForm(f=>({...f,[key]:e.target.value})),
  });
  const payload=():Partial<ClientInput>&{expected_revision:number}=>({
    expected_revision:detail.revision,
    name:form.name,phone:form.phone||null,cellphone:form.cellphone||null,
    city:form.city||null,contact_person:form.contact_person||null,
    birthday_day:form.birthday_day?Number(form.birthday_day):null,
    birthday_month:form.birthday_month?Number(form.birthday_month):null,
    status:form.status||null,tag:form.tag||null,
    last_contact_on:form.last_contact_on||null,
    last_purchase_on:form.last_purchase_on||null,
    erp_code:form.erp_code||null,origin:form.origin,notes:form.notes||null,
  });
  async function save(confirm:boolean){
    const result=await operationsApi.updateClient(token,store,detail.id,
      {...payload(),confirm});
    if(result.result==="review"){
      askWarnings(result.warnings,
        ()=>void perform(()=>save(true),"Cadastro atualizado."));
      return false;
    }
    setEditing(false);
    await onSaved();
    return true;
  }
  return <div className="modal-backdrop" role="dialog" aria-modal="true">
    <div className="modal-card" style={{maxWidth:900,textAlign:"left"}}>
      <h3>{detail.name}</h3>
      {!editing&&<>
        <div className="routine-kpis">
          <div className="panel"><span>Status</span><strong>{statusName(detail.status)}</strong>
            <small>{detail.inactive_by_purchases===null?"Sem compras confiáveis":
              detail.inactive_by_purchases?`Inativo há ${detail.days_since_purchase} dias`:"Dentro do prazo"}</small></div>
          <div className="panel"><span>Tag</span><strong>{detail.tag??"—"}</strong>
            <small>Classificação comercial</small></div>
          <div className="panel"><span>Último contato</span><strong>{detail.last_contact_on??"—"}</strong>
            <small>Registrado na carteira</small></div>
        </div>
        <div className="table-wrap"><table><tbody>
          <tr><th>Cidade</th><td>{detail.city??"—"}</td>
            <th>Aniversário</th><td>{detail.birthday??"—"}</td></tr>
          <tr><th>Telefone</th><td>{detail.phone??"—"}</td>
            <th>Celular</th><td>{detail.cellphone??"—"}</td></tr>
          <tr><th>Pessoa de contato</th><td>{detail.contact_person??"—"}</td>
            <th>Cadastro ERP</th><td>{detail.erp_code??"—"}</td></tr>
          <tr><th>Origem</th><td>{originName(detail.origin)}</td>
            <th>Última compra</th><td>{detail.last_purchase_on??"Sem dados"}</td></tr>
          <tr><th>Observações</th><td colSpan={3} style={{whiteSpace:"pre-wrap"}}>
            {detail.notes||"—"}</td></tr>
        </tbody></table></div>
        {detail.pending_followups.length>0&&<>
          <h3>Retornos previstos</h3>
          <div className="table-wrap"><table><thead><tr><th>Data</th><th>Responsável</th>
            <th>Obs.</th></tr></thead><tbody>
            {detail.pending_followups.map(f=><tr key={f.id}>
              <td>{f.next_on}</td><td>{f.seller}</td><td>{f.note||"—"}</td></tr>)}
          </tbody></table></div></>}
        <h3>Histórico de atendimentos</h3>
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Canal</th>
          <th>Responsável</th><th>Resultado</th><th>Retorno</th><th>Obs.</th></tr></thead>
          <tbody>{detail.history.items.map(h=><tr key={h.id}>
            <td>{h.date}</td><td>{channelName(h.channel)}</td><td>{h.seller}</td>
            <td>{outcomeName(h.outcome)}</td>
            <td>{h.next_on?h.next_on+(h.followup_done_at?" (realizado)":""):"—"}</td>
            <td>{h.note||"—"}</td></tr>)}</tbody></table></div>
        {detail.history.items.length===0&&<p className="empty">Nenhum contato registrado.</p>}
        {detail.history.items.length<detail.history.total&&
          <button className="btn-secondary" disabled={working}
            onClick={onMoreHistory}>
            Carregar mais ({detail.history.total-detail.history.items.length} restantes)
          </button>}
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Fechar</button>
          {canWrite&&<button className="btn-primary" onClick={()=>setEditing(true)}>
            Editar cadastro</button>}
        </div>
      </>}
      {editing&&<>
        <div className="routine-form-grid">
          <label className="routine-wide">Empresa<input maxLength={100} {...field("name")}/></label>
          <label>Cidade<input maxLength={60} {...field("city")}/></label>
          <label>Pessoa de contato<input maxLength={100} {...field("contact_person")}/></label>
          <label>Telefone<input maxLength={40} {...field("phone")}/></label>
          <label>Celular / WhatsApp<input maxLength={40} {...field("cellphone")}/></label>
          <label>Dia aniversário<input type="number" min={1} max={31} {...field("birthday_day")}/></label>
          <label>Mês aniversário<input type="number" min={1} max={12} {...field("birthday_month")}/></label>
          <label>Status comercial<select {...field("status")}>
            <option value="">Sem status</option>
            <option value="ativo">Ativo</option>
            <option value="inativo">Inativo</option>
            <option value="prospect">Prospect</option></select></label>
          <label>Tag<input maxLength={60} list="tag-options" {...field("tag")}/>
            <datalist id="tag-options">{options.tags.map(t=><option key={t} value={t}/>)}</datalist></label>
          <label>Último contato<input type="date" {...field("last_contact_on")}/></label>
          <label>Última compra<input type="date" {...field("last_purchase_on")}/></label>
          <label>Cadastro ERP<input maxLength={50} {...field("erp_code")}/></label>
          <label>Origem<select {...field("origin")}>
            <option value="google">Pesquisa no Google</option>
            <option value="inativo60">Lista de inativos 60 dias</option>
            <option value="inativo90">Lista de inativos 90 dias</option>
            <option value="carteira">Carteira anterior</option>
            <option value="planilha">Planilha importada</option>
            <option value="indicacao">Indicação</option>
            <option value="outro">Outro</option></select></label>
          <label className="routine-wide">Observações gerais
            <textarea maxLength={2000} rows={3} {...field("notes")}/></label>
        </div>
        <div className="modal-actions">
          <button className="btn-secondary" disabled={working}
            onClick={()=>setEditing(false)}>Cancelar</button>
          <button className="btn-primary" disabled={working||!form.name.trim()}
            onClick={()=>void perform(()=>save(false),
              saved=>saved?"Cadastro atualizado.":"")}>
            Salvar alterações</button>
        </div>
      </>}
    </div>
  </div>;
}

/* ---------------- Cadastro e contatos ---------------- */

function ContatosTab({token,store,year,month,period,canWrite,working,perform,setError,askWarnings}:{
  token:string;store:string;year:number;month:number;period:string;
  canWrite:boolean;working:boolean;
  perform:(a:()=>Promise<unknown>,s:string|((r:unknown)=>string))=>Promise<void>;
  setError:(v:string)=>void;
  askWarnings:(w:ClientWarning[],proceed:()=>void)=>void;
}){
  const [form,setForm]=useState({...emptyForm});
  const [options,setOptions]=useState<ClientFilters>({cities:[],statuses:[],tags:[]});
  const [sellers,setSellers]=useState<TeamMember[]>([]);
  const [calls,setCalls]=useState<ContactRow[]>([]);
  const [callsTotal,setCallsTotal]=useState(0);
  const [clientQuery,setClientQuery]=useState("");
  const [clientOptions,setClientOptions]=useState<ClientRow[]>([]);
  const [clientId,setClientId]=useState("");
  const [sellerId,setSellerId]=useState("");
  const [callDate,setCallDate]=useState(today);
  const [channel,setChannel]=useState("ligacao");
  const [outcome,setOutcome]=useState("apresentacao");
  const [nextOn,setNextOn]=useState("");
  const [note,setNote]=useState("");
  const [editing,setEditing]=useState<ContactRow|null>(null);
  const [loading,setLoading]=useState(false);

  const refresh=useCallback(async()=>{
    if(!store)return;
    setLoading(true);setError("");
    try{
      const [teamRows,log,opts]=await Promise.all([
        operationsApi.team(token,store),
        operationsApi.calls(token,store,year,month),
        operationsApi.clientFilters(token,store),
      ]);
      setSellers(teamRows);setCalls(log.items);
      setCallsTotal(log.total);setOptions(opts);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível carregar os contatos.");}
    finally{setLoading(false);}
  },[token,store,year,month,setError]);
  useEffect(()=>{void refresh();},[refresh]);
  useEffect(()=>{
    setSellerId(current=>sellers.some(s=>s.id===current)?current:sellers[0]?.id??"");
  },[sellers]);
  useEffect(()=>{setEditing(null);},[store,period]);
  useEffect(()=>{
    const timer=setTimeout(async()=>{
      if(!store)return;
      try{
        const result=await operationsApi.clients(token,store,{q:clientQuery,page_size:20});
        setClientOptions(result.items);
      }catch{setClientOptions([]);}
    },300);
    return ()=>clearTimeout(timer);
  },[token,store,clientQuery]);
  const selectedClient=useMemo(()=>
    clientOptions.find(c=>c.id===clientId),[clientOptions,clientId]);

  const field=(key:keyof typeof form)=>({
    value:form[key],
    onChange:(e:{target:{value:string}})=>setForm(f=>({...f,[key]:e.target.value})),
  });

  async function saveClient(confirm:boolean){
    const result=await operationsApi.addClient(token,store,{
      name:form.name,phone:form.phone||null,cellphone:form.cellphone||null,
      erp_code:form.erp_code||null,origin:form.origin,city:form.city||null,
      contact_person:form.contact_person||null,
      birthday_day:form.birthday_day?Number(form.birthday_day):null,
      birthday_month:form.birthday_month?Number(form.birthday_month):null,
      status:form.status||null,tag:form.tag||null,
      last_contact_on:form.last_contact_on||null,
      last_purchase_on:form.last_purchase_on||null,
      notes:form.notes||null,confirm,
    });
    if(result.result==="review"){
      askWarnings(result.warnings,()=>void perform(()=>saveClient(true),
        "Cliente adicionado à carteira da loja."));
      return false;
    }
    setForm({...emptyForm});
    return true;
  }

  function startCorrection(row:ContactRow){
    setEditing(row);setCallDate(row.date);setOutcome(row.outcome);
    setChannel(row.channel);setNextOn(row.next_on??"");setNote(row.note);
    setClientId(row.client_id);setSellerId(row.seller_id);
    setClientOptions(prev=>prev.some(c=>c.id===row.client_id)?prev:
      [{id:row.client_id,store_code:store,name:row.client,phone:null,cellphone:null,
        city:null,contact_person:null,birthday:null,birthday_day:null,
        birthday_month:null,status:null,tag:null,last_contact_on:null,
        erp_code:null,origin:"outro",notes:null,last_purchase_on:null,
        revision:1,inactive_by_purchases:null},...prev]);
    window.scrollTo({top:0,behavior:"smooth"});
  }
  function clearCorrection(){
    setEditing(null);setCallDate(today());setNextOn("");setNote("");
  }

  return <>
    {loading&&<p role="status">Consultando contatos…</p>}
    {canWrite&&<div className="columns routine-columns">
      <article className="panel">
        <div className="panel-head"><div><h2>Adicionar cliente à carteira</h2>
          <p>Somente o nome da empresa é obrigatório. Inconsistências viram avisos, não bloqueios.</p></div></div>
        <div className="routine-form-grid">
          <label className="routine-wide">Empresa / cliente<input maxLength={100}
            placeholder="Nome do cliente" {...field("name")}/></label>
          <label>Cidade<input maxLength={60} {...field("city")}/></label>
          <label>Pessoa de contato<input maxLength={100} {...field("contact_person")}/></label>
          <label>Telefone<input maxLength={40} {...field("phone")}/></label>
          <label>Celular / WhatsApp<input maxLength={40} {...field("cellphone")}/></label>
          <label>Dia aniversário<input type="number" min={1} max={31} {...field("birthday_day")}/></label>
          <label>Mês aniversário<input type="number" min={1} max={12} {...field("birthday_month")}/></label>
          <label>Status comercial<select {...field("status")}>
            <option value="">Sem status</option>
            <option value="ativo">Ativo</option>
            <option value="inativo">Inativo</option>
            <option value="prospect">Prospect</option></select></label>
          <label>Tag<input maxLength={60} list="new-tag-options" {...field("tag")}/>
            <datalist id="new-tag-options">{options.tags.map(t=><option key={t} value={t}/>)}</datalist></label>
          <label>Origem<select {...field("origin")}>
            <option value="google">Pesquisa no Google</option>
            <option value="inativo60">Lista de inativos 60 dias</option>
            <option value="inativo90">Lista de inativos 90 dias</option>
            <option value="carteira">Carteira anterior</option>
            <option value="indicacao">Indicação</option>
            <option value="outro">Outro</option></select></label>
          <label>Último contato<input type="date" {...field("last_contact_on")}/></label>
          <label>Última compra conhecida<input type="date" {...field("last_purchase_on")}/></label>
          <label>Cadastro ERP (opcional)<input maxLength={50} {...field("erp_code")}/></label>
          <label className="routine-wide">Observações gerais
            <textarea maxLength={2000} rows={3} {...field("notes")}/></label>
        </div>
        <button className="btn-primary" disabled={working||!form.name.trim()}
          onClick={()=>void perform(()=>saveClient(false),
            saved=>saved?"Cliente adicionado à carteira da loja.":"")}>
          + Adicionar cliente</button>
      </article>
      <article className="panel">
        <div className="panel-head"><div><h2>{editing?"Corrigir contato":"Registrar contato"}</h2>
          <p>Associe o atendimento ao responsável que realmente o realizou.</p></div></div>
        <div className="routine-form-grid">
          <label className="routine-wide">Cliente
            <input placeholder="Buscar cliente…" value={clientQuery}
              disabled={!!editing} onChange={e=>setClientQuery(e.target.value)}/>
            <select value={clientId} disabled={!!editing}
              onChange={e=>setClientId(e.target.value)}>
              <option value="">Selecione…</option>
              {clientOptions.map(c=><option value={c.id} key={c.id}>
                {c.name}{c.city?` — ${c.city}`:""}</option>)}
            </select></label>
          <label>Responsável<select value={sellerId} disabled={!!editing}
            onChange={e=>setSellerId(e.target.value)}>
            {sellers.map(s=><option value={s.id} key={s.id}>{s.name}</option>)}</select></label>
          <label>Data<input type="date" value={callDate}
            onChange={e=>setCallDate(e.target.value)}/></label>
          <label>Canal<select value={channel} onChange={e=>setChannel(e.target.value)}>
            <option value="ligacao">Ligação telefônica</option>
            <option value="whatsapp">WhatsApp</option></select></label>
          <label className="routine-wide">Resultado<select value={outcome}
            onChange={e=>setOutcome(e.target.value)}>
            <option value="apresentacao">Apresentou a UMA + WhatsApp</option>
            <option value="sem_resposta">Tentativa sem atendimento</option>
            <option value="whatsapp">Contato via WhatsApp</option>
            <option value="outro">Contato realizado</option>
          </select></label>
          <label>Retorno agendado<input type="date" value={nextOn}
            onChange={e=>setNextOn(e.target.value)}/></label>
          <label className="routine-wide">Observação breve<input maxLength={240}
            value={note} onChange={e=>setNote(e.target.value)}/></label>
        </div>
        {sellers.length===0&&<div className="notice notice-amber">
          É necessário ter um vendedor ativo vinculado a esta loja para registrar contatos.</div>}
        <div className="btn-row">
          <button className="btn-primary" disabled={working||!clientId||!sellerId||!callDate}
            onClick={()=>void perform(async()=>{
              if(editing)await operationsApi.correctCall(token,store,editing.id,{
                date:callDate,channel,outcome,next_on:nextOn||null,note,
                expected_revision:editing.revision});
              else await operationsApi.addCall(token,store,{
                client_id:clientId,seller_id:sellerId,date:callDate,channel,
                outcome,next_on:nextOn||null,note});
              clearCorrection();await refresh();
            },editing?"Correção auditada.":"Contato registrado.")}>{
              editing?"Salvar correção":"Registrar contato"
            }</button>
          {editing&&<button className="btn-secondary" onClick={clearCorrection}>
            Cancelar edição</button>}
        </div>
        {selectedClient&&<p className="small-note">
          {selectedClient.name}{selectedClient.city?` — ${selectedClient.city}`:""}</p>}
      </article>
    </div>}
    <article className="panel routine-form-panel">
      <div className="panel-head"><div><h2>Histórico de contatos do mês</h2>
        <p>Registros de desfecho, canal e retorno agendado.</p></div></div>
      <div className="table-wrap"><table><thead><tr><th>Data</th><th>Cliente</th>
        <th>Responsável</th><th>Canal</th><th>Resultado</th><th>Retorno</th>
        <th>Obs.</th>{canWrite&&<th>Ação</th>}</tr></thead>
        <tbody>{calls.map(c=><tr key={c.id}><td>{c.date}</td><td>{c.client}</td>
          <td>{c.seller}</td><td>{channelName(c.channel)}</td>
          <td>{outcomeName(c.outcome)}</td>
          <td>{c.next_on?c.next_on+(c.followup_done_at?" (realizado)":""):"—"}</td>
          <td>{c.note||"—"}</td>{canWrite&&<td><button className="btn-secondary"
            onClick={()=>startCorrection(c)}>Corrigir</button></td>}</tr>)}</tbody>
      </table></div>
      {calls.length<callsTotal&&<button className="btn-secondary" disabled={working}
        onClick={()=>void perform(async()=>{
          const next=Math.floor(calls.length/100)+1;
          const more=await operationsApi.calls(token,store,year,month,next);
          setCalls(prev=>[...prev,...more.items]);
        },"")}>
        Carregar mais ({callsTotal-calls.length} restantes)</button>}
      {calls.length===0&&<p className="empty">Nenhum contato registrado no mês.</p>}
      <p className="small-note">Alterações anteriores são registradas na auditoria.
        O sistema ainda não importa automaticamente carteiras ou vendas.</p>
    </article>
  </>;
}

/* ---------------- Retornos ---------------- */

function RetornosTab({token,store,canWrite,perform,working}:{
  token:string;store:string;canWrite:boolean;working:boolean;
  perform:(a:()=>Promise<unknown>,s:string|((r:unknown)=>string))=>Promise<void>;
}){
  const [state,setState]=useState("abertos");
  const [data,setData]=useState<FollowupPage|null>(null);
  const [page,setPage]=useState(1);
  const [error,setError]=useState("");
  const [rescheduling,setRescheduling]=useState<ContactRow|null>(null);
  const [newDate,setNewDate]=useState("");

  const load=useCallback(async(pageNumber:number)=>{
    setError("");
    try{
      setData(await operationsApi.followups(token,store,state,pageNumber,100));
      setPage(pageNumber);
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao consultar retornos.");}
  },[token,store,state]);
  useEffect(()=>{void load(1);},[load]);

  const pages=data?Math.max(1,Math.ceil(data.total/data.page_size)):1;
  return <article className="panel routine-form-panel">
    <div className="panel-head"><div><h2>Agenda de retornos</h2>
      <p>Consulta o histórico completo, sem depender do mês selecionado.</p></div>
      <label>Exibir<select value={state} onChange={e=>setState(e.target.value)}>
        <option value="abertos">Pendentes</option>
        <option value="atrasados">Atrasados</option>
        <option value="realizados">Realizados</option>
        <option value="todos">Todos</option></select></label></div>
    {error&&<div className="notice notice-error">{error}</div>}
    {data&&<>
      <div className="table-wrap"><table><thead><tr><th>Retorno</th><th>Cliente</th>
        <th>Responsável</th><th>Contato original</th><th>Situação</th><th>Obs.</th>
        {canWrite&&<th>Ações</th>}</tr></thead>
        <tbody>{data.items.map(item=><tr key={item.id}>
          <td>{item.next_on}</td><td>{item.client}</td><td>{item.seller}</td>
          <td>{item.date} — {outcomeName(item.outcome)}</td>
          <td>{item.followup_done_at?"Realizado":item.overdue?"Atrasado":"Pendente"}</td>
          <td>{item.note||"—"}</td>
          {canWrite&&<td>
            {!item.followup_done_at&&<>
              <button className="btn-secondary"
                onClick={()=>void perform(async()=>{
                  await operationsApi.followupDone(token,store,item.id,item.revision);
                  await load(page);
                },"Retorno marcado como realizado.")}>Concluir</button>{" "}
              <button className="btn-ghost" onClick={()=>{
                setRescheduling(item);setNewDate(item.next_on??"");
              }}>Reagendar</button>
            </>}
          </td>}
        </tr>)}</tbody></table></div>
      {data.items.length===0&&<p className="empty">Nenhum retorno nesta visão.</p>}
      <div className="paging">
        <button className="btn-secondary" disabled={page<=1}
          onClick={()=>void load(page-1)}>Anterior</button>
        <span>{data.total} registros</span>
        <button className="btn-secondary" disabled={page>=pages}
          onClick={()=>void load(page+1)}>Próxima</button>
      </div>
    </>}
    {rescheduling&&<ConfirmDialog title={`Reagendar retorno — ${rescheduling.client}`}
      confirmLabel="Reagendar" cancelLabel="Cancelar" danger={false} busy={working}
      onCancel={()=>setRescheduling(null)}
      onConfirm={()=>void perform(async()=>{
        await operationsApi.followupReschedule(token,store,rescheduling.id,
          newDate,rescheduling.revision);
        setRescheduling(null);await load(page);
      },"Retorno reagendado.")}>
      <label className="form-row">Nova data
        <input type="date" value={newDate} onChange={e=>setNewDate(e.target.value)}/>
      </label>
    </ConfirmDialog>}
  </article>;
}

/* ---------------- Indicadores ---------------- */

function IndicadoresTab({token,store,year,month,setError}:{
  token:string;store:string;year:number;month:number;setError:(v:string)=>void;
}){
  const [metrics,setMetrics]=useState<ContactMetrics|null>(null);
  useEffect(()=>{
    if(!store)return;
    operationsApi.contactMetrics(token,store,year,month)
      .then(setMetrics)
      .catch(cause=>setError(cause instanceof Error?cause.message:"Falha nos indicadores."));
  },[token,store,year,month,setError]);
  if(!metrics)return <p role="status">Calculando indicadores…</p>;
  return <>
    <div className="routine-kpis">
      <div className="panel"><span>Clientes na carteira</span>
        <strong>{metrics.clients_total}</strong><small>Unidade selecionada</small></div>
      <div className="panel"><span>Contatos no período</span>
        <strong>{metrics.contacts_in_period}</strong>
        <small>{metrics.clients_contacted} clientes contatados</small></div>
      <div className="panel"><span>Retornos pendentes</span>
        <strong>{metrics.followups_pending}</strong>
        <small>{metrics.followups_overdue} atrasados</small></div>
      <div className="panel"><span>Inativos por compras</span>
        <strong>{metrics.inactive_by_purchases}</strong>
        <small>Prazo de {metrics.inactivity_days} dias, com última compra confiável</small></div>
    </div>
    <div className="columns routine-columns">
      <article className="panel"><h2>Por status comercial</h2>
        <div className="table-wrap"><table><tbody>
          {Object.entries(metrics.by_status).map(([key,total])=>
            <tr key={key}><td>{key==="sem_status"?"Sem status":statusName(key)}</td>
              <td>{total}</td></tr>)}
        </tbody></table></div></article>
      <article className="panel"><h2>Por tag</h2>
        <div className="table-wrap"><table><tbody>
          {metrics.by_tag.map(row=><tr key={row.tag}>
            <td>{row.tag}</td><td>{row.total}</td></tr>)}
        </tbody></table></div></article>
    </div>
    <article className="panel"><h2>Por cidade</h2>
      <div className="table-wrap"><table><thead><tr><th>Cidade</th><th>Clientes</th></tr></thead>
        <tbody>{metrics.by_city.map(row=><tr key={row.city}>
          <td>{row.city}</td><td>{row.total}</td></tr>)}</tbody></table></div></article>
    <p className="small-note">Conversão em vendas e reativação por compra não são
      calculadas enquanto a integração de vendas do ERP não estiver disponível.</p>
  </>;
}

/* ---------------- Importação ---------------- */

function ImportarTab({token,store,perform,working,askWarnings}:{
  token:string;store:string;working:boolean;
  perform:(a:()=>Promise<unknown>,s:string|((r:unknown)=>string))=>Promise<void>;
  askWarnings:(w:ClientWarning[],proceed:()=>void)=>void;
}){
  const [file,setFile]=useState<File|null>(null);
  const [defaultCity,setDefaultCity]=useState("");
  const [preview,setPreview]=useState<ImportPreview|null>(null);
  const [decisions,setDecisions]=useState<Record<string,{action:"import"|"update"|"skip";client_id?:string;city?:string}>>({});
  const [error,setError]=useState("");
  const [report,setReport]=useState<{imported:number;updated:number;skipped:number;warnings:number}|null>(null);

  async function sendPreview(){
    if(!file)return;
    setError("");setPreview(null);setReport(null);setDecisions({});
    try{
      setPreview(await operationsApi.importPreview(token,store,file,defaultCity||undefined));
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível ler o arquivo.");}
  }
  function decisionFor(row:ImportPreview["rows"][number]){
    return decisions[String(row.index)]??{action:row.suggested};
  }
  function setDecision(row:ImportPreview["rows"][number],
      patch:Partial<{action:"import"|"update"|"skip";client_id:string;city:string}>){
    setDecisions(prev=>({...prev,[String(row.index)]:
      Object.assign({action:row.suggested},prev[String(row.index)],patch)}));
  }
  async function commit(confirm:boolean){
    if(!preview)return;
    const effective={...decisions};
    for(const row of preview.rows){
      const current=effective[String(row.index)]??{action:row.suggested};
      if(current.action==="update"&&!current.client_id&&row.matches.length===1)
        effective[String(row.index)]={...current,client_id:row.matches[0].id};
    }
    const result=await operationsApi.importCommit(token,store,preview.session_id,{
      decisions:effective,confirm});
    if(result.result==="review"){
      askWarnings([{code:"dados_incompletos",message:result.message}],
        ()=>void perform(()=>commit(true),"Importação concluída."));
      return false;
    }
    setReport(result.report);
    setPreview(null);
    return true;
  }
  return <>
    <article className="panel">
      <div className="panel-head"><div><h2>Importar carteira de clientes</h2>
        <p>Arquivos .xlsx com uma aba por cidade ou .csv no formato da planilha de televendas.</p></div></div>
      <div className="routine-filters">
        <label>Arquivo<input type="file" accept=".xlsx,.csv"
          onChange={e=>setFile(e.target.files?.[0]??null)}/></label>
        <label>Cidade padrão (CSV sem identificação)<input maxLength={60}
          value={defaultCity} onChange={e=>setDefaultCity(e.target.value)}/></label>
        <button className="btn-primary" disabled={!file||working}
          onClick={()=>void sendPreview()}>Ler arquivo</button>
      </div>
      {error&&<div className="notice notice-error">{error}</div>}
      {report&&<div className="notice notice-success">
        Importação concluída: {report.imported} importados, {report.updated} atualizados,
        {" "}{report.skipped} ignorados, {report.warnings} registros com avisos.
      </div>}
      {!preview&&!report&&<p className="small-note">A prévia mostra os registros por cidade,
        possíveis duplicidades e avisos antes de gravar qualquer dado.</p>}
    </article>
    {preview&&<article className="panel">
      <div className="panel-head"><div><h2>Prévia — {preview.filename}</h2>
        <p>{preview.rows_total} registros em {preview.cities.length} cidades;
          {" "}{preview.summary.possible_duplicates} possíveis duplicidades;
          {" "}{preview.summary.with_warnings} com avisos.</p></div></div>
      <div className="table-wrap"><table><thead><tr><th>Cidade</th><th>Clientes</th></tr></thead>
        <tbody>{preview.cities.map(c=><tr key={c.city}>
          <td>{c.city}</td><td>{c.total}</td></tr>)}</tbody></table></div>
      <div className="table-wrap" style={{maxHeight:440,overflow:"auto"}}><table>
        <thead><tr><th>#</th><th>Cidade</th><th>Empresa</th><th>Telefone</th>
          <th>Status</th><th>Tag</th><th>Avisos</th><th>Duplicidade</th>
          <th>Decisão</th></tr></thead>
        <tbody>{preview.rows.map(row=>{
          const decision=decisionFor(row);
          return <tr key={row.index}>
            <td>{row.index}</td>
            <td><input style={{width:110}} value={decision.city??row.city??""}
              onChange={e=>setDecision(row,{city:e.target.value||undefined})}/></td>
            <td>{row.name}</td><td>{row.phone??row.cellphone??"—"}</td>
            <td>{row.status_raw??"—"}</td><td>{row.tag??"—"}</td>
            <td>{row.warnings.map(w=>warningName(w)).join("; ")||"—"}</td>
            <td>{row.matches.map(m=>`${m.name} (${m.kinds.join("+")})`).join("; ")||"—"}</td>
            <td>
              <select value={decision.action}
                onChange={e=>setDecision(row,{action:e.target.value as "import"|"update"|"skip"})}>
                <option value="import">Importar</option>
                <option value="update">Atualizar existente</option>
                <option value="skip">Ignorar</option>
              </select>
              {decision.action==="update"&&
                <select value={decision.client_id??""}
                  onChange={e=>setDecision(row,{client_id:e.target.value||undefined})}>
                  <option value="">Escolher cadastro…</option>
                  {row.matches.map(m=><option key={m.id} value={m.id}>
                    {m.name}{m.city?` — ${m.city}`:""}</option>)}
                </select>}
            </td>
          </tr>;
        })}</tbody></table></div>
      <div className="btn-row" style={{marginTop:16}}>
        <button className="btn-primary" disabled={working}
          onClick={()=>void perform(()=>commit(false),
            done=>done?"Importação concluída.":"")}>
          Confirmar importação</button>
        <button className="btn-secondary" disabled={working}
          onClick={()=>void perform(async()=>{
            await operationsApi.discardImport(token,store,preview.session_id);
            setPreview(null);setDecisions({});
          },"Prévia descartada.")}>Descartar prévia</button>
      </div>
      <p className="small-note">A data de contato da planilha não é tratada como
        última compra e não gera registros de ligação.</p>
    </article>}
  </>;
}

/* ---------------- Administração ---------------- */

function AdminTab({token,store,perform,working}:{
  token:string;store:string;working:boolean;
  perform:(a:()=>Promise<unknown>,s:string|((r:unknown)=>string))=>Promise<void>;
}){
  const [days,setDays]=useState<number|null>(null);
  const [tags,setTags]=useState<string[]>([]);
  useEffect(()=>{
    if(!store)return;
    operationsApi.contactSettings(token,store)
      .then(s=>setDays(s.inactivity_days)).catch(()=>setDays(null));
    operationsApi.clientFilters(token,store)
      .then(f=>setTags(f.tags)).catch(()=>setTags([]));
  },[token,store]);
  return <article className="panel" style={{maxWidth:520}}>
    <div className="panel-head"><div><h2>Parâmetros do módulo</h2>
      <p>Configurações da carteira de televendas.</p></div></div>
    <div className="form-row">
      <label>Prazo de inatividade por compras (dias)</label>
      <input type="number" min={1} max={365} value={days??""}
        onChange={e=>setDays(Number(e.target.value))}/>
      <small>Clientes com última compra acima deste prazo são considerados
        inativos pelo critério de compras. O status comercial informado
        manualmente não é alterado.</small>
    </div>
    <button className="btn-primary" disabled={working||!days||days<1||days>365}
      onClick={()=>void perform(async()=>{
        await operationsApi.saveSettings(token,store,days!);
      },"Prazo de inatividade atualizado.")}>Salvar prazo</button>
    <h3>Tags cadastradas</h3>
    <p className="small-note">Tags podem ser escolhidas no cadastro ou criadas
      automaticamente ao salvar um cliente com uma nova classificação.</p>
    <div>{tags.map(tag=><span key={tag} className="chip"
      style={{marginRight:6}}>{tag}</span>)}
      {tags.length===0&&<span className="small-note">Nenhuma tag cadastrada.</span>}</div>
  </article>;
}
