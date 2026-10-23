import {useEffect, useRef, useState} from "react";
import type {ReactNode} from "react";
import {api, type ClosingArchive, type ClosingArchiveRef, type ClosingDraft,
  type ClosingPriority, type ClosingSnapshot, type ClosingView,
  type MyProfile} from "./api";
import {canArchive, EMPTY_CLOSING, monthText, nextMonthDue, SLIDE_MINUTES,
  SLIDE_TITLES, statusLabel, STORE_LABELS} from "./closingContent";

type Props = {token:string; profile:MyProfile};
const currency = (v:string|null) => v===null?"Sem dados":
  new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(Number(v));
const initialMonth=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");};

function Note({value,empty="Ainda não registrado"}:{value:string;empty?:string}){
  return <p className={value.trim()?"closing-note":"closing-note closing-placeholder"}>
    {value.trim()||empty}</p>;
}
function Stat({name,value,caption}:{name:string;value:string;caption?:string}){
  return <div className="closing-stat"><span>{name}</span><strong>{value}</strong>
    {caption&&<small>{caption}</small>}</div>;
}

function ClosingPresentation({
  source, onClose
}:{source:ClosingSnapshot;onClose:()=>void}){
  const [index,setIndex]=useState(0);
  const wrap=useRef<HTMLDivElement|null>(null);
  const draft=source.draft;
  const data=source.data;
  const durations=source.durations.length===7?source.durations:[...SLIDE_MINUTES];
  const [year,month]=source.period.split("-").map(Number);
  const monthName=monthText(year,month);
  const moneyMissing="Sem dados";
  const slides:ReactNode[]=[
    <div className="closing-cover">
      <div className="closing-cover-brand">UNIVERSO DAS MANGUEIRAS</div>
      <h2>Fechamento Mensal UMA</h2>
      <p>{monthName}</p>
      <p>Joinville · Tubarão · Itajaí</p>
      <Note value={draft.opening} empty="Mensagem de abertura não cadastrada"/>
    </div>,
    <div className="closing-slide-stack">
      <div className="closing-stat-grid">
        <Stat name="Faturamento consolidado" value={moneyMissing} caption="Aguardando integração com ERP"/>
        <Stat name="Meta consolidada" value={currency(data.total_target)} caption="Metas das três lojas"/>
        <Stat name="Atingimento" value={moneyMissing} caption="Sem dados para calcular"/>
        <Stat name="Vs. mês anterior" value={moneyMissing} caption="Comparação pendente"/>
        <Stat name="Vs. mesmo mês do ano anterior" value={moneyMissing} caption="Comparação pendente"/>
      </div>
      <div className="closing-unavailable">A evolução mensal será exibida quando houver histórico oficial de vendas.</div>
    </div>,
    <div className="closing-slide-stores">{data.stores.map((store)=>(
      <section className="closing-slide-store" key={store.code}>
        <h3>{store.name}</h3>
        <Stat name="Meta" value={currency(store.target)}/>
        <Stat name="Faturamento" value={moneyMissing}/>
        <Stat name="Atingimento" value={moneyMissing}/>
        <Stat name="Evolução mensal" value={moneyMissing}/>
        <strong>Comentário da gestão</strong>
        <Note value={draft.stores[store.code as keyof ClosingDraft["stores"]]||""}/>
      </section>
    ))}</div>,
    <div className="closing-slide-stack">
      <div className="closing-stat-grid">
        <Stat name="Ligações comerciais" value="Ainda não monitorado"/>
        <Stat name="Clientes ativados / reativados" value="Ainda não monitorado"/>
        <Stat name="Retornos comerciais" value="Ainda não monitorado"/>
      </div>
      <div className="closing-slide-comment"><h3>Oportunidades comerciais</h3>
        <Note value={draft.opportunities}/></div>
      <p className="closing-minor">Campanhas, categorias e ações específicas só entrarão quando houver registros oficiais.</p>
    </div>,
    <div className="closing-slide-stack">
      <div className="closing-quality">
        <div><strong>Loja</strong><strong>Avaliações Google</strong><strong>Checklists</strong><strong>Instagram</strong></div>
        {data.stores.map(store=><div key={store.code}>
          <strong>{store.name}</strong><span>Sem dados</span><span>Sem dados</span><span>Sem dados</span>
        </div>)}
      </div>
      <div className="closing-stat-grid">
        <Stat name="Status WhatsApp — UMA inteira" value="Ainda não monitorado"/>
        <Stat name="Treinamentos realizados" value="Ainda não monitorado"/>
      </div>
    </div>,
    <div className="closing-slide-stack">
      <div className="closing-conversation">
        <section><h3>O que fizemos bem?</h3><Note value={draft.wins}/></section>
        <section><h3>O que podemos melhorar?</h3><Note value={draft.improvements}/></section>
        <section><h3>Avisos e orientações</h3><Note value={draft.notices}/></section>
      </div>
      {data.stores.filter(s=>draft.notes[s.code as keyof ClosingDraft["notes"]]?.trim()).length>0 &&
        <div className="closing-note-by-store"><strong>Recados por loja</strong>
          {data.stores.map(s=>draft.notes[s.code as keyof ClosingDraft["notes"]]?.trim() ?
            <p key={s.code}><b>{s.name}:</b> {draft.notes[s.code as keyof ClosingDraft["notes"]]}</p>:null)}
        </div>}
    </div>,
    <div className="closing-slide-stack">
      <div className="closing-priorities-table">
        <div className="closing-priorities-head">
          <strong>Ação</strong><strong>Responsável</strong><strong>Loja</strong>
          <strong>Prazo</strong><strong>Situação</strong>
        </div>
        {draft.priorities.length===0 ? <p>Nenhuma prioridade cadastrada.</p> :
          draft.priorities.map(p=><div className="closing-priority-row" key={p.id}>
            <span>{p.what}</span><span>{p.owner}</span>
            <span>{STORE_LABELS[p.scope]}</span><span>{p.due.split("-").reverse().join("/")}</span>
            <span>{statusLabel(p.status)}</span>
          </div>)}
      </div>
      <div className="closing-slide-comment">
        <h3>Pendências do fechamento anterior</h3>
        {source.previous_pending.length>0?
          <ul>{source.previous_pending.map(p=><li key={p.id}>{p.what} · {p.owner}</li>)}</ul>:
          <p>Sem pendências anteriores registradas.</p>}
      </div>
      <p className="closing-finale">Transformar resultados e aprendizados em ações para continuar evoluindo.</p>
    </div>
  ];
  const captions=[
    "Resultados, conquistas e prioridades do próximo mês.",
    "Metas, evolução comercial e comparações disponíveis.",
    "Resultados por unidade, sem ranking de vendedores.",
    "Acompanhar clientes e oportunidades de melhoria.",
    "Indicadores de rotina, sem nota geral artificial.",
    "Reconhecimento, melhorias e comunicação com as equipes.",
    "Entre três e cinco ações, com responsáveis e prazos.",
  ];

  useEffect(()=>{
    function key(event:KeyboardEvent){
      if(event.key==="Escape"){event.preventDefault();onClose();}
      if(event.key==="ArrowLeft"){event.preventDefault();setIndex(i=>Math.max(0,i-1));}
      if(event.key==="ArrowRight"){event.preventDefault();setIndex(i=>Math.min(6,i+1));}
    }
    document.addEventListener("keydown",key);
    const prior=document.body.style.overflow;
    document.body.style.overflow="hidden";
    wrap.current?.focus();
    return ()=>{document.removeEventListener("keydown",key);document.body.style.overflow=prior;};
  },[onClose]);

  return <div className="closing-overlay" ref={wrap} tabIndex={-1}
    role="dialog" aria-modal="true" aria-label="Apresentação de fechamento mensal">
    <div className="closing-presenter-bar">
      <strong>Portal UMA · {source.period}</strong>
      <span>Slide {index+1} / 7 · {durations[index]} min · Total: 20 min</span>
      <div className="closing-presenter-actions">
        <button className="btn-secondary" onClick={()=>window.print()}>Imprimir / PDF</button>
        <button className="btn-secondary" onClick={async()=>{try{await wrap.current?.requestFullscreen?.();}catch{/* optional */}}}>Tela cheia</button>
        <button className="btn-secondary" onClick={onClose} aria-label="Fechar apresentação">Fechar ✕</button>
      </div>
    </div>
    <div className="closing-slide-canvas">
      <header className="closing-slide-header">
        <div><span>0{index+1} · {SLIDE_TITLES[index].toUpperCase()} · {durations[index]} MIN</span>
          <h1>{SLIDE_TITLES[index]}</h1><p>{captions[index]}</p></div>
        <span className="closing-brand-mark">UMA</span>
      </header>
      <div className="closing-slide-body">{slides[index]}</div>
      <footer>UNIVERSO DAS MANGUEIRAS AUTOMOTIVAS · REUNIÃO MENSAL
        <span>{source.state==="partial_sales_pending"?"DADOS DE VENDAS PENDENTES":""} · {index+1} / 7</span></footer>
    </div>
    <div className="closing-presenter-bottom">
      <button className="btn-secondary" disabled={index===0} onClick={()=>setIndex(i=>i-1)}>← Anterior</button>
      <span>{index+1} de 7 · Use as setas do teclado</span>
      <button className="btn-primary" disabled={index===6} onClick={()=>setIndex(i=>i+1)}>Próximo →</button>
    </div>
  </div>;
}

