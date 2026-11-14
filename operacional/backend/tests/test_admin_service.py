"""Security invariants for the administration application layer."""
from uuid import uuid4
from types import SimpleNamespace

import pytest

import app.admin_service as admin_module
from app.admin_service import AdminError, AdminService, require_superadmin
from app.policy import STORE_CODES, Principal


def fake_user(*, superadmin=False, active=True, profile="administrator"):
    return SimpleNamespace(
        id=uuid4(), auth_subject="oidc-sub", display_name="Test",
        profile=profile, is_superadmin=superadmin, active=active,
        deleted_at=None,
    )


def fake_group(*, stores=("JOINVILLE",), name="Vendedores Joinville", active=True):
    return SimpleNamespace(
        id=uuid4(), name=name, description="", active=active,
        stores=set(stores),
    )


class FakeAdminRepository:
    db = None  # load_principal e stubado nos testes de previa

    def __init__(self):
        self.actor = fake_user(superadmin=True)
        self.target = fake_user(profile="seller")
        self.access_group = fake_group()
        self.groups = {self.access_group.id: self.access_group}
        self.membership = {self.target.id: self.access_group.id}
        self.scopes = {}
        self.grant_sets = {}
        self.changes = []
        self.events = []
        self.commits = 0

    # --- leitura ---
    def user(self, user_id):
        return self.target if user_id == self.target.id else None

    def user_by_subject(self, subject):
        return None

    def group(self, group_id):
        return self.groups.get(group_id)

    def group_of(self, user_id):
        return self.groups.get(self.membership.get(user_id))

    def group_by_name(self, name_key):
        for group in self.groups.values():
            if group.name.casefold() == name_key:
                return group
        return None

    def group_stores(self, group_id):
        group = self.groups.get(group_id)
        return sorted(group.stores) if group else []

    def groups_covering(self, store_code):
        return sorted(
            (group for group in self.groups.values()
             if group.active and store_code in group.stores),
            key=lambda group: group.name,
        )

    def member_count(self, group_id):
        return sum(1 for gid in self.membership.values() if gid == group_id)

    def members(self, group_id):
        return [self.target] if self.membership.get(self.target.id) == group_id else []

    def grants(self, group_id):
        return sorted(self.grant_sets.get(group_id, ["sales.view"]))

    def overrides(self, user_id):
        return {}

    def user_scope(self, user_id):
        return sorted(self.scopes.get(user_id, set()))

    def user_stores(self, user_id):
        group = self.group_of(user_id)
        stores = set(group.stores) if group else set()
        scope = self.scopes.get(user_id, set())
        if scope:
            stores &= scope
        return sorted(stores)

    # --- escrita ---
    def create_user(self, *, subject, name, profile):
        created = fake_user(profile=profile)
        self.changes.append(("user", subject, name, profile))
        return created

    def create_group(self, *, name, description):
        group = fake_group(name=name, stores=())
        self.groups[group.id] = group
        self.changes.append(("group", name))
        return group

    def set_membership(self, user_id, group_id):
        if group_id is None:
            self.membership.pop(user_id, None)
        else:
            self.membership[user_id] = group_id

    def move_members(self, from_group, to_group):
        moved = 0
        for user_id, gid in list(self.membership.items()):
            if gid == from_group:
                self.membership[user_id] = to_group
                moved += 1
        return moved

    def delete_group(self, group):
        self.groups.pop(group.id, None)
        self.changes.append(("delete_group", group.name))

    def replace_user_scope(self, user_id, stores):
        self.scopes[user_id] = set(stores)

    def replace_group_stores(self, group_id, stores):
        self.groups[group_id].stores = set(stores)

    def replace_grants(self, group_id, allowed):
        self.grant_sets[group_id] = set(allowed)
        self.changes.append(("grants", allowed))

    def replace_overrides(self, user_id, updates):
        self.changes.append(("overrides", updates))

    def audit(self, actor, action, entity_type, entity_id, details):
        self.events.append((action, details))

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


