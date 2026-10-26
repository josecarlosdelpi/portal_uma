"""Recuperacao do unico SuperAdmin local pelo operador do banco.

Roda SOMENTE por terminal privado, nunca por rota publica.
"""
import os
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import LocalCredential, User
from app.admin_repository import AdminRepository
from app.local_identity import (
    LocalAuthError, generate_temporary_password, now_utc,
    password_digest, revoke_sessions, TEMPORARY_VALIDITY, username_key,
)


def recover_local_superadmin(db: Session, expected_username: str) -> str:
    username = username_key(expected_username)
    user = db.scalar(select(User).where(
        User.is_superadmin.is_(True),User.active.is_(True),
        User.deleted_at.is_(None),
    ).with_for_update())
    if user is None or not user.auth_subject.startswith("local:"):
        raise LocalAuthError(403, "SuperAdmin local nao encontrado")
    cred = db.get(LocalCredential, user.id)
    if cred is None or cred.username_key != username:
        raise LocalAuthError(403, "Identidade nao confere")
    password = generate_temporary_password()
    cred.password_hash = password_digest(password)
    cred.must_change_password = True
    cred.temporary_expires_at = now_utc() + TEMPORARY_VALIDITY
    cred.failed_attempts = 0
    cred.locked_until = None
    revoke_sessions(db, user.id)
    AdminRepository(db).audit(
        user, "security.superadmin.local_recovery", "user", str(user.id),
        {"username":username, "reason":"offline_recovery",
         "sessions_revoked":True, "password":"not_logged"},
    )
    db.commit()
    return password


def main() -> None:
    if os.environ.get("UMA_CONFIRM_SUPERADMIN_RESET") != "I_UNDERSTAND_ONE_TIME":
        raise SystemExit("Confirmacao privada obrigatoria")
    username = os.environ.get("UMA_SUPERADMIN_USERNAME","")
    with Session(get_engine()) as db:
        try:
            temporary = recover_local_superadmin(db,username)
        except LocalAuthError as error:
            raise SystemExit(error.message) from error
    print("Senha provisoria do SuperAdmin, exibida uma unica vez:",temporary)
    print("Expira em 72 horas. Mantenha esta saida fora de logs e nao compartilhe.")


if __name__ == "__main__":
    main()
