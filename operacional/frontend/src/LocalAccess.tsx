import {useCallback,useState} from "react";
import type {FormEvent} from "react";
import {App} from "./App";
import {MfaPanel} from "./AccountsManager";
import {ApiError,MfaRequired,localLogin,localChangePassword,localLogout} from "./api";
import {UMA_LOGO_DATA_URI} from "./umaBrand";

const key="uma_operational_local_session";
type Props={onUseExternalLogin?:()=>void;externalError?:string};

export function LocalAccess({onUseExternalLogin,externalError}:Props){
  const [token,setToken]=useState(()=>window.sessionStorage.getItem(key)??"");
  const [temporary,setTemporary]=useState("");
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [newPassword,setNewPassword]=useState("");
  const [confirm,setConfirm]=useState("");
  const [needsMfa,setNeedsMfa]=useState(false);
  const [totp,setTotp]=useState("");
  const [mfaEnrollToken,setMfaEnrollToken]=useState("");
  const [displayName,setDisplayName]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");

  const logout=useCallback(()=>{
    if(token)void localLogout(token).catch(()=>{});
    window.sessionStorage.removeItem(key);
    setToken("");setTemporary("");setPassword("");setNewPassword("");setConfirm("");setError("");
  },[token]);

  async function login(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError("");
    try{
      const result=await localLogin(username,password,totp||undefined);
      setPassword("");setTotp("");setNeedsMfa(false);
      setDisplayName(result.display_name);
      if(result.mfa_setup_required&&!result.must_change_password)
        setMfaEnrollToken(result.access_token);
      else if(result.must_change_password)setTemporary(result.access_token);
      else{window.sessionStorage.setItem(key,result.access_token);setToken(result.access_token);}
    }catch(cause){
      if(cause instanceof MfaRequired){setNeedsMfa(true);setError(cause.invalid?cause.message:"");}
      else setError(cause instanceof Error?cause.message:"Não foi possível acessar.");
    }
    finally{setBusy(false);}
  }

  async function change(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(newPassword!==confirm){setError("A confirmação precisa ser igual à nova senha.");return;}
    setBusy(true);setError("");
    try{
      const result=await localChangePassword(temporary,newPassword);
      setTemporary("");setNewPassword("");setConfirm("");
      if(result.mfa_setup_required)setMfaEnrollToken(result.access_token);
      else{window.sessionStorage.setItem(key,result.access_token);setToken(result.access_token);}
    }catch(cause){setError(cause instanceof ApiError&&cause.status===422?
      "Escolha uma senha diferente da provisória, com pelo menos 12 caracteres.":
      cause instanceof Error?cause.message:"Não foi possível trocar a senha.");}
    finally{setBusy(false);}
  }

  if(token)return <App token={token} onLogout={logout}/>;

  if(mfaEnrollToken)return <div className="login-stage">
    <main className="login-panel local-login-panel" style={{maxWidth:"560px"}}>
      <h1>Proteção obrigatória: MFA</h1>
      <p>Olá, {displayName}. Sua conta de SuperAdmin exige autenticação em
        duas etapas antes de acessar o portal. Configure o autenticador e,
        depois, entre novamente com senha + código.</p>
      <MfaPanel token={mfaEnrollToken}/>
      <button className="btn-secondary" style={{marginTop:"12px"}}
        onClick={()=>setMfaEnrollToken("")}>Voltar ao login</button>
    </main></div>;

  return <div className="login-stage"><main className="login-panel local-login-panel">
    <img className="login-logo-original" src={UMA_LOGO_DATA_URI} alt="Universo das Mangueiras"/>
    <div className="eyebrow">ACESSO AO PORTAL UMA</div>
    {temporary?<><h1>Crie sua senha pessoal</h1>
      <p>Olá, {displayName}. Antes de entrar, substitua a senha provisória.</p>
      {error&&<div className="notice notice-error" role="alert">{error}</div>}
      <form className="local-login-form" onSubmit={event=>void change(event)}>
        <label>Nova senha<input type="password" required minLength={12} maxLength={128}
          autoComplete="new-password" value={newPassword}
          onChange={event=>setNewPassword(event.target.value)}/></label>
        <label>Confirmar nova senha<input type="password" required minLength={12} maxLength={128}
          autoComplete="new-password" value={confirm}
          onChange={event=>setConfirm(event.target.value)}/></label>
        <button className="btn-primary" type="submit" disabled={busy}>{
          busy?"Salvando…":"Alterar senha e acessar"
        }</button>
      </form>
      <p className="local-login-help">Sua senha pessoal não poderá ser consultada pelo administrador.</p>
      <button className="btn-secondary" onClick={()=>{
        setTemporary("");setNewPassword("");setConfirm("");setError("");
      }}>Voltar ao login</button>
    </>:<>
      <h1>Gestão da UMA, em um só lugar.</h1>
      <p>Entre com seu usuário e senha individual, sem precisar de e-mail.</p>
      {externalError&&<div className="notice notice-error" role="alert">{externalError}</div>}
      {error&&<div className="notice notice-error" role="alert">{error}</div>}
      <form className="local-login-form" onSubmit={event=>void login(event)}>
        <label>Usuário<input type="text" required minLength={3} maxLength={40}
          autoComplete="username" placeholder="Ex.: bruno.joi" value={username}
          onChange={event=>setUsername(event.target.value)}/></label>
        <label>Senha<input type="password" required autoComplete="current-password"
          value={password} onChange={event=>setPassword(event.target.value)}/></label>
        {needsMfa&&<label>Código do autenticador<input type="text" required
          inputMode="numeric" pattern="[0-9]{6}" maxLength={6}
          autoComplete="one-time-code" placeholder="000000" value={totp}
          onChange={event=>setTotp(event.target.value.replace(/\D/g,"").slice(0,6))}/></label>}
        <button type="submit" className="btn-primary" disabled={busy}>{
          busy?"Entrando…":"Entrar no Portal UMA"
        }</button>
      </form>
      <p className="local-login-help">No primeiro acesso, use a senha provisória entregue
        pelo SuperAdmin. Você será obrigado a criar uma senha pessoal.</p>
      {onUseExternalLogin&&<button className="btn-secondary"
        onClick={onUseExternalLogin}>Entrar com conta externa</button>}
    </>}
  </main></div>;
}
