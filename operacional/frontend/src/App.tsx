import { useCallback, useEffect, useRef, useState } from "react";
import {
  LayoutDashboard, Phone, Star, Package, ListChecks, CalendarCheck,
  Target, MessageCircle, GraduationCap, ClipboardCheck, Settings,
  Pin, PinOff, GripVertical, ChevronUp, ChevronDown, Menu, ChevronsRight,
  Settings2, X, ShoppingCart,
} from "lucide-react";
import { api, type MyProfile, type PortalUser, type StoreGroup, type AuditEvent, type LocalResetPassword, ApiError } from "./api";
import { labelStore, permissionGroups, readPermissionCodes } from "./catalog";
import { TargetsPage } from "./TargetsPage";
import { OverviewPage } from "./OverviewPage";
import { SalesPage } from "./SalesPage";
import { ClosingPage } from "./ClosingPage";
import { UMA_LOGO_DATA_URI } from "./umaBrand";
import { ReviewsPage } from "./ReviewsPage";
import { SuppliesPage } from "./SuppliesPage";
import { ContactsPage } from "./ContactsPage";
import { ChecklistPage } from "./ChecklistPage";
import { DailyTasksPage } from "./DailyTasksPage";
import { WhatsAppPage } from "./WhatsAppPage";
import { TrainingPage } from "./TrainingPage";
import { AccountsManager, TemporaryPasswordNotice } from "./AccountsManager";

type Tab = "usuarios" | "grupos" | "auditoria";
type Area = "access" | "targets" | "overview" | "closing" | "reviews" | "supplies" | "contacts" | "checklist" | "daily" | "whatsapp" | "training" | "sales";

/** Identificadores estaveis dos modulos (mesmos chaves do backend /preferences). */
const NAV_ITEMS: ReadonlyArray<{ key: Area; label: string; icon: typeof Star }> = [
  { key: "overview", label: "Visão geral", icon: LayoutDashboard },
  { key: "sales", label: "Vendas", icon: ShoppingCart },
  { key: "contacts", label: "Telemarketing", icon: Phone },
  { key: "reviews", label: "Avaliações Google", icon: Star },
  { key: "supplies", label: "Materiais e insumos", icon: Package },
  { key: "checklist", label: "Checklist semanal", icon: ListChecks },
  { key: "daily", label: "Tarefas diárias", icon: CalendarCheck },
  { key: "targets", label: "Metas diárias", icon: Target },
  { key: "whatsapp", label: "Canais digitais", icon: MessageCircle },
  { key: "training", label: "Padrões e treinamentos", icon: GraduationCap },
  { key: "closing", label: "Fechamento Mensal", icon: ClipboardCheck },
  { key: "access", label: "Configurações", icon: Settings },
];
const navLabel = (key: string) => NAV_ITEMS.find(i => i.key === key)?.label ?? key;

/** Texto do breadcrumb a partir da area ativa. */
const errorText = (error: unknown) => error instanceof Error ? error.message : "Não foi possível concluir.";
const profileLabel = (profile: string) =>
  profile === "superadmin" ? "SuperAdmin" : profile === "administrator" ? "Administrador" : "Vendedor";

