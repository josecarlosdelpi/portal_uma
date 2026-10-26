"""Verificacao de token OIDC no servidor. Sem bypass em desenvolvimento."""
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=300)


def verify_identity(token: str, settings: Settings) -> str:
    if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
        raise HTTPException(status_code=503, detail="Identity provider not configured")
    if settings.app_env == "production" and not settings.oidc_jwks_url.startswith("https://"):
        raise HTTPException(status_code=503, detail="Identity provider misconfigured")
    try:
        signing_key = jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={"require": ["sub", "exp", "iat"]},
            leeway=30,
        )
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject.strip():
            raise jwt.InvalidTokenError("Missing subject")
        return subject
    except (jwt.PyJWTError, ValueError, OSError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=401, detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    if token.startswith("uma_"):
        from app.local_identity import LocalAuthError, valid_session
        try:
            return valid_session(db, token, allow_limited=False)[0]
        except LocalAuthError as err:
            raise HTTPException(status_code=err.status_code, detail=err.message) from err
    subject = verify_identity(token, settings)
    if subject.startswith("local:"):
        raise HTTPException(status_code=403, detail="Access not provisioned")
    user = db.scalar(select(User).where(User.auth_subject == subject))
    if user is None or not user.active or user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="Access not provisioned")
    return user