@pytest.mark.parametrize("actor", [
    fake_user(superadmin=False),
    fake_user(superadmin=True, active=False),
])
def test_only_active_superadmin_controls_access(actor):
    with pytest.raises(AdminError) as exc:
        AdminService(FakeAdminRepository(), actor)
    assert exc.value.status_code == 403


def test_non_delegable_permissions_rejected_for_groups():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    for denied in ("users.manage", "audit.view", "security.manage",
                   "finance.import", "made.up.permission"):
        with pytest.raises(AdminError) as error:
            service.replace_group_permissions(repo.access_group.id, [denied])
        assert error.value.status_code == 422
    assert repo.events == [] and repo.commits == 0


def test_full_scope_permission_requires_all_stores():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.replace_group_permissions(repo.access_group.id, ["monthly_closing.view"])
    assert error.value.status_code == 422
    assert repo.commits == 0


def test_write_and_indicator_grants_are_allowed_with_audit():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    result = service.replace_group_permissions(
        repo.access_group.id, ["sales.view", "sales.revenue.view", "checklist.edit"]
    )
    assert "checklist.edit" in result["permissions"]
    assert repo.commits == 1
    assert repo.events[0][0] == "group.permissions.updated"


def test_group_lifecycle_create_duplicate_deactivate_delete():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    created = service.create_group(
        name="Estoque", description="Equipe de estoque",
        store_codes=["JOINVILLE", "TUBARAO"], permissions=["supplies.view"],
    )
    assert created["name"] == "Estoque"
    assert created["stores"] == ["JOINVILLE", "TUBARAO"]
    assert repo.events[0][0] == "group.created"

    # grupo com membros nao pode ser desativado
    repo.membership[repo.target.id] = repo.access_group.id
    with pytest.raises(AdminError) as error:
        service.set_group_active(repo.access_group.id, False)
    assert error.value.status_code == 409
    # nem excluido sem reatribuicao
    with pytest.raises(AdminError) as error:
        service.delete_group(repo.access_group.id, None)
    assert error.value.status_code == 422


def test_create_group_rejects_full_scope_without_all_stores():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.create_group(
            name="Gerencia", description="",
            store_codes=["JOINVILLE"], permissions=["monthly_closing.view"],
        )
    assert error.value.status_code == 422
    assert repo.commits == 0


def test_override_cannot_grant_governance():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.replace_user_overrides(repo.target.id, {"users.manage": True})
    assert error.value.status_code == 422
    assert not repo.changes and not repo.events


def test_override_inherit_allow_deny_and_audit():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    result = service.replace_user_overrides(
        repo.target.id,
        {"sales.view": False, "targets.view": True, "reviews.view": None},
    )
    assert result["overrides"] == {"sales.view": False, "targets.view": True}
    assert repo.commits == 1
    assert repo.events[0][0] == "user.permissions.updated"


def test_user_scope_must_stay_inside_group_coverage():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.assign_user_store(repo.target.id, "TUBARAO")
    assert error.value.status_code == 422
    assert repo.commits == 0
    result = service.assign_user_store(repo.target.id, "JOINVILLE")
    assert result["stores"] == ["JOINVILLE"]
    assert result["store_scope"] == ["JOINVILLE"]
    assert repo.events[0][0] == "user.access.changed"


def test_user_update_requires_active_group():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    repo.access_group.active = False
    with pytest.raises(AdminError) as error:
        service.update_user_access(repo.target.id, store_codes=["JOINVILLE"])
    assert error.value.status_code == 422
    assert repo.commits == 0


def test_cannot_create_superadmin_and_user_requires_group():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError):
        service.add_user(subject="identity", name="Name", profile="superadmin")
    with pytest.raises(AdminError):
        service.add_user(subject="identity", name="Name", profile="seller")
    assert repo.commits == 0


def test_add_user_registers_membership_and_audit():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    result = service.add_user(
        subject="oidc-novo", name="Novo", profile="seller",
        group_id=repo.access_group.id,
    )
    assert result["group"]["name"] == "Vendedores Joinville"
    assert result["stores"] == ["JOINVILLE"]
    assert repo.events[0][0] == "user.created"
    assert repo.commits == 1


