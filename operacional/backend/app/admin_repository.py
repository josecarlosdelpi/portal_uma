"""Persistence for access administration. No HTTP or role decisions here."""
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AccessInvitation, AuditEvent, GroupMembership, GroupPermission, StoreGroup, User, LocalCredential,
    UserPermissionOverride,
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

    def groups(self) -> list[StoreGroup]:
        return list(self.db.scalars(select(StoreGroup).order_by(StoreGroup.store_code)))

    def group(self, group_id: UUID) -> StoreGroup | None:
        return self.db.get(StoreGroup, group_id)

    def group_for_store(self, store_code: str) -> StoreGroup | None:
        return self.db.scalar(
            select(StoreGroup).where(StoreGroup.store_code == store_code, StoreGroup.active.is_(True))
        )

    def user_stores(self, user_id: UUID) -> list[str]:
        return list(self.db.scalars(
            select(StoreGroup.store_code).join(GroupMembership, GroupMembership.group_id == StoreGroup.id)
            .where(GroupMembership.user_id == user_id)
            .order_by(StoreGroup.store_code)
        ))

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
        self.db.execute(delete(GroupMembership).where(GroupMembership.user_id == user_id))
        self.db.add(GroupMembership(user_id=user_id, group_id=group_id))
        self.db.flush()

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
