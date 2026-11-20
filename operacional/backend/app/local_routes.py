"""Login por usuario, sem e-mail, senha provisoria e troca obrigatoria."""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.local_identity import LocalIdentityService, LocalAuthError

LOGIN_IP_WINDOW_SECONDS = 300
LOGIN_IP_MAX_ATTEMPTS = 20
_login_attempts: dict[str, deque] = defaultdict(deque)


def _check_login_rate(client_ip: str) -> None:
    """Janela deslizante por IP: complementa o bloqueio por usuario."""
    now = time.monotonic()
    hits = _login_attempts[client_ip]
    while hits and now - hits[0] > LOGIN_IP_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= LOGIN_IP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de acesso. Aguarde alguns minutos.",
        )
    hits.append(now)

router = APIRouter(prefix="/api/v1/local-auth", tags=["local-identity"])
bearer = HTTPBearer(auto_error=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, max_length=10)


class ChangePassword(Strict):
    new_password: str = Field(min_length=12, max_length=128)


class MfaConfirm(Strict):
    code: str = Field(min_length=6, max_length=10)


class MfaDisable(Strict):
    password: str = Field(min_length=1, max_length=256)


def reply(call) -> JSONResponse:
    try:
        result = call()
    except LocalAuthError as error:
        raise HTTPException(
            status_code=error.status_code, detail=error.message,
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def require_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Autenticacao obrigatoria")
    return credentials.credentials


@router.post("/login")
def login(payload: Login, request: Request,
          db: Session = Depends(get_db)) -> JSONResponse:
    # X-Real-IP e reescrito pelo nosso Nginx ($remote_addr) — confiavel.
    # X-Forwarded-For NAO e usado: o cliente pode forja-lo para contornar
    # o bloqueio por IP. Sem proxy (dev/teste), cai no peer TCP real.
    client_ip = (request.headers.get("x-real-ip")
                 or (request.client.host if request.client else "unknown"))
    _check_login_rate(client_ip)
    return reply(lambda: LocalIdentityService(db).login(
        username=payload.username, password=payload.password,
        totp=payload.totp,
    ))


@router.post("/mfa/setup")
def mfa_setup(auth: HTTPAuthorizationCredentials | None = Depends(bearer),
              db: Session = Depends(get_db)) -> JSONResponse:
    token = require_token(auth)
    return reply(lambda: LocalIdentityService(db).mfa_setup(token))


@router.post("/mfa/enable")
def mfa_enable(payload: MfaConfirm,
               auth: HTTPAuthorizationCredentials | None = Depends(bearer),
               db: Session = Depends(get_db)) -> JSONResponse:
    token = require_token(auth)
    return reply(lambda: LocalIdentityService(db).mfa_enable(token, payload.code))


@router.post("/mfa/disable")
def mfa_disable(payload: MfaDisable,
                auth: HTTPAuthorizationCredentials | None = Depends(bearer),
                db: Session = Depends(get_db)) -> JSONResponse:
    token = require_token(auth)
    return reply(lambda: LocalIdentityService(db).mfa_disable(
        token, payload.password))


@router.post("/change-password")
def change_password(payload: ChangePassword,
                    auth: HTTPAuthorizationCredentials | None = Depends(bearer),
                    db: Session = Depends(get_db)) -> JSONResponse:
    token = require_token(auth)
    return reply(lambda: LocalIdentityService(db).change_password(
        token=token, new_password=payload.new_password,
    ))


@router.post("/logout")
def logout(auth: HTTPAuthorizationCredentials | None = Depends(bearer),
           db: Session = Depends(get_db)) -> JSONResponse:
    token = require_token(auth)
    return reply(lambda: LocalIdentityService(db).logout(token))
