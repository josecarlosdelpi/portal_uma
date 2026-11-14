/** Administracao de usuarios, grupos de acesso e permissoes efetivas.
 *  O backend e a unica autoridade; esta tela apenas reflete as respostas. */
import { useEffect, useRef, useState } from "react";
import {
  api, type AccessGroup, type AccessPreview, type EffectivePermissions,
  type GroupDetail, type GroupUpdatePreview, type LocalResetPassword,
  type PortalUser, type ReassignmentPreview,
} from "./api";
import { LatestRequest } from "./asyncGate";
import {
  grantableCodes, labelStore, permissionGroups, permissionName,
} from "./catalog";
import { TemporaryPasswordNotice } from "./AccountsManager";

const STORE_LABELS: Record<string, string> = {
  JOINVILLE: "Joinville", ITAJAI: "Itajaí", TUBARAO: "Tubarão",
};
const ALL_STORES = Object.keys(STORE_LABELS);

const profileLabel = (profile: string) =>
  profile === "superadmin" ? "SuperAdmin"
  : profile === "administrator" ? "Administrador"
  : profile === "staff" ? "Equipe interna" : "Vendedor";

const kindLabel = (kind: string) =>
  kind === "edit" ? "Editar" : kind === "action" ? "Ação" : "Ver";

type Update = (operation: () => Promise<unknown>, success: string) => Promise<void>;

function StoreChecks({ options, selected, onToggle, disabled }: {
  options: string[]; selected: string[];
  onToggle: (code: string) => void; disabled?: boolean;
}) {
  return <div className="scope-checks">
    {options.map((code) => <label key={code} className="check-line">
      <input type="checkbox" checked={selected.includes(code)}
        disabled={disabled} onChange={() => onToggle(code)} />
      <span>{labelStore(code)}</span>
    </label>)}
  </div>;
}

function PermissionMatrix({ selected, onToggle, disabled }: {
  selected: string[]; onToggle: (code: string) => void; disabled?: boolean;
}) {
  return <div className="permissions">
    {permissionGroups.map((section) => <div key={section.module}>
      <h4>{section.title}</h4>
      <p className="small-note">{section.help}</p>
      {section.permissions.map((permission) => <label key={permission.code}
        className="permission-line check-line">
        <input type="checkbox" checked={selected.includes(permission.code)}
          disabled={disabled} onChange={() => onToggle(permission.code)} />
        <span>{permission.name}
          <small className="perm-kind">{kindLabel(permission.kind)}
            {permission.requiresAllStores ? " · exige as 3 lojas" : ""}</small>
          {permission.note && <small className="perm-note">{permission.note}</small>}
        </span>
      </label>)}
    </div>)}
  </div>;
}

// -------------------- Usuarios --------------------

