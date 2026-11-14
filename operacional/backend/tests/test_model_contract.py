"""Schema assertions to prevent accidental loss of data boundaries."""
from app.models import Base


def test_schema_has_expected_core_tables():
    names = set(Base.metadata.tables)
    assert names == {
        "users", "local_credentials", "local_sessions", "stores",
        "access_groups", "access_group_stores", "user_store_scopes",
        "group_memberships", "access_invitations",
        "group_permissions", "user_permission_overrides", "audit_events",
        "monthly_sales_targets", "store_target_settings",
        "monthly_closing_drafts", "monthly_closing_archives",
        "google_review_months", "supply_materials", "supply_stocks",
        "supply_movements", "contact_clients", "contact_attempts",
        "weekly_tasks", "weekly_task_checks", "weekly_call_goals", "daily_tasks",
        "whatsapp_posts", "whatsapp_files", "training_documents", "whatsapp_days_off", "instagram_months", "training_records",
        "procedures", "procedure_stores", "procedure_versions", "procedure_files",
        "user_preferences",
        "erp_import_batches", "erp_sale_rows", "erp_return_rows", "erp_source_files",
        "financial_obligations",
    }


def test_unique_external_identity_and_group_name():
    users = Base.metadata.tables["users"]
    groups = Base.metadata.tables["access_groups"]
    assert any("auth_subject" in [c.name for c in x.columns] for x in users.constraints if hasattr(x, "columns") and x.__class__.__name__ == "UniqueConstraint")
    # Grupos sao livres de loja: nome unico, sem coluna store_code.
    assert "store_code" not in groups.columns
    assert any("name" in [c.name for c in x.columns] for x in groups.constraints if hasattr(x, "columns") and x.__class__.__name__ == "UniqueConstraint")


def test_group_store_coverage_and_user_scope_are_composite_keys():
    coverage = Base.metadata.tables["access_group_stores"]
    scope = Base.metadata.tables["user_store_scopes"]
    assert {c.name for c in coverage.primary_key.columns} == {"group_id", "store_code"}
    assert {c.name for c in scope.primary_key.columns} == {"user_id", "store_code"}
    memberships = Base.metadata.tables["group_memberships"]
    assert {c.name for c in memberships.primary_key.columns} == {"user_id", "group_id"}
    # Um usuario comum tem exatamente um grupo principal, garantido pelo banco.
    unique_cols = {
        tuple(c.name for c in constraint.columns)
        for constraint in memberships.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id",) in unique_cols
