"""Leitura das permissoes efetivas: grupo de acesso + lojas do usuario + excecoes."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccessGroup, AccessGroupStore, GroupMembership, GroupPermission, User,
    UserPermissionOverride, UserStoreScope,
)
from app.policy import Principal, STORE_CODES


def load_principal(db: Session, user: User) -> Principal:
    if user.is_superadmin:
        return Principal(
            user_id=str(user.id), profile=user.profile, active=user.active,
            is_superadmin=True, store_codes=STORE_CODES,
        )

    group_ids = list(db.scalars(
        select(GroupMembership.group_id)
        .join(AccessGroup, AccessGroup.id == GroupMembership.group_id)
        .where(GroupMembership.user_id == user.id, AccessGroup.active.is_(True))
    ))

    stores = frozenset(db.scalars(
        select(AccessGroupStore.store_code)
        .where(AccessGroupStore.group_id.in_(group_ids))
    ).all()) if group_ids else frozenset()

    # Restricao individual de lojas: quando existem linhas, o usuario fica
    # limitado a intercessao com a abrangencia do(s) grupo(s).
    scoped = frozenset(db.scalars(
        select(UserStoreScope.store_code).where(UserStoreScope.user_id == user.id)
    ).all())
    if scoped:
        stores = stores & scoped

    grants = frozenset(db.scalars(
        select(GroupPermission.code)
        .where(GroupPermission.group_id.in_(group_ids), GroupPermission.granted.is_(True))
    ).all()) if group_ids else frozenset()

    overrides = dict(db.execute(
        select(UserPermissionOverride.code, UserPermissionOverride.granted)
        .where(UserPermissionOverride.user_id == user.id)
    ).all())
    return Principal(
        user_id=str(user.id), profile=user.profile, active=user.active,
        store_codes=stores, group_grants=grants, overrides=overrides,
    )