def test_superadmin_cannot_be_disabled():
    repo = FakeAdminRepository()
    repo.target = fake_user(superadmin=True)
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.set_user_active(repo.target.id, False)
    assert error.value.status_code == 403
    assert repo.commits == 0


def test_account_status_changes_are_audited():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    result = service.set_user_active(repo.target.id, False)
    assert result["active"] is False
    assert repo.events[0][0] == "user.status.changed"
    assert repo.commits == 1


# ---------- resolucao inequivococa de grupo (cadastro legado) ----------


def test_legacy_store_code_resolution_with_ambiguous_groups_rejected():
    """Dois grupos ativos cobrindo a mesma loja: store_code nao escolhe."""
    repo = FakeAdminRepository()
    repo.groups[repo.access_group.id] = repo.access_group
    admin_group = fake_group(stores=("JOINVILLE", "ITAJAI", "TUBARAO"),
                             name="Administradores")
    repo.groups[admin_group.id] = admin_group
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.add_user(subject="novo", name="Novo", profile="seller",
                         store_code="JOINVILLE")
    assert error.value.status_code == 422
    assert repo.commits == 0


def test_legacy_store_code_resolution_unique_group_still_works():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    result = service.add_user(subject="novo", name="Novo", profile="seller",
                              store_code="JOINVILLE")
    assert result["group"]["id"] == str(repo.access_group.id)


def test_legacy_store_code_resolution_ignores_inactive_groups():
    repo = FakeAdminRepository()
    extra = fake_group(stores=("JOINVILLE",), name="Inativo", active=False)
    repo.groups[extra.id] = extra
    service = AdminService(repo, repo.actor)
    result = service.add_user(subject="novo", name="Novo", profile="seller",
                              store_code="JOINVILLE")
    assert result["group"]["id"] == str(repo.access_group.id)


# ---------- preservacao de escopo ----------


def test_update_user_access_preserves_scope_when_not_sent():
    """Mudar so a funcao nao pode ampliar lojas nem apagar o escopo."""
    repo = FakeAdminRepository()
    repo.scopes[repo.target.id] = {"JOINVILLE"}
    service = AdminService(repo, repo.actor)
    result = service.update_user_access(repo.target.id, profile="staff")
    assert result["profile"] == "staff"
    assert result["store_scope"] == ["JOINVILLE"]
    assert repo.scopes[repo.target.id] == {"JOINVILLE"}


def test_update_user_access_explicit_empty_scope_inherits_group():
    repo = FakeAdminRepository()
    repo.access_group.stores = {"JOINVILLE", "TUBARAO"}
    repo.scopes[repo.target.id] = {"JOINVILLE"}
    service = AdminService(repo, repo.actor)
    result = service.update_user_access(repo.target.id, store_codes=[])
    assert result["store_scope"] == []
    assert result["stores"] == ["JOINVILLE", "TUBARAO"]


def test_group_change_keeps_restrictive_scope_rows():
    """Escopo preservado ao trocar de grupo: nunca amplia, so restringe."""
    repo = FakeAdminRepository()
    repo.access_group.stores = {"JOINVILLE", "TUBARAO"}
    repo.scopes[repo.target.id] = {"JOINVILLE"}
    narrower = fake_group(stores=("JOINVILLE",), name="Restrito")
    repo.groups[narrower.id] = narrower
    service = AdminService(repo, repo.actor)
    result = service.update_user_access(repo.target.id, group_id=narrower.id)
    assert result["store_scope"] == ["JOINVILLE"]
    assert result["stores"] == ["JOINVILLE"]


def test_scope_outside_group_coverage_rejected():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.update_user_access(repo.target.id, store_codes=["TUBARAO"])
    assert error.value.status_code == 422
    assert repo.commits == 0


# ---------- previas de acesso efetivo ----------


