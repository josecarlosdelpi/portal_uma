import { useAuth } from "react-oidc-context";
import { useCallback, useEffect, useState } from "react";
import { api, type MyProfile, type PortalUser, type StoreGroup, type AuditEvent } from "./api";
import { labelStore, permissionGroups, readPermissionCodes } from "./catalog";
import { TargetsPage } from "./TargetsPage";
import { OverviewPage } from "./OverviewPage";
import { ClosingPage } from "./ClosingPage";

type Tab = "usuarios" | "grupos" | "auditoria";
type Area = "access" | "targets" | "overview" | "closing";
const errorText = (error: unknown) => error instanceof Error ? error.message : "Não foi possível concluir.";
const profileLabel = (profile: string) =>
  profile === "superadmin" ? "SuperAdmin" : profile === "administrator" ? "Administrador" : "Vendedor";

export function App() {
  const auth = useAuth();
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<Tab>("usuarios");
  const [area, setArea] = useState<Area>("overview");
  const [users, setUsers] = useState<PortalUser[]>([]);
  const [groups, setGroups] = useState<StoreGroup[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [auditOffset, setAuditOffset] = useState(0);
  const [hasMoreAudit, setHasMoreAudit] = useState(false);
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("");
  const [groupDraft, setGroupDraft] = useState<string[]>([]);
  const [overrideDraft, setOverrideDraft] = useState<Record<string, boolean | null>>({});
  const [storeDraft, setStoreDraft] = useState("");
  const [working, setWorking] = useState(false);
  const token = auth.user?.access_token ?? "";

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const me = await api.me(token);
      setProfile(me);
      if (me.profile === "superadmin") {
        const [people, branches] = await Promise.all([api.users(token), api.groups(token)]);
        setUsers(people);
        setGroups(branches);
      } else {
        setUsers([]);
        setGroups([]);
      }
    } catch (problem) {
      setProfile(null);
      setError(errorText(problem));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (auth.isAuthenticated) void refresh();
    else setProfile(null);
  }, [auth.isAuthenticated, refresh]);

  useEffect(() => {
    const group = groups.find((candidate) => candidate.id === selectedGroup);
    setGroupDraft(group?.permissions ?? []);
  }, [groups, selectedGroup]);

  useEffect(() => {
    const user = users.find((candidate) => candidate.id === selectedUser);
    const current: Record<string, boolean | null> = {};
    readPermissionCodes.forEach((permission) => {
      current[permission] = user?.overrides[permission] ?? null;
    });
    setOverrideDraft(current);
    setStoreDraft(user?.stores[0] ?? "");
  }, [users, selectedUser]);

  useEffect(() => {
    if (tab !== "auditoria" || profile?.profile !== "superadmin" || !token) return;
    void api.audit(token, auditOffset, 30).then((page) => {
      setEvents(page.items);
      setHasMoreAudit(page.items.length === page.limit);
    }).catch((problem: unknown) => setError(errorText(problem)));
  }, [tab, profile?.profile, token, auditOffset]);

  const update = async (operation: () => Promise<unknown>, success: string) => {
    setWorking(true);
    setError("");
    try {
      await operation();
      await refresh();
      setMessage(success);
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setWorking(false);
    }
  };
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!profile) return;
    setArea(previous => {
      if (previous === "overview" && profile.features.overview) return previous;
      if (previous === "targets" && profile.features.targets) return previous;
      if (previous === "closing" && profile.features.monthly_closing) return previous;
      if (previous === "access" && profile.profile === "superadmin") return previous;
      if (profile.features.overview) return "overview";
      if (profile.features.targets) return "targets";
      if (profile.features.monthly_closing) return "closing";
      return "access";
    });
  }, [profile]);

  if (auth.isLoading) return <div className="login-stage"><div className="login-panel">Validando sessão segura…</div></div>;
  if (auth.error) return <div className="login-stage"><div className="login-panel"><h1>Falha na autenticação</h1><p>{auth.error.message}</p><button onClick={() => void auth.signinRedirect()}>Tentar novamente</button></div></div>;
  if (!auth.isAuthenticated) {
    return <div className="login-stage"><main className="login-panel">
      <div className="login-brand">UMA <span>•</span> PORTAL</div>
      <div className="eyebrow">Versão operacional</div>
      <h1>Gestão da UMA, em um só lugar.</h1>
      <p>Entre com sua conta individual para acessar somente os dados autorizados.</p>
      <button className="btn-primary" onClick={() => void auth.signinRedirect()}>Entrar com segurança →</button>
      <small>Esta versão não oferece acessos fictícios.</small>
    </main></div>;
  }

  const user = users.find((candidate) => candidate.id === selectedUser);
  const group = groups.find((candidate) => candidate.id === selectedGroup);
  const isSuperAdmin = profile?.profile === "superadmin";
  const isSeller = user?.profile === "seller";
  const canViewTargets = profile?.features?.targets ?? false;
  const canViewOverview = profile?.features?.overview ?? false;
  const canViewClosing = profile?.features?.monthly_closing ?? false;

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-logo">U</div><div><strong>PORTAL UMA</strong><small>Gestão operacional</small></div></div>
      <div className="side-heading">NAVEGAÇÃO</div>
      <nav aria-label="Menu principal">
        {canViewOverview && <button className={"nav-item" + (area === "overview" ? " active" : "")}
          onClick={() => setArea("overview")}>▦ &nbsp;Visão Geral</button>}
        {!canViewOverview && <div className="nav-item disabled">▦ &nbsp;Visão Geral <span className="soon">Restrito</span></div>}
        {canViewTargets && <button className={"nav-item" + (area === "targets" ? " active" : "")}
          onClick={() => setArea("targets")}>▤ &nbsp;Metas diárias</button>}
        {canViewClosing && <button className={"nav-item" + (area === "closing" ? " active" : "")}
          onClick={() => setArea("closing")}>▥ &nbsp;Fechamento mensal</button>}
        {isSuperAdmin && <button className={"nav-item" + (area === "access" ? " active" : "")}
          onClick={() => { setArea("access"); setTab("usuarios"); }}>⚙ &nbsp;Configurações</button>}
      </nav>
      <div className="side-spacer"/>
      <div className="sidebar-note"><strong>Ambiente operacional</strong><p>Sem dados demonstrativos. Acesso governado pela API segura.</p></div>
      <div className="sidebar-bottom">Universo das Mangueiras Automotivas</div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb">Portal UMA <span> / </span> <strong>{area === "overview" ? "Visão Geral" : area === "closing" ? "Fechamento mensal" : area === "targets" ? "Metas diárias" : isSuperAdmin ? "Configurações" : "Meu acesso"}</strong></div>
        <div className="topbar-right"><span>{profile?.display_name ?? "Usuário autenticado"}</span><span className="avatar">UMA</span><button className="btn-ghost" onClick={() => void auth.signoutRedirect()}>Sair</button></div>
      </header>
      <div className="workspace">
        {area === "overview" && profile ? <OverviewPage token={token} profile={profile} /> :
         area === "closing" && profile ? <ClosingPage token={token} profile={profile} /> :
         area === "targets" && profile ? <TargetsPage token={token} profile={profile} /> : <>
        <div className="page-header"><div><div className="eyebrow">PORTAL OPERACIONAL</div><h1>{isSuperAdmin ? "Configurações do sistema" : "Meu acesso ao Portal UMA"}</h1><p>Controle de usuários, unidades e permissões com registros de auditoria.</p></div></div>
        <div className="notice notice-amber">A versão operacional está em desenvolvimento. Não utilizar dados comerciais reais até a homologação.</div>
        {error && <div className="notice notice-error" role="alert">{error}</div>}
        {message && <div className="notice notice-success" role="status">{message}</div>}
        {loading && <p aria-live="polite">Atualizando informações…</p>}
        {!profile && !loading && <section className="panel"><h2>Não foi possível carregar seu perfil.</h2><p>Confirme que sua identidade foi cadastrada no Portal UMA.</p><button onClick={() => void refresh()}>Tentar novamente</button></section>}
        {profile && !isSuperAdmin && <section className="panel"><h2>Área administrativa restrita</h2><p>Você está autenticado como {profileLabel(profile.profile)}. A configuração de usuários e permissões é exclusiva do SuperAdmin.</p><p>As telas comerciais serão habilitadas em uma próxima etapa.</p></section>}
        {isSuperAdmin && <div className="tabs" role="tablist" aria-label="Configurações">
          <button role="tab" aria-selected={tab === "usuarios"} className={tab === "usuarios" ? "tab active" : "tab"} onClick={() => setTab("usuarios")}>Usuários</button>
          <button role="tab" aria-selected={tab === "grupos"} className={tab === "grupos" ? "tab active" : "tab"} onClick={() => setTab("grupos")}>Permissões por loja</button>
          <button role="tab" aria-selected={tab === "auditoria"} className={tab === "auditoria" ? "tab active" : "tab"} onClick={() => {setAuditOffset(0); setTab("auditoria");}}>Auditoria</button>
        </div>}
        {isSuperAdmin && tab === "usuarios" && <div className="columns">
          <section className="panel"><div className="panel-head"><div><h2>Usuários cadastrados</h2><p>Selecione um colaborador para administrar seu acesso.</p></div><span className="count">{users.length} contas</span></div>
            {users.length === 0 ? <p className="empty">Nenhum usuário cadastrado.</p> :
            <div className="user-list">{users.map((person) => <button key={person.id} className={"user-row" + (selectedUser === person.id ? " selected" : "")} onClick={() => setSelectedUser(person.id)}>
              <span className="user-avatar">{person.display_name.slice(0, 2).toUpperCase()}</span><span className="user-text"><strong>{person.display_name}</strong><small>{profileLabel(person.profile)} · {person.stores.map(labelStore).join(", ") || "Todas as lojas"}</small></span>
              <span className={"pill " + (person.active ? "pill-green" : "pill-grey")}>{person.active ? "Ativo" : "Suspenso"}</span>
            </button>)}</div>}
            <p className="small-note">O convite de novos usuários será integrado ao provedor de identidade antes da operação.</p>
          </section>
          <section className="panel">
            {!user ? <div className="empty">Selecione um usuário para visualizar as configurações.</div> : <><div className="panel-head"><div><h2>{user.display_name}</h2><p>{profileLabel(user.profile)}</p></div></div>
              <div className="form-row"><label htmlFor="user-store">Loja vinculada</label><select id="user-store" value={storeDraft} disabled={!isSeller || working} onChange={(event) => setStoreDraft(event.target.value)}>
                {!isSeller && <option value="">Todas as lojas</option>}
                {Object.entries({JOINVILLE:"Joinville", ITAJAI:"Itajaí", TUBARAO:"Tubarão"}).map(([code,name]) => <option key={code} value={code}>{name}</option>)}
              </select></div>
              {isSeller && <button className="btn-secondary" disabled={working || storeDraft === user.stores[0]} onClick={() => void update(() => api.setUserStore(token,user.id,storeDraft),"Vínculo de loja atualizado.")}>Salvar loja</button>}
              {!user.profile.includes("superadmin") && <div className="status-control"><div><strong>Conta {user.active ? "ativa" : "suspensa"}</strong><small>{user.active ? "Usuário pode acessar de acordo com suas permissões." : "A conta está bloqueada no Portal UMA."}</small></div>
                <button disabled={working} className="btn-secondary" onClick={() => {
                  if (!window.confirm(user.active ? "Suspender este usuário?" : "Reativar este usuário?")) return;
                  void update(() => api.setActive(token,user.id,!user.active),"Situação da conta atualizada.");
                }}>{user.active ? "Suspender conta" : "Reativar conta"}</button></div>}
              {isSeller && <><h3>Exceções individuais</h3><p className="small-note">Herdar usa a configuração da loja. Permitir e bloquear alteram apenas a leitura deste usuário.</p><div className="permissions">{permissionGroups.map((section) => <div key={section.title}><h4>{section.title}</h4>{section.permissions.map((permission) => <div className="permission-line" key={permission.code}><div>{permission.name}</div>
                <select aria-label={"Exceção: " + permission.name} disabled={working} value={overrideDraft[permission.code] === null || overrideDraft[permission.code] === undefined ? "inherit" : overrideDraft[permission.code] ? "allow" : "deny"}
                  onChange={(event) => setOverrideDraft((previous) => ({...previous,[permission.code]:event.target.value === "inherit" ? null : event.target.value === "allow"}))}>
                  <option value="inherit">Herdar</option><option value="allow">Permitir</option><option value="deny">Bloquear</option>
                </select></div>)}</div>)}</div>
                <button className="btn-primary" disabled={working} onClick={() => void update(() => api.saveOverrides(token,user.id,overrideDraft),"Permissões individuais atualizadas.")}>Salvar exceções</button>
              </>}
            </>}
          </section>
        </div>}
        {isSuperAdmin && tab === "grupos" && <div className="columns">
          <section className="panel"><h2>Grupos de lojas</h2><p>As permissões configuradas aqui são herdadas pelos vendedores da respectiva unidade.</p>
            <div className="user-list">{groups.map((candidate) => <button key={candidate.id} className={"user-row" + (selectedGroup === candidate.id ? " selected" : "")} onClick={() => setSelectedGroup(candidate.id)}><span className="user-avatar">⌂</span><span className="user-text"><strong>{labelStore(candidate.store)}</strong><small>{candidate.permissions.length} permissões de leitura habilitadas</small></span></button>)}</div>
          </section>
          <section className="panel">{!group ? <div className="empty">Selecione uma loja para configurar os indicadores.</div> : <><h2>Permissões — {labelStore(group.store)}</h2><p>Marque somente os módulos e indicadores visíveis para os vendedores desta loja.</p>
            <div className="permissions">{permissionGroups.map((section) => <div key={section.title}><h4>{section.title}</h4><p className="small-note">{section.help}</p>{section.permissions.map((permission) => <label key={permission.code} className="permission-line check-line"><input type="checkbox" checked={groupDraft.includes(permission.code)} disabled={working} onChange={(event) => setGroupDraft((previous) => event.target.checked ? [...previous,permission.code] : previous.filter((code) => code !== permission.code))}/><span>{permission.name}</span></label>)}</div>)}</div>
            <button className="btn-primary" disabled={working} onClick={() => void update(() => api.saveGroup(token,group.id,groupDraft),"Permissões da loja atualizadas.")}>Salvar permissões</button>
          </>}</section>
        </div>}
        {isSuperAdmin && tab === "auditoria" && <section className="panel"><div className="panel-head"><div><h2>Histórico administrativo</h2><p>Registro das alterações realizadas no sistema.</p></div><button className="btn-secondary" onClick={() => setAuditOffset(0)}>Atualizar</button></div>
          <div className="table-wrap"><table><thead><tr><th>Data e horário</th><th>Ação</th><th>Objeto</th><th>Identificador</th></tr></thead><tbody>{events.map((event) => <tr key={event.id}><td>{new Date(event.created_at).toLocaleString("pt-BR")}</td><td>{event.action}</td><td>{event.entity_type}</td><td className="mono">{event.entity_id ?? "—"}</td></tr>)}</tbody></table></div>
          {events.length === 0 && <p className="empty">Nenhum registro nesta página.</p>}<div className="paging"><button disabled={auditOffset===0} className="btn-secondary" onClick={() => setAuditOffset((current) => Math.max(0,current-30))}>Anterior</button><span>Página {Math.floor(auditOffset/30)+1}</span><button disabled={!hasMoreAudit} className="btn-secondary" onClick={() => setAuditOffset((current) => current+30)}>Próxima</button></div>
        </section>}
        </>}
      </div>
    </main>
  </div>;
}
