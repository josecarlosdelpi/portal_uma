"""Negative tests confirm that the server never trusts client-side permissions."""
import pytest

from app.policy import (
    Principal, READ_PERMISSIONS, STORE_CODES, can_access, visible_stores,
)


def seller(*, store="JOINVILLE", grants=None, overrides=None):
    return Principal(
        user_id="seller-1", profile="seller", store_codes=frozenset([store]),
        group_grants=frozenset(grants or ["sales.view", "sales.revenue.view"]),
        overrides=overrides or {},
    )


def test_reject_unknown_identity_and_unknown_permissions():
    anonymous = Principal(user_id="a", profile="unknown")
    assert not can_access(anonymous, "sales.view", "JOINVILLE")
    assert not can_access(seller(), "dangerous.unknown", "JOINVILLE")
    assert not can_access(seller(), "sales.view", "NO_SUCH_STORE")


def test_seller_cannot_read_another_store():
    assert can_access(seller(), "sales.view", "JOINVILLE")
    assert not can_access(seller(), "sales.view", "ITAJAI")
    assert not can_access(seller(), "sales.view", "TUBARAO")


def test_seller_is_read_only_even_with_override():
    p = seller(overrides={"sales.import": True, "users.manage": True})
    assert not can_access(p, "sales.import", "JOINVILLE")
    assert not can_access(p, "users.manage", "JOINVILLE")


def test_seller_must_have_store_and_permission():
    assert not can_access(seller(grants=["sales.view"]), "sales.revenue.view", "JOINVILLE")
    assert not can_access(seller(), "sales.view", None)


def test_individual_override_can_deny_or_allow_only_read_access():
    p = seller(overrides={"sales.view": False, "targets.view": True})
    assert not can_access(p, "sales.view", "JOINVILLE")
    assert can_access(p, "targets.view", "JOINVILLE")
    assert not can_access(p, "targets.view", "ITAJAI")


def test_ambiguous_group_memberships_are_denied():
    p = Principal(
        user_id="x", profile="seller",
        store_codes=frozenset(["JOINVILLE", "ITAJAI"]),
        group_grants=frozenset(["sales.view"]),
    )
    assert not can_access(p, "sales.view", "JOINVILLE")
    assert visible_stores(p) == frozenset()


def test_administrators_manage_operations_but_not_security():
    admin = Principal(user_id="admin", profile="administrator")
    assert visible_stores(admin) == STORE_CODES
    assert can_access(admin, "sales.import", "ITAJAI")
    assert can_access(admin, "monthly_closing.archive", "TUBARAO")
    assert not can_access(admin, "users.manage", "ITAJAI")
    assert not can_access(admin, "audit.view", "JOINVILLE")


def test_superadmin_and_inactive():
    root = Principal(user_id="root", profile="administrator", is_superadmin=True)
    assert can_access(root, "users.manage", "JOINVILLE")
    assert can_access(root, "audit.view", "TUBARAO")
    assert not can_access(root, "nonexistent.permission", "JOINVILLE")
    off = Principal(user_id="off", profile="administrator", active=False, is_superadmin=True)
    assert not can_access(off, "users.manage", "JOINVILLE")
    assert visible_stores(off) == frozenset()


def test_indicators_are_not_implied_by_module():
    p = seller(grants=["sales.view"])
    assert can_access(p, "sales.view", "JOINVILLE")
    assert not can_access(p, "sales.attainment.view", "JOINVILLE")


def test_seller_permissions_never_apply_without_store_filter():
    p = seller()
    for permission in READ_PERMISSIONS:
        assert not can_access(p, permission, None)
