import {useCallback,useEffect,useRef,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {attachmentsApi} from "./attachmentsApi";
import {operationsApi,type TeamMember} from "./operationsApi";
import {routinesApi,type TrainingEntry,type TrainingStep} from "./routinesApi";
import {proceduresApi,hydrateImages,type Procedure,type VersionInfo} from "./proceduresApi";
import {ProcedureEditor} from "./ProcedureEditor";
import {ConfirmDialog} from "./ConfirmDialog";
import {ChevronDown,X} from "lucide-react";

type Props={token:string;profile:MyProfile};
const STEP_OPTIONS=[
  {value:"participou",label:"Treinamento apresentado"},
  {value:"pratica",label:"Execução prática verificada"},
] as const;
const stepLabel=(step:string)=>step.split(",")
  .map(s=>s==="pratica"?"Prática verificada":"Apresentado").join(" + ");

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
  if(error)return <section>
    <div className="page-header"><div><h1>Documento indisponível</h1>
      <p>As informações históricas do treinamento foram preservadas.</p></div>
      <button className="btn-secondary" onClick={onBack}>Voltar</button></div>
    <div className="notice notice-error">{error}</div></section>;
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

const mediaKind=(media:string)=>media.startsWith("image/")?"image"
  :media==="application/pdf"?"pdf":media.startsWith("video/")?"video"
  :media.startsWith("audio/")?"audio":"other";
const fmtSize=(n:number)=>n>=1048576?(n/1048576).toFixed(1)+" MB":Math.max(1,Math.round(n/1024))+" KB";

function FilePreview({token,store,entry,onClose,onDownload}:{
  token:string;store:string;entry:TrainingEntry;onClose:()=>void;onDownload:()=>void}){
  const [url,setUrl]=useState("");
  const [err,setErr]=useState("");
  const kind=mediaKind(entry.document?.media_type??"");
  useEffect(()=>{
    let objectUrl="";let cancelled=false;
    attachmentsApi.previewTraining(token,store,entry.id)
      .then(u=>{if(cancelled){URL.revokeObjectURL(u);return;}objectUrl=u;setUrl(u);})
      .catch(c=>{if(!cancelled)
        setErr(c instanceof Error?c.message:"Não foi possível exibir a prévia.");});
    return ()=>{cancelled=true;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[token,store,entry]);
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Prévia do anexo">
    <div className="modal-card pdf-view-card">
      <div className="fav-org-head"><h3>{entry.document?.name??"Arquivo anexado"}</h3>
        <button type="button" className="fav-org-close" aria-label="Fechar" onClick={onClose}>
          <X size={16}/></button></div>
      {err?<div className="notice notice-error">{err} Baixe o arquivo para consultar.</div>
        :!url?<p role="status">Carregando prévia…</p>
        :kind==="image"?<img className="pdf-frame file-preview-media" src={url} alt="Prévia do anexo"/>
        :kind==="pdf"?<iframe className="pdf-frame" src={url} title="Prévia do PDF anexado"/>
        :kind==="video"?<video className="pdf-frame" src={url} controls/>
        :kind==="audio"?<audio src={url} controls className="file-audio"/>
        :<p className="small-note">Este formato não pode ser exibido no portal. Baixe o arquivo.</p>}
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onDownload}>Baixar</button>
        <button type="button" className="btn-primary" onClick={onClose}>Fechar</button>
      </div></div></div>;
}

function MultiSelect({label,options,value,onChange,empty}:{
  label:string;options:{value:string;label:string}[];value:string[];
  onChange:(v:string[])=>void;empty:string}){
  const [open,setOpen]=useState(false);
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!open)return;
    const onDown=(e:MouseEvent)=>{if(ref.current&&!ref.current.contains(e.target as Node))setOpen(false);};
    const onKey=(e:KeyboardEvent)=>{if(e.key==="Escape")setOpen(false);};
    document.addEventListener("mousedown",onDown);
    document.addEventListener("keydown",onKey);
    return ()=>{document.removeEventListener("mousedown",onDown);
      document.removeEventListener("keydown",onKey);};
  },[open]);
  const toggle=(v:string)=>onChange(value.includes(v)?value.filter(x=>x!==v):[...value,v]);
  const summary=!value.length?empty
    :value.length===options.length?"Todos"
    :value.length===1?(options.find(o=>o.value===value[0])?.label??"1 selecionado")
    :`${value.length} selecionados`;
  return <div className="step-multi" ref={ref}>
    <span className="step-multi-label">{label}</span>
    <button type="button" className="step-multi-btn" aria-haspopup="listbox" aria-expanded={open}
      onClick={()=>setOpen(o=>!o)}><span>{summary}</span><ChevronDown size={14}/></button>
    {open&&<div className="step-multi-panel" role="listbox" aria-multiselectable="true">
      <div className="step-multi-tools">
        <button type="button" onClick={()=>onChange(options.map(o=>o.value))}>Selecionar todos</button>
        <button type="button" onClick={()=>onChange([])}>Limpar seleção</button></div>
      <div className="step-multi-options">
      {options.map(o=><label key={o.value} className="check-line" role="option"
        aria-selected={value.includes(o.value)}>
        <input type="checkbox" checked={value.includes(o.value)} onChange={()=>toggle(o.value)}/>
        {o.label}</label>)}
      </div>
    </div>}
  </div>;
}

