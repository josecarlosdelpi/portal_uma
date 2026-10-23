"""Provisionamento inicial LOCAL do unico SuperAdmin, via terminal privado.

Nao disponibilizar este fluxo como rota HTTP ou em CI. A senha temporaria
somente aparece uma vez no terminal do operador e expira em 72 horas.
"""
import os
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import LocalCredential, User
from app.admin_repository import AdminRepository
from app.local_identity import (
    LocalAuthError, generate_temporary_password, now_utc,
    password_digest, username_key, TEMPORARY_VALIDITY,
)


def provision_initial_local_superadmin(db: Session, username: str, name: str) -> tuple[User, str]:
    key = username_key(username)
    name = " ".join(name.strip().split())
    if not 2 <= len(name) <= 150:
        raise LocalAuthError(422, "Nome do SuperAdmin invalido")
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(624092618)"))
    if db.scalar(select(func.count(User.id)).where(User.is_superadmin.is_(True))):
        raise LocalAuthError(409, "O SuperAdmin unico ja existe")
    if db.scalar(select(LocalCredential.user_id).where(LocalCredential.username_key == key)):
        raise LocalAuthError(409, "Login indisponivel")
    generated = generate_temporary_password()
    user = User(
        id=uuid4(), auth_subject="local:" + uuid4().hex, display_name=name,
        profile="administrator", is_superadmin=True, active=True,
    )
    db.add(user)
    db.flush()
    db.add(LocalCredential(
        user_id=user.id, username_key=key,
        password_hash=password_digest(generated), must_change_password=True,
        temporary_expires_at=now_utc() + TEMPORARY_VALIDITY,
        failed_attempts=0,
    ))
    AdminRepository(db).audit(
        user, "security.superadmin.local_bootstrapped",
        "user", str(user.id),
        {"username": key, "password": "not_logged", "bootstrap": "local"},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise LocalAuthError(409, "Falha no provisionamento") from exc
    return user, generated


def main() -> None:
    if os.environ.get("UMA_CONFIRM_INITIAL_SUPERADMIN") != "I_UNDERSTAND_ONE_TIME":
        raise SystemExit("Confirme explicitamente o provisionamento seguro antes de prosseguir.")
    username = os.environ.get("UMA_INITIAL_SUPERADMIN_USERNAME", "")
    name = os.environ.get("UMA_INITIAL_SUPERADMIN_NAME", "")
    with Session(get_engine()) as db:
        try:
            user, secret = provision_initial_local_superadmin(db, username, name)
        except LocalAuthError as error:
            raise SystemExit(error.message) from error
    print("SuperAdmin local criado:", user.display_name)
    print("Login:", username_key(username))
    print("Senha TEMPORARIA (exibida apenas agora):", secret)
    print("Registre em meio seguro; validade 72 horas. Nao compartilhe esta saida.")


if __name__ == "__main__":
    main()
