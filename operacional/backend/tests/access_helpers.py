"""Fabrica de grupos de acesso para os fixtures de teste.

Replica o modelo novo: grupos tem abrangencia (access_group_stores) e
permissoes (group_permissions); administradores NAO possuem mais acesso
implicito — recebem um grupo completo como na migracao 0020.
"""
from uuid import uuid4

from app.models import (
    AccessGroup, AccessGroupStore, GroupMembership, GroupPermission,
)
from app.policy import OPERATIONAL_PERMISSIONS, STORE_CODES


def seed_group(db, name, stores, permissions=(), members=()):
    group = AccessGroup(id=uuid4(), name=name, active=True)
    db.add(group)
    db.flush()
    for code in stores:
        db.add(AccessGroupStore(group_id=group.id, store_code=code))
    for member in members:
        db.add(GroupMembership(user_id=member.id, group_id=group.id))
    for code in permissions:
        db.add(GroupPermission(group_id=group.id, code=code, granted=True))
    return group


def seed_admin_access(db, admin, *, name="Administradores"):
    """Concede ao usuario o acesso operacional completo das tres lojas."""
    return seed_group(
        db, name, sorted(STORE_CODES), sorted(OPERATIONAL_PERMISSIONS), [admin],
    )
