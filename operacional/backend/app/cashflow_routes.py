"""Rotas do Fluxo de Caixa Estimado (modulo Financeiro).

Leitura exige 'cashflow.view' por loja; por padrao somente o SuperAdmin.
Nenhuma rota importa arquivos nem altera o ERP: apenas apura sobre os
snapshots vigentes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import current_user
from app.cashflow_service import CashflowService
from app.db import get_db
from app.models import User
from app.operations_service import OperationError

router = APIRouter(prefix="/api/v1/cashflow", tags=["cashflow"])


def service(user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> CashflowService:
    return CashflowService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/preview")
def preview(date_from: str = Query(...),
            date_to: str = Query(...),
            store: str | None = Query(default=None),
            svc: CashflowService = Depends(service)) -> dict:
    return checked(lambda: svc.preview(date_from, date_to, store))


@router.get("/lines")
def lines(bucket: str = Query(...),
          date_from: str = Query(...),
          date_to: str = Query(...),
          store: str | None = Query(default=None),
          page: int = Query(default=1, ge=1),
          page_size: int = Query(default=25, ge=1, le=200),
          svc: CashflowService = Depends(service)) -> dict:
    return checked(lambda: svc.lines(bucket, date_from, date_to,
                                     store, page, page_size))
