import {useEffect, useState} from "react";
import {api, type OverviewSnapshot, type MyProfile} from "./api";

type Props = {token: string; profile: MyProfile};
const currency = (value: string | null) =>
  value === null ? "Sem dados" :
  new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(Number(value));
const currentPeriod = () => {
  const now = new Date();
  return now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2,"0");
};

export function OverviewPage({token, profile}: Props) {
  const [period,setPeriod] = useState(currentPeriod);
  const [snapshot,setSnapshot] = useState<OverviewSnapshot | null>(null);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");
  const [year,month] = period.split("-").map(Number);

  useEffect(() => {
    if (!profile.features.overview || !token || !year || !month) return;
    const controller = new AbortController();
    setSnapshot(null);
    setLoading(true);
    setError("");
    void api.overview(token,year,month).then((out) => {
      if (!controller.signal.aborted) setSnapshot(out);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Não foi possível consultar.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  },[token,profile.features.overview,year,month]);

  if (!profile.features.overview) {
    return <section className="panel"><h2>Visão Geral não autorizada</h2>
      <p>Seu perfil não possui permissão para consultar este módulo.</p></section>;
  }
  return <div>
    <div className="page-header"><div className="eyebrow">RESULTADOS DA UMA</div>
      <h1>Visão Geral</h1>
      <p>{profile.profile === "seller" ? "Indicadores autorizados da sua loja." :
          "Acompanhamento comercial consolidado de Joinville, Tubarão e Itajaí."}</p></div>
    <div className="overview-top">
      <div className="form-row"><label htmlFor="overview-period">Competência</label>
        <input id="overview-period" type="month" min="2020-01" max="2100-12"
          value={period} onChange={(event) => setPeriod(event.target.value)}/></div>
      <span className="chip">Fonte comercial: integração pendente</span>
    </div>
    <div className="notice notice-amber" role="status">
      Os indicadores de faturamento ainda não estão conectados ao ERP. Os campos sem dados
      não representam vendas zeradas. As metas exibidas são as cadastradas no Portal UMA.
    </div>
    {loading && <p role="status">Carregando indicadores…</p>}
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {snapshot && <>
      <div className="overview-kpis">
        <div className="panel overview-kpi"><span>Meta do período</span>
          <strong>{currency(snapshot.summary.monthly_target)}</strong>
          <small>{snapshot.summary.monthly_target===null?"Metas incompletas ou não autorizadas":"Valores cadastrados no portal"}</small></div>
        <div className="panel overview-kpi"><span>Faturamento realizado</span><strong>Sem dados</strong>
          <small>Aguardando integração com o ERP</small></div>
        <div className="panel overview-kpi"><span>Atingimento da meta</span><strong>Sem dados</strong>
          <small>Depende das vendas oficiais</small></div>
        <div className="panel overview-kpi"><span>Última atualização de vendas</span>
          <strong>Não disponível</strong><small>Os dados ainda não foram importados</small></div>
      </div>
      <section className="panel">
        <div className="panel-head"><div><h2>{snapshot.scope==="consolidated"?
          "Desempenho das três lojas" : "Sua unidade"}</h2>
          <p>Comparativo entre meta planejada e vendas realizadas, assim que a fonte oficial estiver disponível.</p>
        </div></div>
        <div className="overview-store-grid">
          {snapshot.stores.map((store) => <div className="overview-store" key={store.code}>
            <h3>{store.name}</h3>
            <div><span>Meta mensal</span><strong>{store.target_visibility==="restricted"?
              "Restrito" : currency(store.target)}</strong></div>
            <div><span>Faturamento</span><strong>Sem dados</strong></div>
            <div><span>Atingimento</span><strong>Sem dados</strong></div>
          </div>)}
        </div>
      </section>
      <section className="panel overview-next"><h2>Próximos passos dos indicadores</h2>
        <p>Depois que o relatório do ERP for validado, esta visão poderá mostrar o faturamento,
        o cumprimento das metas, a evolução mensal e a comparação com o mesmo período do ano anterior.
        Nenhuma dessas informações será estimada a partir de registros fictícios.</p></section>
    </>}
  </div>;
}
