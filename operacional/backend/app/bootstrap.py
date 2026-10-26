"""One-time provisioning of the first SuperAdmin from a trusted OIDC subject.

This is an explicit maintenance command run by an operator who already has
direct database credentials. It is NOT a public API and creates no password.
"""
import os
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import AuditEvent, User


class BootstrapError(Exception):
    pass


def provision_first_superadmin(session: Session, subject: str, display_name: str) -> User:
    subject = subject.strip()
    display_name = display_name.strip()

    if not subject or len(subject) > 250 or not display_name or len(display_name) > 150:
        raise BootstrapError("Identificador OIDC e nome da pessoa precisam ser válidos.")
    # PostgreSQL transaction-scoped lock avoids duplicate concurrent invocations.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(624092618)"))
    existing = session.scalar(
        select(func.count(User.id)).where(User.is_superadmin.is_(True))
    )
    if existing:
        raise BootstrapError("Já existe SuperAdmin. Use a administração segura existente.")
    if session.scalar(select(User).where(User.auth_subject == subject)):
        raise BootstrapError("Esta identidade já está vinculada a outra conta.")

    user = User(
        id=uuid4(), auth_subject=subject, display_name=display_name,
        profile="administrator", is_superadmin=True, active=True,
    )
    try:
        session.add(user)
        session.flush()
        session.add(AuditEvent(
            id=uuid4(), actor_id=user.id, actor_subject=subject,
            action="security.superadmin.bootstrapped", entity_type="user",
            entity_id=str(user.id),
            details={"reason": "initial_provision", "role": "superadmin"},
        ))
        session.commit()
    except (IntegrityError, DBAPIError) as cause:
        session.rollback()
        raise BootstrapError("Não foi possível concluir o provisionamento seguro.") from cause
    return user


def main() -> None:
    config = get_settings()
    # Fail closed: never create a privileged account without identity verification ready.
    if not all([config.oidc_issuer, config.oidc_audience, config.oidc_jwks_url]):
        raise SystemExit("Configure o provedor OIDC antes de provisionar a conta inicial.")
    if config.app_env == "production" and not config.oidc_jwks_url.startswith("https://"):
        raise SystemExit("Em produção, o endpoint JWKS deve usar HTTPS.")

    subject = os.environ.get("UMA_INITIAL_SUPERADMIN_SUBJECT", "")
    name = os.environ.get("UMA_INITIAL_SUPERADMIN_NAME", "")
    # Only run when the operator explicitly acknowledges the production-bound action.
    if os.environ.get("UMA_CONFIRM_INITIAL_SUPERADMIN") != "I_UNDERSTAND_ONE_TIME":
        raise SystemExit("Operação não autorizada: confirmação administrativa ausente.")
    with Session(get_engine()) as session:
        try:
            provision_first_superadmin(session, subject, name)
        except BootstrapError as error:
            raise SystemExit(str(error)) from error
    print("Conta SuperAdmin inicial vinculada à identidade OIDC informada; nenhuma senha criada.")


if __name__ == "__main__":
    main()
