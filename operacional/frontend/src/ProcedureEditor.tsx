import {useCallback,useEffect,useRef,useState} from "react";
import {EditorContent,useEditor} from "@tiptap/react";
import type {EditorView} from "@tiptap/pm/view";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Image from "@tiptap/extension-image";
import {Table} from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import {TextStyle} from "@tiptap/extension-text-style";
import {Extension} from "@tiptap/core";
import type {Procedure,VersionInfo} from "./proceduresApi";
import {proceduresApi,hydrateImages} from "./proceduresApi";
import {stores,labelStore} from "./catalog";
import {ConfirmDialog} from "./ConfirmDialog";

const FontSize=Extension.create({
  name:"fontSize",
  addGlobalAttributes(){return[{types:["textStyle"],attributes:{fontSize:{
    default:null,parseHTML:e=>e.style.fontSize||null,
    renderHTML:a=>a.fontSize?{style:`font-size:${a.fontSize}`}:{},
  }}}];},
});

const ResizableImage=Image.extend({
  addAttributes(){
    return{
      ...this.parent?.(),
      width:{
        default:null,
        parseHTML:(e:HTMLElement)=>e.getAttribute("width")||e.style.width||null,
        renderHTML:(a:Record<string,unknown>)=>a.width?{style:`width:${a.width}`}:{},
      },
    };
  },
  addNodeView(){
    return({node,editor,getPos})=>{
      const wrap=document.createElement("span");
      wrap.className="img-wrap";
      wrap.style.width=node.attrs.width?String(node.attrs.width):"auto";
      const img=document.createElement("img");
      img.dataset.apiSrc=node.attrs.src;
      img.src=node.attrs.src;img.alt=node.attrs.alt||"";
      wrap.appendChild(img);
      const handle=document.createElement("span");
      handle.className="img-resize-handle";
      handle.contentEditable="false";
      wrap.appendChild(handle);
      handle.addEventListener("mousedown",e=>{
        e.preventDefault();e.stopPropagation();
        const startX=e.clientX;const startW=wrap.getBoundingClientRect().width;
        const limit=editor.view.dom.clientWidth||1;
        const move=(ev:MouseEvent)=>{
          const pct=Math.min(100,Math.max(5,Math.round((startW+ev.clientX-startX)/limit*100)));
          wrap.style.width=pct+"%";
        };
        const up=(ev:MouseEvent)=>{
          document.removeEventListener("mousemove",move);
          document.removeEventListener("mouseup",up);
          const pct=Math.min(100,Math.max(5,Math.round((startW+ev.clientX-startX)/limit*100)));
          const pos=typeof getPos==="function"?getPos():undefined;
          if(pos!==undefined){
            editor.chain().command(({tr})=>{
              tr.setNodeMarkup(pos,undefined,{...node.attrs,width:pct+"%"});return true;
            }).run();
          }
        };
        document.addEventListener("mousemove",move);
        document.addEventListener("mouseup",up);
      });
      return{
        dom:wrap,
        update(updated){
          if(updated.type.name!==node.type.name)return false;
          wrap.style.width=updated.attrs.width?String(updated.attrs.width):"auto";
          // Preserva o blob autenticado quando o src nao mudou.
          if(updated.attrs.src!==img.dataset.apiSrc){
            img.dataset.apiSrc=updated.attrs.src;img.src=updated.attrs.src;
          }
          return true;
        },
        selectNode(){wrap.classList.add("img-selected");},
        deselectNode(){wrap.classList.remove("img-selected");},
      };
    };
  },
});

/** Insere imagens enviadas para upload na posicao do cursor/soltura. */
function insertUploaded(view:EditorView,files:File[],upload:(f:File)=>Promise<string>,
                        onError:(m:string)=>void,pos?:number){
  for(const file of files){
    void upload(file).then(url=>{
      const node=view.state.schema.nodes.image.create({src:url});
      const tr=pos===undefined?view.state.tr.replaceSelectionWith(node)
        :view.state.tr.insert(pos,node);
      view.dispatch(tr);
    }).catch(()=>onError("Não foi possível inserir a imagem. Tente novamente."));
  }
}

