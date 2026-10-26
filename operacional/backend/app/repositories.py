"""Leitura das permissoes efetivas: grupo unico da loja + overrides do usuario."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GroupMembership, GroupPermission, StoreGroup, User, UserPermissionOverride
from app.policy import Principal


def load_principal(db: Session, user: User) -> Principal:
    if user.is_superadmin:
        return Principal(user_id=str(user.id), profile=user.profile, active=user.active, is_superadmin=True)

    if user.profile == "administrator":
        return Principal(user_id=str(user.id), profile="administrator", active=user.active)

    rows = db.execute(
        select(StoreGroup.store_code, GroupPermission.code, GroupPermission.granted)
        .join(GroupMembership, GroupMembership.group_id == StoreGroup.id)
        .outerjoin(GroupPermission, GroupPermission.group_id == StoreGroup.id)
        .where(GroupMembership.user_id == user.id, StoreGroup.active.is_(True))
    ).all()

    stores = frozenset(store_code for store_code, _, _ in rows)
    grants = frozenset(code for _, code, granted in rows if code is not None and granted)
    overrides = dict(db.execute(
        select(UserPermissionOverride.code, UserPermissionOverride.granted)
        .where(UserPermissionOverride.user_id == user.id)
    ).all())
    return Principal(
        user_id=str(user.id), profile=user.profile, active=user.active,
        store_codes=stores, group_grants=grants, overrides=overrides,
    )
