"""Authenticated upload/download/delete for private operational attachments."""
from datetime import date
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.attachments_service import (
    AttachmentService, MAX_ART_BYTES, MAX_TRAINING_BYTES
)
from app.operations_service import OperationError

router = APIRouter(prefix="/api/v1/routines", tags=["private-files"])


def service(user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> AttachmentService:
    return AttachmentService(db, user)


def checked(call):
    try:
        return call()
    except OperationError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


def as_download(metadata: dict, content: bytes) -> Response:
    filename = quote(metadata["name"], safe="")
    return Response(
        content=content, media_type=metadata["media_type"],
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + filename,
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


async def bytes_limited(file: UploadFile, limit: int) -> bytes:
    try:
        body = await file.read(limit + 1)
    finally:
        await file.close()
    if not body or len(body) > limit:
        raise HTTPException(
            status_code=413, detail="Arquivo vazio ou acima do limite permitido"
        )
    return body


@router.put("/whatsapp/{post_date}/files/{kind}")
async def upload_whatsapp_file(
    post_date: date,
    kind: Literal["art", "evidence"],
    expected_revision: int = Query(ge=0),
    file: UploadFile = File(...),
    svc: AttachmentService = Depends(service),
) -> dict:
    raw = await bytes_limited(file, MAX_ART_BYTES)
    return checked(lambda:svc.put_whatsapp(
        post_date, kind, raw, file.filename, file.content_type, expected_revision
    ))


@router.get("/whatsapp/{post_date}/files/{kind}")
def download_whatsapp_file(
    post_date: date, kind: Literal["art", "evidence"],
    svc: AttachmentService = Depends(service),
) -> Response:
    metadata, raw = checked(lambda:svc.get_whatsapp(post_date, kind))
    return as_download(metadata, raw)


@router.delete("/whatsapp/{post_date}/files/{kind}")
def remove_whatsapp_file(
    post_date: date, kind: Literal["art", "evidence"],
    expected_revision: int = Query(ge=1),
    svc: AttachmentService = Depends(service),
) -> dict:
    return checked(lambda:svc.delete_whatsapp(post_date, kind, expected_revision))


@router.put("/trainings/{store_code}/{record_id}/document")
async def upload_training_file(
    store_code: str, record_id: UUID,
    expected_revision: int = Query(ge=0),
    file: UploadFile = File(...),
    svc: AttachmentService = Depends(service),
) -> dict:
    raw = await bytes_limited(file, MAX_TRAINING_BYTES)
    return checked(lambda:svc.put_training(
        store_code, record_id, raw, file.filename, file.content_type, expected_revision
    ))


@router.get("/trainings/{store_code}/{record_id}/document")
def download_training_file(
    store_code: str, record_id: UUID,
    svc: AttachmentService = Depends(service),
) -> Response:
    metadata, raw = checked(lambda:svc.get_training(store_code, record_id))
    return as_download(metadata, raw)


@router.delete("/trainings/{store_code}/{record_id}/document")
def remove_training_file(
    store_code: str, record_id: UUID,
    expected_revision: int = Query(ge=1),
    svc: AttachmentService = Depends(service),
) -> dict:
    return checked(lambda:svc.delete_training(store_code, record_id, expected_revision))