def _stub_principal(repo):
    def _load(_db, user):
        group = repo.group_of(user.id)
        return Principal(
            user_id=str(user.id), profile=user.profile, active=user.active,
            is_superadmin=user.is_superadmin,
            store_codes=frozenset(repo.user_stores(user.id)),
            group_grants=frozenset(repo.grants(group.id)) if group else frozenset(),
            overrides=repo.overrides(user.id),
        )
    return _load


def test_preview_user_access_shows_grants_and_revocations(monkeypatch):
    repo = FakeAdminRepository()
    repo.grant_sets[repo.access_group.id] = {"sales.view", "checklist.edit"}
    richer = fake_group(stores=("JOINVILLE", "TUBARAO"), name="Gerencia")
    repo.groups[richer.id] = richer
    repo.grant_sets[richer.id] = {"sales.view", "targets.view", "targets.edit"}
    monkeypatch.setattr(admin_module, "load_principal", _stub_principal(repo))
    service = AdminService(repo, repo.actor)
    preview = service.preview_user_access(repo.target.id, group_id=richer.id)
    granted = {(d["code"], tuple(d["stores"])) for d in preview["granted"]}
    assert granted == {
        ("targets.edit", ("JOINVILLE", "TUBARAO")),
        ("targets.view", ("JOINVILLE", "TUBARAO")),
        ("sales.view", ("TUBARAO",)),          # mesma permissao, loja acrescentada
    }
    assert preview["revoked"] == [{"code": "checklist.edit", "stores": ["JOINVILLE"]}]
    assert preview["before"]["checklist.edit"] == ["JOINVILLE"]
    assert preview["stores"] == ["JOINVILLE", "TUBARAO"]
    assert repo.commits == 0  # previa nunca persiste


def test_preview_diff_is_per_permission_and_store(monkeypatch):
    """sales.view de uma loja para as tres: a previa lista as lojas
    acrescentadas, nao apenas o codigo ja existente."""
    repo = FakeAdminRepository()
    repo.grant_sets[repo.access_group.id] = {"sales.view"}
    wide = fake_group(stores=("JOINVILLE", "TUBARAO", "ITAJAI"), name="Amplo")
    repo.groups[wide.id] = wide
    repo.grant_sets[wide.id] = {"sales.view"}
    monkeypatch.setattr(admin_module, "load_principal", _stub_principal(repo))
    service = AdminService(repo, repo.actor)
    preview = service.preview_user_access(repo.target.id, group_id=wide.id)
    assert preview["granted"] == [
        {"code": "sales.view", "stores": ["ITAJAI", "TUBARAO"]}]
    assert preview["revoked"] == []


def test_preview_same_group_with_scope_change(monkeypatch):
    """Mesmo grupo, mudanca de lojas: a previa ainda mostra o impacto."""
    repo = FakeAdminRepository()
    repo.access_group.stores = {"JOINVILLE", "TUBARAO"}
    repo.grant_sets[repo.access_group.id] = {"sales.view"}
    monkeypatch.setattr(admin_module, "load_principal", _stub_principal(repo))
    service = AdminService(repo, repo.actor)
    preview = service.preview_user_access(
        repo.target.id, group_id=repo.access_group.id,
        store_codes=["JOINVILLE"])
    assert preview["granted"] == []
    assert preview["revoked"] == [
        {"code": "sales.view", "stores": ["TUBARAO"]}]
    assert preview["stores"] == ["JOINVILLE"]


