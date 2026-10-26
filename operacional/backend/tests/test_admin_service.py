"""Security invariants for the administration application layer."""
from uuid import uuid4
from types import SimpleNamespace

import pytest

from app.admin_service import AdminError, AdminService, require_superadmin


def fake_user(*, superadmin=False, active=True, profile="administrator"):
    return SimpleNamespace(
        id=uuid4(), auth_subject="oidc-sub", display_name="Test",
        profile=profile, is_superadmin=superadmin, active=active,
    )


class FakeAdminRepository:
    def __init__(self):
        self.actor = fake_user(superadmin=True)
        self.target = fake_user(profile="seller")
        self.store_group = SimpleNamespace(id=uuid4(), store_code="JOINVILLE", active=True)
        self.changes = []
        self.events = []
        self.commits = 0

    def user(self, user_id):
        return self.target if user_id == self.target.id else None

    def user_by_subject(self, subject):
        return None

    def group(self, group_id):
        return self.store_group if group_id == self.store_group.id else None

    def group_for_store(self, store_code):
        return self.store_group if store_code == "JOINVILLE" else None

    def grants(self, group_id):
        return ["sales.view"]

    def overrides(self, user_id):
        return {}

    def user_stores(self, user_id):
        return ["JOINVILLE"]

    def replace_grants(self, group_id, allowed):
        self.changes.append(("grants", allowed))

    def replace_overrides(self, user_id, updates):
        self.changes.append(("overrides", updates))

    def assign_store(self, user_id, group_id):
        self.changes.append(("store", group_id))

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


def test_only_read_grants_for_store_group():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.replace_group_permissions(repo.store_group.id, ["sales.import"])
    assert error.value.status_code == 422
    assert repo.events == [] and repo.commits == 0

    result = service.replace_group_permissions(
        repo.store_group.id, ["sales.view", "sales.revenue.view"]
    )
    assert result["store"] == "JOINVILLE"
    assert repo.commits == 1
    assert repo.events[0][0] == "group.permissions.updated"


def test_override_cannot_grant_write_or_cross_store():
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
        repo.target.id, {"sales.view": False, "targets.view": True, "reviews.view": None}
    )
    assert result["overrides"] == {"sales.view": False, "targets.view": True}
    assert repo.commits == 1
    assert repo.events[0][0] == "user.permissions.updated"


def test_user_store_reassignment_is_restricted():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError) as error:
        service.assign_user_store(repo.target.id, "TUBARAO")
    assert error.value.status_code == 422
    assert repo.commits == 0
    result = service.assign_user_store(repo.target.id, "JOINVILLE")
    assert result["stores"] == ["JOINVILLE"]
    assert repo.events[0][0] == "user.store.changed"


def test_cannot_create_superadmin_or_multiple_store_seller():
    repo = FakeAdminRepository()
    service = AdminService(repo, repo.actor)
    with pytest.raises(AdminError):
        service.add_user(subject="identity", name="Name", profile="superadmin", store_code=None)
    with pytest.raises(AdminError):
        service.add_user(subject="identity", name="Name", profile="seller", store_code=None)
    assert repo.commits == 0


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
