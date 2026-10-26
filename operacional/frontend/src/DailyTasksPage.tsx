import {useCallback,useEffect,useMemo,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {operationsApi,type TeamMember} from "./operationsApi";
import {dailyTasksApi,type DailyTask,type DailyPriority,type DailyTaskStatus,
  type DailySnapshot} from "./dailyTasksApi";

type Props={token:string;profile:MyProfile};
const localToday=()=>{
  const d=new Date();
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),
    String(d.getDate()).padStart(2,"0")].join("-");
};
const prioLabels:Record<DailyPriority,string>={
  baixa:"Baixa",normal:"Normal",alta:"Alta"
};
const statusLabels:Record<DailyTaskStatus,string>={
  pendente:"Pendente",em_andamento:"Em andamento",concluida:"Concluída"
};

export function DailyTasksPage({token,profile}:Props){
  const [store,setStore]=useState(profile.stores[0]??"");
  const [day,setDay]=useState(localToday);
  const [data,setData]=useState<DailySnapshot|null>(null);
  const [team,setTeam]=useState<TeamMember[]>([]);
  const [title,setTitle]=useState("");
  const [details,setDetails]=useState("");
  const [priority,setPriority]=useState<DailyPriority>("normal");
  const [status,setStatus]=useState<DailyTaskStatus>("pendente");
  const [assignee,setAssignee]=useState("");
  const [editing,setEditing]=useState<DailyTask|null>(null);
  const [onlyOpen,setOnlyOpen]=useState(false);
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canWrite=profile.profile!=="seller";
  const refresh=useCallback(async()=>{
    if(!store||!day)return;
    setLoading(true);setError("");
    try{
      const [snapshot,people]=await Promise.all([
        dailyTasksApi.day(token,store,day),
        canWrite?operationsApi.team(token,store):Promise.resolve([] as TeamMember[])
      ]);
      setData(snapshot);setTeam(people);
    }catch(cause){
      setError(cause instanceof Error?cause.message:"Não foi possível consultar as tarefas.");
    }finally{setLoading(false);}
  },[token,store,day,canWrite]);
  useEffect(()=>{void refresh();},[refresh]);

  const items=useMemo(()=>data?.items.filter(item=>!onlyOpen||item.status!=="concluida")??[],
    [data,onlyOpen]);
  function resetForm(){
    setEditing(null);setTitle("");setDetails("");setPriority("normal");
    setStatus("pendente");setAssignee("");
  }
  function beginEdit(task:DailyTask){
    setEditing(task);setTitle(task.title);setDetails(task.details);
    setPriority(task.priority);setStatus(task.status);
    setAssignee(task.assignee_id??"");
    window.scrollTo({top:0,behavior:"smooth"});
  }
  async function perform(fn:()=>Promise<unknown>,success:string){
    setWorking(true);setError("");setMessage("");
    try{await fn();await refresh();setMessage(success);}
    catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível salvar.");}
    finally{setWorking(false);}
  }
  const standard=(task:DailyTask)=>({
    date:task.date,title:task.title,details:task.details,
    priority:task.priority,assignee_id:task.assignee_id
  });
  return <section>
    <div className="page-header"><div>
      <div className="eyebrow">GESTÃO DO DIA A DIA</div>
      <h1>Tarefas diárias</h1>
      <p>Atividades por data, loja e responsável, separadas do checklist semanal e do ERP.</p>
    </div></div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters">
      <label>Loja<select value={store} onChange={e=>{setStore(e.target.value);resetForm();}}>
        {profile.stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}
      </select></label>
      <label>Data<input type="date" min="2020-01-01" max="2100-12-31"
        value={day} onChange={e=>{setDay(e.target.value);resetForm();}}/></label>
      <button className="btn-secondary" onClick={()=>{setDay(localToday());resetForm();}}>
        Hoje</button>
    </div>
    {loading&&<p role="status">Carregando tarefas do dia…</p>}
    {data&&!loading&&<>
      <div className="routine-kpis">
        <div className="panel"><span>Programadas</span><strong>{data.summary.total}</strong>
          <small>Para {day.split("-").reverse().join("/")}</small></div>
        <div className="panel"><span>Pendentes</span><strong>{data.summary.pending}</strong>
          <small>Não iniciadas</small></div>
        <div className="panel"><span>Em andamento</span><strong>{data.summary.in_progress}</strong>
          <small>Em execução</small></div>
        <div className="panel"><span>Concluídas</span><strong>{data.summary.completed}</strong>
          <small>Validadas pela gestão</small></div>
      </div>
      <article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Agenda da loja</h2>
          <p>Conferência diária com histórico de alterações.</p></div>
          <label className="daily-filter"><input type="checkbox" checked={onlyOpen}
            onChange={e=>setOnlyOpen(e.target.checked)}/> Somente abertas</label>
        </div>
        <div className="daily-task-list">
          {items.map(task=><div className="daily-task-item" key={task.id}>
            <div className="daily-task-main">
              <div className="daily-task-top">
                <span className={"daily-task-priority daily-task-priority-"+task.priority}>
                  {prioLabels[task.priority]}</span>
                <span className={task.status==="concluida"?"routine-good":
                  task.status==="em_andamento"?"daily-task-progress":"routine-alert"}>
                  {statusLabels[task.status]}</span>
              </div>
              <h3>{task.title}</h3>
              {task.details&&<p>{task.details}</p>}
              <small>Responsável: {task.assignee}</small>
              {task.completed_at&&<small>Conclusão registrada</small>}
            </div>
            {canWrite&&<div className="daily-task-actions">
              {task.status!=="concluida"?
                <button className="btn-primary" disabled={working}
                  onClick={()=>void perform(()=>dailyTasksApi.edit(token,store,task.id,{
                    ...standard(task),status:"concluida",expected_revision:task.revision
                  }),"Tarefa concluída e registrada na auditoria.")}>Concluir</button>:
                <button className="btn-secondary" disabled={working}
                  onClick={()=>void perform(()=>dailyTasksApi.edit(token,store,task.id,{
                    ...standard(task),status:"pendente",expected_revision:task.revision
                  }),"Tarefa reaberta.")}>Reabrir</button>}
              <button className="btn-secondary" disabled={working}
                onClick={()=>beginEdit(task)}>Editar</button>
              <button className="btn-secondary daily-task-danger" disabled={working}
                onClick={()=>{
                  if(!window.confirm("Excluir esta tarefa? A exclusão será registrada."))return;
                  void perform(async()=>{
                    await dailyTasksApi.remove(token,store,task.id,task.revision);
                    if(editing?.id===task.id)resetForm();
                  },"Tarefa excluída com histórico preservado.");
                }}>Excluir</button>
            </div>}
          </div>)}
          {items.length===0&&<p className="empty">
            {onlyOpen?"Nenhuma tarefa aberta para este dia.":"Nenhuma tarefa registrada para este dia."}
          </p>}
        </div>
      </article>
    </>}
    {canWrite&&<article className="panel routine-form-panel">
      <div className="panel-head"><div><h2>{editing?"Editar tarefa":"Nova tarefa diária"}</h2>
        <p>{editing?"Atualize informações ou status mantendo o histórico.":"Atribua uma atividade para a data selecionada."}</p>
      </div></div>
      <div className="routine-form-grid">
        <label className="routine-wide">Descrição da tarefa
          <input maxLength={120} value={title} placeholder="Ex.: Conferir pedidos pendentes"
            onChange={e=>setTitle(e.target.value)}/></label>
        <label className="routine-wide">Orientações
          <textarea maxLength={400} rows={3} value={details}
            onChange={e=>setDetails(e.target.value)}/></label>
        <label>Prioridade<select value={priority}
          onChange={e=>setPriority(e.target.value as DailyPriority)}>
          <option value="baixa">Baixa</option><option value="normal">Normal</option>
          <option value="alta">Alta</option>
        </select></label>
        <label>Responsável<select value={assignee}
          onChange={e=>setAssignee(e.target.value)}>
          <option value="">Equipe da loja</option>
          {team.map(member=><option value={member.id} key={member.id}>{member.name}</option>)}
        </select></label>
        {editing&&<label>Situação<select value={status}
          onChange={e=>setStatus(e.target.value as DailyTaskStatus)}>
          <option value="pendente">Pendente</option>
          <option value="em_andamento">Em andamento</option>
          <option value="concluida">Concluída</option>
        </select></label>}
      </div>
      <div className="btn-row">
        <button className="btn-primary" disabled={working||title.trim().length<3||!day||!store}
          onClick={()=>void perform(async()=>{
            const body={date:day,title,details,priority,assignee_id:assignee||null};
            if(editing){
              await dailyTasksApi.edit(token,store,editing.id,{
                ...body,status,expected_revision:editing.revision
              });
            }else{
              await dailyTasksApi.create(token,store,body);
            }
            resetForm();
          },editing?"Tarefa atualizada.":"Tarefa criada e registrada.")}>
          {working?"Salvando…":editing?"Salvar alterações":"Cadastrar tarefa"}
        </button>
        {editing&&<button className="btn-secondary" disabled={working}
          onClick={resetForm}>Cancelar edição</button>}
      </div>
    </article>}
    <div className="notice notice-amber">
      Vendedores permanecem com consulta apenas à própria loja, conforme as permissões definidas
      pelo SuperAdmin. Registrar ou concluir tarefas exige um administrador.
    </div>
  </section>;
}
