"""Schema assertions to prevent accidental loss of data boundaries."""
from app.models import Base


def test_schema_has_expected_core_tables():
    names = set(Base.metadata.tables)
    assert names == {
        "users", "local_credentials", "local_sessions", "stores", "store_groups", "group_memberships", "access_invitations",
        "group_permissions", "user_permission_overrides", "audit_events",
        "monthly_sales_targets", "store_target_settings",
        "monthly_closing_drafts", "monthly_closing_archives",
        "google_review_months", "supply_materials", "supply_stocks",
        "supply_movements", "contact_clients", "contact_attempts",
        "weekly_tasks", "weekly_task_checks", "weekly_call_goals",
        "whatsapp_posts", "whatsapp_days_off", "instagram_months", "training_records",
    }


def test_unique_external_identity_and_store_group():
    users = Base.metadata.tables["users"]
    groups = Base.metadata.tables["store_groups"]
    assert any("auth_subject" in [c.name for c in x.columns] for x in users.constraints if hasattr(x, "columns") and x.__class__.__name__ == "UniqueConstraint")
    assert any("store_code" in [c.name for c in x.columns] for x in groups.constraints if hasattr(x, "columns") and x.__class__.__name__ == "UniqueConstraint")
