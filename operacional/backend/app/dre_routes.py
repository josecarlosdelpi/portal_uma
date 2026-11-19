"""Rotas da DRE Gerencial — Previa (modulo Financeiro).

Leitura exige 'dre.view' por loja; por padrao somente o SuperAdmin.
Nenhuma rota importa arquivos nem altera o ERP: apenas apura sobre os
snapshots vigentes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.dre_service import DreService
from app.models import User
from app.operations_service import OperationError

router = APIRouter(prefix="/api/v1/dre", tags=["dre"])


def service(user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> DreService:
    return DreService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/preview")
def preview(month: str | None = Query(default=None),
            mode: str = Query(default="month"),
            store: str | None = Query(default=None),
            svc: DreService = Depends(service)) -> dict:
    return checked(lambda: svc.preview(month, mode, store))


@router.get("/lines")
def lines(bucket: str = Query(...),
          month: str | None = Query(default=None),
          mode: str = Query(default="month"),
          store: str | None = Query(default=None),
          page: int = Query(default=1, ge=1),
          page_size: int = Query(default=25, ge=1, le=200),
          svc: DreService = Depends(service)) -> dict:
    return checked(lambda: svc.lines(bucket, month, mode, store, page, page_size))


@router.get("/classification")
def classification(svc: DreService = Depends(service)) -> dict:
    return checked(svc.classification_view)
