import {useState} from "react";
import {api,type LocalCreateAccount} from "./api";
import {labelStore} from "./catalog";

const stores=["JOINVILLE","ITAJAI","TUBARAO"];

export function TemporaryPasswordNotice({username,password,onClose}:{
  username:string;password:string;onClose:()=>void
}){
  const [copied,setCopied]=useState(false);
  async function copy(){
    try{await navigator.clipboard.writeText("Usuário: "+username+"\nSenha provisória: "+password);setCopied(true);}
    catch{setCopied(false);}
  }
  return <div className="local-secret-once" role="status">
    <h3>Senha provisória criada</h3>
    <p>Aparece apenas nesta operação. Entregue ao colaborador;
      ela expira em 72 horas e será trocada no primeiro acesso.</p>
    <small>Usuário</small><code>{username}</code>
    <small>Senha provisória</small><code>{password}</code>
    <div className="btn-row">
      <button className="btn-primary" type="button" onClick={()=>void copy()}>{
        copied?"Copiado":"Copiar usuário e senha"
      }</button>
      <button className="btn-secondary" type="button" onClick={onClose}>Ocultar senha</button>
    </div>
    <p className="small-note">Não será possível consultar esta senha novamente.
      Caso precise, gere outra na lista de usuários.</p>
  </div>;
}

export function AccountsManager({token,onCreated}:{
  token:string;onCreated:()=>Promise<void>
}){
  const [show,setShow]=useState(false);
  const [name,setName]=useState("");
  const [username,setUsername]=useState("");
  const [role,setRole]=useState<"administrator"|"seller">("seller");
  const [store,setStore]=useState("JOINVILLE");
  const [result,setResult]=useState<LocalCreateAccount|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);

  async function create(){
    setBusy(true);setError("");setResult(null);
    try{
      const row=await api.createLocalUser(token,{
        username:username.trim(),display_name:name.trim(),profile:role,
        store_code:role==="seller"?store:null
      });
      setResult(row);setShow(false);setName("");setUsername("");
      await onCreated();
    }catch(cause){setError(cause instanceof Error?cause.message:"Falha ao cadastrar.");}
    finally{setBusy(false);}
  }
  return <section className="panel access-invitations">
    <div className="panel-head"><div><h2>Cadastro de colaboradores</h2>
      <p>Crie acessos com usuário e senha provisória, sem e-mail.</p></div>
      <button className="btn-primary" onClick={()=>{
        setShow(!show);setResult(null);setError("");
      }}>{show?"Fechar formulário":"+ Novo usuário"}</button>
    </div>
    <p className="small-note">Apenas o SuperAdmin pode criar ou excluir usuários e
      redefinir senhas. A conta SuperAdmin inicial é criada separadamente.</p>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {result&&<TemporaryPasswordNotice username={result.username}
      password={result.temporary_password} onClose={()=>setResult(null)}/>}
    {show&&<div className="local-account-form"><h3>Novo colaborador</h3>
      <div className="local-account-grid">
        <label>Nome do colaborador<input value={name} maxLength={150}
          placeholder="Nome completo" onChange={e=>setName(e.target.value)}/></label>
        <label>Nome de usuário<input value={username} maxLength={40}
          autoCapitalize="none" placeholder="Ex.: bruno.joi"
          onChange={e=>setUsername(e.target.value)}/></label>
        <label>Perfil<select value={role} onChange={e=>
          setRole(e.target.value as "seller"|"administrator")}>
          <option value="seller">Vendedor — somente leitura</option>
          <option value="administrator">Administrador — três lojas</option>
        </select></label>
        {role==="seller"&&<label>Loja<select value={store}
          onChange={e=>setStore(e.target.value)}>
          {stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}
        </select></label>}
      </div>
      <p className="small-note">Uma senha única será exibida após cadastrar.
        Entregue-a pessoalmente ao colaborador.</p>
      <div className="btn-row">
        <button className="btn-primary" disabled={busy||name.trim().length<2||
          !/^[a-z][a-z0-9._-]{2,39}$/.test(username.trim().toLowerCase())}
          onClick={()=>void create()}>{busy?"Cadastrando…":"Cadastrar e gerar senha"}</button>
        <button className="btn-secondary" onClick={()=>setShow(false)}>Cancelar</button>
      </div>
    </div>}
  </section>;
}
