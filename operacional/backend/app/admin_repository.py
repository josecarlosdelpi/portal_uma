"""Persistence for access administration. No HTTP or role decisions here."""
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AccessGroup, AccessGroupStore, AccessInvitation, AuditEvent, GroupMembership,
    GroupPermission, User, LocalCredential, UserPermissionOverride, UserStoreScope,
)


class AdminRepository:
    def __init__(self, db: Session):
        self.db = db

    def users(self) -> list[User]:
        return list(self.db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.display_name, User.id)))

    def user(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def user_by_subject(self, subject: str) -> User | None:
        return self.db.scalar(select(User).where(User.auth_subject == subject))

    def create_user(self, *, subject: str, name: str, profile: str) -> User:
        user = User(id=uuid4(), auth_subject=subject, display_name=name,
                    profile=profile, is_superadmin=False, active=True)
        self.db.add(user)
        self.db.flush()
        return user

    def invitations(self) -> list[AccessInvitation]:
        return list(self.db.scalars(
            select(AccessInvitation).order_by(
                AccessInvitation.created_at.desc(), AccessInvitation.id.desc()
            )
        ))

    def invitation(self, invitation_id: UUID) -> AccessInvitation | None:
        return self.db.scalar(
            select(AccessInvitation).where(
                AccessInvitation.id == invitation_id
            ).with_for_update()
        )

    def invitation_by_email(self, email_key: str) -> AccessInvitation | None:
        return self.db.scalar(
            select(AccessInvitation).where(
                AccessInvitation.email_key == email_key
            ).with_for_update()
        )

    def add_invitation(self, *, email: str, email_key: str, name: str,
                       profile: str, store_code: str | None,
                       actor_id: UUID) -> AccessInvitation:
        invitation = AccessInvitation(
            id=uuid4(), email=email, email_key=email_key,
            display_name=name, profile=profile, store_code=store_code,
            status="prepared", revision=1,
            prepared_by=actor_id, updated_by=actor_id,
        )
        self.db.add(invitation)
        self.db.flush()
        return invitation

    def local_credential(self, user_id: UUID) -> LocalCredential | None:
        return self.db.get(LocalCredential, user_id)

    # ---- grupos de acesso ----

    def groups(self) -> list[AccessGroup]:
        return list(self.db.scalars(
            select(AccessGroup).order_by(AccessGroup.name, AccessGroup.id)
        ))

    def group(self, group_id: UUID) -> AccessGroup | None:
        return self.db.get(AccessGroup, group_id)

    def group_by_name(self, name_key: str) -> AccessGroup | None:
        return self.db.scalar(
            select(AccessGroup).where(func.lower(AccessGroup.name) == name_key)
        )

    def groups_covering(self, store_code: str) -> list[AccessGroup]:
        """Grupos ativos cuja abrangencia inclui a loja (ordem deterministica)."""
        return list(self.db.scalars(
            select(AccessGroup)
            .join(AccessGroupStore, AccessGroupStore.group_id == AccessGroup.id)
            .where(AccessGroupStore.store_code == store_code,
                   AccessGroup.active.is_(True))
            .order_by(AccessGroup.name, AccessGroup.id)
        ))

    def create_group(self, *, name: str, description: str) -> AccessGroup:
        group = AccessGroup(id=uuid4(), name=name, description=description, active=True)
        self.db.add(group)
        self.db.flush()
        return group

    def delete_group(self, group: AccessGroup) -> None:
        self.db.delete(group)
        self.db.flush()

    def group_stores(self, group_id: UUID) -> list[str]:
        return list(self.db.scalars(
            select(AccessGroupStore.store_code)
            .where(AccessGroupStore.group_id == group_id)
            .order_by(AccessGroupStore.store_code)
        ))

    def replace_group_stores(self, group_id: UUID, stores: set[str]) -> None:
        self.db.execute(delete(AccessGroupStore).where(AccessGroupStore.group_id == group_id))
        self.db.add_all(
            AccessGroupStore(group_id=group_id, store_code=code)
            for code in sorted(stores)
        )
        self.db.flush()

    def members(self, group_id: UUID) -> list[User]:
        return list(self.db.scalars(
            select(User)
            .join(GroupMembership, GroupMembership.user_id == User.id)
            .where(GroupMembership.group_id == group_id, User.deleted_at.is_(None))
            .order_by(User.display_name, User.id)
        ))

    def member_count(self, group_id: UUID) -> int:
        return int(self.db.scalar(
            select(func.count(GroupMembership.user_id))
            .join(User, User.id == GroupMembership.user_id)
            .where(GroupMembership.group_id == group_id, User.deleted_at.is_(None))
        ) or 0)

    def group_of(self, user_id: UUID) -> AccessGroup | None:
        return self.db.scalar(
            select(AccessGroup)
            .join(GroupMembership, GroupMembership.group_id == AccessGroup.id)
            .where(GroupMembership.user_id == user_id)
            .order_by(AccessGroup.name)
            .limit(1)
        )

    def set_membership(self, user_id: UUID, group_id: UUID | None) -> None:
        self.db.execute(delete(GroupMembership).where(GroupMembership.user_id == user_id))
        if group_id is not None:
            self.db.add(GroupMembership(user_id=user_id, group_id=group_id))
        self.db.flush()

    def move_members(self, from_group: UUID, to_group: UUID) -> int:
        user_ids = list(self.db.scalars(
            select(GroupMembership.user_id).where(GroupMembership.group_id == from_group)
        ))
        for user_id in user_ids:
            self.set_membership(user_id, to_group)
        return len(user_ids)

    # ---- lojas autorizadas por usuario ----

    def user_scope(self, user_id: UUID) -> list[str]:
        return list(self.db.scalars(
            select(UserStoreScope.store_code)
            .where(UserStoreScope.user_id == user_id)
            .order_by(UserStoreScope.store_code)
        ))

    def replace_user_scope(self, user_id: UUID, stores: set[str]) -> None:
        self.db.execute(delete(UserStoreScope).where(UserStoreScope.user_id == user_id))
        self.db.add_all(
            UserStoreScope(user_id=user_id, store_code=code)
            for code in sorted(stores)
        )
        self.db.flush()

    def user_stores(self, user_id: UUID) -> list[str]:
        """Lojas efetivas: abrangencia do grupo intersectada com o escopo individual."""
        group_ids = list(self.db.scalars(
            select(GroupMembership.group_id)
            .join(AccessGroup, AccessGroup.id == GroupMembership.group_id)
            .where(GroupMembership.user_id == user_id, AccessGroup.active.is_(True))
        ))
        if not group_ids:
            return []
        stores = set(self.db.scalars(
            select(AccessGroupStore.store_code)
            .where(AccessGroupStore.group_id.in_(group_ids))
        ).all())
        scoped = set(self.user_scope(user_id))
        if scoped:
            stores &= scoped
        return sorted(stores)

    def grants(self, group_id: UUID) -> list[str]:
        return list(self.db.scalars(
            select(GroupPermission.code)
            .where(GroupPermission.group_id == group_id, GroupPermission.granted.is_(True))
            .order_by(GroupPermission.code)
        ))

    def overrides(self, user_id: UUID) -> dict[str, bool]:
        return dict(self.db.execute(
            select(UserPermissionOverride.code, UserPermissionOverride.granted)
            .where(UserPermissionOverride.user_id == user_id)
        ).all())

    def assign_store(self, user_id: UUID, group_id: UUID) -> None:
        """Compatibilidade: vincula o usuario ao grupo (membrosip unica)."""
        self.set_membership(user_id, group_id)

    def replace_grants(self, group_id: UUID, allowed: set[str]) -> None:
        self.db.execute(delete(GroupPermission).where(GroupPermission.group_id == group_id))
        self.db.add_all(
            GroupPermission(group_id=group_id, code=code, granted=True)
            for code in sorted(allowed)
        )
        self.db.flush()

    def replace_overrides(self, user_id: UUID, updates: dict[str, bool | None]) -> None:
        self.db.execute(delete(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id))
        self.db.add_all(
            UserPermissionOverride(user_id=user_id, code=code, granted=granted)
            for code, granted in sorted(updates.items()) if granted is not None
        )
        self.db.flush()

    def audit(self, actor: User, action: str, entity_type: str, entity_id: str | None,
              details: dict) -> None:
        self.db.add(AuditEvent(
            id=uuid4(), actor_id=actor.id, actor_subject=actor.auth_subject,
            action=action, entity_type=entity_type, entity_id=entity_id,
            details=details,
        ))

    def audit_history(self, *, limit: int, offset: int) -> list[AuditEvent]:
        return list(self.db.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit).offset(offset)
        ))

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
