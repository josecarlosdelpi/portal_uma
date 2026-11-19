"""Rotas do modulo Financeiro (ERP — despesas e pagamentos).

Leitura exige 'finance.view' por loja; importacao manual exige
'finance.import', exclusiva do SuperAdmin nesta etapa.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.attachments_routes import bytes_limited
from app.auth import current_user
from app.db import get_db
from app.finance_service import FinanceService
from app.models import User
from app.operations_service import OperationError

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])

MAX_CSV_BYTES = 10 * 1024 * 1024


def service(user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> FinanceService:
    return FinanceService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/import")
async def import_despesas(file: UploadFile = File(...),
                          svc: FinanceService = Depends(service)) -> dict:
    raw = await bytes_limited(file, MAX_CSV_BYTES)
    name = file.filename or "Despesas.csv"
    return checked(lambda: svc.import_despesas(raw, name))


@router.get("/batches")
def list_batches(svc: FinanceService = Depends(service)) -> dict:
    return checked(svc.list_batches)


@router.get("/sync")
def sync_status(svc: FinanceService = Depends(service)) -> dict:
    return checked(svc.sync_status)


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, svc: FinanceService = Depends(service)) -> dict:
    try:
        parsed = UUID(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Lote nao localizado") from exc
    return checked(lambda: svc.batch_detail(parsed))


@router.get("/overview")
def overview(store: str | None = Query(default=None),
             month: str | None = Query(default=None),
             svc: FinanceService = Depends(service)) -> dict:
    return checked(lambda: svc.overview(store, month))


@router.get("/obligations")
def obligations(store: str | None = Query(default=None),
                category: str | None = Query(default=None),
                status: str | None = Query(default=None),
                supplier: str | None = Query(default=None),
                due_from: str | None = Query(default=None),
                due_to: str | None = Query(default=None),
                sort: str | None = Query(default=None),
                page: int = Query(default=1, ge=1),
                page_size: int = Query(default=25, ge=1, le=200),
                svc: FinanceService = Depends(service)) -> dict:
    return checked(lambda: svc.obligations(
        store, category, status, supplier, due_from, due_to, sort, page, page_size))


@router.get("/payments")
def payments(store: str | None = Query(default=None),
             category: str | None = Query(default=None),
             supplier: str | None = Query(default=None),
             paid_from: str | None = Query(default=None),
             paid_to: str | None = Query(default=None),
             sort: str | None = Query(default=None),
             page: int = Query(default=1, ge=1),
             page_size: int = Query(default=25, ge=1, le=200),
             svc: FinanceService = Depends(service)) -> dict:
    return checked(lambda: svc.payments(
        store, category, supplier, paid_from, paid_to, sort, page, page_size))


@router.get("/purchases")
def purchases(store: str | None = Query(default=None),
              supplier: str | None = Query(default=None),
              page: int = Query(default=1, ge=1),
              page_size: int = Query(default=25, ge=1, le=200),
              svc: FinanceService = Depends(service)) -> dict:
    return checked(lambda: svc.purchases(store, supplier, page, page_size))