type Props={token:string;procedure:Procedure;onClose:(changed:boolean)=>void};

export function ProcedureEditor({token,procedure,onClose}:Props){
  const [proc,setProc]=useState(procedure);
  const [title,setTitle]=useState(procedure.title);
  const [summary,setSummary]=useState(procedure.summary);
  const [allStores,setAllStores]=useState(procedure.applies_to_all);
  const [picked,setPicked]=useState<string[]>(procedure.stores);
  const [versions,setVersions]=useState<VersionInfo[]>([]);
  const [viewing,setViewing]=useState<VersionInfo|null>(null);
  const [working,setWorking]=useState(false);
  const [confirmingObs,setConfirmingObs]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const draft=proc.draft_version;
  const [editingMode,setEditingMode]=useState(!!draft);
  const canEdit=editingMode;
  const viewRef=useRef<HTMLDivElement>(null);

  const upload=useCallback(async(file:File)=>{
    const result=await proceduresApi.uploadFile(token,proc.id,file);
    return result.url;
  },[token,proc.id]);
  const onUploadError=useCallback((m:string)=>setError(m),[]);

  const editor=useEditor({
    extensions:[StarterKit,Underline,TextStyle,FontSize,ResizableImage.configure({inline:false}),
      Table.configure({resizable:false}),TableRow,TableCell,TableHeader],
    content:proc.content_html||"",
    editable:editingMode,
    onUpdate:({editor:e})=>{void hydrateImages(e.view.dom,token);},
    editorProps:{
      attributes:{class:"doc-content",role:"textbox","aria-label":"Conteúdo do procedimento"},
      handlePaste:(view,event)=>{
        const files=Array.from(event.clipboardData?.files??[]).filter(f=>f.type.startsWith("image/"));
        if(!files.length)return false;
        event.preventDefault();
        insertUploaded(view,files,upload,onUploadError);
        return true;
      },
      handleDrop:(view,event)=>{
        const files=Array.from(event.dataTransfer?.files??[]).filter(f=>f.type.startsWith("image/"));
        if(!files.length)return false;
        event.preventDefault();
        const pos=view.posAtCoords({left:event.clientX,top:event.clientY})?.pos;
        insertUploaded(view,files,upload,onUploadError,pos);
        return true;
      },
    },
  });

  useEffect(()=>{void proceduresApi.versions(token,proc.id).then(setVersions).catch(()=>{});},[token,proc.id]);
  useEffect(()=>{if(editor)void hydrateImages(editor.view.dom,token);},[editor,token]);
  useEffect(()=>{void hydrateImages(viewRef.current,token);},[viewing,token]);

  async function pickImage(){
    const input=document.createElement("input");
    input.type="file";input.accept="image/png,image/jpeg,image/webp";
    input.onchange=async()=>{
      const file=input.files?.[0];if(!file||!editor)return;
      setError("");
      insertUploaded(editor.view,[file],upload,onUploadError);
    };
    input.click();
  }

  async function save(publish:boolean){
    if(!editor)return;
    setWorking(true);setError("");setMessage("");
    try{
      const saved=await proceduresApi.save(token,proc.id,{
        title,summary,applies_to_all:allStores,store_codes:allStores?[]:picked,
        content_html:editor.getHTML(),expected_revision:draft?.revision??1,
      });
      setProc(saved);
      if(publish){
        const rev=saved.draft_version?.revision??((draft?.revision??0)+1);
        const done=await proceduresApi.publish(token,proc.id,rev);
        setProc(done);setMessage("Procedimento publicado.");
        onClose(true);
      }else{
        setMessage("Rascunho salvo. Você pode continuar editando depois.");
        void proceduresApi.versions(token,proc.id).then(setVersions).catch(()=>{});
      }
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao salvar.");}
    finally{setWorking(false);}
  }

  async function confirmObsolete(){
    setWorking(true);setError("");
    try{setProc(await proceduresApi.obsolete(token,proc.id));
      setConfirmingObs(false);setMessage("Procedimento marcado como obsoleto.");}
    catch(c){setError(c instanceof Error?c.message:"Falha ao marcar obsoleto.");setConfirmingObs(false);}
    finally{setWorking(false);}
  }

  async function openVersion(v:VersionInfo){
    try{const full=await proceduresApi.getVersion(token,proc.id,v.id);setViewing(full);}
    catch{setError("Não foi possível abrir a versão.");}
  }

  if(viewing)return <section>
    <div className="page-header"><div><div className="eyebrow">HISTÓRICO</div>
      <h1>{proc.code} — versão {viewing.version_label}</h1>
      <p>{viewing.status==="publicado"?"Publicada":"Rascunho"} · {viewing.published_at?new Date(viewing.published_at).toLocaleString("pt-BR"):"sem publicação"}</p></div>
      <button className="btn-secondary" onClick={()=>setViewing(null)}>Voltar ao editor</button></div>
    <article className="panel"><div ref={viewRef} className="doc-content doc-readonly"
      dangerouslySetInnerHTML={{__html:viewing.content_html??""}}/></article>
  </section>;

  const t=(chain:string)=>()=>{editor?.chain().focus();
    (editor?.chain().focus() as any)[chain]().run();};

  const subtitle=draft
    ?(canEdit?`Rascunho v${draft.version_label} · revisão ${draft.revision} · salve quando quiser`
      :`Rascunho v${draft.version_label} em andamento`)
    :canEdit?"Nova versão em elaboração":"Publicado";

  return <section>
    <div className="page-header"><div><div className="eyebrow">EDITOR DE DOCUMENTO</div>
      <h1>{proc.code} · {title||"Sem título"}</h1>
      <p>{subtitle}</p></div>
      <div className="page-actions">
        <button className="btn-secondary" onClick={()=>onClose(true)}>Voltar</button>
        {!canEdit&&proc.current_version&&!draft&&<button className="btn-primary" onClick={()=>{
          setEditingMode(true);editor?.setEditable(true);editor?.commands.focus();
        }}>Criar nova versão</button>}
        {proc.current_version&&proc.status!=="obsoleto"&&<button className="btn-secondary" disabled={working}
          onClick={()=>setConfirmingObs(true)}>Obsoleto</button>}
        {!canEdit&&draft&&<button className="btn-primary" onClick={()=>{
          setEditingMode(true);editor?.setEditable(true);editor?.commands.focus();
        }}>Continuar edição</button>}
        {canEdit&&<button className="btn-secondary" disabled={working} onClick={()=>void save(false)}>
          {working?"Salvando…":"Salvar rascunho"}</button>}
        {canEdit&&<button className="btn-primary" disabled={working} onClick={()=>void save(true)}>Publicar</button>}
      </div></div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <article className="panel">
      <div className="routine-form-grid">
        <label>Título<input maxLength={140} value={title} disabled={!canEdit}
          onChange={e=>setTitle(e.target.value)}/></label>
        <label>Resumo (opcional)<input maxLength={300} value={summary} disabled={!canEdit}
          onChange={e=>setSummary(e.target.value)}/></label>
        <label>Aplicabilidade<select value={allStores?"all":"picked"} disabled={!canEdit}
          onChange={e=>setAllStores(e.target.value==="all")}>
          <option value="all">Todas as lojas</option>
          <option value="picked">Lojas selecionadas</option>
        </select></label>
        {!allStores&&<div className="routine-wide">
          {Object.keys(stores).map(code=><label key={code} className="check-line">
            <input type="checkbox" checked={picked.includes(code)} disabled={!canEdit}
              onChange={e=>setPicked(prev=>e.target.checked?[...prev,code]:prev.filter(x=>x!==code))}/>
            {labelStore(code)}</label>)}
        </div>}
      </div>
    </article>
    {canEdit&&<div className="editor-toolbar" role="toolbar" aria-label="Formatação">
      <button type="button" onClick={t("toggleBold")}><b>B</b></button>
      <button type="button" onClick={t("toggleItalic")}><i>I</i></button>
      <button type="button" onClick={t("toggleUnderline")}><u>U</u></button>
      <button type="button" onClick={t("toggleStrike")}><s>S</s></button>
      <select defaultValue="" onChange={e=>{if(!e.target.value)return;
        if(e.target.value==="p")editor?.chain().focus().setParagraph().run();
        else (editor?.chain().focus() as any).setHeading({level:Number(e.target.value)}).run();
        e.target.value="";}}>
        <option value="" disabled>Estilo…</option><option value="p">Texto</option>
        <option value="1">Título 1</option><option value="2">Título 2</option><option value="3">Título 3</option>
      </select>
      <select defaultValue="" onChange={e=>{if(!e.target.value)return;
        editor?.chain().focus().setMark("textStyle",{fontSize:e.target.value}).run();
        e.target.value="";}}>
        <option value="" disabled>Tamanho…</option><option value="12px">Pequeno</option>
        <option value="16px">Normal</option><option value="22px">Grande</option><option value="28px">Maior</option>
      </select>
      <button type="button" onClick={t("toggleBulletList")}>• Lista</button>
      <button type="button" onClick={t("toggleOrderedList")}>1. Lista</button>
      <button type="button" onClick={()=>editor?.chain().focus().insertTable({rows:3,cols:3,withHeaderRow:true}).run()}>Tabela</button>
      <button type="button" onClick={()=>void pickImage()}>Imagem…</button>
      <select defaultValue="" onChange={e=>{if(!e.target.value)return;
        editor?.chain().focus().updateAttributes("image",{width:e.target.value}).run();
        e.target.value="";}}>
        <option value="" disabled>Largura img…</option>
        <option value="25%">25%</option><option value="50%">50%</option>
        <option value="75%">75%</option><option value="100%">100%</option>
      </select>
      <button type="button" onClick={t("undo")}>↶ Desfazer</button>
      <button type="button" onClick={t("redo")}>↷ Refazer</button>
      <span className="toolbar-hint">Cole imagens com Ctrl+V direto no texto</span>
    </div>}
    <article className="panel editor-panel"><EditorContent editor={editor}/></article>
    {versions.length>0&&<article className="panel">
      <div className="panel-head"><div><h2>Versões</h2><p>Histórico do documento.</p></div></div>
      <div className="table-wrap"><table><thead><tr><th>Versão</th><th>Situação</th>
        <th>Criada em</th><th>Publicada em</th><th></th></tr></thead>
        <tbody>{versions.map(v=><tr key={v.id}>
          <td>v{v.version_label}</td>
          <td>{v.status==="publicado"?"Publicada":"Rascunho"}</td>
          <td>{new Date(v.created_at).toLocaleString("pt-BR")}</td>
          <td>{v.published_at?new Date(v.published_at).toLocaleString("pt-BR"):"—"}</td>
          <td><button className="btn-secondary" onClick={()=>void openVersion(v)}>Abrir</button></td>
        </tr>)}</tbody></table></div>
    </article>}
    {confirmingObs&&<ConfirmDialog title="Marcar procedimento como obsoleto"
      confirmLabel="Sim, marcar como obsoleto" danger={false}
      busy={working} onCancel={()=>setConfirmingObs(false)} onConfirm={()=>void confirmObsolete()}>
      <p>Tem certeza de que deseja marcar o procedimento {proc.code} — {proc.title} como obsoleto?
      O procedimento deixará de aparecer para os vendedores, mas suas versões e o histórico de
      treinamentos continuarão preservados para consulta administrativa.</p>
    </ConfirmDialog>}
  </section>;
}
