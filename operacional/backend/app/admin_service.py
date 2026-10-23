"""Business use cases for permissions and user administration.

Every mutation is restricted to the only system superadmin, is atomic with
its audit event, and never grants write or cross-store permissions to sellers.
"""
from uuid import UUID
import re

from sqlalchemy.exc import IntegrityError

from app.admin_repository import AdminRepository
from app.models import AccessInvitation, StoreGroup, User
from app.policy import READ_PERMISSIONS, STORE_CODES


class AdminError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def require_superadmin(user: User) -> None:
    if not user.active or not user.is_superadmin:
        raise AdminError(403, "Access denied")


class AdminService:
    def __init__(self, repo: AdminRepository, actor: User):
        require_superadmin(actor)
        self.repo = repo
        self.actor = actor

    def _save(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as exc:
            self.repo.rollback()
            raise AdminError(409, "Conflicting record") from exc

    def list_users(self) -> list[dict]:
        return [
            {
                "id": str(user.id),
                "display_name": user.display_name,
                "profile": "superadmin" if user.is_superadmin else user.profile,
                "active": user.active,
                "stores": self.repo.user_stores(user.id),
                "overrides": self.repo.overrides(user.id),
            }
            for user in self.repo.users()
        ]

    def list_groups(self) -> list[dict]:
        return [
            {
                "id": str(group.id),
                "store": group.store_code,
                "name": group.name,
                "active": group.active,
                "permissions": self.repo.grants(group.id),
            }
            for group in self.repo.groups()
        ]

    def add_user(self, *, subject: str, name: str, profile: str,
                 store_code: str | None) -> dict:
        subject = subject.strip()
        name = name.strip()
        if not subject or not name:
            raise AdminError(422, "Identity and display name must be nonempty")
        if profile not in {"administrator", "seller"}:
            raise AdminError(422, "Unsupported profile")
        if profile == "seller" and store_code not in STORE_CODES:
            raise AdminError(422, "Seller must have one valid store")
        if profile == "administrator" and store_code is not None:
            raise AdminError(422, "Administrators are not tied to one store")
        if self.repo.user_by_subject(subject) is not None:
            raise AdminError(409, "Identity is already registered")
        group = self.repo.group_for_store(store_code) if store_code else None
        if profile == "seller" and group is None:
            raise AdminError(422, "Store group not configured")

        user = self.repo.create_user(subject=subject, name=name, profile=profile)
        if group:
            self.repo.assign_store(user.id, group.id)
        self.repo.audit(self.actor, "user.created", "user", str(user.id),
                        {"profile": profile, "store": store_code})
        self._save()
        return {"id": str(user.id), "display_name": user.display_name,
                "profile": profile, "active": True, "stores": [store_code] if group else []}

    @staticmethod
    def _public_invitation(invite: AccessInvitation) -> dict:
        return {
            "id": str(invite.id),
            "email": invite.email,
            "display_name": invite.display_name,
            "profile": invite.profile,
            "store_code": invite.store_code,
            "status": invite.status,
            "revision": invite.revision,
            "created_at": invite.created_at.isoformat(),
            "delivery": "not_configured",
        }

    def list_invitations(self) -> list[dict]:
        return [self._public_invitation(invite) for invite in self.repo.invitations()]

    def prepare_invitation(self, *, email: str, name: str, profile: str,
                           store_code: str | None) -> dict:
        """Safe pre-registration only. Does not send email, mint tokens or create passwords."""
        name = " ".join(name.strip().split())
        email = email.strip()
        email_key = email.casefold()
        if not 2 <= len(name) <= 150:
            raise AdminError(422, "Informe o nome do colaborador")
        if (len(email_key) > 254 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email_key
        )):
            raise AdminError(422, "Informe um e-mail valido")
        if profile not in {"administrator", "seller"}:
            raise AdminError(422, "Perfil invalido")
        if profile == "seller":
            if store_code not in STORE_CODES or self.repo.group_for_store(store_code) is None:
                raise AdminError(422, "Selecione uma loja valida para o vendedor")
        elif store_code is not None:
            raise AdminError(422, "Administrador tem acesso as tres lojas")

        existing = self.repo.invitation_by_email(email_key)
        if existing is not None and existing.status != "cancelled":
            raise AdminError(409, "Este e-mail ja tem um pre-cadastro")
        if existing is None:
            invite = self.repo.add_invitation(
                email=email_key, email_key=email_key, name=name,
                profile=profile, store_code=store_code, actor_id=self.actor.id,
            )
            action = "access.invitation.prepared"
        else:
            invite = existing
            invite.email = email_key
            invite.display_name = name
            invite.profile = profile
            invite.store_code = store_code
            invite.status = "prepared"
            invite.updated_by = self.actor.id
            invite.revision += 1
            action = "access.invitation.reopened"
        self.repo.audit(self.actor, action, "access_invitation", str(invite.id),
                        {"profile": profile, "store": store_code,
                         "delivery": "not_configured"})
        self._save()
        return self._public_invitation(invite)

    def cancel_invitation(self, invitation_id: UUID, expected_revision: int) -> dict:
        invite = self.repo.invitation(invitation_id)
        if invite is None:
            raise AdminError(404, "Pre-cadastro nao encontrado")
        if invite.revision != expected_revision:
            raise AdminError(409, "O pre-cadastro foi alterado. Atualize a tela")
        if invite.status != "prepared":
            raise AdminError(409, "Somente pre-cadastros nao enviados podem ser cancelados")
        invite.status = "cancelled"
        invite.updated_by = self.actor.id
        invite.revision += 1
        self.repo.audit(self.actor, "access.invitation.cancelled",
                        "access_invitation", str(invite.id),
                        {"previous": "prepared", "current": "cancelled"})
        self._save()
        return self._public_invitation(invite)

    def replace_group_permissions(self, group_id: UUID, permissions: list[str]) -> dict:
        group = self.repo.group(group_id)
        if group is None or not group.active:
            raise AdminError(404, "Store group not found")
        unknown = set(permissions) - READ_PERMISSIONS
        if unknown:
            raise AdminError(422, "Only known read permissions may be granted to sellers")
        previous = self.repo.grants(group_id)
        allowed = set(permissions)
        self.repo.replace_grants(group_id, allowed)
        self.repo.audit(self.actor, "group.permissions.updated", "group", str(group_id),
                        {"store": group.store_code, "previous": previous, "current": sorted(allowed)})
        self._save()
        return {"store": group.store_code, "permissions": sorted(allowed)}

    def replace_user_overrides(self, user_id: UUID, permissions: dict[str, bool | None]) -> dict:
        user = self.repo.user(user_id)
        if user is None:
            raise AdminError(404, "User not found")
        if user.is_superadmin or user.profile != "seller":
            raise AdminError(422, "Overrides are only supported for sellers")
        if set(permissions) - READ_PERMISSIONS:
            raise AdminError(422, "Only known read permissions may be overridden")
        previous = self.repo.overrides(user_id)
        self.repo.replace_overrides(user_id, permissions)
        current = {key: value for key, value in permissions.items() if value is not None}
        self.repo.audit(self.actor, "user.permissions.updated", "user", str(user_id),
                        {"previous": previous, "current": current})
        self._save()
        return {"user_id": str(user_id), "overrides": current}

    def assign_user_store(self, user_id: UUID, store_code: str) -> dict:
        user = self.repo.user(user_id)
        if user is None:
            raise AdminError(404, "User not found")
        if user.is_superadmin or user.profile != "seller":
            raise AdminError(422, "Only sellers may be assigned to store groups")
        if store_code not in STORE_CODES:
            raise AdminError(422, "Unknown store")
        group = self.repo.group_for_store(store_code)
        if group is None:
            raise AdminError(422, "Store group not configured")
        previous = self.repo.user_stores(user_id)
        self.repo.assign_store(user_id, group.id)
        self.repo.audit(self.actor, "user.store.changed", "user", str(user_id),
                        {"previous": previous, "current": [store_code]})
        self._save()
        return {"user_id": str(user_id), "stores": [store_code]}

    def set_user_active(self, user_id: UUID, active: bool) -> dict:
        user = self.repo.user(user_id)
        if user is None:
            raise AdminError(404, "User not found")
        if user.is_superadmin or user.id == self.actor.id:
            raise AdminError(403, "The superadministrator cannot be deactivated here")
        previous = user.active
        user.active = active
        self.repo.audit(self.actor, "user.status.changed", "user", str(user_id),
                        {"previous": previous, "current": active})
        self._save()
        return {"user_id": str(user_id), "active": active}

    def list_audit(self, *, limit: int, offset: int) -> dict:
        events = self.repo.audit_history(limit=limit, offset=offset)
        return {"items": [
            {
                "id": str(event.id),
                "actor_id": str(event.actor_id) if event.actor_id is not None else None,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "details": event.details,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ], "limit": limit, "offset": offset}
