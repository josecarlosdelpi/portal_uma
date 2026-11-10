"""Rotas autenticadas dos procedimentos internos e imagens privadas."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.operations_service import OperationError
from app.procedures_service import ProceduresService, MAX_IMAGE_BYTES

router = APIRouter(prefix="/api/v1/procedures", tags=["procedures"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcedureNew(Strict):
    title: str = Field(min_length=3, max_length=140)
    summary: str = Field(default="", max_length=300)
    applies_to_all: bool = True
    store_codes: list[str] = Field(default_factory=list, max_length=3)
    content_html: str = Field(default="", max_length=400_000)


class ProcedureSave(ProcedureNew):
    expected_revision: int = Field(ge=0)


class PublishBody(Strict):
    expected_revision: int = Field(ge=0)


def service(user: User = Depends(current_user), db: Session = Depends(get_db)) -> ProceduresService:
    return ProceduresService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as err:
        raise HTTPException(err.status_code, err.message) from err


@router.get("")
def list_procedures(status: str | None = Query(None, pattern=r"^(rascunho|publicado|obsoleto)$"),
                    store: str | None = None, q: str | None = Query(None, max_length=80),
                    svc: ProceduresService = Depends(service)) -> list[dict]:
    return checked(lambda: svc.list_procedures(status, store, q))


@router.post("", status_code=201)
def create_procedure(body: ProcedureNew, svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.create(body.title, body.summary, body.applies_to_all,
                                      body.store_codes, body.content_html))


@router.get("/{procedure_id}")
def get_procedure(procedure_id: UUID, svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.get(procedure_id))


@router.put("/{procedure_id}")
def save_procedure(procedure_id: UUID, body: ProcedureSave,
                   svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.save(procedure_id, body.title, body.summary,
                                    body.applies_to_all, body.store_codes,
                                    body.content_html, body.expected_revision))


@router.post("/{procedure_id}/publish")
def publish_procedure(procedure_id: UUID, body: PublishBody,
                      svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.publish(procedure_id, body.expected_revision))


@router.post("/{procedure_id}/obsolete")
def obsolete_procedure(procedure_id: UUID,
                       svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.mark_obsolete(procedure_id))


@router.delete("/{procedure_id}")
def delete_procedure(procedure_id: UUID,
                     svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.delete(procedure_id))


@router.get("/{procedure_id}/versions")
def list_versions(procedure_id: UUID, svc: ProceduresService = Depends(service)) -> list[dict]:
    return checked(lambda: svc.versions(procedure_id))


@router.get("/{procedure_id}/versions/{version_id}")
def get_version(procedure_id: UUID, version_id: UUID,
                svc: ProceduresService = Depends(service)) -> dict:
    return checked(lambda: svc.get_version(procedure_id, version_id))


@router.put("/{procedure_id}/files", status_code=201)
async def upload_file(procedure_id: UUID, file: UploadFile = File(...),
                      svc: ProceduresService = Depends(service)) -> dict:
    try:
        raw = await file.read(MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Imagem vazia ou acima de 3 MB")
    return checked(lambda: svc.put_file(procedure_id, raw, file.filename, file.content_type))


@router.get("/files/{file_id}")
def download_file(file_id: UUID, svc: ProceduresService = Depends(service)) -> Response:
    meta, raw = checked(lambda: svc.get_file(file_id))
    return Response(
        content=raw, media_type=meta["media_type"],
        headers={"Cache-Control": "private, no-store", "Pragma": "no-cache",
                 "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )
