import {useCallback,useEffect,useRef,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {attachmentsApi} from "./attachmentsApi";
import {operationsApi,type TeamMember} from "./operationsApi";
import {routinesApi,type TrainingEntry} from "./routinesApi";
import {proceduresApi,hydrateImages,type Procedure,type VersionInfo} from "./proceduresApi";
import {ProcedureEditor} from "./ProcedureEditor";

type Props={token:string;profile:MyProfile};
const today=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};

function DocView({token,procId,versionId,onBack}:{token:string;procId:string;versionId?:string;onBack:()=>void}){
  const [full,setFull]=useState<Procedure|null>(null);
  const [ver,setVer]=useState<VersionInfo|null>(null);
  const [error,setError]=useState("");
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    void Promise.all([
      proceduresApi.get(token,procId),
      versionId?proceduresApi.getVersion(token,procId,versionId):Promise.resolve(null),
    ]).then(([p,v])=>{setFull(p);setVer(v);}).catch(c=>setError(c.message));
  },[token,procId,versionId]);
  useEffect(()=>{void hydrateImages(ref.current,token);},[full,ver,token]);
  if(error)return <div className="notice notice-error">{error}</div>;
  if(!full)return <p>Carregando…</p>;
  const html=ver?.content_html??full.content_html??"";
  const label=ver?`Versão ${ver.version_label} ${ver.status==="publicado"?"publicada":"(rascunho)"}`:
    full.version?.status==="publicado"?`Versão ${full.version.version_label} publicada`:"Rascunho";
  return <section>
    <div className="page-header"><div><div className="eyebrow">PROCEDIMENTO</div>
      <h1>{full.code} — {full.title}</h1>
      <p>{label}{" · "}{full.applies_to_all?"Todas as lojas":full.stores.map(labelStore).join(", ")}</p></div>
      <button className="btn-secondary" onClick={onBack}>Voltar</button></div>
    {full.summary&&<p className="small-note">{full.summary}</p>}
    <article className="panel"><div ref={ref} className="doc-content doc-readonly"
      dangerouslySetInnerHTML={{__html:html}}/></article>
  </section>;
}