export function UserDetailPanel({ token, user, groups, working, update, onDeleted }: {
  token: string; user: PortalUser; groups: AccessGroup[];
  working: boolean; update: Update; onDeleted: () => void;
}) {
  const [profile, setProfile] = useState(user.profile);
  const [groupId, setGroupId] = useState(user.group?.id ?? "");
  const [scope, setScope] = useState<string[]>(user.store_scope);
  const [overrides, setOverrides] = useState<Record<string, boolean | null>>({});
  const [effective, setEffective] = useState<EffectivePermissions | null>(null);
  const [preview, setPreview] = useState<AccessPreview | null>(null);
  const [previewStatus, setPreviewStatus] =
    useState<"idle" | "loading" | "ready" | "error">("idle");
  const [inheritAll, setInheritAll] = useState(false);
  const [resetResult, setResetResult] = useState<LocalResetPassword | null>(null);
  const [showEffective, setShowEffective] = useState(false);
  // So a previa correspondente a selecao ATUAL pode habilitar a
  // confirmacao — respostas antigas em voo sao descartadas.
  const previewGate = useRef(new LatestRequest<AccessPreview>());

  useEffect(() => {
    previewGate.current.invalidate();
    setProfile(user.profile);
    setGroupId(user.group?.id ?? "");
    setScope(user.store_scope);
    setOverrides(user.overrides);
    setEffective(null);
    setPreview(null);
    setPreviewStatus("idle");
    setInheritAll(false);
    setResetResult(null);
    setShowEffective(false);
  }, [user.id, user.profile, user.group?.id, user.store_scope, user.overrides]);

  const selectedGroup = groups.find((g) => g.id === groupId) ?? null;
  const groupStores = selectedGroup?.stores ?? [];
  const groupChanged = groupId !== (user.group?.id ?? "");
  const scopeChanged = JSON.stringify([...scope].sort()) !==
    JSON.stringify([...user.store_scope].sort());
  const accessDirty = profile !== user.profile || groupChanged || scopeChanged;
  // Restricao individual que nao existe na nova abrangencia nunca vira
  // "herdar tudo" por conta propria: exige definicao explicita.
  const scopeConflict = groupChanged && user.store_scope.length > 0 &&
    scope.length === 0;

  const loadEffective = () => {
    setShowEffective(true);
    void api.effectivePermissions(token, user.id)
      .then(setEffective).catch(() => setEffective(null));
  };

  const refreshPreview = (gid: string, codes: string[]) => {
    if (!gid) {
      previewGate.current.invalidate();
      setPreview(null); setPreviewStatus("idle"); return;
    }
    setPreview(null);
    setPreviewStatus("loading");
    void previewGate.current.issue(() => api.previewUserAccess(token, user.id, {
      group_id: gid, store_codes: [...codes].sort(),
    })).then((result) => {
      if (result === null) return;
      setPreview(result);
      setPreviewStatus("ready");
    }).catch(() => {
      setPreview(null);
      setPreviewStatus("error");
    });
  };

  // Ao trocar de grupo, preserva as restricoes ainda validas na nova
  // abrangencia — o acesso nunca e ampliado sem acao explicita. A previa
  // recebe exatamente o escopo que sera salvo, para nao divergir.
  const changeGroup = (id: string) => {
    setGroupId(id);
    setInheritAll(false);
    const next = groups.find((g) => g.id === id);
    const filtered = scope.filter((s) => next?.stores.includes(s));
    setScope(filtered);
    refreshPreview(id, filtered);
  };

  const overrideOf = (code: string) =>
    overrides[code] === undefined || overrides[code] === null ? "inherit"
    : overrides[code] ? "allow" : "deny";

  const toggleScope = (code: string) => {
    const nextScope = scope.includes(code)
      ? scope.filter((c) => c !== code) : [...scope, code];
    setScope(nextScope);
    setInheritAll(false);
    refreshPreview(groupId, nextScope);
  };

  // Salvar so com a previa carregada quando grupo ou lojas mudam —
  // falha ou ausencia de previa bloqueia a confirmacao.
  const storeChangePending = (groupChanged || scopeChanged) &&
    previewStatus !== "ready";
  const saveBlocked = working || !accessDirty || !groupId ||
    storeChangePending || (scopeConflict && !inheritAll);

  return <>
    <div className="panel-head"><div><h2>{user.display_name}</h2>
      <p>{profileLabel(user.profile)}{user.username ? " · @" + user.username : ""}</p>
    </div></div>

    {user.profile !== "superadmin" && <>
      <div className="form-row"><label htmlFor="user-profile">Função</label>
        <select id="user-profile" value={profile} disabled={working}
          onChange={(event) => setProfile(event.target.value as typeof profile)}>
          <option value="seller">Vendedor — aparece nos cadastros da loja</option>
          <option value="administrator">Administrador</option>
          <option value="staff">Equipe interna — sem vínculo de loja</option>
        </select>
        <p className="small-note">A função não concede permissões: o acesso vem
          do grupo e das exceções individuais.</p>
      </div>
      <div className="form-row"><label htmlFor="user-group">Grupo de acesso</label>
        <select id="user-group" value={groupId} disabled={working}
          onChange={(event) => changeGroup(event.target.value)}>
          <option value="">Selecione um grupo…</option>
          {groups.filter((g) => g.active || g.id === user.group?.id)
            .map((g) => <option key={g.id} value={g.id}>
              {g.name}{g.active ? "" : " (inativo)"}</option>)}
        </select>
      </div>
      {selectedGroup && <div className="form-row">
        <label>Lojas autorizadas dentro do grupo</label>
        <StoreChecks options={groupStores} selected={scope}
          onToggle={toggleScope} disabled={working} />
        <p className="small-note">Sem seleção, o usuário herda toda a abrangência
          do grupo ({selectedGroup.stores.map(labelStore).join(", ")}).</p>
      </div>}
      {scopeConflict && <div className="access-summary">
        <h4>Restrição individual incompatível</h4>
        <p className="small-note">O usuário hoje está restrito a{" "}
          {user.store_scope.map(labelStore).join(", ")}, que não faz parte da
          abrangência do novo grupo. Escolha as lojas acima ou confirme
          explicitamente a opção abaixo — nada é decidido automaticamente.</p>
        <label className="check-line">
          <input type="checkbox" checked={inheritAll} disabled={working}
            onChange={(e) => { setInheritAll(e.target.checked);
              if (e.target.checked) refreshPreview(groupId, []); }} />
          <span>Herdar toda a abrangência do novo grupo
            ({selectedGroup?.stores.map(labelStore).join(", ")})</span>
        </label>
      </div>}
      {(groupChanged || scopeChanged) && <div className="access-summary">
        <h4>Impacto da alteração de acesso</h4>
        {previewStatus === "loading" &&
          <p className="small-note">Calculando acesso efetivo…</p>}
        {previewStatus === "error" && <p className="small-note">
          Não foi possível calcular a prévia — revise os dados antes de salvar
          (a confirmação fica bloqueada).</p>}
        {previewStatus === "ready" && preview && <>
          <p className="small-note">{groupChanged
            ? <>Ao mover para <strong>{preview.group?.name}</strong>:</>
            : "Com o novo escopo de lojas:"}
            {preview.granted.length === 0 && preview.revoked.length === 0
              ? " nenhum acesso muda."
              : <> {"+" + preview.granted.length + " acesso(s) acrescentado(s), −" +
                  preview.revoked.length + " removido(s)."}</>}
            {" "}Lojas efetivas: <strong>{preview.stores.map(labelStore).join(", ") || "nenhuma"}</strong>.</p>
          {preview.granted.length > 0 && <p className="small-note">
            Ganha: {preview.granted.slice(0, 8).map((d) =>
              permissionName(d.code) + " (" + d.stores.map(labelStore).join(", ") + ")"
            ).join(", ")}{preview.granted.length > 8 ? "…" : ""}</p>}
          {preview.revoked.length > 0 && <p className="small-note">
            Perde: {preview.revoked.slice(0, 8).map((d) =>
              permissionName(d.code) + " (" + d.stores.map(labelStore).join(", ") + ")"
            ).join(", ")}{preview.revoked.length > 8 ? "…" : ""}</p>}
        </>}
      </div>}
      <button className="btn-primary" disabled={saveBlocked}
        onClick={() => void update(() => api.updateUserAccess(token, user.id, {
          ...(profile !== user.profile ? { profile } : {}),
          ...(groupChanged ? { group_id: groupId } : {}),
          ...(scopeChanged ? { store_codes: [...scope].sort() } : {}),
        }), "Acesso do usuário atualizado.")}>Salvar função, grupo e lojas</button>
      {storeChangePending && previewStatus !== "error" &&
        <p className="small-note">Aguarde a prévia de acesso para confirmar.</p>}

      <h3>Exceções individuais</h3>
      <p className="small-note">Herdar usa a configuração do grupo. Permitir concede
        e Bloquear retira a permissão apenas para este usuário.</p>
      <div className="permissions">
        {permissionGroups.map((section) => <div key={section.module}>
          <h4>{section.title}</h4>
          {section.permissions.map((permission) => <div className="permission-line"
            key={permission.code}>
            <div>{permission.name}
              <small className="perm-kind">{kindLabel(permission.kind)}</small>
              {permission.note && <small className="perm-note">{permission.note}</small>}
            </div>
            <select aria-label={"Exceção: " + permission.name} disabled={working}
              value={overrideOf(permission.code)}
              onChange={(event) => setOverrides((previous) => ({
                ...previous,
                [permission.code]: event.target.value === "inherit" ? null
                  : event.target.value === "allow",
              }))}>
              <option value="inherit">Herdar</option>
              <option value="allow">Permitir</option>
              <option value="deny">Bloquear</option>
            </select>
          </div>)}
        </div>)}
      </div>
      <button className="btn-primary" disabled={working}
        onClick={() => void update(() => api.saveOverrides(
          token, user.id,
          Object.fromEntries(grantableCodes.map((code) => [code, overrides[code] ?? null])),
        ), "Exceções individuais atualizadas.")}>Salvar exceções</button>

      <div className="status-control"><div>
        <strong>Conta {user.active ? "ativa" : "suspensa"}</strong>
        <small>{user.active
          ? "Usuário pode acessar de acordo com suas permissões."
          : "A conta está bloqueada no Portal UMA."}</small></div>
        <button disabled={working} className="btn-secondary" onClick={() => {
          if (!window.confirm(user.active ? "Suspender este usuário?" : "Reativar este usuário?")) return;
          void update(() => api.setActive(token, user.id, !user.active), "Situação da conta atualizada.");
        }}>{user.active ? "Suspender acesso" : "Reativar acesso"}</button></div>

      <div className="local-account-actions">
        {user.username && <button className="btn-secondary" disabled={working}
          onClick={() => void update(async () => {
            setResetResult(await api.resetLocalPassword(token, user.id));
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
              onDeleted();
            }, "Usuário excluído da lista; acesso revogado, histórico preservado.");
          }}>Excluir usuário</button>
      </div>
      {resetResult && <TemporaryPasswordNotice
        username={resetResult.username} password={resetResult.temporary_password}
        onClose={() => setResetResult(null)} />}

      <h3>Permissões efetivas</h3>
      <p className="small-note">Resultado calculado pelo backend: padrão do grupo,
        exceção individual e lojas onde cada permissão vale.</p>
      <button className="btn-secondary" onClick={loadEffective}>
        {showEffective ? "Recalcular" : "Consultar permissões efetivas"}</button>
      {showEffective && effective && <div className="effective-list">
        <p className="small-note">Grupo: <strong>{effective.group?.name ?? "—"}</strong> ·
          Lojas autorizadas: <strong>{effective.stores.map(labelStore).join(", ") || "nenhuma"}</strong></p>
        {permissionGroups.map((section) => {
          const items = effective.items.filter((i) => i.module === section.module);
          if (!items.length) return null;
          return <div key={section.module}><h4>{section.title}</h4>
            {items.map((item) => <div className="permission-line" key={item.code}>
              <div>{permissionName(item.code)}
                <small className="perm-kind">
                  grupo: {item.group_default ? "sim" : "não"} ·
                  exceção: {item.override === null || item.override === undefined
                    ? "herdar" : item.override ? "permitir" : "bloquear"}
                </small></div>
              <span className={"pill " + (item.effective ? "pill-green" : "pill-grey")}>
                {item.effective ? item.stores.map(labelStore).join(", ") : "Negado"}
              </span>
            </div>)}
          </div>;
        })}
      </div>}
    </>}
    {user.profile === "superadmin" && <p className="small-note">
      A conta SuperAdmin é a autoridade de governança e não usa grupos ou exceções.</p>}
  </>;
}

