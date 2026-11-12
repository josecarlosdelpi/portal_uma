"""Rotas do modulo comercial ERP: importacao, status e indicadores."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.erp_csv import KIND_DEVOLUCOES, KIND_VENDAS
from app.erp_import import ErpImportError, import_erp_file
from app.erp_sales_service import SalesError, SalesService
from app.models import User

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])

MAX_IMPORT_BYTES = 10 * 1024 * 1024
KIND_MAP = {"vendas": KIND_VENDAS, "devolucoes": KIND_DEVOLUCOES}


def service(user: User = Depends(current_user), db: Session = Depends(get_db)) -> SalesService:
    return SalesService(db, user)


def checked(call):
    try:
        return call()
    except (SalesError, ErpImportError) as error:
        raise HTTPException(error.status_code, detail=error.message) from error


def _batch_payload(batch) -> dict:
    return {
        "id": str(batch.id), "kind": batch.kind, "source": batch.source,
        "status": batch.status, "file_name": batch.file_name,
        "rows_total": batch.rows_total, "rows_applied": batch.rows_applied,
        "rows_rejected": batch.rows_rejected,
        "period_start": batch.period_start.isoformat() if batch.period_start else None,
        "period_end": batch.period_end.isoformat() if batch.period_end else None,
        "error_summary": batch.error_summary,
        "applied_at": batch.applied_at.isoformat() if batch.applied_at else None,
    }


@router.post("/imports/{kind}")
async def upload_erp_file(
    kind: Literal["vendas", "devolucoes"],
    file: UploadFile = File(...),
    svc: SalesService = Depends(service),
) -> dict:
    checked(lambda: svc.require_write())
    try:
        content = await file.read(MAX_IMPORT_BYTES + 1)
    finally:
        await file.close()
    if not content or len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "Arquivo vazio ou acima do limite de 10 MB.")
    batch = checked(lambda: import_erp_file(
        svc.db, kind=KIND_MAP[kind], content=content,
        file_name=file.filename or "arquivo.csv",
        source="MANUAL_UPLOAD", actor=svc.user,
    ))
    payload = _batch_payload(batch)
    if batch.status == "FAILED":
        raise HTTPException(422, detail={"message": "Arquivo rejeitado na validacao.", "batch": payload})
    return {"batch": payload}


@router.get("/status")
def sales_status(svc: SalesService = Depends(service)) -> dict:
    return checked(lambda: svc.status())


@router.get("/imports")
def list_batches(limit: int = Query(default=30, ge=1, le=100),
                 svc: SalesService = Depends(service)) -> dict:
    return {"items": checked(lambda: svc.batches(limit))}


@router.post("/sync")
def trigger_sync(svc: SalesService = Depends(service)) -> dict:
    return {"results": checked(lambda: svc.sync_now())}


@router.get("/summary")
def sales_summary(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    store: str | None = Query(default=None),
    svc: SalesService = Depends(service),
) -> dict:
    return checked(lambda: svc.summary(date_from, date_to, store))


@router.get("/daily")
def sales_daily(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    store: str | None = Query(default=None),
    svc: SalesService = Depends(service),
) -> dict:
    return checked(lambda: svc.daily(date_from, date_to, store))


@router.get("/top/{dimension}")
def sales_top(
    dimension: Literal["products", "sellers", "customers"],
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    store: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
    svc: SalesService = Depends(service),
) -> dict:
    return checked(lambda: svc.top(dimension, date_from, date_to, store, limit))
