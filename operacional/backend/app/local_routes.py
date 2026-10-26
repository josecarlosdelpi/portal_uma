"""Login por usuario, sem e-mail, senha provisoria e troca obrigatoria."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.local_identity import LocalIdentityService, LocalAuthError

router = APIRouter(prefix="/api/v1/local-auth", tags=["local-identity"])
bearer = HTTPBearer(auto_error=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class ChangePassword(Strict):
    new_password: str = Field(min_length=12, max_length=128)


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
def login(payload: Login, db: Session = Depends(get_db)) -> JSONResponse:
    return reply(lambda: LocalIdentityService(db).login(
        username=payload.username, password=payload.password,
    ))


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
