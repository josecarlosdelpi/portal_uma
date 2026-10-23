"""Thin HTTP boundary: validate inputs, require identity, delegate to use cases."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.admin_repository import AdminRepository
from app.admin_service import AdminError, AdminService
from app.auth import current_user
from app.db import get_db
from app.models import User
from app.local_identity import LocalIdentityService, LocalAuthError

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


class CreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_subject: str = Field(min_length=1, max_length=250)
    display_name: str = Field(min_length=1, max_length=150)
    profile: str
    store_code: str | None = None


class GroupPermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: list[str] = Field(default_factory=list, max_length=50)


class UserOverridesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: dict[str, bool | None] = Field(default_factory=dict)


class StoreAssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_code: str


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


def service(user: User = Depends(current_user), db: Session = Depends(get_db)) -> AdminService:
    try:
        return AdminService(AdminRepository(db), user)
    except AdminError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


def http_result(callback):
    try:
        return callback()
    except AdminError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


class PrepareInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=5, max_length=254)
    profile: str = Field(pattern=r"^(administrator|seller)$")
    store_code: str | None = None


class CancelInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class NewLocalUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40)
    display_name: str = Field(min_length=2, max_length=150)
    profile: str = Field(pattern=r"^(administrator|seller)$")
    store_code: str | None = None


def secure_result(call):
    try:
        return call()
    except LocalAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error

def secret_response(call, status_code: int = 200) -> JSONResponse:
    # Senhas provisórias não podem ser armazenadas por caches intermediários.
    return JSONResponse(
        content=secure_result(call), status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.post("/local-users", status_code=201)
def create_local_user(payload: NewLocalUser,
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> JSONResponse:
    return secret_response(lambda: LocalIdentityService(db).create_account(
        actor, username=payload.username, name=payload.display_name,
        profile=payload.profile, store_code=payload.store_code,
    ), status_code=201)


@router.post("/users/{user_id}/reset-password")
def reset_local_password(user_id: UUID, actor: User = Depends(current_user),
                         db: Session = Depends(get_db)) -> JSONResponse:
    return secret_response(lambda: LocalIdentityService(db).reset_password(actor, user_id))


@router.delete("/users/{user_id}")
def remove_user(user_id: UUID, actor: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    return secure_result(lambda: LocalIdentityService(db).delete_user(actor, user_id))


@router.get("/invitations")
def invitations(admin: AdminService = Depends(service)) -> list[dict]:
    return admin.list_invitations()


@router.post("/invitations", status_code=201)
def prepare_invitation(payload: PrepareInvitation,
                       admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.prepare_invitation(
        email=payload.email, name=payload.display_name,
        profile=payload.profile, store_code=payload.store_code,
    ))


@router.delete("/invitations/{invitation_id}")
def cancel_invitation(invitation_id: UUID, payload: CancelInvitation,
                      admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.cancel_invitation(
        invitation_id, payload.expected_revision,
    ))


@router.get("/users")
def list_users(admin: AdminService = Depends(service)) -> list[dict]:
    return admin.list_users()


@router.post("/users", status_code=201)
def create_user(payload: CreateUser, admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.add_user(
        subject=payload.auth_subject, name=payload.display_name,
        profile=payload.profile, store_code=payload.store_code,
    ))


@router.patch("/users/{user_id}/active")
def set_user_active(user_id: UUID, payload: UserStatusUpdate,
                    admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.set_user_active(user_id, payload.active))


@router.put("/users/{user_id}/store")
def assign_user_store(user_id: UUID, payload: StoreAssignmentUpdate,
                      admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.assign_user_store(user_id, payload.store_code))


@router.put("/users/{user_id}/overrides")
def replace_user_overrides(user_id: UUID, payload: UserOverridesUpdate,
                           admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.replace_user_overrides(user_id, payload.permissions))


@router.get("/groups")
def list_groups(admin: AdminService = Depends(service)) -> list[dict]:
    return admin.list_groups()


@router.put("/groups/{group_id}/permissions")
def replace_group_permissions(group_id: UUID, payload: GroupPermissionUpdate,
                              admin: AdminService = Depends(service)) -> dict:
    return http_result(lambda: admin.replace_group_permissions(group_id, payload.permissions))


@router.get("/audit")
def list_audit(limit: int = Query(default=50, ge=1, le=100),
               offset: int = Query(default=0, ge=0),
               admin: AdminService = Depends(service)) -> dict:
    return admin.list_audit(limit=limit, offset=offset)