function TrainingDetails({entry,canWrite,working,onBack,onViewProc,onPreviewPdf,onDownloadPdf,onDeletePdf}:{
  entry:TrainingEntry;canWrite:boolean;working:boolean;
  onBack:()=>void;onViewProc:()=>void;onPreviewPdf:()=>void;onDownloadPdf:()=>void;onDeletePdf:()=>void}){
  return <section>
    <div className="page-header"><div><div className="eyebrow">TREINAMENTO</div>
      <h1>Detalhes do treinamento</h1>
      <p>Consulta completa do registro · não representa assinatura eletrônica.</p></div>
      <button className="btn-secondary" onClick={onBack}>Voltar ao histórico</button></div>
    <article className="panel"><div className="detail-rows">
      <div className="detail-row"><dt>Loja</dt><dd>{labelStore(entry.store_code)}</dd></div>
      <div className="detail-row"><dt>Colaborador</dt><dd>{entry.participant}</dd></div>
      <div className="detail-row"><dt>Data e horário</dt>
        <dd>{new Date(entry.happened_on).toLocaleString("pt-BR")}</dd></div>
      <div className="detail-row"><dt>Instrutor / responsável</dt><dd>{entry.instructor}</dd></div>
      <div className="detail-row"><dt>Procedimento</dt><dd>{entry.procedure}</dd></div>
      <div className="detail-row"><dt>Versão utilizada</dt><dd>{entry.version}</dd></div>
      <div className="detail-row"><dt>Etapas realizadas</dt><dd>{stepLabel(entry.step)}</dd></div>
      <div className="detail-row detail-wide"><dt>Observações</dt>
        <dd>{entry.note?entry.note:<em className="detail-empty">Nenhuma observação registrada</em>}</dd></div>
    </div>
    {entry.procedure_id&&<div className="detail-actions">
      <button className="btn-secondary" onClick={onViewProc}>Ver procedimento utilizado</button></div>}
    </article>
    <article className="panel"><div className="panel-head"><div><h2>Arquivo anexado</h2>
      <p>Documento privado, acessível apenas com sua sessão.</p></div></div>
      {entry.document?<div>
        <p className="small-note">{entry.document.name} · {entry.document.media_type}
          {" · "}{fmtSize(entry.document.size)}</p>
        <div className="routine-file-actions">
        {mediaKind(entry.document.media_type)!=="other"&&
          <button className="btn-secondary" onClick={onPreviewPdf}>Visualizar</button>}
        <button className="btn-secondary" onClick={onDownloadPdf}>Baixar</button>
        {canWrite&&<button className="btn-secondary" disabled={working} onClick={onDeletePdf}>Excluir</button>}
        </div></div>:<p className="small-note">Nenhum arquivo anexado a este registro.</p>}
    </article>
  </section>;
}

