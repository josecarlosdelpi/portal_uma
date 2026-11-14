import {useState} from "react";
import {api,type AccessGroup,type LocalCreateAccount} from "./api";
import {labelStore,permissionName} from "./catalog";

const ROLE_OPTIONS:Array<{value:"seller"|"administrator"|"staff";label:string}>=[
  {value:"seller",label:"Vendedor — aparece nos cadastros da loja"},
  {value:"administrator",label:"Administrador"},
  {value:"staff",label:"Equipe interna — sem vínculo de loja"},
];
const roleLabel=(value:string)=>ROLE_OPTIONS.find(o=>o.value===value)?.label??value;

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

export function AccountsManager({token,groups,onCreated}:{
  token:string;groups:AccessGroup[];onCreated:(userId:string)=>Promise<void>
}){
  const [show,setShow]=useState(false);
  const [name,setName]=useState("");
  const [username,setUsername]=useState("");
  const [role,setRole]=useState<"administrator"|"seller"|"staff">("seller");
  const [groupId,setGroupId]=useState("");
  const [scope,setScope]=useState<string[]>([]);
  const [result,setResult]=useState<LocalCreateAccount|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);

  const group=groups.find(g=>g.id===groupId);
  const groupStores=group?.stores??[];
  // Sem marcacoes = usuario herda toda a abrangencia do grupo.
  const effectiveStores=scope.length?scope:groupStores;

  function chooseGroup(id:string){
    setGroupId(id);setScope([]);
  }
  function toggleScope(code:string){
    setScope(prev=>prev.includes(code)?prev.filter(c=>c!==code):[...prev,code]);
  }

  async function create(){
    if(!group)return;
    setBusy(true);setError("");setResult(null);
    try{
      const row=await api.createLocalUser(token,{
        username:username.trim(),display_name:name.trim(),profile:role,
        group_id:group.id,...(scope.length?{store_codes:scope}:{})
      });
      setResult(row);setShow(false);setName("");setUsername("");setGroupId("");setScope([]);
      await onCreated(row.id);
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
      redefinir senhas. O acesso do colaborador vem do grupo selecionado.</p>
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
        <label>Função<select value={role} onChange={e=>
          setRole(e.target.value as "seller"|"administrator"|"staff")}>
          {ROLE_OPTIONS.map(option=><option key={option.value}
            value={option.value}>{option.label}</option>)}
        </select></label>
        <label>Grupo de acesso<select value={groupId}
          onChange={e=>chooseGroup(e.target.value)}>
          <option value="">Selecione um grupo…</option>
          {groups.filter(g=>g.active).map(g=><option key={g.id}
            value={g.id}>{g.name} — {g.stores.map(labelStore).join(", ")}</option>)}
        </select></label>
      </div>
      {group&&<div className="form-row"><label>Lojas autorizadas dentro do grupo</label>
        <div className="scope-checks">{groupStores.map(code=><label key={code}
          className="check-line"><input type="checkbox" checked={scope.includes(code)}
          onChange={()=>toggleScope(code)}/><span>{labelStore(code)}</span></label>)}
        </div>
        <p className="small-note">Sem seleção, o usuário herda toda a abrangência do grupo.
          Marque lojas para restringir o acesso a um subconjunto.</p>
      </div>}
      {group&&<div className="access-summary"><h4>Resumo do acesso</h4>
        <p>Função: <strong>{roleLabel(role)}</strong> · Grupo: <strong>{group.name}</strong> ·
          Lojas: <strong>{effectiveStores.map(labelStore).join(", ")||"—"}</strong></p>
        <p className="small-note">{group.permissions.length===0
          ?"Este grupo ainda não tem permissões configuradas — o usuário não acessará módulos."
          :group.permissions.length+" permissões herdadas: "+
            group.permissions.slice(0,6).map(permissionName).join(", ")+
            (group.permissions.length>6?"…":"")}
        </p>
      </div>}
      <p className="small-note">Uma senha única será exibida após cadastrar.
        Entregue-a pessoalmente ao colaborador.</p>
      <div className="btn-row">
        <button className="btn-primary" disabled={busy||!group||name.trim().length<2||
          !/^[a-z][a-z0-9._-]{2,39}$/.test(username.trim().toLowerCase())}
          onClick={()=>void create()}>{busy?"Cadastrando…":"Cadastrar e gerar senha"}</button>
        <button className="btn-secondary" onClick={()=>setShow(false)}>Cancelar</button>
      </div>
    </div>}
  </section>;
}
