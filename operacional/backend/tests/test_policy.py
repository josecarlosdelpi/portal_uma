"""Negative tests confirm that the server never trusts client-side permissions."""
import pytest

from app.policy import (
    Principal, READ_PERMISSIONS, STORE_CODES, can_access, visible_stores,
)


def seller(*, stores=("JOINVILLE",), grants=None, overrides=None):
    return Principal(
        user_id="seller-1", profile="seller",
        store_codes=frozenset(stores),
        group_grants=frozenset(grants or ["sales.view", "sales.revenue.view"]),
        overrides=overrides or {},
    )


def test_reject_unknown_identity_and_unknown_permissions():
    anonymous = Principal(user_id="a", profile="unknown")
    assert not can_access(anonymous, "sales.view", "JOINVILLE")
    assert not can_access(seller(), "dangerous.unknown", "JOINVILLE")
    assert not can_access(seller(), "sales.view", "NO_SUCH_STORE")


def test_profile_alone_grants_nothing():
    """Funcao (profile) nao concede permissao: tudo vem do grupo."""
    administrator = Principal(user_id="admin", profile="administrator")
    assert visible_stores(administrator) == frozenset()
    assert not can_access(administrator, "sales.view", "JOINVILLE")
    assert not can_access(administrator, "sales.import", "ITAJAI")
    assert not can_access(administrator, "daily_tasks.edit", "ITAJAI")


def test_seller_cannot_read_another_store():
    assert can_access(seller(), "sales.view", "JOINVILLE")
    assert not can_access(seller(), "sales.view", "ITAJAI")
    assert not can_access(seller(), "sales.view", "TUBARAO")


def test_governance_never_delegable():
    """Governanca segue exclusiva do SuperAdmin mesmo com concessao explicita."""
    p = seller(overrides={"users.manage": True, "audit.view": True},
               grants=["sales.view", "users.manage", "audit.view"])
    assert not can_access(p, "users.manage", "JOINVILLE")
    assert not can_access(p, "audit.view", "JOINVILLE")
    p_all = seller(stores=tuple(sorted(STORE_CODES)),
                   overrides={"finance.import": True})
    assert not can_access(p_all, "finance.import", "JOINVILLE")


def test_seller_must_have_store_and_permission():
    assert not can_access(seller(grants=["sales.view"]), "sales.revenue.view", "JOINVILLE")
    assert not can_access(seller(), "sales.view", None)


def test_individual_override_can_deny_or_allow():
    p = seller(overrides={"sales.view": False, "targets.view": True})
    assert not can_access(p, "sales.view", "JOINVILLE")
    assert can_access(p, "targets.view", "JOINVILLE")
    assert not can_access(p, "targets.view", "ITAJAI")


def test_write_permission_is_grantable_to_any_profile():
    """Vendedor pode receber edicao elegivel via grupo ou excecao individual."""
    p = seller(grants=["sales.view", "daily_tasks.edit"])
    assert can_access(p, "daily_tasks.edit", "JOINVILLE")
    assert not can_access(p, "daily_tasks.edit", "TUBARAO")
    q = seller(overrides={"checklist.edit": True})
    assert can_access(q, "checklist.edit", "JOINVILLE")


def test_multi_store_principal_uses_explicit_coverage():
    """Varias lojas sao validas quando o grupo cobre cada uma delas."""
    p = seller(stores=("JOINVILLE", "ITAJAI"), grants=["sales.view"])
    assert can_access(p, "sales.view", "JOINVILLE")
    assert can_access(p, "sales.view", "ITAJAI")
    assert not can_access(p, "sales.view", "TUBARAO")
    assert visible_stores(p) == frozenset({"JOINVILLE", "ITAJAI"})


def test_full_scope_permissions_require_all_three_stores():
    """Importacao e fechamento consolidado exigem abrangencia total."""
    one_store = seller(
        grants=["monthly_closing.view", "sales.import"],
        overrides={"monthly_closing.view": True, "sales.import": True},
    )
    assert not can_access(one_store, "monthly_closing.view", "JOINVILLE")
    assert not can_access(one_store, "sales.import", "JOINVILLE")
    two_stores = seller(stores=("JOINVILLE", "ITAJAI"),
                        grants=["monthly_closing.view"])
    assert not can_access(two_stores, "monthly_closing.view", "JOINVILLE")
    full = seller(stores=tuple(sorted(STORE_CODES)),
                  grants=["monthly_closing.view", "sales.import"])
    assert can_access(full, "monthly_closing.view")
    assert can_access(full, "monthly_closing.view", "TUBARAO")
    assert can_access(full, "sales.import", "ITAJAI")


def test_override_deny_wins_even_with_group_grant():
    p = seller(stores=tuple(sorted(STORE_CODES)),
               grants=["monthly_closing.view"],
               overrides={"monthly_closing.view": False})
    assert not can_access(p, "monthly_closing.view")


def test_superadmin_and_inactive():
    root = Principal(user_id="root", profile="administrator", is_superadmin=True,
                     store_codes=STORE_CODES)
    assert can_access(root, "users.manage", "JOINVILLE")
    assert can_access(root, "audit.view", "TUBARAO")
    assert can_access(root, "finance.import", "JOINVILLE")
    assert not can_access(root, "nonexistent.permission", "JOINVILLE")
    off = Principal(user_id="off", profile="administrator", active=False,
                    is_superadmin=True, store_codes=STORE_CODES)
    assert not can_access(off, "users.manage", "JOINVILLE")
    assert visible_stores(off) == frozenset()


def test_indicators_are_not_implied_by_module():
    p = seller(grants=["sales.view"])
    assert can_access(p, "sales.view", "JOINVILLE")
    assert not can_access(p, "sales.attainment.view", "JOINVILLE")


def test_store_bound_permissions_never_apply_without_store():
    p = seller()
    for permission in READ_PERMISSIONS:
        assert not can_access(p, permission, None)


def test_daily_task_permissions_follow_group_grants():
    editor = seller(grants=["daily_tasks.view", "daily_tasks.edit"])
    assert can_access(editor, "daily_tasks.view", "JOINVILLE")
    assert can_access(editor, "daily_tasks.edit", "JOINVILLE")
    assert not can_access(editor, "daily_tasks.edit", "TUBARAO")
    viewer = seller(grants=["daily_tasks.view"], overrides={"daily_tasks.edit": False})
    assert can_access(viewer, "daily_tasks.view", "JOINVILLE")
    assert not can_access(viewer, "daily_tasks.edit", "JOINVILLE")
