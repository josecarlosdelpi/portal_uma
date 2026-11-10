import {useEffect,useId,useRef} from "react";
import type {ReactNode} from "react";

type Props={
  title:string;
  children:ReactNode;
  confirmLabel:string;
  cancelLabel?:string;
  danger?:boolean;
  busy?:boolean;
  onConfirm:()=>void;
  onCancel:()=>void;
};

/** Modal de confirmacao padrao do Portal UMA (substitui window.confirm).
    Fecha com Esc e clique no backdrop; foco inicial no botao de confirmar. */
export function ConfirmDialog({title,children,confirmLabel,cancelLabel="Cancelar",
  danger=true,busy=false,onConfirm,onCancel}:Props){
  const titleId=useId();
  const confirmRef=useRef<HTMLButtonElement>(null);
  useEffect(()=>{
    const onKey=(e:KeyboardEvent)=>{if(e.key==="Escape"&&!busy)onCancel();};
    document.addEventListener("keydown",onKey);
    confirmRef.current?.focus();
    return ()=>document.removeEventListener("keydown",onKey);
  },[busy,onCancel]);
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby={titleId}
    onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onCancel();}}>
    <div className="modal-card"><h3 id={titleId}>{title}</h3>
      {children}
      <div className="modal-actions">
        <button type="button" className="btn-secondary" disabled={busy} onClick={onCancel}>
          {cancelLabel}</button>
        <button type="button" ref={confirmRef} className={danger?"btn-danger":"btn-primary"}
          disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
      </div></div></div>;
}
