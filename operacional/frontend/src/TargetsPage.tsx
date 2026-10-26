import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type MyProfile, type TargetSnapshot } from "./api";
import { labelStore } from "./catalog";

type Props = { token: string; profile: MyProfile };

const money = (amount: string | number | null | undefined) =>
  amount === null || amount === undefined ? "Sem informação" :
  new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(Number(amount));

const localMonth = () => {
  const now = new Date();
  return now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0");
};

const weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function monthBusinessDates(period: string): string[] {
  const [year, month] = period.split("-").map(Number);
  if (!year || !month || month < 1 || month > 12) return [];
  const total = new Date(year, month, 0).getDate();
  const dates: string[] = [];
  for (let day = 1; day <= total; day++) {
    const date = new Date(year, month - 1, day, 12);
    if (date.getDay() === 0 || date.getDay() === 6) continue;
    dates.push(period + "-" + String(day).padStart(2, "0"));
  }
  return dates;
}

export function TargetsPage({token, profile}: Props) {
  const availableStores = profile.stores;
  const [store, setStore] = useState(availableStores[0] ?? "");
  const [period, setPeriod] = useState(localMonth);
  const [snapshot, setSnapshot] = useState<TargetSnapshot | null>(null);
  const [goalDraft, setGoalDraft] = useState("");
  const [minimumDraft, setMinimumDraft] = useState("");
  const [daysOffDraft, setDaysOffDraft] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const canWrite = profile.profile !== "seller";
  const allBusinessDays = useMemo(() => monthBusinessDates(period), [period]);
  const [year, month] = period.split("-").map(Number);

  const fetchSnapshot = useCallback(async () => {
    if (!store || !token || !year || !month) return;
    setLoading(true);
    setError("");
    try {
      const response = await api.target(token, store, year, month);
      setSnapshot(response);
      setGoalDraft(response.target.amount ?? "");
      setMinimumDraft(response.minimum.amount ?? "");
      setDaysOffDraft(response.days_off);
    } catch (cause) {
      setSnapshot(null);
      setError(cause instanceof Error ? cause.message : "Falha ao consultar metas.");
    } finally {
      setLoading(false);
    }
  }, [token, store, year, month]);

  useEffect(() => {
    let cancelled = false;
    if (!store || !token || !year || !month) return;
    setLoading(true);
    setError("");
    setMessage("");
    setSnapshot(null);
    void api.target(token, store, year, month).then((response) => {
      if (cancelled) return;
      setSnapshot(response);
      setGoalDraft(response.target.amount ?? "");
      setMinimumDraft(response.minimum.amount ?? "");
      setDaysOffDraft(response.days_off);
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "Falha ao consultar metas.");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {cancelled = true;};
  }, [token, store, year, month]);

  const save = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await action();
      await fetchSnapshot();
      setMessage(success);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  };

  const toggleDate = (date: string) => {
    setDaysOffDraft((before) =>
      before.includes(date) ? before.filter((value) => value !== date) : [...before, date].sort()
    );
  };

  if (!profile.features.targets) {
    return <section className="panel"><h2>Metas não disponíveis</h2><p>Seu acesso a este módulo não foi habilitado para a loja.</p></section>;
  }

  if (!store) {
    return <section className="panel"><h2>Loja não vinculada</h2><p>Solicite a configuração da sua unidade ao administrador do portal.</p></section>;
  }

  return <section className="target-page">
    <div className="page-header"><div>
      <div className="eyebrow">GESTÃO COMERCIAL</div>
      <h1>Metas diárias</h1>
      <p>Metas mensais, dias sem expediente e distribuição inicial por loja.</p>
    </div></div>
    <div className="notice notice-amber">
      As vendas oficiais ainda não estão integradas. O quadro abaixo é uma previsão de distribuição da meta,
      não uma apuração do faturamento ou a meta diária dinâmica.
    </div>
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {message && <div className="notice notice-success" role="status">{message}</div>}

    <div className="target-filters">
      <div className="form-row"><label htmlFor="target-store">Loja</label>
        <select id="target-store" value={store} disabled={saving}
          onChange={(event) => setStore(event.target.value)}>
          {availableStores.map((code) => <option value={code} key={code}>{labelStore(code)}</option>)}
        </select>
      </div>
      <div className="form-row"><label htmlFor="target-month">Mês de referência</label>
        <input id="target-month" type="month" min="2020-01" max="2100-12"
          value={period} disabled={saving} onChange={(event) => setPeriod(event.target.value)}/>
      </div>
      <button className="btn-secondary" type="button" disabled={loading || saving}
        onClick={() => void fetchSnapshot()}>Atualizar</button>
    </div>

    {loading && <div className="panel" role="status">Carregando metas da loja…</div>}
    {snapshot && !loading && <>
      <div className="target-kpis">
        <div className="panel target-kpi"><span>Meta mensal</span><strong>{money(snapshot.target.amount)}</strong>
          <small>{snapshot.target.amount === null ? "Aguardando cadastro" : "Meta cadastrada no Portal UMA"}</small></div>
        <div className="panel target-kpi"><span>Dias de expediente</span><strong>{snapshot.working_day_count}</strong>
          <small>Segunda a sexta, descontados os dias fechados</small></div>
        <div className="panel target-kpi"><span>Mínimo após atingir a meta</span><strong>{money(snapshot.minimum.amount)}</strong>
          <small>Configurado por loja para todos os meses</small></div>
        <div className="panel target-kpi"><span>Faturamento realizado</span><strong>Sem dados</strong>
          <small>Aguardando a importação comercial</small></div>
      </div>

      <div className="columns">
        <article className="panel">
          <div className="panel-head"><div><h2>Parâmetros da loja</h2><p>{labelStore(store)} · competência {period}</p></div></div>
          <div className="target-editor">
            <div className="form-row">
              <label htmlFor="target-amount">Meta mensal (R$)</label>
              <input id="target-amount" type="number" inputMode="decimal" min="0.01"
                step="0.01" placeholder="Ex.: 50000,00" value={goalDraft} disabled={!canWrite || saving}
                onChange={(event) => setGoalDraft(event.target.value)}/>
              <small>Esse valor será usado nos painéis e no fechamento mensal após a integração.</small>
            </div>
            {canWrite && <button type="button" className="btn-primary"
              disabled={saving || !goalDraft || Number(goalDraft) <= 0 || goalDraft === snapshot.target.amount}
              onClick={() => void save(
                () => api.saveTargetGoal(token, store, year, month, goalDraft, snapshot.target.revision),
                "Meta mensal salva com histórico de alteração."
              )}>Salvar meta mensal</button>}
            <div className="target-divider"/>
            <div className="form-row">
              <label htmlFor="minimum-daily">Mínimo diário após atingir a meta (R$)</label>
              <input id="minimum-daily" type="number" inputMode="decimal" min="0" step="0.01"
                placeholder="Ex.: 700,00" value={minimumDraft} disabled={!canWrite || saving}
                onChange={(event) => setMinimumDraft(event.target.value)}/>
              <small>Esta configuração vale para os próximos meses da loja, até ser alterada.</small>
            </div>
            {canWrite && <button type="button" className="btn-secondary"
              disabled={saving || minimumDraft === "" || Number(minimumDraft) < 0 ||
                minimumDraft === snapshot.minimum.amount}
              onClick={() => void save(
                () => api.saveTargetMinimum(token, store, minimumDraft, snapshot.minimum.revision),
                "Mínimo diário salvo com histórico de alteração."
              )}>Salvar mínimo diário</button>}
          </div>
        </article>
        <article className="panel">
          <div className="panel-head"><div><h2>Dias de expediente</h2>
            <p>Marque os dias úteis em que esta loja ficará fechada.</p></div></div>
          <div className="day-selector" aria-label="Dias úteis do mês">
            {allBusinessDays.map((day) => {
              const closed = daysOffDraft.includes(day);
              const dayNumber = Number(day.slice(-2));
              const weekday = (new Date(year,month-1,dayNumber,12).getDay()+6)%7;
              return <button type="button" key={day} aria-pressed={closed}
                className={"day-tile" + (closed ? " day-closed" : "")}
                disabled={!canWrite || saving} onClick={() => toggleDate(day)}>
                <strong>{day.slice(-2)}</strong><small>{weekdays[weekday]}</small>
                <span>{closed ? "Fechado" : "Aberto"}</span>
              </button>;
            })}
          </div>
          <p className="small-note">Os sábados e domingos não são contabilizados. Feriados só serão excluídos quando marcados aqui.</p>
          {canWrite && <button className="btn-primary" type="button"
            disabled={saving || JSON.stringify([...daysOffDraft].sort()) === JSON.stringify(snapshot.days_off)}
            onClick={() => void save(
              () => api.saveTargetCalendar(token, store, year, month, daysOffDraft, snapshot.target.revision),
              "Calendário da loja atualizado."
            )}>Salvar dias sem expediente</button>}
        </article>
      </div>

      <article className="panel target-plan">
        <div className="panel-head"><div><h2>Distribuição inicial da meta</h2>
          <p>Prévia orientativa antes da integração dos valores de vendas.</p></div>
          <span className="count">{snapshot.working_day_count} dias</span>
        </div>
        <div className="table-wrap"><table><thead><tr>
          <th>Data</th><th>Dia da semana</th><th>Meta diária-base</th><th>Faturamento</th>
        </tr></thead><tbody>{snapshot.base_plan.map((day) => <tr key={day.date}>
          <td>{day.date.split("-").reverse().join("/")}</td>
          <td>{weekdays[day.weekday]}</td>
          <td>{money(day.base_daily_target)}</td>
          <td><span className="target-no-data">Aguardando importação</span></td>
        </tr>)}</tbody></table></div>
        {snapshot.base_plan.length === 0 && <p className="empty">Não há dias de expediente para esta competência.</p>}
        <p className="small-note">Quando as vendas oficiais estiverem disponíveis, a meta do dia passará a considerar o faturamento acumulado até o dia anterior e os dias de funcionamento restantes. Após atingir a meta mensal, utilizará o mínimo diário da loja.</p>
      </article>
    </>}
  </section>;
}
