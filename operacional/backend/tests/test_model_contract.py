"""Schema assertions to prevent accidental loss of data boundaries."""
from app.models import Base


def test_schema_has_expected_core_tables():
    names = set(Base.metadata.tables)
    assert names == {
        "users", "stores", "store_groups", "group_memberships",
        "group_permissions", "user_permission_overrides", "audit_events",
    }


def test_unique_external_identity_and_store_group():
    users = Base.metadata.tables["users"]
    groups = Base.metadata.tables["store_groups"]
    assert any("auth_subject" in [c.name for c in x.columns] for x in users.constraints if hasattr(x, "columns") and x.__class__.__name__ == "UniqueConstraint")
    assert any("store_code" in [c.name for c in x.columns] for x in groups.constraints if hasattr(x, "columns") and x.__class__.__name__ == "UniqueConstraint")
