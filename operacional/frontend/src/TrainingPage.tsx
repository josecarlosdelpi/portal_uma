import {useCallback,useEffect,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {operationsApi,type TeamMember} from "./operationsApi";
import {routinesApi,type TrainingEntry} from "./routinesApi";

type Props={token:string;profile:MyProfile};
const today=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
const popTitles=[
  ["POP-COM-01","Atendimento e cotação"],
  ["POP-COM-02","Prospecção e reativação"],
  ["POP-COM-03","Demanda não atendida"]
];

export function TrainingPage({token,profile}:Props){
  const [store,setStore]=useState(profile.stores[0]??"");
  const [entries,setEntries]=useState<TrainingEntry[]>([]);
  const [people,setPeople]=useState<TeamMember[]>([]);
  const [participant,setParticipant]=useState("");
  const [procedure,setProcedure]=useState("POP-COM-01");
  const [version,setVersion]=useState("Rascunho 0.1");
  const [title,setTitle]=useState("");
  const [instructor,setInstructor]=useState("");
  const [day,setDay]=useState(today);
  const [hour,setHour]=useState("09:00");
  const [step,setStep]=useState<"participou"|"pratica">("participou");
  const [note,setNote]=useState("");
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canWrite=profile.profile!=="seller";

  const refresh=useCallback(async()=>{
    if(!store)return;
    setLoading(true);setError("");
    try{
      const [rows,team]=await Promise.all([
        routinesApi.trainings(token,store),canWrite?operationsApi.team(token,store):Promise.resolve([] as TeamMember[])
      ]);
      setEntries(rows);setPeople(team);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível carregar treinamentos.");}
    finally{setLoading(false);}
  },[token,store,canWrite]);
  useEffect(()=>{void refresh();},[refresh]);
  useEffect(()=>{setParticipant(current=>people.some(p=>p.id===current)?current:people[0]?.id??"");},[people]);

  async function save(){
    setWorking(true);setError("");setMessage("");
    try{
      await routinesApi.addTraining(token,store,{
        participant_id:participant,procedure,version,title,instructor,
        happened_on:day+"T"+hour+":00",step,note
      });
      await refresh();setMessage("Participação registrada sem assinatura eletrônica.");
      setNote("");setTitle("");
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao registrar.");}
    finally{setWorking(false);}
  }
  return <section>
    <div className="page-header"><div><div className="eyebrow">CLAREZA E CAPACITAÇÃO</div>
      <h1>Padrões e treinamento</h1>
      <p>Registre procedimentos, versões, participantes e verificação prática por loja.</p></div></div>
    <div className="notice notice-amber">Os procedimentos abaixo ainda são rascunhos.
      O registro de participação não comprova ciência assinada: anexos PDF e assinatura
      eletrônica só serão habilitados após configurar armazenamento privado e consentimentos.</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-procedures">
      {popTitles.map(([code,name])=><article className="panel" key={code}>
        <span className="routine-procedure-code">{code} · RASCUNHO 0.1</span>
        <h2>{name}</h2>
        <p>{code==="POP-COM-01"?
          "Padrão esperado para atendimento, cotação e acompanhamento.":
          code==="POP-COM-02"?
          "Organização de contatos e reativação de clientes.":
          "Registro de pedidos não atendidos e oportunidades de melhoria."}</p>
        <span className="routine-alert">Não aprovado</span>
      </article>)}
    </div>
    <div className="routine-filters"><label>Unidade<select value={store} onChange={e=>setStore(e.target.value)}>
      {profile.stores.map(code=><option value={code} key={code}>{labelStore(code)}</option>)}
    </select></label></div>
    {loading&&<p role="status">Consultando registros…</p>}
    {canWrite&&<article className="panel routine-form-panel">
      <div className="panel-head"><div><h2>Registrar treinamento</h2>
        <p>Registre presença e verificação prática separadamente.</p></div></div>
      <div className="routine-form-grid">
        <label>Colaborador<select value={participant} onChange={e=>setParticipant(e.target.value)}>
          {people.map(person=><option value={person.id} key={person.id}>{person.name}</option>)}</select></label>
        <label>Procedimento<select value={procedure} onChange={e=>setProcedure(e.target.value)}>
          {popTitles.map(([code,name])=><option value={code} key={code}>{code} — {name}</option>)}
          <option value="Outro">Outro procedimento</option>
        </select></label>
        <label>Versão<input maxLength={45} value={version} onChange={e=>setVersion(e.target.value)}/></label>
        <label>Instrutor / responsável<input maxLength={90} value={instructor}
          onChange={e=>setInstructor(e.target.value)}/></label>
        <label>Data<input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
        <label>Horário<input type="time" value={hour} onChange={e=>setHour(e.target.value)}/></label>
        <label>Etapa<select value={step} onChange={e=>setStep(e.target.value as typeof step)}>
          <option value="participou">Treinamento apresentado</option>
          <option value="pratica">Execução prática verificada</option>
        </select></label>
        <label className="routine-wide">Referência complementar<input maxLength={140}
          value={title} onChange={e=>setTitle(e.target.value)}/></label>
        <label className="routine-wide">Observações<input maxLength={350}
          value={note} onChange={e=>setNote(e.target.value)}/></label>
      </div>
      {people.length===0&&<div className="notice notice-amber">Cadastre os vendedores vinculados à loja
        antes de registrar um treinamento.</div>}
      <button className="btn-primary" disabled={working||!participant||!procedure.trim()||
        !version.trim()||!instructor.trim()||!day||!hour}
        onClick={()=>void save()}>Registrar participação</button>
    </article>}
    <article className="panel routine-form-panel">
      <div className="panel-head"><div><h2>Histórico de treinamentos</h2>
        <p>Registros administrativos por colaborador e procedimento.</p></div></div>
      <div className="table-wrap"><table><thead><tr><th>Data</th><th>Colaborador</th>
        <th>Procedimento</th><th>Versão</th><th>Etapa</th><th>Assinatura</th></tr></thead>
        <tbody>{entries.map(entry=><tr key={entry.id}>
          <td>{new Date(entry.happened_on).toLocaleString("pt-BR")}</td>
          <td>{entry.participant}</td><td>{entry.procedure}</td><td>{entry.version}</td>
          <td>{entry.step==="pratica"?"Prática verificada":"Participação registrada"}</td>
          <td><span className="routine-alert">Pendente</span></td>
        </tr>)}</tbody></table></div>
      {entries.length===0&&<p className="empty">Nenhum treinamento cadastrado nesta loja.</p>}
    </article>
  </section>;
}
