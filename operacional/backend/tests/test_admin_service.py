"""Security invariants for the administration application layer."""
from uuid import uuid4
from types import SimpleNamespace

import pytest

from app.admin_service import AdminError, AdminService, require_superadmin
from app.policy import STORE_CODES


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
    def __init__(self):
        self.actor = fake_user(superadmin=True)
        self.target = fake_user(profile="seller")
        self.access_group = fake_group()
        self.groups = {self.access_group.id: self.access_group}
        self.membership = {self.target.id: self.access_group.id}
        self.scopes = {}
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

    def member_count(self, group_id):
        return sum(1 for gid in self.membership.values() if gid == group_id)

    def members(self, group_id):
        return [self.target] if self.membership.get(self.target.id) == group_id else []

    def grants(self, group_id):
        return ["sales.view"]

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