export function TrainingPage({token,profile}:Props){
  const canWrite=profile.profile!=="seller";
  const isSuperAdmin=profile.profile==="superadmin";
  const [tab,setTab]=useState<"procedimentos"|"treinamentos"|"meus">("procedimentos");
  const [procs,setProcs]=useState<Procedure[]>([]);
  const [q,setQ]=useState("");
  const [statusFilter,setStatusFilter]=useState<""|"rascunho"|"publicado"|"obsoleto">("");
  const [deleting,setDeleting]=useState<Procedure|null>(null);
  const [obsoleting,setObsoleting]=useState<Procedure|null>(null);
  const [removingRec,setRemovingRec]=useState<TrainingEntry|null>(null);
  const [deletingDoc,setDeletingDoc]=useState<TrainingEntry|null>(null);
  const [storeFilter,setStoreFilter]=useState("");
  const [viewing,setViewing]=useState<{id:string;versionId?:string}|null>(null);
  const [editing,setEditing]=useState<Procedure|null>(null);
  const [details,setDetails]=useState<TrainingEntry|null>(null);
  const [saved,setSaved]=useState<TrainingEntry|null>(null);
  const [recentId,setRecentId]=useState("");
  const [pdfPreview,setPdfPreview]=useState<TrainingEntry|null>(null);
  const [confirmingEdit,setConfirmingEdit]=useState<TrainingEntry|null>(null);
  const [pendingUpload,setPendingUpload]=useState<{entry:TrainingEntry;file:File}|null>(null);
  const scrollPos=useRef(0);
  const formRef=useRef<HTMLElement>(null);
  const participantRef=useRef<HTMLSelectElement>(null);
  const [fileKey,setFileKey]=useState(0);
  const [attach,setAttach]=useState<File|null>(null);
  const [filterStores,setFilterStores]=useState<string[]>([]);

  const [store,setStore]=useState(profile.stores[0]??"");
  const [entries,setEntries]=useState<TrainingEntry[]>([]);
  const [people,setPeople]=useState<TeamMember[]>([]);
  const [team,setTeam]=useState<TeamMember[]>([]);
  const [histProcs,setHistProcs]=useState<{procedure_id:string;procedure:string}[]>([]);
  const [mine,setMine]=useState<TrainingEntry[]>([]);
  const [editRec,setEditRec]=useState<TrainingEntry|null>(null);
  const [participant,setParticipant]=useState("");
  const [procedureId,setProcedureId]=useState("");
  const [instructor,setInstructor]=useState("");
  const [day,setDay]=useState("");
  const [hour,setHour]=useState("");
  const [steps,setSteps]=useState<string[]>([]);
  const [stepOpen,setStepOpen]=useState(false);
  const stepRef=useRef<HTMLDivElement>(null);
  const [note,setNote]=useState("");
  const [fPersons,setFPersons]=useState<string[]>([]);
  const [fProcs,setFProcs]=useState<string[]>([]);
  const [fStart,setFStart]=useState("");
  const [fEnd,setFEnd]=useState("");
  const [hasMore,setHasMore]=useState(false);
  const PAGE_SIZE=200;
  const reqSeq=useRef(0);
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

  const activeStores=filterStores.length?filterStores:profile.stores;
  const refreshTrainings=useCallback(async()=>{
    const stores=filterStores.length?filterStores:profile.stores;
    if(!stores.length)return;
    const seq=++reqSeq.current;
    setLoading(true);setError("");
    try{
      const [rows,hprocs,...teams]=await Promise.all([
        routinesApi.trainingsMulti(token,stores,{participant_ids:fPersons,
          procedure_ids:fProcs,start:fStart||undefined,end:fEnd||undefined,
          limit:PAGE_SIZE}),
        routinesApi.trainingProcedures(token,stores),
        ...(canWrite?stores.map(s=>operationsApi.team(token,s).catch(()=>[] as TeamMember[]))
          :[Promise.resolve([] as TeamMember[])])]);
      if(seq!==reqSeq.current)return rows;
      setEntries(rows);setHasMore(rows.length===PAGE_SIZE);setHistProcs(hprocs);
      const seen=new Map<string,TeamMember>();
      for(const t of teams)for(const m of t)seen.set(m.id,m);
      setPeople([...seen.values()]);
      return rows;
    }catch(cause){if(seq===reqSeq.current)
      setError(cause instanceof Error?cause.message:"Não foi possível carregar.");}
    finally{if(seq===reqSeq.current)setLoading(false);}
  },[token,filterStores,canWrite,fPersons,fProcs,fStart,fEnd,profile.stores]);
  useEffect(()=>{if(canWrite)void refreshTrainings();},[refreshTrainings,canWrite]);
  // A equipe do formulario depende exclusivamente da loja de cadastro.
  const teamSeq=useRef(0);
  const [teamError,setTeamError]=useState("");
  useEffect(()=>{
    if(!canWrite||!store)return;
    const seq=++teamSeq.current;setTeamError("");
    void operationsApi.team(token,store)
      .then(m=>{if(seq===teamSeq.current)setTeam(m);})
      .catch(c=>{if(seq===teamSeq.current){setTeam([]);
        setTeamError(c instanceof Error?c.message
          :"Não foi possível carregar os colaboradores desta loja.");}});
  },[token,store,canWrite]);

  async function loadMore(){
    if(loading)return;setLoading(true);setError("");
    try{const rows=await routinesApi.trainingsMulti(token,activeStores,
      {participant_ids:fPersons,procedure_ids:fProcs,
        start:fStart||undefined,end:fEnd||undefined,
        limit:PAGE_SIZE,offset:entries.length});
      setEntries(prev=>{const ids=new Set(prev.map(e=>e.id));
        return [...prev,...rows.filter(r=>!ids.has(r.id))];});
      setHasMore(rows.length===PAGE_SIZE);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível carregar.");}
    finally{setLoading(false);}
  }
  useEffect(()=>{if(!recentId)return;
    const t=setTimeout(()=>setRecentId(""),12000);return()=>clearTimeout(t);},[recentId]);
  useEffect(()=>{if(!canWrite)void routinesApi.myTrainings(token).then(setMine).catch(()=>{});},[token,canWrite]);
  useEffect(()=>{
    if(!stepOpen)return;
    const onDown=(e:MouseEvent)=>{
      if(stepRef.current&&!stepRef.current.contains(e.target as Node))setStepOpen(false);};
    const onKey=(e:KeyboardEvent)=>{if(e.key==="Escape")setStepOpen(false);};
    document.addEventListener("mousedown",onDown);
    document.addEventListener("keydown",onKey);
    return ()=>{document.removeEventListener("mousedown",onDown);
      document.removeEventListener("keydown",onKey);};
  },[stepOpen]);

  async function newProcedure(){
    setWorking(true);setError("");
    try{const created=await proceduresApi.create(token,{title:"Novo procedimento",
      summary:"",applies_to_all:true,store_codes:[],content_html:""});
      const full=await proceduresApi.get(token,created.id);setEditing(full);}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao criar.");}
    finally{setWorking(false);}
  }

  async function confirmObsolete(){
    if(!obsoleting)return;const p=obsoleting;
    setWorking(true);setError("");setMessage("");
    try{await proceduresApi.obsolete(token,p.id);setObsoleting(null);await refreshProcs();
      setMessage(`${p.code} marcado como obsoleto.`);}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao marcar obsoleto.");setObsoleting(null);}
    finally{setWorking(false);}
  }

  async function confirmDelete(){
    if(!deleting)return;setWorking(true);setError("");setMessage("");
    try{await proceduresApi.deleteProcedure(token,deleting.id);
      setDeleting(null);await refreshProcs();setMessage("Procedimento excluído.");}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao excluir.");setDeleting(null);}
    finally{setWorking(false);}
  }

  function clearForm(){setParticipant("");setProcedureId("");setInstructor("");
    setDay("");setHour("");setSteps([]);setNote("");setAttach(null);
    setStepOpen(false);setFileKey(k=>k+1);}

  function startEdit(entry:TrainingEntry){setConfirmingEdit(entry);}

  function applyEdit(){const entry=confirmingEdit;if(!entry)return;
    setConfirmingEdit(null);setEditRec(entry);setStore(entry.store_code);
    setParticipant(entry.participant_id);setProcedureId(entry.procedure_id??"");
    setInstructor(entry.instructor);setDay(entry.happened_on.slice(0,10));
    setHour(entry.happened_on.slice(11,16));setSteps(entry.step.split(","));
    setNote(entry.note);setAttach(null);setFileKey(k=>k+1);
    requestAnimationFrame(()=>{
      formRef.current?.scrollIntoView({behavior:"smooth",block:"start"});
      setTimeout(()=>participantRef.current?.focus(),400);});
  }

  async function uploadAttach(rec:TrainingEntry,file:File):Promise<boolean>{
    try{await attachmentsApi.uploadTraining(token,rec.store_code,rec.id,file,
      rec.document?.revision??0);return true;}
    catch{setPendingUpload({entry:rec,file});return false;}
  }
  async function retryUpload(){
    if(!pendingUpload)return;const {entry,file}=pendingUpload;
    setWorking(true);setError("");
    if(await uploadAttach(entry,file)){
      setPendingUpload(null);const rows=await refreshTrainings();
      setSaved(rows?.find(r=>r.id===entry.id)??entry);}
    setWorking(false);
  }

  async function save(){
    if(working)return;
    setWorking(true);setError("");setMessage("");
    try{
      const step=STEP_OPTIONS.map(o=>o.value).filter(v=>steps.includes(v)).join(",") as TrainingStep;
      const body={participant_id:participant,procedure_id:procedureId||null,
        title:editRec?editRec.title:"",instructor,happened_on:day+"T"+hour+":00",step,note};
      if(editRec){
        await routinesApi.updateTraining(token,editRec.store_code,editRec.id,
          {...body,expected_revision:editRec.revision});
        if(attach){const ok=await uploadAttach(editRec,attach);setAttach(null);
          if(!ok){setPendingUpload({entry:editRec,file:attach});
            await refreshTrainings();return;}}
        await refreshTrainings();setMessage("Registro atualizado.");
        setEditRec(null);clearForm();
      }else{
        const created=await routinesApi.addTraining(token,store,body);
        const file=attach;clearForm();setRecentId(created.id);
        if(file){const ok=await uploadAttach(created,file);
          if(!ok){await refreshTrainings();return;}}
        const rows=await refreshTrainings();
        setSaved(rows?.find(r=>r.id===created.id)??created);
      }
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao registrar.");}
    finally{setWorking(false);}
  }

  async function confirmRemoveRec(){
    if(!removingRec)return;const entry=removingRec;
    setWorking(true);setError("");setMessage("");
    try{await routinesApi.deleteTraining(token,entry.store_code,entry.id,entry.revision);
      setRemovingRec(null);await refreshTrainings();
      setMessage("Registro excluído. Histórico preservado na auditoria.");}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao excluir.");setRemovingRec(null);}
    finally{setWorking(false);}
  }

  async function downloadDoc(e:TrainingEntry){if(e.document)await attachmentsApi.downloadTraining(token,e.store_code,e.id,e.document.name).catch(c=>setError(c.message));}
  async function confirmDeleteDoc(){
    if(!deletingDoc?.document)return;const e=deletingDoc;
    setWorking(true);setError("");
    try{await attachmentsApi.deleteTraining(token,e.store_code,e.id,e.document!.revision);
      if(details&&details.id===e.id)setDetails({...details,document:null,document_attached:false});
      setDeletingDoc(null);await refreshTrainings();setMessage("PDF anexado excluído.");}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao excluir.");setDeletingDoc(null);}
    finally{setWorking(false);}}

  function openDetails(e:TrainingEntry){scrollPos.current=window.scrollY;setDetails(e);}
  function closeDetails(){setDetails(null);
    requestAnimationFrame(()=>window.scrollTo(0,scrollPos.current));}

  const docModals=<>
    {deletingDoc&&<ConfirmDialog title="Excluir arquivo anexado" confirmLabel="Confirmar exclusão"
      busy={working} onCancel={()=>setDeletingDoc(null)} onConfirm={()=>void confirmDeleteDoc()}>
      <p>Tem certeza de que deseja excluir o arquivo {deletingDoc.document?.name} anexado ao treinamento
      de {deletingDoc.participant}?</p>
    </ConfirmDialog>}
    {pdfPreview&&<FilePreview token={token} store={pdfPreview.store_code} entry={pdfPreview}
      onClose={()=>setPdfPreview(null)} onDownload={()=>void downloadDoc(pdfPreview)}/>}
  </>;

  if(editing)return <ProcedureEditor token={token} procedure={editing}
    onClose={changed=>{setEditing(null);if(changed)void refreshProcs();}}/>;
  if(viewing)return <DocView token={token} procId={viewing.id} versionId={viewing.versionId}
    onBack={()=>setViewing(null)}/>;
  if(details)return <>
    <TrainingDetails entry={details} canWrite={canWrite} working={working}
      onBack={closeDetails}
      onViewProc={()=>{if(details.procedure_id)
        setViewing({id:details.procedure_id,versionId:details.procedure_version_id??undefined});}}
      onPreviewPdf={()=>setPdfPreview(details)}
      onDownloadPdf={()=>void downloadDoc(details)}
      onDeletePdf={()=>setDeletingDoc(details)}/>
    {docModals}
  </>;

  const hist=(canWrite?entries:mine);
  return <section>
    <div className="page-header"><div><div className="eyebrow">CLAREZA E CAPACITAÇÃO</div>
      <h1>Padrões e treinamentos</h1>
      <p>Procedimentos internos com editor completo e histórico de treinamentos por versão.</p></div>
    </div>
    <div className="tab-bar">
      <button role="tab" aria-selected={tab==="procedimentos"} className={tab==="procedimentos"?"tab active":"tab"}
        onClick={()=>setTab("procedimentos")}>Procedimentos</button>
      <button role="tab" aria-selected={tab==="treinamentos"} className={tab==="treinamentos"?"tab active":"tab"}
        onClick={()=>setTab("treinamentos")}>{canWrite?"Treinamentos":"Meus treinamentos"}</button>
    </div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    {deleting&&<ConfirmDialog title="Excluir procedimento" confirmLabel="Sim, excluir"
      busy={working} onCancel={()=>setDeleting(null)} onConfirm={()=>void confirmDelete()}>
      <p>Tem certeza de que deseja excluir o procedimento {deleting.code} — {deleting.title}?
      O documento deixará de aparecer nas consultas do Portal UMA. Suas versões e os registros
      históricos de treinamentos serão preservados para fins de auditoria.</p>
    </ConfirmDialog>}
    {obsoleting&&<ConfirmDialog title="Marcar procedimento como obsoleto"
      confirmLabel="Sim, marcar como obsoleto" danger={false}
      busy={working} onCancel={()=>setObsoleting(null)} onConfirm={()=>void confirmObsolete()}>
      <p>Tem certeza de que deseja marcar o procedimento {obsoleting.code} — {obsoleting.title} como
      obsoleto? O procedimento deixará de aparecer para os vendedores, mas suas versões e o histórico
      de treinamentos continuarão preservados para consulta administrativa.</p>
    </ConfirmDialog>}
    {removingRec&&<ConfirmDialog title="Excluir treinamento" confirmLabel="Confirmar exclusão"
      busy={working} onCancel={()=>setRemovingRec(null)} onConfirm={()=>void confirmRemoveRec()}>
      <p>Tem certeza de que deseja excluir o treinamento de {removingRec.participant}
      {" "}({removingRec.happened_on.slice(0,10)})? A exclusão é lógica e auditada.</p>
    </ConfirmDialog>}
    {saved&&<ConfirmDialog title="Treinamento registrado com sucesso!"
      confirmLabel="Ver registro" cancelLabel="Registrar outro treinamento" danger={false}
      onCancel={()=>setSaved(null)} onConfirm={()=>{setDetails(saved);setSaved(null);}}>
      <p>{saved.participant} — {saved.procedure}{saved.version?` (versão ${saved.version})`:""}</p>
    </ConfirmDialog>}
    {confirmingEdit&&<ConfirmDialog title="Editar treinamento"
      confirmLabel="Continuar para edição" danger={false}
      onCancel={()=>setConfirmingEdit(null)} onConfirm={applyEdit}>
      <p>Deseja editar o treinamento de {confirmingEdit.participant}
      {" — "}{confirmingEdit.procedure} ({confirmingEdit.happened_on.slice(0,10)})?
      O formulário será preenchido com os dados existentes; nenhuma alteração será gravada
      até você clicar em Salvar alterações.</p>
    </ConfirmDialog>}
    {pendingUpload&&<ConfirmDialog title="Anexo pendente"
      confirmLabel="Tentar enviar novamente" cancelLabel="Fechar" danger={false}
      busy={working} onCancel={()=>setPendingUpload(null)} onConfirm={()=>void retryUpload()}>
      <p>O treinamento de {pendingUpload.entry.participant} foi registrado, mas o arquivo
      {" "}{pendingUpload.file.name} não pôde ser enviado. O registro não será duplicado;
      você pode tentar enviar o anexo novamente.</p>
    </ConfirmDialog>}
    {docModals}

    {tab==="procedimentos"&&<>
      <div className="routine-filters">
        {canWrite&&<button className="btn-primary" disabled={working}
          onClick={()=>void newProcedure()}>+ Novo Procedimento</button>}
        <div className="filters-spacer"/>
        <label>Busca<input value={q} onChange={e=>setQ(e.target.value)} placeholder="Título ou código"/></label>
        {canWrite&&<label>Situação<select value={statusFilter} onChange={e=>setStatusFilter(e.target.value as typeof statusFilter)}>
          <option value="">Todas</option><option value="publicado">Publicado</option>
          <option value="rascunho">Rascunho</option><option value="obsoleto">Obsoleto</option>
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
          <td>{p.status==="obsoleto"?<span className="badge-obs">Obsoleto</span>
            :p.draft_version?<span className="badge-draft">Rascunho v{p.draft_version.version_label}</span>
            :<span className="badge-pub">Publicado v{p.current_version!.version_label}</span>}</td>
          <td>{new Date(p.updated_at).toLocaleDateString("pt-BR")}</td>
          <td><div className="routine-file-actions">
            <button className="btn-secondary" onClick={()=>setViewing({id:p.id})}>Abrir</button>
            {canWrite&&p.status!=="obsoleto"&&(p.draft_version||p.current_version)&&
              <button className="btn-secondary" onClick={async()=>setEditing(await proceduresApi.get(token,p.id))}>
                {p.draft_version?"Continuar edição":"Nova versão"}</button>}
            {canWrite&&p.status==="rascunho"&&!p.draft_version&&
              <button className="btn-secondary" onClick={async()=>setEditing(await proceduresApi.get(token,p.id))}>Editar</button>}
            {canWrite&&p.status==="publicado"&&
              <button className="btn-secondary" disabled={working} onClick={()=>setObsoleting(p)}>Obsoleto</button>}
            {canWrite&&(isSuperAdmin||!p.current_version)&&
              <button className="btn-secondary" disabled={working} onClick={()=>setDeleting(p)}>Excluir</button>}
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
          <td>{e.version}</td><td>{stepLabel(e.step)}</td>
          <td>{e.instructor}</td>
          <td><button className="btn-secondary" onClick={()=>openDetails(e)}>Visualizar</button></td>
        </tr>)}</tbody></table></div>
      {hist.length===0&&<p className="empty">Nenhum treinamento registrado.</p>}
    </article>}

    {tab==="treinamentos"&&canWrite&&<>
      <article ref={formRef} className={"panel routine-form-panel"+(editRec?" editing-form":"")}>
        <div className="panel-head"><div><h2>{editRec?"Editar treinamento":"Registrar treinamento"}</h2>
          <p>{editRec?`Revisão ${editRec.revision} · edição auditada`:"A versão publicada vigente é registrada automaticamente."}</p></div>
          {editRec&&<button className="btn-secondary" onClick={()=>{setEditRec(null);clearForm();}}>Cancelar edição</button>}</div>
        <div className="routine-form-grid">
          <label>Loja<select value={editRec?editRec.store_code:store} disabled={!!editRec}
            onChange={e=>setStore(e.target.value)}>
            {profile.stores.map(c=><option key={c} value={c}>{labelStore(c)}</option>)}</select></label>
          <label>Colaborador<select ref={participantRef} value={participant} onChange={e=>setParticipant(e.target.value)}>
            <option value="">Selecione…</option>
            {editRec&&participant&&!team.some(p=>p.id===participant)&&
              <option value={participant}>{editRec.participant}</option>}
            {team.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select>
            {teamError&&<span className="notice notice-error" role="alert">{teamError}</span>}</label>
          <label>Procedimento<select value={procedureId} onChange={e=>setProcedureId(e.target.value)}>
            <option value="">Selecione…</option>
            {procs.filter(p=>p.current_version).map(p=><option key={p.id} value={p.id}>
              {p.code} — {p.title} (v{p.current_version!.version_label})</option>)}
          </select></label>
          <label>Instrutor / responsável<input maxLength={90} value={instructor}
            onChange={e=>setInstructor(e.target.value)}/></label>
          <label>Data<input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
          <label>Horário<input type="time" value={hour} onChange={e=>setHour(e.target.value)}/></label>
          <div className="step-multi" ref={stepRef}>
            <span className="step-multi-label">Etapa</span>
            <button type="button" className="step-multi-btn" aria-haspopup="listbox"
              aria-expanded={stepOpen} onClick={()=>setStepOpen(o=>!o)}>
              <span>{steps.length
                ?STEP_OPTIONS.filter(o=>steps.includes(o.value)).map(o=>o.label).join(" + ")
                :"Selecione…"}</span><ChevronDown size={14}/></button>
            {stepOpen&&<div className="step-multi-panel" role="listbox" aria-multiselectable="true">
              {STEP_OPTIONS.map(o=><label key={o.value} className="check-line" role="option"
                aria-selected={steps.includes(o.value)}>
                <input type="checkbox" checked={steps.includes(o.value)}
                  onChange={e=>setSteps(prev=>e.target.checked
                    ?STEP_OPTIONS.map(x=>x.value).filter(v=>prev.includes(v)||v===o.value)
                    :prev.filter(v=>v!==o.value))}/>
                {o.label}</label>)}
            </div>}
          </div>
          <label className="routine-wide">Observações<input maxLength={350}
            value={note} onChange={e=>setNote(e.target.value)}/></label>
          <label className="routine-wide">Arquivo complementar (opcional)<input type="file" key={fileKey}
            disabled={working}
            accept=".jpg,.jpeg,.png,.webp,.pdf,.docx,.xlsx,.pptx,.txt,.csv,.mp4,.webm,.mov,.mp3,.wav"
            onChange={e=>setAttach(e.target.files?.[0]??null)}/></label>
          {editRec?.document&&<p className="small-note routine-wide">Anexo atual:
            {" "}{editRec.document.name} · {fmtSize(editRec.document.size)}
            {" — selecionar um novo arquivo substitui o atual."}</p>}
        </div>
        <button className="btn-primary" disabled={working||!participant||!procedureId
          ||!instructor.trim()||!steps.length||!day||!hour}
          onClick={()=>void save()}>{working?"Salvando…":editRec?"Salvar alterações":"Registrar participação"}</button>
      </article>
      <article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Histórico de treinamentos</h2>
          <p>Registros administrativos com edição e exclusão lógica auditadas.</p></div></div>
        <div className="routine-filters">
          <MultiSelect label="Loja" empty="Todas" value={filterStores} onChange={setFilterStores}
            options={profile.stores.map(c=>({value:c,label:labelStore(c)}))}/>
          <MultiSelect label="Colaborador" empty="Todos" value={fPersons} onChange={setFPersons}
            options={people.map(p=>({value:p.id,label:p.name}))}/>
          <MultiSelect label="Procedimento" empty="Todos" value={fProcs} onChange={setFProcs}
            options={[...new Map([
              ...procs.filter(p=>p.current_version)
                .map(p=>[p.id,`${p.code} — ${p.title}`] as [string,string]),
              ...histProcs.map(h=>[h.procedure_id,h.procedure] as [string,string]),
            ]).entries()].map(([value,label])=>({value,label}))}/>
          <label>De<input type="date" value={fStart} onChange={e=>setFStart(e.target.value)}/></label>
          <label>Até<input type="date" value={fEnd} onChange={e=>setFEnd(e.target.value)}/></label>
        </div>
        {loading&&<p role="status">Consultando registros…</p>}
        <div className="table-wrap"><table><thead><tr><th>Data</th>
          {activeStores.length>1&&<th>Loja</th>}<th>Colaborador</th>
          <th>Procedimento</th><th>Versão</th><th>Etapa</th><th>Anexo</th><th>Ações</th></tr></thead>
          <tbody>{entries.map(e=><tr key={e.id} className={e.id===recentId?"row-new":""}>
            <td>{new Date(e.happened_on).toLocaleString("pt-BR")}</td>
            {activeStores.length>1&&<td>{labelStore(e.store_code)}</td>}
            <td>{e.participant}</td>
            <td>{e.procedure}</td><td>{e.version}</td>
            <td>{stepLabel(e.step)}</td>
            <td>{e.document?<span className="count">Anexado</span>:"—"}</td>
            <td><div className="routine-file-actions">
              <button className="btn-secondary" onClick={()=>openDetails(e)}>Visualizar</button>
              <button className="btn-secondary" onClick={()=>startEdit(e)}>Editar</button>
              {isSuperAdmin&&<button className="btn-secondary" disabled={working} onClick={()=>setRemovingRec(e)}>Excluir</button>}
            </div></td></tr>)}</tbody></table></div>
        {entries.length===0&&!loading&&<p className="empty">Nenhum treinamento encontrado.</p>}
        {hasMore&&<button className="btn-secondary" disabled={loading}
          onClick={()=>void loadMore()}>Carregar mais registros</button>}
      </article>
    </>}
  </section>;
}