function textLabel(label:string,value:string,onChange:(v:string)=>void,limit=3000){
  return <label className="closing-field"><span>{label}</span>
    <textarea rows={3} maxLength={limit} value={value}
      onChange={(event)=>onChange(event.target.value)} placeholder="Escreva o comentário da gestão…"/></label>;
}

export function ClosingPage({token,profile}:Props){
  const [period,setPeriod]=useState(initialMonth);
  const [report,setReport]=useState<ClosingView|null>(null);
  const [draft,setDraft]=useState<ClosingDraft>(structuredClone(EMPTY_CLOSING));
  const [dirty,setDirty]=useState(false);
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [archives,setArchives]=useState<ClosingArchiveRef[]>([]);
  const [showDeck,setShowDeck]=useState<ClosingSnapshot|null>(null);
  const [year,month]=period.split("-").map(Number);

  useEffect(()=>{
    if(!token || !profile.features.monthly_closing || !year || !month)return;
    let active=true;
    setLoading(true);setError("");setMessage("");setReport(null);
    void Promise.all([api.closing(token,year,month),api.closingArchives(token,year,month)])
      .then(([current,stored])=>{
        if(!active)return;
        setReport(current);setDraft(current.draft);setDirty(false);setArchives(stored);
      }).catch((cause:unknown)=>{if(active)setError(cause instanceof Error?cause.message:"Erro na consulta.");})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[token,profile.features.monthly_closing,year,month]);

  function changePeriod(value:string){
    if(dirty && !window.confirm("Existem alterações não salvas. Descartar e mudar de mês?"))return;
    setPeriod(value);
  }
  function edit(partial:Partial<ClosingDraft>){setDraft(previous=>({...previous,...partial}));setDirty(true);setMessage("");}
  function setStoreValue(which:"stores"|"notes",code:keyof ClosingDraft["stores"],value:string){
    edit({[which]:{...draft[which],[code]:value}} as Partial<ClosingDraft>);
  }
  function updatePriority(id:string,field:keyof ClosingPriority,value:string){
    edit({priorities:draft.priorities.map(p=>p.id===id?{...p,[field]:value}:p)});
  }
  function addPriority(){
    if(draft.priorities.length>=5)return;
    edit({priorities:[...draft.priorities,{
      id:crypto.randomUUID(),what:"",owner:"",scope:"all",
      due:nextMonthDue(year,month),status:"pendente"
    }]});
  }
  function removePriority(id:string){edit({priorities:draft.priorities.filter(p=>p.id!==id)});}

  async function save(){
    if(!report)return;
    setWorking(true);setError("");setMessage("");
    try{
      const fresh=await api.saveClosing(token,year,month,draft,report.revision);
      setReport(fresh);setDraft(fresh.draft);setDirty(false);setMessage("Rascunho salvo com histórico de alteração.");
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao salvar.");}
    finally{setWorking(false);}
  }

  async function archive(){
    if(!report || !canArchive(draft,!dirty))return;
    if(!window.confirm("Arquivar esta versão do fechamento? O faturamento do ERP continua pendente."))return;
    setWorking(true);setError("");setMessage("");
    try{
      const a=await api.archiveClosing(token,year,month,report.revision);
      const newer=await Promise.all([api.closing(token,year,month),api.closingArchives(token,year,month)]);
      setReport(newer[0]);setArchives(newer[1]);
      setMessage("Versão "+a.version+" arquivada com os números disponíveis no momento.");
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao arquivar.");}
    finally{setWorking(false);}
  }

  function currentSnapshot():ClosingSnapshot|null{
    if(!report)return null;
    return {period, draft, data:report.data,previous_pending:report.previous_pending,
      durations:report.durations,state:"partial_sales_pending",
      source:"Portal UMA — vendas oficiais ainda não integradas"};
  }

  async function openArchive(id:string){
    setWorking(true);setError("");
    try{const item:ClosingArchive=await api.closingArchive(token,year,month,id);
      setShowDeck(item.snapshot);
    }catch(cause){setError(cause instanceof Error?cause.message:"Arquivo indisponível.");}
    finally{setWorking(false);}
  }

  if(!profile.features.monthly_closing) return <div className="panel">
    <h2>Fechamento mensal restrito</h2>
    <p>A apresentação consolidada das três lojas é exclusiva da gestão.</p>
  </div>;

  return <div className="closing-editor">
    <div className="page-header"><div className="eyebrow">REUNIÃO GERENCIAL</div>
      <h1>Fechamento mensal</h1><p>Sete slides · 20 minutos · Joinville, Tubarão e Itajaí.</p></div>
    <div className="notice notice-amber">
      Faturamento, atividades comerciais e indicadores operacionais aguardam fontes oficiais.
      Os slides exibem “Sem dados”, nunca vendas simuladas. Rascunhos e arquivos são reais dentro do Portal UMA.
    </div>
    <div className="closing-toolbar">
      <div className="form-row"><label htmlFor="closing-period">Competência</label>
        <input id="closing-period" type="month" min="2020-01" max="2100-12"
          value={period} disabled={working} onChange={e=>changePeriod(e.target.value)}/></div>
      <span className="chip">{dirty?"Alterações não salvas":"Rascunho sincronizado"}</span>
      <button type="button" className="btn-secondary" disabled={!report||working}
        onClick={()=>{const preview=currentSnapshot();if(preview)setShowDeck(preview);}}>Apresentar 7 slides</button>
      <button type="button" className="btn-primary" disabled={!report||working||!dirty}
        onClick={()=>void save()}>Salvar rascunho</button>
    </div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    {loading&&<p role="status">Carregando fechamento…</p>}
    {report&&!loading&&<>
      <div className="closing-overview">
        <div className="panel"><span>Faturamento consolidado</span><strong>Sem dados</strong><small>Integração ERP pendente</small></div>
        <div className="panel"><span>Meta consolidada</span><strong>{currency(report.data.total_target)}</strong><small>Metas cadastradas nas três lojas</small></div>
        <div className="panel"><span>Tempo da apresentação</span><strong>20 minutos</strong><small>Sete slides aprovados</small></div>
      </div>
      <section className="panel closing-fields">
        <div className="panel-head"><div><h2>Textos da apresentação</h2>
          <p>Esses comentários serão exibidos nos slides correspondentes.</p></div>
        </div>
        {textLabel("Mensagem de abertura",draft.opening,v=>edit({opening:v}),2000)}
        <div className="closing-editor-columns">
          {report.data.stores.map(s=><div key={s.code}>
            {textLabel("Comentário — "+s.name,
              draft.stores[s.code as keyof ClosingDraft["stores"]],
              v=>setStoreValue("stores",s.code as keyof ClosingDraft["stores"],v),1600)}
          </div>)}
        </div>
        {textLabel("Atividades e oportunidades comerciais",draft.opportunities,v=>edit({opportunities:v}))}
        <div className="closing-editor-columns">
          {textLabel("Conquistas e reconhecimentos",draft.wins,v=>edit({wins:v}))}
          {textLabel("Oportunidades de melhoria",draft.improvements,v=>edit({improvements:v}))}
          {textLabel("Avisos e orientações",draft.notices,v=>edit({notices:v}))}
        </div>
        <h3>Recados específicos das lojas</h3>
        <div className="closing-editor-columns">
          {report.data.stores.map(s=><div key={s.code}>
            {textLabel(s.name,
              draft.notes[s.code as keyof ClosingDraft["notes"]],
              v=>setStoreValue("notes",s.code as keyof ClosingDraft["notes"],v),1600)}
          </div>)}
        </div>
      </section>
      <section className="panel closing-actions">
        <div className="panel-head"><div><h2>Prioridades do próximo mês</h2>
          <p>Cadastre de três a cinco ações com responsável, unidade, prazo e situação.</p></div>
          <span className="chip">{draft.priorities.length} / 5</span>
        </div>
        {draft.priorities.map((priority,index)=><div key={priority.id} className="closing-action">
          <div className="closing-action-header"><strong>Prioridade {index+1}</strong>
            <button className="btn-secondary" onClick={()=>removePriority(priority.id)}>Retirar</button></div>
          <div className="closing-action-grid">
            <label>Ação<input type="text" maxLength={300} value={priority.what}
              onChange={e=>updatePriority(priority.id,"what",e.target.value)}/></label>
            <label>Responsável<input type="text" maxLength={150} value={priority.owner}
              onChange={e=>updatePriority(priority.id,"owner",e.target.value)}/></label>
            <label>Unidade<select value={priority.scope}
              onChange={e=>updatePriority(priority.id,"scope",e.target.value)}>
              {Object.entries(STORE_LABELS).map(([code,name])=><option key={code} value={code}>{name}</option>)}
            </select></label>
            <label>Prazo<input type="date" value={priority.due}
              onChange={e=>updatePriority(priority.id,"due",e.target.value)}/></label>
            <label>Situação<select value={priority.status}
              onChange={e=>updatePriority(priority.id,"status",e.target.value)}>
              <option value="pendente">Pendente</option><option value="andamento">Em andamento</option>
              <option value="concluida">Concluída</option>
            </select></label>
          </div>
        </div>)}
        {draft.priorities.length===0&&<p className="small-note">Nenhuma prioridade cadastrada.</p>}
        <div className="btn-row">
          <button className="btn-secondary" disabled={working||draft.priorities.length>=5} onClick={addPriority}>+ Adicionar prioridade</button>
          <button className="btn-primary" disabled={working||!dirty} onClick={()=>void save()}>Salvar rascunho</button>
        </div>
        {report.previous_pending.length>0&&<div className="closing-previous">
          <strong>Pendências do mês anterior</strong>
          {report.previous_pending.map(p=><p key={p.id}>{p.what} · {p.owner}</p>)}
        </div>}
      </section>
      <section className="panel closing-archive-panel">
        <div className="panel-head"><div><h2>Arquivo de fechamentos</h2>
          <p>Os números e comentários são congelados em cada versão arquivada.</p></div></div>
        <div className="notice notice-amber">Enquanto não houver vendas oficiais, o fechamento será arquivado como <strong>parcial — dados de vendas pendentes</strong>.</div>
        <button className="btn-primary" disabled={working||!canArchive(draft,!dirty)}
          onClick={()=>void archive()}>Arquivar nova versão</button>
        {!canArchive(draft,!dirty)&&<p className="small-note">
          Para arquivar, salve o rascunho e cadastre entre três e cinco prioridades completas.</p>}
        <div className="closing-history">
          {archives.map(a=><div key={a.id} className="closing-history-row">
            <div><strong>Versão {a.version}</strong>
              <small>{new Date(a.created_at).toLocaleString("pt-BR")} · Vendas pendentes</small></div>
            <button className="btn-secondary" disabled={working} onClick={()=>void openArchive(a.id)}>Consultar / apresentar</button>
          </div>)}
          {archives.length===0&&<p className="small-note">Ainda não há fechamentos arquivados para este mês.</p>}
        </div>
      </section>
    </>}
    {showDeck&&<ClosingPresentation source={showDeck} onClose={()=>setShowDeck(null)}/>}
  </div>;
}