def test_group_change_with_fully_incompatible_scope_requires_explicit_choice():
    """Restricao que nao existe no novo grupo nao vira 'herdar tudo'
    silenciosamente: o backend exige definicao explicita."""
    repo = FakeAdminRepository()
    repo.scopes[repo.target.id] = {"JOINVILLE"}
    other = fake_group(stores=("TUBARAO",), name="So Tubarao")
    repo.groups[other.id] = other
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.update_user_access(repo.target.id, group_id=other.id)
    assert error.value.status_code == 422
    assert "escopo" in error.value.message.lower()
    assert repo.commits == 0
    # Explicitamente vazio = decisao consciente de herdar toda a abrangencia
    result = service.update_user_access(
        repo.target.id, group_id=other.id, store_codes=[])
    assert result["stores"] == ["TUBARAO"]
    assert result["store_scope"] == []
    # Ou explicitamente com uma loja do novo grupo
    repo.scopes[repo.target.id] = {"JOINVILLE"}
    repo.membership[repo.target.id] = repo.access_group.id
    result = service.update_user_access(
        repo.target.id, group_id=other.id, store_codes=["TUBARAO"])
    assert result["store_scope"] == ["TUBARAO"]


def test_group_change_with_partially_compatible_scope_is_preserved():
    """Se parte da restricao segue valida, ela e preservada sem exigir
    redefinicao — o acesso nunca e ampliado."""
    repo = FakeAdminRepository()
    repo.access_group.stores = {"JOINVILLE", "ITAJAI"}
    repo.scopes[repo.target.id] = {"JOINVILLE", "ITAJAI"}
    narrower = fake_group(stores=("JOINVILLE",), name="Restrito")
    repo.groups[narrower.id] = narrower
    service = AdminService(repo, repo.actor)
    result = service.update_user_access(repo.target.id, group_id=narrower.id)
    # escopo preservado (inclusive a loja fora da nova abrangencia, que
    # simplesmente nao tem efeito) — efetivo segue restrito a JOINVILLE
    assert result["stores"] == ["JOINVILLE"]


def test_preview_user_access_respects_scope_intersection(monkeypatch):
    repo = FakeAdminRepository()
    wider = fake_group(stores=("JOINVILLE", "TUBARAO"), name="Duas lojas")
    repo.groups[wider.id] = wider
    repo.grant_sets[wider.id] = {"sales.view"}
    monkeypatch.setattr(admin_module, "load_principal", _stub_principal(repo))
    service = AdminService(repo, repo.actor)
    preview = service.preview_user_access(
        repo.target.id, group_id=wider.id, store_codes=["TUBARAO"])
    assert preview["stores"] == ["TUBARAO"]
    with pytest.raises(AdminError) as error:
        service.preview_user_access(
            repo.target.id, group_id=wider.id, store_codes=["ITAJAI"])
    assert error.value.status_code == 422


def test_preview_reassignment_reports_per_member_impact(monkeypatch):
    repo = FakeAdminRepository()
    repo.scopes[repo.target.id] = {"JOINVILLE"}
    repo.access_group.stores = {"JOINVILLE", "TUBARAO"}
    repo.grant_sets[repo.access_group.id] = {"sales.view", "checklist.edit"}
    target_group = fake_group(stores=("TUBARAO",), name="Estoque")
    repo.groups[target_group.id] = target_group
    repo.grant_sets[target_group.id] = {"supplies.view"}
    monkeypatch.setattr(admin_module, "load_principal", _stub_principal(repo))
    service = AdminService(repo, repo.actor)
    preview = service.preview_reassignment(repo.access_group.id, target_group.id)
    assert preview["member_count"] == 1
    member = preview["members"][0]
    # Escopo individual preservado: usuario continua limitado a JOINVILLE,
    # que o grupo de destino nao cobre -> acesso efetivo cai para zero.
    assert member["stores_after"] == []
    assert member["stores_before"] == ["JOINVILLE"]
    revoked = {(d["code"], tuple(d["stores"])) for d in member["revoked"]}
    assert revoked == {
        ("sales.view", ("JOINVILLE",)),
        ("checklist.edit", ("JOINVILLE",)),
    }


def test_preview_reassignment_rejects_invalid_target():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.preview_reassignment(repo.access_group.id, repo.access_group.id)
    assert error.value.status_code == 422
    inactive = fake_group(name="Inativo", active=False)
    repo.groups[inactive.id] = inactive
    with pytest.raises(AdminError) as error:
        service.preview_reassignment(repo.access_group.id, inactive.id)
    assert error.value.status_code == 422