export function App({ token, onLogout }: { token: string; onLogout: () => void }) {
  const logoutRef = useRef(onLogout);
  logoutRef.current = onLogout;
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
  const [resetResult, setResetResult] = useState<LocalResetPassword | null>(null);

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
      if (problem instanceof ApiError && (problem.status === 401 || problem.status === 403)) logoutRef.current();
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void refresh(); }, [refresh]);

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
      if (previous === "sales" && profile.features.sales) return previous;
      if (previous === "targets" && profile.features.targets) return previous;
      if (previous === "closing" && profile.features.monthly_closing) return previous;
      if (previous === "reviews" && profile.features.reviews) return previous;
      if (previous === "supplies" && profile.features.supplies) return previous;
      if (previous === "contacts" && profile.features.telemarketing) return previous;
      if (previous === "checklist" && profile.features.checklist) return previous;
      if (previous === "daily" && profile.features.daily_tasks) return previous;
      if (previous === "whatsapp" && (profile.features.whatsapp_status||profile.features.instagram)) return previous;
      if (previous === "training" && profile.features.training) return previous;
      if (previous === "access" && profile.profile === "superadmin") return previous;
      if (profile.features.overview) return "overview";
      if (profile.features.sales) return "sales";
      if (profile.features.targets) return "targets";
      if (profile.features.monthly_closing) return "closing";
      if (profile.features.reviews) return "reviews";
      if (profile.features.supplies) return "supplies";
      if (profile.features.telemarketing) return "contacts";
      if (profile.features.checklist) return "checklist";
      if (profile.features.daily_tasks) return "daily";
      if (profile.features.whatsapp_status||profile.features.instagram) return "whatsapp";
      if (profile.features.training) return "training";
      return "access";
    });
  }, [profile]);

  const user = users.find((candidate) => candidate.id === selectedUser);
  const group = groups.find((candidate) => candidate.id === selectedGroup);
  const isSuperAdmin = profile?.profile === "superadmin";
  const isSeller = user?.profile === "seller";
  const canViewTargets = profile?.features?.targets ?? false;
  const canViewSales = profile?.features?.sales ?? false;
  const canViewOverview = profile?.features?.overview ?? false;
  const canViewClosing = profile?.features?.monthly_closing ?? false;
  const canViewReviews = profile?.features?.reviews ?? false;
  const canViewSupplies = profile?.features?.supplies ?? false;
  const canViewContacts = profile?.features?.telemarketing ?? false;
  const canViewChecklist = profile?.features?.checklist ?? false;
  const canViewDaily = profile?.features?.daily_tasks ?? false;
  const canViewWhatsApp = (profile?.features?.whatsapp_status??false)||(profile?.features?.instagram??false);
  const canViewTraining = profile?.features?.training ?? false;

  // ---- sidebar retratil + favoritos (preferencias por usuario no banco) ----
  const [pinned, setPinned] = useState(true);
  const [tempOpen, setTempOpen] = useState(false);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [prefsLoaded, setPrefsLoaded] = useState(false);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !profile || prefsLoaded) return;
    void api.preferences(token).then(p => {
      setPinned(p.sidebar_pinned); setFavorites(p.favorites);
      lastSaved.current = { p: p.sidebar_pinned, f: p.favorites };
      setPrefsLoaded(true);
    }).catch(() => setPrefsLoaded(true));
  }, [token, profile, prefsLoaded]);

  // Fila serializada + numero de gravacao: respostas intermediarias nunca
  // sobrescrevem alteracoes mais recentes do usuario; falha restaura o
  // ultimo estado confirmado pelo servidor.
  const persistQueue = useRef<Promise<boolean>>(Promise.resolve(true));
  const lastSaved = useRef<{ p: boolean; f: string[] } | null>(null);
  const writeSeq = useRef(0);
  const persist = useCallback((nextPinned: boolean, nextFavs: string[]): Promise<boolean> => {
    const seq = ++writeSeq.current;
    persistQueue.current = persistQueue.current.then(async (): Promise<boolean> => {
      try {
        const saved = await api.savePreferences(
          token, { sidebar_pinned: nextPinned, favorites: nextFavs });
        lastSaved.current = { p: saved.sidebar_pinned, f: saved.favorites };
        if (seq === writeSeq.current) {
          setPinned(saved.sidebar_pinned); setFavorites(saved.favorites);
        }
        return true;
      } catch (problem) {
        setError(errorText(problem));
        if (seq === writeSeq.current && lastSaved.current) {
          setPinned(lastSaved.current.p); setFavorites(lastSaved.current.f);
        }
        return false;
      }
    });
    return persistQueue.current;
  }, [token]);

  // ---- modal "Organizar favoritos" ----
  const [organizing, setOrganizing] = useState<string[] | null>(null);
  const [orgSaving, setOrgSaving] = useState(false);
  const [orgError, setOrgError] = useState("");
  const moveOrg = (index: number, dir: -1 | 1) => {
    setOrganizing(prev => {
      if (!prev) return prev;
      const target = index + dir; if (target < 0 || target >= prev.length) return prev;
      const next = [...prev]; const [item] = next.splice(index, 1); next.splice(target, 0, item);
      return next;
    });
  };
  const onOrgDrop = (targetKey: string) => {
    if (!dragKey || dragKey === targetKey || !organizing) { setDragKey(null); setDropTarget(null); return; }
    const next = organizing.filter(k => k !== dragKey);
    next.splice(next.indexOf(targetKey), 0, dragKey);
    setOrganizing(next); setDragKey(null); setDropTarget(null);
  };
  const saveOrganize = async () => {
    if (!organizing) return;
    setOrgSaving(true); setOrgError("");
    const ok = await persist(pinned, organizing);
    setOrgSaving(false);
    if (ok) setOrganizing(null);
    else setOrgError("Não foi possível salvar a organização. Tente novamente.");
  };

  const togglePin = () => { const next = !pinned; setPinned(next); if (next) setTempOpen(false); void persist(next, favorites); };
  const toggleFav = (key: string) => {
    const next = favorites.includes(key) ? favorites.filter(k => k !== key) : [...favorites, key];
    setFavorites(next); void persist(pinned, next);
  };

  const allowedAreas = new Set<Area>();
  if (canViewOverview) allowedAreas.add("overview");
  if (canViewContacts) allowedAreas.add("contacts");
  if (canViewReviews) allowedAreas.add("reviews");
  if (canViewSupplies) allowedAreas.add("supplies");
  if (canViewChecklist) allowedAreas.add("checklist");
  if (canViewDaily) allowedAreas.add("daily");
  if (canViewTargets) allowedAreas.add("targets");
  if (canViewSales) allowedAreas.add("sales");
  if (canViewWhatsApp) allowedAreas.add("whatsapp");
  if (canViewTraining) allowedAreas.add("training");
  if (canViewClosing) allowedAreas.add("closing");
  if (isSuperAdmin) allowedAreas.add("access");
  const visibleItems = NAV_ITEMS.filter(item => allowedAreas.has(item.key));
  const favItems = favorites.filter(k => allowedAreas.has(k as Area))
    .map(k => NAV_ITEMS.find(i => i.key === k)!).filter(Boolean);
  const selectArea = (key: Area) => {
    setArea(key); if (key === "access") setTab("usuarios");
    if (!pinned) setTempOpen(false);
  };

  return <div className={"shell" + (pinned ? " sb-pinned" : " sb-unpinned") + (tempOpen ? " sb-open" : "")}>
    {!pinned && <button type="button" className="edge-strip" aria-label="Abrir menu lateral"
      onMouseEnter={() => setTempOpen(true)} onClick={() => setTempOpen(true)}>
      <ChevronsRight size={13} aria-hidden="true"/></button>}
    {tempOpen && <div className="side-backdrop" onClick={() => setTempOpen(false)} aria-hidden="true"/>}
    {organizing && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="fav-org-title">
      <div className="modal-card fav-org-card">
        <div className="fav-org-head"><h3 id="fav-org-title">Organizar favoritos</h3>
          <button type="button" className="fav-org-close" aria-label="Fechar" onClick={() => setOrganizing(null)}><X size={16}/></button></div>
        <div className="fav-org-list" role="list">
          {organizing.length === 0 && <p className="fav-empty">Nenhum favorito. Adicione pela ★ no menu.</p>}
          {organizing.map((key, i) => {
            const item = NAV_ITEMS.find(n => n.key === key); if (!item) return null;
            return <div key={key} role="listitem"
              className={"fav-org-item" + (dropTarget === key ? " drop-target" : "")}
              draggable onDragStart={() => setDragKey(key)}
              onDragOver={e => { e.preventDefault(); setDropTarget(key); }}
              onDragLeave={() => setDropTarget(p => p === key ? null : p)}
              onDrop={() => onOrgDrop(key)} onDragEnd={() => { setDragKey(null); setDropTarget(null); }}>
              <span className="drag-grip" aria-hidden="true"><GripVertical size={14}/></span>
              <item.icon size={15} className="nav-icon" strokeWidth={1.9}/>
              <span className="fav-org-name">{item.label}</span>
              <span className="fav-org-actions">
                <button type="button" aria-label={"Subir " + item.label} disabled={i === 0}
                  onClick={() => moveOrg(i, -1)}><ChevronUp size={14}/></button>
                <button type="button" aria-label={"Descer " + item.label} disabled={i === organizing.length - 1}
                  onClick={() => moveOrg(i, 1)}><ChevronDown size={14}/></button>
                <button type="button" aria-label={"Remover " + item.label} className="fav-org-remove"
                  onClick={() => setOrganizing(prev => prev ? prev.filter(k => k !== key) : prev)}><X size={14}/></button>
              </span>
            </div>;
          })}
        </div>
        {orgError && <p className="notice notice-error" role="alert">{orgError}</p>}
        <div className="modal-actions">
          <button className="btn-secondary" disabled={orgSaving} onClick={() => setOrganizing(null)}>Cancelar</button>
          <button className="btn-primary" disabled={orgSaving} onClick={() => void saveOrganize()}>
            {orgSaving ? "Salvando…" : "Salvar alterações"}</button>
        </div>
      </div></div>}
    <aside className={"sidebar" + (tempOpen ? " open" : "")} aria-label="Barra lateral">
      <div className="brand">
        <button type="button" className="pin-btn" aria-label={pinned ? "Desafixar barra lateral" : "Fixar barra lateral"}
          title={pinned ? "Desafixar barra" : "Fixar barra"} onClick={togglePin}>{pinned ? <Pin size={13}/> : <PinOff size={13}/>}</button>
        <img className="brand-logo-image" src={UMA_LOGO_DATA_URI} alt="Logotipo original da Universo das Mangueiras"/>
        <div className="brand-title"><strong>PORTAL UMA</strong></div>
        <small className="brand-sub">Gestão operacional</small>
      </div>
      <div className="side-heading side-heading-fav"><span>FAVORITOS</span>
        <button type="button" className="fav-org-btn" aria-label="Organizar favoritos"
          title="Organizar favoritos" onClick={() => { setOrganizing([...favorites]); setOrgError(""); }}>
          <Settings2 size={13}/></button></div>
      <nav aria-label="Favoritos" className="fav-list">
        {favItems.length === 0 && <p className="fav-empty">Toque na ★ de um módulo para fixá-lo aqui.</p>}
        {favItems.map(item => <div key={item.key} className="nav-item fav-item">
          <button className={"nav-link" + (area === item.key ? " active" : "")}
            onClick={() => selectArea(item.key)}><item.icon size={15} className="nav-icon" strokeWidth={1.9}/><span>{item.label}</span></button>
        </div>)}
      </nav>
      <div className="side-heading">PAINEL DE CONTROLE</div>
      <nav aria-label="Menu principal">
        {visibleItems.map(item => <div className="nav-item" key={item.key}>
          <button className={"nav-link" + (area === item.key ? " active" : "")}
            onClick={() => selectArea(item.key)}><item.icon size={15} className="nav-icon" strokeWidth={1.9}/><span>{item.label}</span></button>
          <button type="button" className={"star-btn" + (favorites.includes(item.key) ? " starred" : "")}
            aria-label={(favorites.includes(item.key) ? "Remover " : "Favoritar ") + item.label}
            aria-pressed={favorites.includes(item.key)}
            onClick={() => toggleFav(item.key)}><Star size={14} fill={favorites.includes(item.key) ? "currentColor" : "none"}/></button>
        </div>)}
      </nav>
      <div className="side-spacer"/>
      <div className="sidebar-note"><strong>Ambiente operacional</strong><p>Sem dados demonstrativos. Acesso governado pela API segura.</p></div>
      <div className="sidebar-bottom">Universo das Mangueiras Automotivas</div>
    </aside>
    <main className="main">
      <header className="topbar"><button type="button" className="menu-btn" aria-label="Abrir menu"
        onClick={() => setTempOpen(true)}><Menu size={20}/></button><div className="breadcrumb">Universo das Mangueiras <span> / </span> <strong>{navLabel(area)}</strong></div>
        <div className="topbar-right"><span>{profile?.display_name ?? "Usuário autenticado"}</span><span className="avatar">UMA</span><button className="btn-ghost" onClick={onLogout}>Sair</button></div>
      </header>
      <div className="workspace">
        {area === "overview" && profile ? <OverviewPage token={token} profile={profile} /> :
         area === "sales" && profile ? <SalesPage token={token} profile={profile} /> :
         area === "closing" && profile ? <ClosingPage token={token} profile={profile} /> :
         area === "targets" && profile ? <TargetsPage token={token} profile={profile} /> :
         area === "reviews" && profile ? <ReviewsPage token={token} profile={profile} /> :
         area === "supplies" && profile ? <SuppliesPage token={token} profile={profile} /> :
         area === "contacts" && profile ? <ContactsPage token={token} profile={profile} /> :
         area === "checklist" && profile ? <ChecklistPage token={token} profile={profile} /> :
         area === "daily" && profile ? <DailyTasksPage token={token} profile={profile} /> :
         area === "whatsapp" && profile ? <WhatsAppPage token={token} profile={profile} /> :
         area === "training" && profile ? <TrainingPage token={token} profile={profile} /> : <>
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
        {isSuperAdmin && tab === "usuarios" && <AccountsManager token={token} onCreated={refresh}/>}
        {isSuperAdmin && tab === "usuarios" && <div className="columns">
          <section className="panel"><div className="panel-head"><div><h2>Usuários cadastrados</h2><p>Selecione um colaborador para administrar seu acesso.</p></div><span className="count">{users.length} contas</span></div>
            {users.length === 0 ? <p className="empty">Nenhum usuário cadastrado.</p> :
            <div className="user-list">{users.map((person) => <button key={person.id} className={"user-row" + (selectedUser === person.id ? " selected" : "")} onClick={() => setSelectedUser(person.id)}>
              <span className="user-avatar">{person.display_name.slice(0, 2).toUpperCase()}</span><span className="user-text"><strong>{person.display_name}</strong><small>{profileLabel(person.profile)} · {person.username ? "@" + person.username + " · " : ""}{person.stores.map(labelStore).join(", ") || "Todas as lojas"}</small></span>
              <span className={"pill " + (person.active ? "pill-green" : "pill-grey")}>{person.active ? (person.must_change_password ? "Senha pendente" : "Ativo") : "Suspenso"}</span>
            </button>)}</div>}
            <p className="small-note">Os pré-cadastros aparecem acima. A ativação real depende do serviço de login.</p>
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
                }}>{user.active ? "Suspender acesso" : "Reativar acesso"}</button></div>}
              {!user.profile.includes("superadmin") && <div className="local-account-actions">
                {user.username && <button className="btn-secondary" disabled={working}
                  onClick={() => void update(async () => {
                    const result = await api.resetLocalPassword(token, user.id);
                    setResetResult(result);
                  }, "Nova senha provisória gerada. Entregue somente ao colaborador.")}>
                  Gerar nova senha provisória</button>}
                <button className="btn-secondary local-delete-action" disabled={working}
                  onClick={() => {
                    if (!window.confirm(
                      "Excluir o acesso de " + user.display_name +
                      "? A conta sairá da lista, todas as sessões serão invalidadas e o histórico será preservado."
                    )) return;
                    void update(async () => {
                      await api.deleteUser(token, user.id);
                      setSelectedUser("");
                      setResetResult(null);
                    }, "Usuário excluído da lista; acesso revogado, histórico preservado.");
                  }}>Excluir usuário</button>
              </div>}
              {resetResult?.user_id === user.id && <TemporaryPasswordNotice
                username={resetResult.username} password={resetResult.temporary_password}
                onClose={() => setResetResult(null)}/>}
              <p className="small-note">A exclusão revoga o acesso sem apagar registros históricos.
                A senha provisória é individual e exige troca no primeiro login.</p>
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
