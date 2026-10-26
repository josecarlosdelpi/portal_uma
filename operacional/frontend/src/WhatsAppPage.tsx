import {useCallback,useEffect,useMemo,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {attachmentsApi} from "./attachmentsApi";
import {routinesApi,type WhatsAppSnapshot,type InstagramSnapshot,type WhatsAppPost} from "./routinesApi";

type Props={token:string;profile:MyProfile};
const currentMonth=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");};
const shortDays=["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];
const statusLabel=(s:string)=>s==="publicado"?"Publicado":s==="arte_pronta"?"Arte pronta":"Planejado";
function businessDates(year:number,month:number):string[]{
  const days=[];
  for(let d=1;d<=new Date(year,month,0).getDate();d++){
    const date=new Date(year,month-1,d,12);
    if(date.getDay()===0||date.getDay()===6)continue;
    days.push(year+"-"+String(month).padStart(2,"0")+"-"+String(d).padStart(2,"0"));
  }
  return days;
}

export function WhatsAppPage({token,profile}:Props){
  const [period,setPeriod]=useState(currentMonth);
  const [posts,setPosts]=useState<WhatsAppSnapshot|null>(null);
  const [instagram,setInstagram]=useState<InstagramSnapshot|null>(null);
  const [day,setDay]=useState("");
  const [code,setCode]=useState("");
  const [category,setCategory]=useState("");
  const [note,setNote]=useState("");
  const [status,setStatus]=useState<WhatsAppPost["status"]>("planejado");
  const [offReason,setOffReason]=useState("");
  const [artFile,setArtFile]=useState<File|null>(null);
  const [evidenceFile,setEvidenceFile]=useState<File|null>(null);
  const [igStore,setIgStore]=useState(profile.stores[0]??"");
  const [igPlanned,setIgPlanned]=useState("0");
  const [igDone,setIgDone]=useState("0");
  const [working,setWorking]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [year,month]=period.split("-").map(Number);
  const dates=useMemo(()=>businessDates(year,month),[year,month]);
  const canWrite=profile.profile!=="seller";
  const hasStatus=profile.features.whatsapp_status;
  const hasInstagram=profile.features.instagram;

  const refresh=useCallback(async()=>{
    if(!year||!month)return;
    setLoading(true);setError("");
    try{
      const [wa,insta]=await Promise.all([
        hasStatus?routinesApi.whatsapp(token,year,month):Promise.resolve(null),
        hasInstagram?routinesApi.instagram(token,year,month):Promise.resolve(null)
      ]);
      setPosts(wa);setInstagram(insta);
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao carregar calendário.");}
    finally{setLoading(false);}
  },[token,year,month,hasStatus,hasInstagram]);
  useEffect(()=>{void refresh();},[refresh]);
  useEffect(()=>{
    if(dates.length&&!dates.includes(day))setDay(dates[0]);
  },[dates,day]);
  const selected=posts?.posts.find(x=>x.date===day);
  const dayOff=posts?.days_off.find(x=>x.date===day);
  const attachments=selected?.files??{};
  useEffect(()=>{
    setCode(selected?.product_code??"");setCategory(selected?.category??"");
    setNote(selected?.note??"");setStatus(selected?.status??"planejado");
    setOffReason(dayOff?.reason??"");
    setArtFile(null);setEvidenceFile(null);
  },[day,posts,selected?.product_code,selected?.revision,dayOff?.reason]);
  const currentIg=instagram?.stores.find(x=>x.store_code===igStore);
  useEffect(()=>{
    setIgPlanned(String(currentIg?.planned??0));
    setIgDone(String(currentIg?.completed??0));
  },[currentIg?.revision,currentIg?.planned,currentIg?.completed,igStore]);

  async function perform(fn:()=>Promise<unknown>,msg:string){
    setWorking(true);setError("");setMessage("");
    try{await fn();await refresh();setMessage(msg);}
    catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível salvar.");}
    finally{setWorking(false);}
  }


  async function downloadFile(kind:"art"|"evidence",name:string){
    setError("");
    try{await attachmentsApi.downloadWhatsApp(token,day,kind,name);}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao baixar anexo.");}
  }

  const attachmentRows=[
    {kind:"art" as const, label:"Arte do Status", file:artFile,setFile:setArtFile,
      current:attachments.art},
    {kind:"evidence" as const,label:"Comprovante da publicação",file:evidenceFile,
      setFile:setEvidenceFile,current:attachments.evidence},
  ];
  const planned=posts?.posts.length??0;
  const ready=posts?.posts.filter(x=>x.status==="arte_pronta").length??0;
  const published=posts?.posts.filter(x=>x.status==="publicado").length??0;
  return <section>
    <div className="page-header"><div><div className="eyebrow">MARKETING E PLANEJAMENTO</div>
      <h1>Status do WhatsApp</h1><p>Calendário único da UMA, sem repetir o mesmo código de produto durante o ano.</p>
    </div></div>
    <div className="notice notice-amber">
      O controle de códigos e publicações é manual. As artes e os comprovantes podem
      ser anexados em armazenamento privado, mas o envio automático ao WhatsApp ainda não está conectado.</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters"><label>Mês de referência<input type="month" min="2020-01" max="2100-12"
      value={period} onChange={e=>setPeriod(e.target.value)}/></label>
      <span className="chip">Seg–sex · calendário único das três lojas</span></div>
    {loading&&<p role="status">Carregando calendário…</p>}
    {hasStatus&&posts&&!loading&&<>
      <div className="routine-kpis">
        <div className="panel"><span>Dias programados</span><strong>{planned}</strong><small>Produtos sem repetição anual</small></div>
        <div className="panel"><span>Arte pronta</span><strong>{ready}</strong><small>Etapa manual · anexo opcional</small></div>
        <div className="panel"><span>Publicados</span><strong>{published}</strong><small>Controle manual das publicações</small></div>
      </div>
      <article className="panel">
        <div className="panel-head"><div><h2>Calendário do mês</h2>
          <p>Segunda promoções, terça lançamentos, quarta linha leve, quinta linha pesada, sexta conexões e acessórios.</p></div></div>
        <div className="routine-calendar">
          {dates.map(d=>{
            const entry=posts.posts.find(p=>p.date===d);
            const excluded=posts.days_off.some(x=>x.date===d);
            const dow=new Date(year,month-1,Number(d.slice(-2)),12).getDay();
            return <button type="button" key={d} className={"routine-cal-day"+
              (day===d?" selected":"")+(excluded?" off":"")+(entry?.status==="publicado"?" published":"")}
              onClick={()=>setDay(d)}>
              <strong>{d.slice(-2)}</strong><small>{shortDays[dow]}</small>
              <span>{excluded?"Sem postagem":entry?statusLabel(entry.status):"Sem produto"}</span>
            </button>;
          })}
        </div>
      </article>
      {canWrite&&<article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Programar ou atualizar uma data</h2>
          <p>{day.split("-").reverse().join("/")} · anexos enviados separadamente após salvar o produto.</p></div></div>
        <div className="routine-form-grid">
          <label>Código do produto<input maxLength={55} value={code} disabled={!!dayOff}
            onChange={e=>setCode(e.target.value)} placeholder="Ex.: MM 22002"/></label>
          <label>Etapa<select value={status} disabled={!!dayOff}
            onChange={e=>setStatus(e.target.value as WhatsAppPost["status"])}>
            <option value="planejado">Programado</option>
            <option value="arte_pronta">Arte pronta (confirmação manual)</option>
            <option value="publicado">Publicado (confirmação manual)</option>
          </select></label>
          <label className="routine-wide">Categoria / tema<input maxLength={120}
            value={category} disabled={!!dayOff} onChange={e=>setCategory(e.target.value)}/></label>
          <label className="routine-wide">Observações<input maxLength={450} value={note}
            disabled={!!dayOff} onChange={e=>setNote(e.target.value)}/></label>
        </div>
        <button className="btn-primary" disabled={working||!day||!!dayOff||!code.trim()}
          onClick={()=>void perform(()=>routinesApi.saveWhatsApp(token,day,{
            product_code:code,category,note,status,expected_revision:selected?.revision??0
          }),"Planejamento atualizado; repetição anual verificada.")}>Salvar programação</button>
        {selected&&<button className="btn-secondary" disabled={working}
          onClick={()=>{
            if(!window.confirm("Excluir o planejamento desta data? A exclusão ficará na auditoria."))return;
            void perform(()=>routinesApi.deleteWhatsApp(token,day,selected.revision),
              "Planejamento removido com registro de auditoria.");
          }}>Excluir programação deste dia</button>}
        <div className="routine-dayoff">
          <label><input type="checkbox" checked={!!dayOff} disabled={working||!!selected}
            onChange={e=>void perform(()=>routinesApi.dayOff(token,day,e.target.checked,offReason),
              "Exceção do calendário atualizada.")}/> Sem postagem nesta data (feriado/fechamento)</label>
          <input maxLength={150} placeholder="Motivo opcional" value={offReason}
            disabled={!!selected} onChange={e=>setOffReason(e.target.value)}/>
          {!!selected&&<small>Para marcar sem postagem, é necessário retirar a programação existente desta data.</small>}
        </div>
      </article>}

      {selected&&<article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Artes e comprovantes da data</h2>
          <p>Arquivos privados protegidos por login. Aceita JPG, PNG ou WebP, até 3 MB cada.</p>
        </div></div>
        <div className="routine-file-list">
          {attachmentRows.map(row=><div className="routine-file-item" key={row.kind}>
            <div><strong>{row.label}</strong>
              <p>{row.current?
                row.current.name+" · "+(row.current.size/1024).toFixed(0)+" KB":
                "Nenhum anexo enviado"}</p>
            </div>
            <div className="routine-file-actions">
              {row.current&&<button className="btn-secondary" disabled={working}
                onClick={()=>void downloadFile(row.kind,row.current!.name)}>Baixar</button>}
              {canWrite&&<>
                <input aria-label={"Selecionar "+row.label} type="file"
                  key={day+"-"+row.kind+"-"+(row.current?.revision??0)}
                  accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
                  disabled={working} onChange={e=>row.setFile(e.target.files?.[0]??null)}/>
                <button className="btn-primary" disabled={working||!row.file}
                  onClick={()=>void perform(async()=>{
                    if(!row.file)return;
                    await attachmentsApi.uploadWhatsApp(
                      token,day,row.kind,row.file,row.current?.revision??0
                    );
                    row.setFile(null);
                  },row.label+" anexado com sucesso.")}>Anexar / substituir</button>
                {row.current&&<button className="btn-secondary" disabled={working}
                  onClick={()=>{
                    if(!window.confirm("Remover "+row.label+"? O histórico da operação será mantido."))return;
                    void perform(()=>attachmentsApi.deleteWhatsApp(
                      token,day,row.kind,row.current!.revision
                    ),"Anexo removido. A exclusão foi auditada.");
                  }}>Excluir anexo</button>}
              </>}
            </div>
          </div>)}
        </div>
      </article>}
      <article className="panel routine-form-panel"><div className="panel-head"><div><h2>Histórico do calendário</h2>
        <p>Produtos planejados e confirmados no mês.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Produto</th><th>Categoria</th>
          <th>Etapa</th><th>Publicação</th><th>Anexos</th></tr></thead><tbody>{posts.posts.map(p=><tr key={p.date}>
          <td>{p.date}</td><td>{p.product_code}</td><td>{p.category||"—"}</td>
          <td>{statusLabel(p.status)}</td><td>{p.published_on?"Registrada":"Pendente"}</td><td>{[p.has_art_file?"Arte":null,p.has_evidence_file?"Comprovante":null].filter(Boolean).join(" e ")||"—"}</td>
        </tr>)}</tbody></table></div>
      </article>
    </>}
    {hasInstagram&&instagram&&!loading&&<article className="panel routine-form-panel">
      <div className="panel-head"><div><h2>Instagram — posts previstos e realizados</h2>
        <p>Contagem mensal por loja, sem integração automática.</p></div></div>
      <div className="routine-storecards">
        {instagram.stores.map(row=><div className="routine-instagram-card" key={row.store_code}>
          <strong>{labelStore(row.store_code)}</strong>
          <span>{row.completed===null?"Sem dados":row.completed} / {row.planned===null?"Sem dados":row.planned}</span>
          <small>Posts realizados / previstos</small>
        </div>)}
      </div>
      {canWrite&&<div className="routine-form-grid">
        <label>Loja<select value={igStore} onChange={e=>setIgStore(e.target.value)}>
          {instagram.stores.map(row=><option value={row.store_code} key={row.store_code}>{labelStore(row.store_code)}</option>)}</select></label>
        <label>Quantidade prevista<input type="number" step={1} min={0} max={500}
          value={igPlanned} onChange={e=>setIgPlanned(e.target.value)}/></label>
        <label>Posts realizados<input type="number" step={1} min={0} max={500}
          value={igDone} onChange={e=>setIgDone(e.target.value)}/></label>
        <button className="btn-primary" disabled={working||!igStore||
          ![igPlanned,igDone].every(x=>x!==""&&Number.isInteger(Number(x))&&Number(x)>=0&&Number(x)<=500)}
          onClick={()=>void perform(()=>routinesApi.saveInstagram(token,igStore,year,month,
            Number(igPlanned),Number(igDone),currentIg?.revision??0),"Resultado do Instagram atualizado.")}>
            Salvar Instagram</button>
      </div>}
    </article>}
  </section>;
}
