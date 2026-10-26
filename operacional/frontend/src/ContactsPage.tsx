import {useCallback,useEffect,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {operationsApi,type ClientRow,type TeamMember,type ContactRow} from "./operationsApi";

type Props={token:string;profile:MyProfile};
const initialMonth=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");};
const today=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
const outcomeName=(value:string)=>({
  apresentacao:"Apresentação + WhatsApp",sem_resposta:"Não atendeu",whatsapp:"Contato via WhatsApp",outro:"Contato realizado"
}[value as "apresentacao"|"sem_resposta"|"whatsapp"|"outro"]??value);

export function ContactsPage({token,profile}:Props){
  const [store,setStore]=useState(profile.stores[0]??"");
  const [period,setPeriod]=useState(initialMonth);
  const [clients,setClients]=useState<ClientRow[]>([]);
  const [sellers,setSellers]=useState<TeamMember[]>([]);
  const [calls,setCalls]=useState<ContactRow[]>([]);
  const [newName,setNewName]=useState("");
  const [origin,setOrigin]=useState("google");
  const [phone,setPhone]=useState("");
  const [erpCode,setErpCode]=useState("");
  const [lastPurchase,setLastPurchase]=useState("");
  const [clientId,setClientId]=useState("");
  const [sellerId,setSellerId]=useState("");
  const [callDate,setCallDate]=useState(today);
  const [outcome,setOutcome]=useState("apresentacao");
  const [nextOn,setNextOn]=useState("");
  const [note,setNote]=useState("");
  const [editing,setEditing]=useState<ContactRow|null>(null);
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [year,month]=period.split("-").map(Number);
  const canWrite=profile.profile!=="seller";

  const refresh=useCallback(async()=>{
    if(!store||!year||!month)return;
    setLoading(true);setError("");
    try{
      const [customerRows,teamRows,log]=await Promise.all([
        operationsApi.clients(token,store),operationsApi.team(token,store),
        operationsApi.calls(token,store,year,month)
      ]);
      setClients(customerRows);setSellers(teamRows);setCalls(log.items);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível carregar os contatos.");}
    finally{setLoading(false);}
  },[token,store,year,month]);
  useEffect(()=>{void refresh();},[refresh]);
  useEffect(()=>{
    setClientId(current=>clients.some(item=>item.id===current)?current:clients[0]?.id??"");
    setSellerId(current=>sellers.some(item=>item.id===current)?current:sellers[0]?.id??"");
  },[clients,sellers]);
  useEffect(()=>{setEditing(null);},[store,period]);

  const followUps=calls.filter(call=>!!call.next_on);
  async function perform(action:()=>Promise<unknown>,success:string){
    setWorking(true);setError("");setMessage("");
    try{await action();await refresh();setMessage(success);}
    catch(cause){setError(cause instanceof Error?cause.message:"Falha ao registrar contato.");}
    finally{setWorking(false);}
  }
  function startCorrection(row:ContactRow){
    setEditing(row);setCallDate(row.date);setOutcome(row.outcome);
    setNextOn(row.next_on??"");setNote(row.note);setClientId(row.client_id);setSellerId(row.seller_id);
    window.scrollTo({top:0,behavior:"smooth"});
  }
  function clearCorrection(){
    setEditing(null);setCallDate(today());setNextOn("");setNote("");
  }

  return <section>
    <div className="page-header"><div><div className="eyebrow">PROCESSO COMERCIAL</div>
      <h1>Televendas e ligações</h1>
      <p>Uma carteira por loja, com autoria de contato, histórico e lembretes de retorno.</p>
    </div></div>
    <div className="notice notice-amber">
      Esta etapa registra clientes e ligações de forma independente. Compras, ativações e premiações por venda
      continuarão pendentes até definirmos a conciliação com o ERP.</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters">
      <label>Loja<select value={store} onChange={e=>setStore(e.target.value)}>
        {profile.stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}</select></label>
      <label>Mês de referência<input type="month" min="2020-01" max="2100-12"
        value={period} onChange={e=>setPeriod(e.target.value)}/></label>
      <span className="chip">Histórico compartilhado pela unidade</span>
    </div>
    {loading&&<p role="status">Consultando carteira…</p>}
    {!loading&&<>
      <div className="routine-kpis">
        <div className="panel"><span>Clientes na carteira</span><strong>{clients.length}</strong><small>Unidade selecionada</small></div>
        <div className="panel"><span>Ligações registradas</span><strong>{calls.length}</strong><small>Competência selecionada</small></div>
        <div className="panel"><span>Retornos agendados</span><strong>{followUps.length}</strong><small>Chamadas com próxima tentativa</small></div>
      </div>
      {canWrite&&<div className="columns routine-columns">
        <article className="panel">
          <div className="panel-head"><div><h2>Adicionar cliente à carteira</h2>
            <p>Sem designar a carteira a um vendedor individual.</p></div></div>
          <div className="routine-form-grid">
            <label className="routine-wide">Oficina / cliente<input maxLength={100} value={newName}
              placeholder="Nome do cliente" onChange={e=>setNewName(e.target.value)}/></label>
            <label>Origem<select value={origin} onChange={e=>setOrigin(e.target.value)}>
              <option value="google">Pesquisa no Google</option>
              <option value="inativo60">Lista de inativos 60 dias</option>
              <option value="inativo90">Lista de inativos 90 dias</option>
              <option value="carteira">Carteira anterior</option>
            </select></label>
            <label>Telefone<input maxLength={40} value={phone} onChange={e=>setPhone(e.target.value)}/></label>
            <label>Cadastro ERP (opcional)<input maxLength={50} value={erpCode} onChange={e=>setErpCode(e.target.value)}/></label>
            <label>Última compra conhecida<input type="date" value={lastPurchase}
              onChange={e=>setLastPurchase(e.target.value)}/></label>
          </div>
          <button className="btn-primary" disabled={working||!newName.trim()}
            onClick={()=>void perform(async()=>{
              await operationsApi.addClient(token,store,{
                name:newName,phone:phone||null,erp_code:erpCode||null,
                origin,last_purchase_on:lastPurchase||null
              });
              setNewName("");setPhone("");setErpCode("");setLastPurchase("");
            },"Cliente adicionado à carteira da loja.")}>+ Adicionar cliente</button>
        </article>
        <article className="panel">
          <div className="panel-head"><div><h2>{editing?"Corrigir ligação":"Registrar ligação"}</h2>
            <p>Associe o contato ao vendedor que realmente o realizou.</p></div></div>
          <div className="routine-form-grid">
            <label className="routine-wide">Cliente<select value={clientId} disabled={!!editing} onChange={e=>setClientId(e.target.value)}>
              {clients.map(c=><option value={c.id} key={c.id}>{c.name}</option>)}</select></label>
            <label>Responsável<select value={sellerId} disabled={!!editing} onChange={e=>setSellerId(e.target.value)}>
              {sellers.map(s=><option value={s.id} key={s.id}>{s.name}</option>)}</select></label>
            <label>Data<input type="date" value={callDate} onChange={e=>setCallDate(e.target.value)}/></label>
            <label className="routine-wide">Resultado<select value={outcome} onChange={e=>setOutcome(e.target.value)}>
              <option value="apresentacao">Apresentou a UMA + WhatsApp</option>
              <option value="sem_resposta">Tentativa sem atendimento</option>
              <option value="whatsapp">Contato via WhatsApp</option>
              <option value="outro">Contato realizado</option>
            </select></label>
            <label>Próxima tentativa<input type="date" value={nextOn} onChange={e=>setNextOn(e.target.value)}/></label>
            <label className="routine-wide">Observação breve<input maxLength={240} value={note}
              onChange={e=>setNote(e.target.value)}/></label>
          </div>
          {sellers.length===0&&<div className="notice notice-amber">
            É necessário ter um vendedor ativo vinculado a esta loja para registrar ligações.</div>}
          <div className="btn-row">
            <button className="btn-primary" disabled={working||!clientId||!sellerId||!callDate}
              onClick={()=>void perform(async()=>{
                if(editing)await operationsApi.correctCall(token,store,editing.id,{
                  date:callDate,outcome,next_on:nextOn||null,note,expected_revision:editing.revision
                });else await operationsApi.addCall(token,store,{
                  client_id:clientId,seller_id:sellerId,date:callDate,
                  outcome,next_on:nextOn||null,note
                });
                clearCorrection();
              },editing?"Correção auditada.":"Ligação registrada.")}>{
                editing?"Salvar correção":"Registrar ligação"
              }</button>
            {editing&&<button className="btn-secondary" onClick={clearCorrection}>Cancelar edição</button>}
          </div>
        </article>
      </div>}
      <article className="panel routine-form-panel"><div className="panel-head"><div><h2>Carteira da loja</h2>
        <p>Registros compartilhados entre a equipe autorizada.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Cliente</th><th>Origem</th>
          <th>Cadastro ERP</th><th>Telefone</th><th>Última compra conhecida</th></tr></thead>
          <tbody>{clients.map(c=><tr key={c.id}><td>{c.name}</td><td>{c.origin}</td>
            <td>{c.erp_code??"—"}</td><td>{c.phone??"—"}</td>
            <td>{c.last_purchase_on??"Sem dados"}</td></tr>)}</tbody></table></div>
        {clients.length===0&&<p className="empty">Nenhum cliente cadastrado na carteira desta loja.</p>}
      </article>
      <article className="panel routine-form-panel"><div className="panel-head"><div><h2>Histórico de ligações</h2>
        <p>Histórico por loja, com registros de desfecho e próxima tentativa.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Cliente</th><th>Vendedor</th>
          <th>Contato</th><th>Retorno</th><th>Obs.</th>{canWrite&&<th>Ação</th>}</tr></thead>
          <tbody>{calls.map(c=><tr key={c.id}><td>{c.date}</td><td>{c.client}</td>
            <td>{c.seller}</td><td>{outcomeName(c.outcome)}</td><td>{c.next_on??"—"}</td>
            <td>{c.note||"—"}</td>{canWrite&&<td><button className="btn-secondary"
              onClick={()=>startCorrection(c)}>Corrigir</button></td>}</tr>)}</tbody>
        </table></div>
        {calls.length===0&&<p className="empty">Nenhuma ligação registrada no mês.</p>}
        <p className="small-note">Alterações anteriores são registradas na auditoria.
          O sistema ainda não importa automaticamente carteiras ou vendas.</p>
      </article>
    </>}
  </section>;
}