export function TrainingPage({token,profile}:Props){
  const canWrite=profile.profile!=="seller";
  const [tab,setTab]=useState<"procedimentos"|"treinamentos"|"meus">("procedimentos");
  const [procs,setProcs]=useState<Procedure[]>([]);
  const [q,setQ]=useState("");
  const [statusFilter,setStatusFilter]=useState<""|"rascunho"|"publicado">("");
  const [storeFilter,setStoreFilter]=useState("");
  const [viewing,setViewing]=useState<{id:string;versionId?:string}|null>(null);
  const [editing,setEditing]=useState<Procedure|null>(null);

  const [store,setStore]=useState(profile.stores[0]??"");
  const [entries,setEntries]=useState<TrainingEntry[]>([]);
  const [people,setPeople]=useState<TeamMember[]>([]);
  const [mine,setMine]=useState<TrainingEntry[]>([]);
  const [editRec,setEditRec]=useState<TrainingEntry|null>(null);
  const [participant,setParticipant]=useState("");
  const [procedureId,setProcedureId]=useState("");
  const [title,setTitle]=useState("");
  const [instructor,setInstructor]=useState("");
  const [day,setDay]=useState(today);
  const [hour,setHour]=useState("09:00");
  const [step,setStep]=useState<"participou"|"pratica">("participou");
  const [note,setNote]=useState("");
  const [fPerson,setFPerson]=useState("");
  const [fProc,setFProc]=useState("");
  const [fStart,setFStart]=useState("");
  const [fEnd,setFEnd]=useState("");
  const [docFile,setDocFile]=useState<File|null>(null);
  const [docId,setDocId]=useState("");
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  const refreshProcs=useCallback(async()=>{
    try{setProcs(await proceduresApi.list(token,{status:statusFilter||undefined,
      store:storeFilter||undefined,q:q||undefined}));}
    catch(cause){setError(cause instanceof Error?cause.message:"Erro ao listar procedimentos.");}
  },[token,q,statusFilter,storeFilter]);
  useEffect(()=>{void refreshProcs();},[refreshProcs]);

  const refreshTrainings=useCallback(async()=>{
    if(!store)return;setLoading(true);setError("");
    try{
      const [rows,team]=await Promise.all([
        routinesApi.trainings(token,store,{participant_id:fPerson||undefined,
          procedure_id:fProc||undefined,start:fStart||undefined,end:fEnd||undefined}),
        canWrite?operationsApi.team(token,store):Promise.resolve([] as TeamMember[])]);
      setEntries(rows);setPeople(team);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível carregar.");}
    finally{setLoading(false);}
  },[token,store,canWrite,fPerson,fProc,fStart,fEnd]);
  useEffect(()=>{if(canWrite)void refreshTrainings();},[refreshTrainings,canWrite]);
  useEffect(()=>{setParticipant(current=>people.some(p=>p.id===current)?current:people[0]?.id??"");},[people]);
  useEffect(()=>{if(!canWrite)void routinesApi.myTrainings(token).then(setMine).catch(()=>{});},[token,canWrite]);

  async function newProcedure(){
    setWorking(true);setError("");
    try{const created=await proceduresApi.create(token,{title:"Novo procedimento",
      summary:"",applies_to_all:true,store_codes:[],content_html:""});
      const full=await proceduresApi.get(token,created.id);setEditing(full);}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao criar.");}
    finally{setWorking(false);}
  }

  function startEdit(entry:TrainingEntry){
    setEditRec(entry);setParticipant(entry.participant_id);
    setProcedureId(entry.procedure_id??"");setTitle(entry.title);
    setInstructor(entry.instructor);setDay(entry.happened_on.slice(0,10));
    setHour(entry.happened_on.slice(11,16));setStep(entry.step);setNote(entry.note);
  }

  async function save(){
    setWorking(true);setError("");setMessage("");
    try{
      const body={participant_id:participant,procedure_id:procedureId||null,
        title,instructor,happened_on:day+"T"+hour+":00",step,note};
      if(editRec)await routinesApi.updateTraining(token,store,editRec.id,{...body,expected_revision:editRec.revision});
      else await routinesApi.addTraining(token,store,body);
      await refreshTrainings();setMessage(editRec?"Registro atualizado.":"Participação registrada. Não representa assinatura eletrônica.");
      setEditRec(null);setNote("");setTitle("");
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao registrar.");}
    finally{setWorking(false);}
  }

  async function removeRec(entry:TrainingEntry){
    if(!window.confirm(`Excluir o treinamento de ${entry.participant} (${entry.happened_on.slice(0,10)})? A exclusão é lógica e auditada.`))return;
    setWorking(true);setError("");setMessage("");
    try{await routinesApi.deleteTraining(token,store,entry.id,entry.revision);
      await refreshTrainings();setMessage("Registro excluído. Histórico preservado na auditoria.");}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao excluir.");}
    finally{setWorking(false);}
  }

  const selectedDoc=entries.find(x=>x.id===docId);
  async function uploadDoc(){
    if(!docFile||!selectedDoc)return;setWorking(true);setError("");
    try{await attachmentsApi.uploadTraining(token,store,docId,docFile,selectedDoc.document?.revision??0);
      setDocFile(null);await refreshTrainings();setMessage("PDF anexado (não é assinatura eletrônica).");}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha no anexo.");}
    finally{setWorking(false);}
  }
  async function downloadDoc(e:TrainingEntry){if(e.document)await attachmentsApi.downloadTraining(token,store,e.id,e.document.name).catch(c=>setError(c.message));}
  async function deleteDoc(e:TrainingEntry){if(!e.document||!window.confirm("Excluir o PDF anexado?"))return;
    setWorking(true);try{await attachmentsApi.deleteTraining(token,store,e.id,e.document.revision);await refreshTrainings();}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao excluir.");}finally{setWorking(false);}}

  if(editing)return <ProcedureEditor token={token} procedure={editing}
    onClose={changed=>{setEditing(null);if(changed)void refreshProcs();}}/>;
  if(viewing)return <DocView token={token} procId={viewing.id} versionId={viewing.versionId}
    onBack={()=>setViewing(null)}/>;

  const hist=(canWrite?entries:mine);
  return <section>
    <div className="page-header"><div><div className="eyebrow">CLAREZA E CAPACITAÇÃO</div>
      <h1>Padrões e treinamento</h1>
      <p>Procedimentos internos com editor completo e histórico de treinamentos por versão.</p></div>
      {canWrite&&<button className="btn-primary" disabled={working} onClick={()=>void newProcedure()}>
        + Novo Procedimento</button>}</div>
    <div className="tab-bar">
      <button role="tab" aria-selected={tab==="procedimentos"} className={tab==="procedimentos"?"tab active":"tab"}
        onClick={()=>setTab("procedimentos")}>Procedimentos</button>
      <button role="tab" aria-selected={tab==="treinamentos"} className={tab==="treinamentos"?"tab active":"tab"}
        onClick={()=>setTab("treinamentos")}>{canWrite?"Treinamentos":"Meus treinamentos"}</button>
    </div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}

    {tab==="procedimentos"&&<>
      <div className="routine-filters">
        <label>Busca<input value={q} onChange={e=>setQ(e.target.value)} placeholder="Título ou código"/></label>
        {canWrite&&<label>Situação<select value={statusFilter} onChange={e=>setStatusFilter(e.target.value as typeof statusFilter)}>
          <option value="">Todas</option><option value="publicado">Publicado</option><option value="rascunho">Rascunho</option>
        </select></label>}
        <label>Loja<select value={storeFilter} onChange={e=>setStoreFilter(e.target.value)}>
          <option value="">Todas</option>{profile.stores.map(c=><option key={c} value={c}>{labelStore(c)}</option>)}
        </select></label>
      </div>
      <article className="panel"><div className="table-wrap"><table>
        <thead><tr><th>Código</th><th>Título</th><th>Aplicável</th><th>Situação</th><th>Atualizado</th><th></th></tr></thead>
        <tbody>{procs.map(p=><tr key={p.id}>
          <td>{p.code}</td><td>{p.title}</td>
          <td>{p.applies_to_all?"Todas":p.stores.map(labelStore).join(", ")}</td>
          <td>{p.draft_version?<span className="badge-draft">Rascunho v{p.draft_version.version_label}</span>
            :p.current_version?<span className="badge-pub">Publicado v{p.current_version.version_label}</span>:"—"}</td>
          <td>{new Date(p.updated_at).toLocaleDateString("pt-BR")}</td>
          <td><div className="routine-file-actions">
            <button className="btn-secondary" onClick={()=>setViewing({id:p.id})}>Abrir</button>
            {canWrite&&<button className="btn-secondary" onClick={async()=>setEditing(await proceduresApi.get(token,p.id))}>
              {p.draft_version?"Continuar edição":p.current_version?"Nova versão":"Editar"}</button>}
          </div></td></tr>)}</tbody></table></div>
        {procs.length===0&&<p className="empty">Nenhum procedimento encontrado.</p>}
      </article>
    </>}

    {tab==="treinamentos"&&!canWrite&&<article className="panel">
      <div className="panel-head"><div><h2>Meus treinamentos</h2>
        <p>Somente registros vinculados à sua conta.</p></div></div>
      <div className="table-wrap"><table><thead><tr><th>Data</th><th>Procedimento</th>
        <th>Versão</th><th>Etapa</th><th>Instrutor</th><th></th></tr></thead>
        <tbody>{hist.map(e=><tr key={e.id}>
          <td>{new Date(e.happened_on).toLocaleString("pt-BR")}</td><td>{e.procedure}</td>
          <td>{e.version}</td><td>{e.step==="pratica"?"Prática verificada":"Apresentado"}</td>
          <td>{e.instructor}</td>
          <td>{e.procedure_id&&<button className="btn-secondary"
            onClick={()=>setViewing({id:e.procedure_id!,versionId:e.procedure_version_id??undefined})}>
            Abrir procedimento</button>}</td></tr>)}</tbody></table></div>
      {hist.length===0&&<p className="empty">Nenhum treinamento registrado.</p>}
    </article>}

    {tab==="treinamentos"&&canWrite&&<>
      <div className="routine-filters">
        <label>Loja<select value={store} onChange={e=>setStore(e.target.value)}>
          {profile.stores.map(c=><option key={c} value={c}>{labelStore(c)}</option>)}
        </select></label>
        <label>Colaborador<select value={fPerson} onChange={e=>setFPerson(e.target.value)}>
          <option value="">Todos</option>{people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label>
        <label>Procedimento<select value={fProc} onChange={e=>setFProc(e.target.value)}>
          <option value="">Todos</option>{procs.filter(p=>p.current_version).map(p=><option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
        </select></label>
        <label>De<input type="date" value={fStart} onChange={e=>setFStart(e.target.value)}/></label>
        <label>Até<input type="date" value={fEnd} onChange={e=>setFEnd(e.target.value)}/></label>
      </div>
      <article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>{editRec?"Editar treinamento":"Registrar treinamento"}</h2>
          <p>{editRec?`Revisão ${editRec.revision} · edição auditada`:"A versão publicada vigente é registrada automaticamente."}</p></div>
          {editRec&&<button className="btn-secondary" onClick={()=>setEditRec(null)}>Cancelar edição</button>}</div>
        <div className="routine-form-grid">
          <label>Colaborador<select value={participant} onChange={e=>setParticipant(e.target.value)}>
            {people.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
          <label>Procedimento<select value={procedureId} onChange={e=>setProcedureId(e.target.value)}>
            <option value="">Selecione…</option>
            {procs.filter(p=>p.current_version).map(p=><option key={p.id} value={p.id}>
              {p.code} — {p.title} (v{p.current_version!.version_label})</option>)}
          </select></label>
          <label>Instrutor / responsável<input maxLength={90} value={instructor}
            onChange={e=>setInstructor(e.target.value)}/></label>
          <label>Data<input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
          <label>Horário<input type="time" value={hour} onChange={e=>setHour(e.target.value)}/></label>
          <label>Etapa<select value={step} onChange={e=>setStep(e.target.value as typeof step)}>
            <option value="participou">Treinamento apresentado</option>
            <option value="pratica">Execução prática verificada</option></select></label>
          <label className="routine-wide">Referência complementar<input maxLength={140}
            value={title} onChange={e=>setTitle(e.target.value)}/></label>
          <label className="routine-wide">Observações<input maxLength={350}
            value={note} onChange={e=>setNote(e.target.value)}/></label>
        </div>
        <button className="btn-primary" disabled={working||!participant||!procedureId||!instructor.trim()}
          onClick={()=>void save()}>{working?"Salvando…":editRec?"Salvar alterações":"Registrar participação"}</button>
      </article>
      {entries.length>0&&<article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Anexar PDF complementar</h2>
          <p>PDF privado de até 5 MB. Não é assinatura eletrônica.</p></div></div>
        <div className="routine-form-grid">
          <label className="routine-wide">Registro<select value={docId} onChange={e=>setDocId(e.target.value)}>
            <option value="">Selecione…</option>
            {entries.map(r=><option key={r.id} value={r.id}>{r.participant} — {r.procedure} ({r.happened_on.slice(0,10)})</option>)}
          </select></label>
          <label className="routine-wide">PDF<input type="file" accept=".pdf,application/pdf"
            key={docId+"-"+(selectedDoc?.document?.revision??0)} disabled={working}
            onChange={e=>setDocFile(e.target.files?.[0]??null)}/></label>
        </div>
        <button className="btn-primary" disabled={!docFile||!selectedDoc||working}
          onClick={()=>void uploadDoc()}>Anexar PDF</button>
      </article>}
      <article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Histórico de treinamentos</h2>
          <p>Registros administrativos com edição e exclusão lógica auditadas.</p></div></div>
        {loading&&<p role="status">Consultando registros…</p>}
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Colaborador</th>
          <th>Procedimento</th><th>Versão</th><th>Etapa</th><th>PDF</th><th>Ações</th></tr></thead>
          <tbody>{entries.map(e=><tr key={e.id}>
            <td>{new Date(e.happened_on).toLocaleString("pt-BR")}</td><td>{e.participant}</td>
            <td>{e.procedure}</td><td>{e.version}</td>
            <td>{e.step==="pratica"?"Prática verificada":"Apresentado"}</td>
            <td>{e.document?<div className="routine-file-actions">
              <button className="btn-secondary" onClick={()=>void downloadDoc(e)}>Baixar</button>
              <button className="btn-secondary" disabled={working} onClick={()=>void deleteDoc(e)}>Excluir</button>
            </div>:"—"}</td>
            <td><div className="routine-file-actions">
              <button className="btn-secondary" onClick={()=>startEdit(e)}>Editar</button>
              <button className="btn-secondary" disabled={working} onClick={()=>void removeRec(e)}>Excluir</button>
            </div></td></tr>)}</tbody></table></div>
        {entries.length===0&&!loading&&<p className="empty">Nenhum treinamento nesta loja.</p>}
      </article>
    </>}
  </section>;
}