// -------------------- Grupos --------------------

export function GroupEditor({ token, groups, working, update }: {
  token: string; groups: AccessGroup[];
  working: boolean; update: Update;
}) {
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [storeSel, setStoreSel] = useState<string[]>([]);
  const [permSel, setPermSel] = useState<string[]>([]);
  const [detail, setDetail] = useState<GroupDetail | null>(null);
  const [dupName, setDupName] = useState("");
  const [reassign, setReassign] = useState("");
  const [reassignImpact, setReassignImpact] = useState<ReassignmentPreview | null>(null);
  const [reassignStatus, setReassignStatus] =
    useState<"idle" | "loading" | "ready" | "error">("idle");
  const [updatePreview, setUpdatePreview] = useState<GroupUpdatePreview | null>(null);
  const [updateStatus, setUpdateStatus] =
    useState<"idle" | "loading" | "ready" | "error">("idle");
  const [widenConfirmed, setWidenConfirmed] = useState(false);
  // Gates anti-corrida: so a ultima previa emitida pode atualizar a UI.
  const reassignGate = useRef(new LatestRequest<ReassignmentPreview>());
  const updateGate = useRef(new LatestRequest<GroupUpdatePreview>());

  const selected = groups.find((g) => g.id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    void api.groupDetail(token, selectedId).then(setDetail).catch(() => setDetail(null));
  }, [token, selectedId, groups]);

  const choose = (id: string) => {
    setCreating(false);
    setSelectedId(id);
    const group = groups.find((g) => g.id === id);
    setName(group?.name ?? "");
    setDescription(group?.description ?? "");
    setStoreSel(group?.stores ?? []);
    setPermSel(group?.permissions ?? []);
    setDupName("");
    setReassign("");
    setReassignImpact(null);
    setReassignStatus("idle");
    setUpdatePreview(null);
    setUpdateStatus("idle");
    setWidenConfirmed(false);
    reassignGate.current.invalidate();
    updateGate.current.invalidate();
  };

  const chooseReassign = (id: string) => {
    setReassign(id);
    setReassignImpact(null);
    if (id && selectedId) {
      setReassignStatus("loading");
      void reassignGate.current.issue(
        () => api.reassignmentPreview(token, selectedId, id),
      ).then((result) => {
        if (result === null) return;
        setReassignImpact(result);
        setReassignStatus("ready");
      }).catch(() => setReassignStatus("error"));
    } else {
      reassignGate.current.invalidate();
      setReassignStatus("idle");
    }
  };

  const startCreate = () => {
    setCreating(true);
    setSelectedId("");
    setName(""); setDescription(""); setStoreSel([]); setPermSel([]); setDetail(null);
  };

  const toggle = (list: string[], code: string, apply: (next: string[]) => void) =>
    apply(list.includes(code) ? list.filter((c) => c !== code) : [...list, code]);

  const dirty = selected && (
    name !== selected.name || description !== selected.description ||
    JSON.stringify([...storeSel].sort()) !== JSON.stringify([...selected.stores].sort()) ||
    JSON.stringify([...permSel].sort()) !== JSON.stringify([...selected.permissions].sort()));

  // Mudanca de abrangencia ou de permissoes num grupo COM membros exige
  // previa de impacto antes de salvar; ampliacao exige confirmacao explicita.
  const accessFieldsDirty = !!selected && (
    JSON.stringify([...storeSel].sort()) !== JSON.stringify([...selected.stores].sort()) ||
    JSON.stringify([...permSel].sort()) !== JSON.stringify([...selected.permissions].sort()));
  const needsUpdatePreview = accessFieldsDirty &&
    (selected?.member_count ?? 0) > 0;

  useEffect(() => {
    if (!needsUpdatePreview || !selected) {
      updateGate.current.invalidate();
      setUpdatePreview(null); setUpdateStatus("idle");
      setWidenConfirmed(false);
      return;
    }
    setUpdatePreview(null); setUpdateStatus("loading");
    setWidenConfirmed(false);
    void updateGate.current.issue(() => api.groupUpdatePreview(
      token, selected.id, {
        name: name.trim() || selected.name,
        description: description.trim(),
        store_codes: [...storeSel].sort(),
        permissions: [...permSel].sort(),
      },
    )).then((result) => {
      if (result === null) return;
      setUpdatePreview(result); setUpdateStatus("ready");
    }).catch(() => setUpdateStatus("error"));
    // A previa recalcula a cada mudanca de lojas/permissoes; nome e
    // descricao nao afetam o acesso e nao disparam recalculo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selected?.id, needsUpdatePreview, storeSel, permSel]);

  const widensAccess = needsUpdatePreview && (updatePreview?.widens ?? false);
  const saveBlocked = working || !dirty || !storeSel.length ||
    (needsUpdatePreview && updateStatus !== "ready") ||
    (widensAccess && !widenConfirmed);

  return <div className="columns">
    <section className="panel">
      <div className="panel-head"><div><h2>Grupos de acesso</h2>
        <p>Cada usuário pertence a um grupo; a abrangência limita as lojas.</p></div>
        <button className="btn-primary" onClick={startCreate}>+ Novo grupo</button></div>
      <div className="user-list">{groups.map((candidate) =>
        <button key={candidate.id}
          className={"user-row" + (selectedId === candidate.id ? " selected" : "")}
          onClick={() => choose(candidate.id)}>
          <span className="user-avatar">◆</span>
          <span className="user-text"><strong>{candidate.name}</strong>
            <small>{candidate.stores.map(labelStore).join(", ") || "sem lojas"} ·
              {" "}{candidate.member_count} usuário{candidate.member_count === 1 ? "" : "s"}</small></span>
          <span className={"pill " + (candidate.active ? "pill-green" : "pill-grey")}>
            {candidate.active ? "Ativo" : "Inativo"}</span>
        </button>)}</div>
    </section>
    <section className="panel">
      {creating ? <>
        <h2>Novo grupo de acesso</h2>
        <p className="small-note">Grupos novos começam sem permissões sensíveis:
          marque apenas o que for necessário.</p>
        <div className="form-row"><label>Nome<input value={name} maxLength={120}
          placeholder="Ex.: Estoque — Joinville" onChange={(e) => setName(e.target.value)} /></label></div>
        <div className="form-row"><label>Descrição<input value={description} maxLength={300}
          placeholder="Finalidade do grupo" onChange={(e) => setDescription(e.target.value)} /></label></div>
        <div className="form-row"><label>Abrangência por loja</label>
          <StoreChecks options={ALL_STORES} selected={storeSel}
            onToggle={(code) => toggle(storeSel, code, setStoreSel)} /></div>
        <h3>Permissões padrão do grupo</h3>
        <PermissionMatrix selected={permSel} disabled={working}
          onToggle={(code) => toggle(permSel, code, setPermSel)} />
        <div className="btn-row">
          <button className="btn-primary" disabled={working || name.trim().length < 2 || !storeSel.length}
            onClick={() => void update(async () => {
              const created = await api.createGroup(token, {
                name: name.trim(), description: description.trim(),
                store_codes: storeSel, permissions: permSel,
              });
              setCreating(false);
              setSelectedId(created.id);
            }, "Grupo criado.")}>Criar grupo</button>
          <button className="btn-secondary" onClick={() => setCreating(false)}>Cancelar</button>
        </div>
      </> : !selected ? <div className="empty">
        Selecione um grupo para configurar ou crie um novo.</div> : <>
        <div className="panel-head"><div><h2>{selected.name}</h2>
          <p>{selected.member_count} usuário{selected.member_count === 1 ? "" : "s"} vinculado{selected.member_count === 1 ? "" : "s"} — alterações afetam quem herda do grupo.</p></div></div>
        <div className="form-row"><label>Nome<input value={name} maxLength={120}
          disabled={working} onChange={(e) => setName(e.target.value)} /></label></div>
        <div className="form-row"><label>Descrição<input value={description} maxLength={300}
          disabled={working} onChange={(e) => setDescription(e.target.value)} /></label></div>
        <div className="form-row"><label>Abrangência por loja</label>
          <StoreChecks options={ALL_STORES} selected={storeSel}
            onToggle={(code) => toggle(storeSel, code, setStoreSel)} disabled={working} /></div>
        <h3>Permissões do grupo</h3>
        <PermissionMatrix selected={permSel} disabled={working}
          onToggle={(code) => toggle(permSel, code, setPermSel)} />
        {needsUpdatePreview && <div className="access-summary">
          <h4>Impacto da alteração nos {selected.member_count} usuário(s) do grupo</h4>
          {updateStatus === "loading" &&
            <p className="small-note">Calculando o impacto por usuário e loja…</p>}
          {updateStatus === "error" && <p className="small-note">
            Não foi possível calcular o impacto — o salvamento fica bloqueado
            até a prévia carregar.</p>}
          {updateStatus === "ready" && updatePreview && <>
            {updatePreview.members.every((m) =>
              m.granted.length === 0 && m.revoked.length === 0)
              ? <p className="small-note">Nenhum acesso efetivo muda para os
                usuários do grupo.</p>
              : updatePreview.members.map((member) => <p key={member.user_id}
                className="small-note"><strong>{member.display_name}</strong>:
                {member.granted.length === 0 && member.revoked.length === 0
                  ? " sem mudança de acesso"
                  : " +" + member.granted.length + " / −" + member.revoked.length +
                    " acesso(s)"}
                {" · lojas: " + (member.stores_after.map(labelStore).join(", ") || "nenhuma")}
                {member.granted.length + member.revoked.length > 0 &&
                  <><br />{"Δ " + [...member.granted.map((d) => "+" + permissionName(d.code) +
                    " (" + d.stores.map(labelStore).join(",") + ")"),
                    ...member.revoked.map((d) => "−" + permissionName(d.code) +
                    " (" + d.stores.map(labelStore).join(",") + ")"),
                    ].slice(0, 6).join(", ")}</>}
              </p>)}
            {updatePreview.widens && <label className="check-line">
              <input type="checkbox" checked={widenConfirmed} disabled={working}
                onChange={(e) => setWidenConfirmed(e.target.checked)} />
              <span>Confirmo que esta alteração <strong>amplia</strong> o acesso
                de {updatePreview.members.filter((m) => m.granted.length > 0).length}{" "}
                usuário(s), conforme o impacto exibido acima.</span>
            </label>}
          </>}
        </div>}
        <button className="btn-primary" disabled={saveBlocked}
          onClick={() => void update(async () => {
            const result = await api.updateGroup(token, selected.id, {
              name: name.trim(), description: description.trim(),
              store_codes: storeSel, permissions: permSel,
            });
            setUpdatePreview(null); setUpdateStatus("idle");
            setWidenConfirmed(false);
            window.alert("Grupo atualizado. " + result.members_affected +
              " usuário(s) afetado(s) pela mudança de permissões.");
          }, "Grupo atualizado.")}>
          Salvar alterações ({selected.member_count} usuário{selected.member_count === 1 ? "" : "s"})</button>
        {needsUpdatePreview && updateStatus !== "ready" &&
          <p className="small-note">Aguarde a prévia de impacto para confirmar
            — a alteração afeta os usuários do grupo.</p>}

        {detail && <><h3>Usuários vinculados</h3>
          {detail.members.length === 0 ? <p className="empty">Nenhum usuário neste grupo.</p> :
          <div className="user-list">{detail.members.map((member) =>
            <div key={member.id} className="user-row">
              <span className="user-avatar">{member.display_name.slice(0, 2).toUpperCase()}</span>
              <span className="user-text"><strong>{member.display_name}</strong>
                <small>{member.active ? "Conta ativa" : "Conta suspensa"}</small></span>
            </div>)}</div>}</>}

        <h3>Ações do grupo</h3>
        <div className="local-account-grid">
          <label>Duplicar grupo<input value={dupName} maxLength={120}
            placeholder={"Cópia de " + selected.name}
            onChange={(e) => setDupName(e.target.value)} /></label>
        </div>
        <button className="btn-secondary" disabled={working || dupName.trim().length < 2}
          onClick={() => void update(async () => {
            const copy = await api.duplicateGroup(token, selected.id, dupName.trim());
            setDupName("");
            setSelectedId(copy.id);
          }, "Grupo duplicado.")}>Duplicar este grupo</button>
        <div className="status-control"><div>
          <strong>Grupo {selected.active ? "ativo" : "inativo"}</strong>
          <small>{selected.active
            ? "Usuários vinculados herdam as permissões configuradas."
            : "Grupo inativo não concede acesso nem aceita novos membros."}</small></div>
          <button className="btn-secondary" disabled={working}
            onClick={() => {
              if (selected.active && selected.member_count > 0) {
                window.alert("Este grupo tem usuários vinculados. Reatribua-os antes de desativar.");
                return;
              }
              void update(() => api.setGroupActive(token, selected.id, !selected.active),
                "Situação do grupo atualizada.");
            }}>{selected.active ? "Desativar grupo" : "Reativar grupo"}</button></div>
        {selected.member_count > 0 && <div className="form-row">
          <label>Reatribuir usuários para</label>
          <select value={reassign} disabled={working}
            onChange={(e) => chooseReassign(e.target.value)}>
            <option value="">Selecione o grupo de destino…</option>
            {groups.filter((g) => g.id !== selected.id && g.active)
              .map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select></div>}
        {selected.member_count > 0 && reassign && <div className="access-summary">
          <h4>Impacto da reatribuição</h4>
          {reassignStatus === "loading" &&
            <p className="small-note">Calculando o acesso de cada usuário…</p>}
          {reassignStatus === "error" && <p className="small-note">
            Não foi possível calcular o impacto — a exclusão fica bloqueada
            até a prévia carregar.</p>}
          {reassignStatus === "ready" && reassignImpact &&
            reassignImpact.members.map((member) => <p key={member.user_id}
              className="small-note"><strong>{member.display_name}</strong>:
              {member.granted.length === 0 && member.revoked.length === 0
                ? " sem mudança de acesso"
                : " +" + member.granted.length + " / −" + member.revoked.length + " acesso(s)"}
              {" · lojas: " + (member.stores_after.map(labelStore).join(", ") || "nenhuma")}
              {member.granted.length + member.revoked.length > 0 &&
                <><br />{"Δ " + [...member.granted.map((d) => "+" + permissionName(d.code) +
                  " (" + d.stores.map(labelStore).join(",") + ")"),
                  ...member.revoked.map((d) => "−" + permissionName(d.code) +
                  " (" + d.stores.map(labelStore).join(",") + ")"),
                  ].slice(0, 6).join(", ")}</>}
            </p>)}
        </div>}
        <button className="btn-secondary local-delete-action" disabled={working ||
          (selected.member_count > 0 &&
            (!reassign || reassignStatus !== "ready"))}
          onClick={() => {
            if (!window.confirm(
              "Excluir o grupo " + selected.name + "?" +
              (selected.member_count > 0
                ? " Os " + selected.member_count + " usuário(s) serão reatribuídos a " +
                  (reassignImpact?.target.name ?? "o grupo selecionado") +
                  " conforme o impacto exibido."
                : ""))) return;
            void update(async () => {
              await api.deleteGroup(token, selected.id, reassign || undefined);
              setSelectedId(""); setDetail(null);
            }, "Grupo excluído.");
          }}>Excluir grupo</button>
      </>}
    </section>
  </div>;
}
