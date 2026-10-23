import {useCallback,useEffect,useState} from "react";
import type {MyProfile} from "./api";
import {labelStore} from "./catalog";
import {operationsApi,type SupplySnapshot,type SupplyMove} from "./operationsApi";

type Props={token:string;profile:MyProfile};
const stores=["JOINVILLE","TUBARAO","ITAJAI"] as const;

export function SuppliesPage({token,profile}:Props){
  const [store,setStore]=useState(profile.stores[0]??"");
  const [stock,setStock]=useState<SupplySnapshot|null>(null);
  const [history,setHistory]=useState<SupplyMove[]>([]);
  const [materialId,setMaterialId]=useState("");
  const [kind,setKind]=useState<"entrada"|"retirada">("retirada");
  const [quantity,setQuantity]=useState("1");
  const [note,setNote]=useState("");
  const [minimum,setMinimum]=useState("0");
  const [newName,setNewName]=useState("");
  const [newUnit,setNewUnit]=useState("unidade");
  const [minima,setMinima]=useState<Record<string,string>>({JOINVILLE:"0",TUBARAO:"0",ITAJAI:"0"});
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canWrite=profile.profile!=="seller";

  const refresh=useCallback(async()=>{
    if(!store)return;
    setLoading(true);setError("");
    try{
      const [items,movements]=await Promise.all([
        operationsApi.supplies(token,store),operationsApi.movements(token,store)
      ]);
      setStock(items);setHistory(movements);
    }catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível consultar insumos.");}
    finally{setLoading(false);}
  },[token,store]);
  useEffect(()=>{void refresh();},[refresh]);
  useEffect(()=>{
    const first=stock?.items.find(item=>item.id===materialId)||stock?.items[0];
    setMaterialId(first?.id??"");setMinimum(String(first?.minimum??0));
  },[stock,materialId]);
  const chosen=stock?.items.find(item=>item.id===materialId);
  const shortage=(stock?.items??[]).filter(item=>item.needs_restock).length;

  async function execute(task:()=>Promise<unknown>,label:string){
    setWorking(true);setError("");setMessage("");
    try{await task();await refresh();setMessage(label);}
    catch(cause){setError(cause instanceof Error?cause.message:"Não foi possível salvar.");}
    finally{setWorking(false);}
  }

  const numericMinima=Object.fromEntries(stores.map(s=>[s,Number(minima[s])]));
  return <section>
    <div className="page-header"><div><div className="eyebrow">ROTINA OPERACIONAL</div>
      <h1>Materiais e insumos</h1>
      <p>Controle independente do estoque comercial do ERP: saldos, reposição e retiradas de cada unidade.</p>
    </div></div>
    <div className="notice notice-amber">
      Cada movimentação altera exclusivamente os insumos da loja e fica no histórico.
      Não existe transferência automática entre lojas.</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {message&&<div className="notice notice-success" role="status">{message}</div>}
    <div className="routine-filters"><label>Unidade<select value={store} onChange={e=>setStore(e.target.value)}>
      {profile.stores.map(code=><option key={code} value={code}>{labelStore(code)}</option>)}
    </select></label>
      <span className="chip">Estoque de consumo interno</span>
    </div>
    {loading&&<p role="status">Carregando estoque…</p>}
    {stock&&!loading&&<>
      <div className="routine-kpis">
        <div className="panel"><span>Materiais cadastrados</span><strong>{stock.items.length}</strong><small>{labelStore(store)}</small></div>
        <div className="panel"><span>Itens para reposição</span><strong>{shortage}</strong><small>Saldo menor ou igual ao mínimo</small></div>
        <div className="panel"><span>Movimentações registradas</span><strong>{history.length}</strong><small>Até os últimos 100 registros</small></div>
      </div>
      <article className="panel">
        <div className="panel-head"><div><h2>Estoque por material</h2>
          <p>O saldo inicial é zero até que sejam registradas entradas de reposição.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Material</th><th>Unidade</th>
          <th>Saldo</th><th>Mínimo</th><th>Situação</th></tr></thead><tbody>
          {stock.items.map(item=><tr key={item.id}><td>{item.name}</td><td>{item.unit}</td>
            <td>{item.balance}</td><td>{item.minimum}</td>
            <td><span className={item.needs_restock?"routine-alert":"routine-good"}>{
              item.needs_restock?"Repor":"Disponível"
            }</span></td></tr>)}
          </tbody></table></div>
        {stock.items.length===0&&<p className="empty">Nenhum material cadastrado.</p>}
      </article>
      {canWrite&&<div className="columns routine-columns">
        <article className="panel">
          <div className="panel-head"><div><h2>Registrar movimentação</h2>
            <p>Não é possível retirar mais unidades que o saldo existente.</p></div></div>
          <div className="routine-form-grid">
            <label>Tipo<select value={kind} onChange={e=>setKind(e.target.value as typeof kind)}>
              <option value="retirada">Retirada / consumo</option><option value="entrada">Entrada / reposição</option>
            </select></label>
            <label>Material<select value={materialId} onChange={e=>setMaterialId(e.target.value)}>
              {stock.items.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}
            </select></label>
            <label>Quantidade<input type="number" min={1} max={9999} step={1}
              value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
            <label>Saldo atual<input value={chosen?.balance??0} readOnly/></label>
            <label className="routine-wide">Observação<input maxLength={180}
              value={note} onChange={e=>setNote(e.target.value)}/></label>
          </div>
          <button className="btn-primary" disabled={working||!chosen||!Number.isInteger(Number(quantity))||
            Number(quantity)<1||Number(quantity)>9999}
            onClick={()=>void execute(()=>operationsApi.moveSupply(token,{
              store_code:store,material_id:materialId,kind,quantity:Number(quantity),
              note,expected_revision:chosen!.revision
            }),"Movimentação registrada e auditada.")}>Registrar movimentação</button>
        </article>
        <article className="panel">
          <div className="panel-head"><div><h2>Configurar mínimo</h2>
            <p>Reposição planejada individualmente para cada loja.</p></div></div>
          <div className="routine-form-grid">
            <label>Material<select value={materialId} onChange={e=>setMaterialId(e.target.value)}>
              {stock.items.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}
            </select></label>
            <label>Estoque mínimo<input type="number" min={0} max={9999} step={1}
              value={minimum} onChange={e=>setMinimum(e.target.value)}/></label>
          </div>
          <button className="btn-secondary" disabled={working||!chosen||!Number.isInteger(Number(minimum))||
            Number(minimum)<0||Number(minimum)>9999||Number(minimum)===chosen.minimum}
            onClick={()=>void execute(()=>operationsApi.changeMinimum(token,store,materialId,
              Number(minimum),chosen!.revision),"Estoque mínimo atualizado.")}>Salvar mínimo</button>
        </article>
      </div>}
      {canWrite&&<article className="panel routine-form-panel">
        <div className="panel-head"><div><h2>Cadastrar material</h2><p>O item será criado para as três lojas, com mínimos próprios.</p></div></div>
        <div className="routine-form-grid">
          <label>Material<input maxLength={80} placeholder="Ex.: Papel toalha" value={newName} onChange={e=>setNewName(e.target.value)}/></label>
          <label>Unidade<select value={newUnit} onChange={e=>setNewUnit(e.target.value)}>
            {["unidade","pacote","caixa","rolo","frasco","resma"].map(u=><option value={u} key={u}>{u}</option>)}
          </select></label>
          {stores.map(code=><label key={code}>Mínimo em {labelStore(code)}<input type="number" step={1} min={0} max={9999}
            value={minima[code]} onChange={e=>setMinima(prev=>({...prev,[code]:e.target.value}))}/></label>)}
        </div>
        <button className="btn-primary" disabled={working||!newName.trim()||
          stores.some(code=>!Number.isInteger(numericMinima[code])||numericMinima[code]<0||numericMinima[code]>9999)}
          onClick={()=>void execute(async()=>{
            await operationsApi.createMaterial(token,{name:newName,unit:newUnit,minima:numericMinima});
            setNewName("");
          },"Material cadastrado nas três lojas.")}>+ Cadastrar material</button>
      </article>}
      <article className="panel routine-form-panel"><div className="panel-head"><div>
        <h2>Histórico de entradas e retiradas</h2><p>Últimas movimentações registradas.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Material</th><th>Tipo</th>
          <th>Qtd.</th><th>Saldo após</th><th>Responsável</th><th>Obs.</th></tr></thead><tbody>
          {history.map(m=><tr key={m.id}><td>{new Date(m.created_at).toLocaleString("pt-BR")}</td>
            <td>{m.material}</td><td>{m.kind}</td><td>{m.quantity}</td><td>{m.resulting_balance}</td>
            <td>{m.actor}</td><td>{m.note||"—"}</td></tr>)}
          </tbody></table></div>
        {history.length===0&&<p className="empty">Nenhuma movimentação registrada nesta loja.</p>}
      </article>
    </>}
  </section>;
}
