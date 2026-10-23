"""Contas locais UMA: usuario sem e-mail, Argon2id, senha provisoria individual.

Nunca colocar senhas nos logs/auditoria. Sessoes de banco com token aleatorio
armazenado somente como hash, revogadas ao trocar senha ou excluir usuario.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
import secrets
from uuid import UUID, uuid4

from argon2 import PasswordHasher, exceptions as argon_errors, Type
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin_repository import AdminRepository
from app.models import AuditEvent, LocalCredential, LocalSession, User
from app.policy import STORE_CODES

PASSWORD_HASHER = PasswordHasher(
    time_cost=2, memory_cost=19456, parallelism=1,
    hash_len=32, salt_len=16, type=Type.ID,
)
USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{2,39}$")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
TEMPORARY_VALIDITY = timedelta(days=3)
LIMITED_SESSION_VALIDITY = timedelta(minutes=15)
FULL_SESSION_VALIDITY = timedelta(hours=12)
LOCK_AFTER_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)


class LocalAuthError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def username_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise LocalAuthError(
            422, "O usuario deve ter de 3 a 40 caracteres: letras sem acento, numeros, ponto, traco ou _"
        )
    return normalized


def generate_temporary_password() -> str:
    """Senha forte nao compartilhada; entregue presencialmente e exibida uma vez."""
    return "".join(secrets.choice(ALPHABET) for _ in range(20))


def password_digest(value: str) -> str:
    return PASSWORD_HASHER.hash(value)


def password_matches(digest: str, candidate: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(digest, candidate)
    except (argon_errors.VerifyMismatchError, argon_errors.InvalidHashError,
            argon_errors.VerificationError):
        return False


def make_session(db: Session, user: User, limited: bool) -> dict:
    token = "uma_" + secrets.token_urlsafe(36)
    duration = LIMITED_SESSION_VALIDITY if limited else FULL_SESSION_VALIDITY
    expiry = now_utc() + duration
    db.add(LocalSession(
        id=uuid4(), user_id=user.id,
        token_hash=sha256(token.encode("utf-8")).hexdigest(),
        limited=limited, expires_at=expiry,
    ))
    return {
        "access_token": token, "token_type": "bearer",
        "expires_at": expiry.isoformat(),
        "must_change_password": limited,
        "display_name": user.display_name,
        "profile": "superadmin" if user.is_superadmin else user.profile,
    }


def valid_session(db: Session, token: str, allow_limited: bool = False) -> tuple[User, LocalSession]:
    if not token.startswith("uma_") or len(token) > 120:
        raise LocalAuthError(401, "Sessao invalida")
    digest = sha256(token.encode("utf-8")).hexdigest()
    item = db.scalar(select(LocalSession).where(LocalSession.token_hash == digest))
    if item is None or item.revoked_at is not None or utc(item.expires_at) <= now_utc():
        raise LocalAuthError(401, "Sessao invalida ou expirada")
    user = db.get(User, item.user_id)
    if user is None or not user.active or user.deleted_at is not None:
        raise LocalAuthError(401, "Sessao invalida ou expirada")
    cred = db.get(LocalCredential, user.id)
    if cred is None:
        raise LocalAuthError(401, "Sessao invalida ou expirada")
    if not allow_limited and (item.limited or cred.must_change_password):
        raise LocalAuthError(403, "Troca de senha obrigatoria antes de acessar o portal")
    return user, item


def revoke_sessions(db: Session, user_id: UUID) -> None:
    db.execute(
        update(LocalSession).where(
            LocalSession.user_id == user_id,
            LocalSession.revoked_at.is_(None),
        ).values(revoked_at=now_utc())
    )


def new_password_allowed(value: str, username: str) -> None:
    if not 12 <= len(value) <= 128 or not value.strip() or username in value.casefold():
        raise LocalAuthError(
            422, "Use uma senha pessoal de 12 a 128 caracteres, diferente do nome de usuario"
        )


class LocalIdentityService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AdminRepository(db)

    @staticmethod
    def require_admin(actor: User) -> None:
        if not actor.active or actor.deleted_at is not None or not actor.is_superadmin:
            raise LocalAuthError(403, "Apenas o SuperAdmin pode administrar contas")

    def _audit(self, actor: User, action: str, target: User, detail: dict) -> None:
        self.repo.audit(actor, action, "user", str(target.id), detail)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise LocalAuthError(409, "Nome de usuario indisponivel") from error

    def create_account(self, actor: User, *, username: str, name: str,
                       profile: str, store_code: str | None) -> dict:
        self.require_admin(actor)
        key = username_key(username)
        name = " ".join(name.strip().split())
        if not 2 <= len(name) <= 150:
            raise LocalAuthError(422, "Informe o nome do colaborador")
        if profile not in {"administrator", "seller"}:
            raise LocalAuthError(422, "Perfil invalido")
        if profile == "seller":
            if store_code not in STORE_CODES or self.repo.group_for_store(store_code) is None:
                raise LocalAuthError(422, "Vendedor precisa pertencer a uma loja valida")
        elif store_code is not None:
            raise LocalAuthError(422, "Administrador tem acesso as tres lojas")
        if self.db.scalar(select(LocalCredential.user_id).where(LocalCredential.username_key == key)):
            raise LocalAuthError(409, "Nome de usuario indisponivel")

        temporary = generate_temporary_password()
        user = self.repo.create_user(
            subject="local:" + uuid4().hex, name=name, profile=profile
        )
        group = self.repo.group_for_store(store_code) if profile == "seller" else None
        if group is not None:
            self.repo.assign_store(user.id, group.id)
        self.db.add(LocalCredential(
            user_id=user.id, username_key=key,
            password_hash=password_digest(temporary),
            must_change_password=True,
            temporary_expires_at=now_utc() + TEMPORARY_VALIDITY,
            failed_attempts=0,
        ))
        self._audit(actor, "user.local_created", user, {
            "username": key, "profile": profile, "store": store_code,
            "temporary_password": "not_logged",
        })
        self._commit()
        return {
            "id": str(user.id), "display_name": user.display_name,
            "username": key, "profile": profile,
            "stores": [store_code] if store_code else [],
            "active": True,
            "must_change_password": True,
            "temporary_password": temporary,
            "temporary_valid_hours": 72,
        }

    def reset_password(self, actor: User, user_id: UUID) -> dict:
        self.require_admin(actor)
        user = self.db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.deleted_at is not None:
            raise LocalAuthError(404, "Usuario nao encontrado")
        if user.is_superadmin:
            raise LocalAuthError(403, "Redefinicao do SuperAdmin exige procedimento de recuperacao separado")
        cred = self.db.get(LocalCredential, user_id)
        if cred is None:
            raise LocalAuthError(422, "Esta conta nao usa senha local")
        secret = generate_temporary_password()
        cred.password_hash = password_digest(secret)
        cred.must_change_password = True
        cred.temporary_expires_at = now_utc() + TEMPORARY_VALIDITY
        cred.failed_attempts = 0
        cred.locked_until = None
        revoke_sessions(self.db, user_id)
        self._audit(actor, "user.password_reset", user, {
            "username": cred.username_key,
            "sessions_revoked": True,
            "password": "not_logged",
        })
        self._commit()
        return {
            "user_id": str(user_id), "username": cred.username_key,
            "temporary_password": secret, "temporary_valid_hours": 72,
            "must_change_password": True,
        }

    def delete_user(self, actor: User, user_id: UUID) -> dict:
        self.require_admin(actor)
        user = self.db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.deleted_at is not None:
            raise LocalAuthError(404, "Usuario nao encontrado")
        if user.is_superadmin or user.id == actor.id:
            raise LocalAuthError(403, "A conta SuperAdmin nao pode ser excluida")
        user.deleted_at = now_utc()
        user.active = False
        revoke_sessions(self.db, user_id)
        cred = self.db.get(LocalCredential, user_id)
        self._audit(actor, "user.deleted", user, {
            "username": cred.username_key if cred else None,
            "previous_active": True, "sessions_revoked": True,
            "history_preserved": True,
        })
        self._commit()
        return {"user_id": str(user_id), "deleted": True}

    def login(self, *, username: str, password: str) -> dict:
        # Resposta generica: impede enumeracao e existencia de usuario.
        wrong = LocalAuthError(401, "Usuario ou senha invalida")
        key = username.strip().casefold()
        if not USERNAME_PATTERN.fullmatch(key) or len(password) > 256:
            raise wrong
        cred = self.db.scalar(
            select(LocalCredential).where(LocalCredential.username_key == key)
            .with_for_update()
        )
        if cred is None:
            # Hash ficticio fixo, apenas para reduzir diferenca de tempo entre usuarios.
            password_matches(DUMMY_PASSWORD_HASH, password)
            raise wrong
        user = self.db.get(User, cred.user_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise wrong
        if cred.locked_until is not None and utc(cred.locked_until) > now_utc():
            raise wrong
        matched = password_matches(cred.password_hash, password)
        if not matched:
            cred.failed_attempts += 1
            if cred.failed_attempts >= LOCK_AFTER_ATTEMPTS:
                cred.locked_until = now_utc() + LOCK_DURATION
                cred.failed_attempts = 0
            self.db.commit()
            raise wrong
        if (cred.must_change_password and cred.temporary_expires_at is not None
                and utc(cred.temporary_expires_at) <= now_utc()):
            raise wrong
        cred.failed_attempts = 0
        cred.locked_until = None
        response = make_session(self.db, user, limited=cred.must_change_password)
        self.db.commit()
        return response

    def change_password(self, token: str, new_password: str) -> dict:
        user, current = valid_session(self.db, token, allow_limited=True)
        cred = self.db.scalar(
            select(LocalCredential).where(LocalCredential.user_id == user.id)
            .with_for_update()
        )
        if cred is None or not cred.must_change_password:
            raise LocalAuthError(409, "Esta conta nao tem troca de senha pendente")
        new_password_allowed(new_password, cred.username_key)
        if password_matches(cred.password_hash, new_password):
            raise LocalAuthError(422, "Escolha uma senha diferente da provisoria")
        cred.password_hash = password_digest(new_password)
        cred.must_change_password = False
        cred.temporary_expires_at = None
        cred.failed_attempts = 0
        cred.locked_until = None
        revoke_sessions(self.db, user.id)
        response = make_session(self.db, user, limited=False)
        self.repo.audit(user, "user.password_changed_first_login", "user",
                        str(user.id), {"sessions_revoked": True})
        self._commit()
        return response

    def logout(self, token: str) -> dict:
        user, session = valid_session(self.db, token, allow_limited=True)
        session.revoked_at = now_utc()
        self.db.commit()
        return {"signed_out": True}


# Um hash inutilizavel para contas reais. Criado apenas para equiparar o caminho de
# verificacao quando o nome informado nao existe. Nao contem segredo de producao.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("unusable-dummy-value-" + secrets.token_hex(12))
