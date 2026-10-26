import { useCallback, useEffect, useState } from "react";
import { api, type AccessInvitation, type PrepareAccessInput } from "./api";
import { labelStore } from "./catalog";

type Props = { token: string };

function statusText(status: AccessInvitation["status"]) {
  switch (status) {
    case "prepared": return "Preparado — não enviado";
    case "sent": return "Convite enviado";
    case "activated": return "Acesso ativado";
    case "cancelled": return "Cancelado";
    case "expired": return "Expirado";
  }
}

const storeCodes = ["JOINVILLE", "ITAJAI", "TUBARAO"];
const emptyForm: PrepareAccessInput = {
  display_name: "", email: "", profile: "seller", store_code: "JOINVILLE",
};

export function AccessInvitations({ token }: Props) {
  const [invitations, setInvitations] = useState<AccessInvitation[]>([]);
  const [form, setForm] = useState<PrepareAccessInput>({ ...emptyForm });
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    const response = await api.invitations(token);
    setInvitations(response);
  }, [token]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    void api.invitations(token).then((items) => {
      if (live) setInvitations(items);
    }).catch((cause: unknown) => {
      if (live) setError(cause instanceof Error ? cause.message : "Falha ao carregar os acessos.");
    }).finally(() => {
      if (live) setLoading(false);
    });
    return () => { live = false; };
  }, [token]);

  async function prepare() {
    setWorking(true); setError(""); setMessage("");
    try {
      await api.prepareInvitation(token, {
        ...form, display_name: form.display_name.trim(),
        email: form.email.trim(),
        store_code: form.profile === "seller" ? form.store_code : null,
      });
      await reload();
      setMessage("Pré-cadastro salvo. Nenhum convite ou senha foi enviado.");
      setForm({ ...emptyForm }); setShowForm(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível preparar o acesso.");
    } finally {
      setWorking(false);
    }
  }

  async function cancel(invite: AccessInvitation) {
    if (!window.confirm(
      "Cancelar o pré-cadastro de " + invite.display_name + "? Nenhuma conta será ativada."
    )) return;
    setWorking(true); setError(""); setMessage("");
    try {
      await api.cancelInvitation(token, invite.id, invite.revision);
      await reload();
      setMessage("Pré-cadastro cancelado. O histórico da ação foi preservado.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível cancelar.");
    } finally {
      setWorking(false);
    }
  }

  function reopen(invite: AccessInvitation) {
    setForm({
      display_name: invite.display_name,
      email: invite.email,
      profile: invite.profile,
      store_code: invite.profile === "seller" ? invite.store_code : null,
    });
    setShowForm(true);
    setMessage("");
  }

  const pending = invitations.filter((item) => item.status === "prepared");
  const history = invitations.filter((item) => item.status !== "prepared");

  return <section className="panel access-invitations">
    <div className="panel-head">
      <div>
        <h2>Novos colaboradores e convites</h2>
        <p>Prepare os acessos dos colaboradores antes de habilitar o envio de convites.</p>
      </div>
      <button className="btn-primary" disabled={working} onClick={() => {
        setShowForm((shown) => !shown); setError(""); setMessage("");
      }}>{showForm ? "Fechar cadastro" : "+ Novo colaborador"}</button>
    </div>
    <div className="notice notice-amber" role="note">
      <strong>Envio de convites e senhas ainda não habilitado.</strong> Os pré-cadastros
      ficam registrados no banco, mas ninguém consegue entrar no portal até que
      o provedor de identidade esteja configurado e o acesso seja ativado.
    </div>
    {error && <div role="alert" className="notice notice-error">{error}</div>}
    {message && <div role="status" className="notice notice-success">{message}</div>}

    {showForm && <div className="access-invite-form">
      <h3>Preparar acesso</h3>
      <div className="access-invite-grid">
        <label>Nome do colaborador
          <input value={form.display_name} maxLength={150} placeholder="Nome e sobrenome"
            onChange={(e) => setForm((old) => ({ ...old, display_name: e.target.value }))}/>
        </label>
        <label>E-mail individual
          <input type="email" value={form.email} maxLength={254}
            placeholder="colaborador@exemplo.com.br" autoComplete="off"
            onChange={(e) => setForm((old) => ({ ...old, email: e.target.value }))}/>
        </label>
        <label>Perfil
          <select value={form.profile} onChange={(e) => setForm((old) => ({
            ...old, profile: e.target.value as PrepareAccessInput["profile"],
            store_code: e.target.value === "seller" ? "JOINVILLE" : null,
          }))}>
            <option value="seller">Vendedor — consulta somente</option>
            <option value="administrator">Administrador operacional — três lojas</option>
          </select>
        </label>
        {form.profile === "seller" && <label>Loja do vendedor
          <select value={form.store_code ?? "JOINVILLE"} onChange={(e) =>
            setForm((old) => ({ ...old, store_code: e.target.value }))}>
            {storeCodes.map((store) => <option value={store} key={store}>{labelStore(store)}</option>)}
          </select>
        </label>}
      </div>
      <p className="small-note">
        O SuperAdmin é único e não pode ser cadastrado por esta tela.
        Não informe senhas pessoais. Neste estágio nenhum e-mail será enviado.
      </p>
      <div className="btn-row">
        <button className="btn-primary" disabled={
          working || form.display_name.trim().length < 2 ||
          !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim()) ||
          (form.profile === "seller" && !form.store_code)
        } onClick={() => void prepare()}>
          {working ? "Salvando…" : "Salvar pré-cadastro"}
        </button>
        <button className="btn-secondary" disabled={working}
          onClick={() => setShowForm(false)}>Cancelar</button>
      </div>
    </div>}
    <h3>Acessos aguardando ativação <span className="chip">{pending.length}</span></h3>
    {loading && <p className="small-note" role="status">Carregando pré-cadastros…</p>}
    {!loading && pending.length === 0 && <p className="empty">
      Nenhum acesso em preparação. Use “Novo colaborador” para começar.
    </p>}
    <div className="access-invite-list">
      {pending.map((invite) => <div className="access-invite-row" key={invite.id}>
        <div className="access-invite-identity">
          <strong>{invite.display_name}</strong>
          <small>{invite.email} · {invite.profile === "seller"
            ? "Vendedor — " + labelStore(invite.store_code ?? "")
            : "Administrador — todas as lojas"}</small>
          <span className="access-invite-state">{statusText(invite.status)}</span>
        </div>
        <button className="btn-secondary" disabled={working}
          onClick={() => void cancel(invite)}>Cancelar pré-cadastro</button>
      </div>)}
    </div>
    {history.length > 0 && <details className="access-invite-history">
      <summary>Ver pré-cadastros anteriores ({history.length})</summary>
      {history.map((invite) => <div className="access-invite-row" key={invite.id}>
        <div className="access-invite-identity">
          <strong>{invite.display_name}</strong>
          <small>{invite.email} · {statusText(invite.status)}</small>
        </div>
        {invite.status === "cancelled" && <button className="btn-secondary"
          disabled={working} onClick={() => reopen(invite)}>Preparar novamente</button>}
      </div>)}
    </details>}
    <div className="access-password-info">
      <strong>Como serão criadas e redefinidas as senhas?</strong>
      <p>Após conectar o serviço de autenticação, cada colaborador receberá um convite
        individual para definir sua senha. A redefinição será feita por esse serviço,
        sem expor a senha ao SuperAdmin ou armazená-la no Portal UMA.</p>
      <p className="small-note">Contas já ativadas podem ter o acesso suspenso na lista de usuários abaixo.
        Os históricos administrativos serão mantidos.</p>
    </div>
  </section>;
}
