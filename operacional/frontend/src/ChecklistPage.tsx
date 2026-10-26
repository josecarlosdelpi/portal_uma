import {useCallback,useEffect,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {routinesApi,type WeeklySnapshot,type WeeklyTask} from "./routinesApi";

type Props={token:string;profile:MyProfile};
const localToday=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
const weekdayNames=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"];

export function ChecklistPage({token,profile}:Props){
  const [store,setStore]=useState(profile.stores[0]??"");
  const [day,setDay]=useState(localToday);
  const [data,setData]=useState<WeeklySnapshot|null>(null);
  const [goal,setGoal]=useState("20");
  const [title,setTitle]=useState("");
  const [details,setDetails]=useState("");
  const [frequency,setFrequency]=useState<"weekly"|"once">("weekly");
  const [weekday,setWeekday]=useState(4);
  const [editing,setEditing]=useState<WeeklyTask|null>(null);
  const [working,setWorking]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canWrite=profile.profile!=="seller";

  const refresh=useCallback(async()=>{
    if(!store||!day)return;
    setLoading(true);setError("");
    try{const got=await routinesApi.weekly(token,store,day);setData(got);setGoal(String(got.calls.target));}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao consultar checklist.");}
    finally{setLoading(false);}
  },[token,store,day]);
  useEffect(()=>{void refresh();},[refresh]);

  async function perform(fn:()=>Promise<unknown>,messageText:string){
    setWorking(true);setError("");setMessage("");
    try{await fn();await refresh();setMessage(messageText);}
    catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível registrar.");}
    finally{setWorking(false);}
  }

  function edit(item:WeeklyTask){
    setEditing(item);setTitle(item.title);setDetails(item.details);
    setFrequency(item.frequency);setWeekday(item.day);
  }
  function reset(){setEditing(null);setTitle("");setDetails("");setFrequency("weekly");setWeekday(4);}

  return <section>
    <div className="page-header"><div><div className="eyebrow">EXECUÇÃO SEMANAL</div>
      <h1>Checklist semanal</h1><p>Rotinas e tarefas extraordinárias por loja, com validação da gestão.</p></div></div>
    <div className="notice notice-amber">As ligações da semana são contadas automaticamente pelos registros de Televendas.
      A conclusão precisa ser validada pela gestão.</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters">
      <label>Loja<select value={store} onChange={e=>setStore(e.target.value)}>
        {profile.stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}</select></label>
      <label>Selecionar uma data da semana<input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
    </div>
    {loading&&<p role="status">Carregando rotinas…</p>}
    {data&&!loading&&<>
      <div className="routine-kpis">
        <div className="panel"><span>Rotinas previstas</span><strong>{data.items.length}</strong>
          <small>Semana de {data.week_start} a {data.week_end}</small></div>
        <div className="panel"><span>Tarefas validadas</span><strong>{data.items.filter(x=>x.done).length}</strong>
          <small>Somente validação da gestão</small></div>
        <div className="panel"><span>Ligações registradas</span><strong>{data.calls.count}</strong>
          <small>Meta: {data.calls.target} · {data.calls.confirmed?"validada":"a validar"}</small></div>
      </div>
      <div className="columns routine-columns">
        <article className="panel">
          <div className="panel-head"><div><h2>Meta semanal de ligações</h2>
            <p>Contagem real dos contatos registrados por loja.</p></div></div>
          <div className="routine-call-progress"><strong>{data.calls.count} / {data.calls.target}</strong>
            <div className="routine-progress-track"><div style={{width:Math.min(100,data.calls.count/data.calls.target*100)+"%"}}/></div>
            <small>{data.calls.reached?"Meta numérica atingida":"Abaixo da meta numérica"}
              {" · "}{data.calls.confirmed?"Concluída oficialmente":"Pendente de validação"}</small></div>
          {canWrite&&<>
            <div className="routine-form-grid">
              <label>Meta desta semana<input type="number" min={1} max={9999} step={1}
                value={goal} onChange={e=>setGoal(e.target.value)}/></label>
            </div>
            <div className="btn-row">
              <button className="btn-primary" disabled={working||!Number.isInteger(Number(goal))||Number(goal)<1||Number(goal)>9999}
                onClick={()=>void perform(()=>routinesApi.callGoal(token,store,day,Number(goal),data.calls.confirmed),
                  "Meta semanal atualizada.")}>Salvar meta</button>
              <button className="btn-secondary" disabled={working}
                onClick={()=>void perform(()=>routinesApi.callGoal(token,store,day,Number(goal),!data.calls.confirmed),
                  "Validação atualizada.")}>{data.calls.confirmed?"Reabrir validação":"Validar resultado"}</button>
            </div>
          </>}
        </article>
        <article className="panel">
          <div className="panel-head"><div><h2>Tarefas da semana</h2>
            <p>Histórico de validação preservado ao editar rotinas futuras.</p></div></div>
          <div className="routine-task-list">{data.items.map(task=><div className="routine-task" key={task.id}>
            <div><small>{weekdayNames[task.day]} · {task.frequency==="weekly"?"Semanal":"Extraordinária"}</small>
              <strong>{task.title}</strong>{task.details&&<p>{task.details}</p>}</div>
            <span className={task.done?"routine-good":"routine-alert"}>{task.done?"Concluída":"Pendente"}</span>
            {canWrite&&<div className="btn-row">
              <button className="btn-secondary" disabled={working}
                onClick={()=>void perform(()=>routinesApi.verifyTask(token,store,task.id,day,!task.done),
                  "Validação da tarefa atualizada.")}>{task.done?"Reabrir":"Validar"}</button>
              <button className="btn-secondary" disabled={working} onClick={()=>edit(task)}>Editar versão</button>
            </div>}
          </div>)}</div>
          {data.items.length===0&&<p className="empty">Nenhuma tarefa cadastrada nesta semana.</p>}
        </article>
      </div>
      {canWrite&&<article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>{editing?"Nova versão da rotina":"Nova tarefa"}</h2>
          <p>Escolha a semana de início, a frequência e o dia programado.</p></div></div>
        <div className="routine-form-grid">
          <label className="routine-wide">Tarefa<input maxLength={100} placeholder="Ex.: Limpeza básica da loja"
            value={title} onChange={e=>setTitle(e.target.value)}/></label>
          <label className="routine-wide">Orientações<input maxLength={350} value={details}
            onChange={e=>setDetails(e.target.value)}/></label>
          <label>Frequência<select value={frequency} onChange={e=>setFrequency(e.target.value as typeof frequency)}>
            <option value="weekly">Toda semana</option><option value="once">Somente esta semana</option>
          </select></label>
          <label>Dia programado<select value={weekday} onChange={e=>setWeekday(Number(e.target.value))}>
            {weekdayNames.map((d,i)=><option key={d} value={i}>{d}</option>)}</select></label>
        </div>
        <div className="btn-row"><button className="btn-primary" disabled={working||title.trim().length<3}
          onClick={()=>void perform(async()=>{
            const params={reference:day,title,details,frequency,day:weekday};
            if(editing)await routinesApi.reviseTask(token,store,editing.id,params);
            else await routinesApi.createTask(token,store,params);
            reset();
          },"Rotina registrada, preservando os períodos anteriores.")}>{
            editing?"Salvar nova versão":"Adicionar tarefa"
          }</button>
          {editing&&<button className="btn-secondary" onClick={reset}>Cancelar edição</button>}
        </div>
      </article>}
    </>}
  </section>;
}
