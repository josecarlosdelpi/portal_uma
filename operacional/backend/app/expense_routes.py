"""Rotas da Gestao de Despesas (modulo Financeiro).

Leitura exige 'expenses.view' por loja; escrita (categorias, regras por
fornecedor e classificacao manual) exige 'expenses.manage' no escopo da
loja — regras gerais UMA exigem gestao nas tres lojas. Nenhuma rota
importa arquivos nem altera o ERP.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.expense_service import ExpenseService
from app.models import User
from app.operations_service import OperationError

router = APIRouter(prefix="/api/v1/expenses", tags=["expenses"])


def service(user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> ExpenseService:
    return ExpenseService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/categories")
def list_categories(include_inactive: bool = Query(default=True),
                    svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.list_categories(include_inactive))


@router.post("/categories", status_code=201)
def create_category(body: dict = Body(...),
                    svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.create_category(body.get("name", "")))


@router.patch("/categories/{category_id}")
def update_category(category_id: str, body: dict = Body(...),
                    svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.update_category(
        category_id, body.get("name"),
        body.get("active") if "active" in body else None))


@router.get("/suppliers")
def search_suppliers(q: str = Query(default=""),
                     limit: int = Query(default=20, ge=1, le=50),
                     svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.search_suppliers(q, limit))


@router.get("/supplier-catalog")
def supplier_catalog(q: str = Query(default=""),
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=25, ge=1, le=100),
                     without_rule: bool = Query(default=False),
                     sort: str = Query(default="alpha"),
                     svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.supplier_catalog(
        q, page, page_size, without_rule, sort))


@router.get("/supplier-rules")
def list_rules(svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.list_rules())


@router.post("/supplier-rules", status_code=201)
def create_rule(body: dict = Body(...),
                svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.create_rule(
        body.get("supplier_key", ""), body.get("supplier_label", ""),
        body.get("store_code"), body.get("category_id", "")))


@router.patch("/supplier-rules/{rule_id}")
def update_rule(rule_id: str, body: dict = Body(...),
                svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.update_rule(
        rule_id, body.get("category_id"),
        body.get("active") if "active" in body else None))


@router.get("/analysis")
def analysis(date_from: str = Query(...), date_to: str = Query(...),
             store: str | None = Query(default=None),
             category_id: str | None = Query(default=None),
             situation: str | None = Query(default=None),
             supplier: str | None = Query(default=None),
             svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.analysis(
        date_from, date_to, store, category_id, situation, supplier))


@router.get("/lines")
def lines(date_from: str = Query(...), date_to: str = Query(...),
          store: str | None = Query(default=None),
          category_id: str | None = Query(default=None),
          situation: str | None = Query(default=None),
          supplier: str | None = Query(default=None),
          page: int = Query(default=1, ge=1),
          page_size: int = Query(default=50, ge=1, le=200),
          svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.lines(
        date_from, date_to, store, category_id, situation, supplier,
        page, page_size))


@router.put("/lines/{fingerprint}/category")
def set_classification(fingerprint: str, body: dict = Body(...),
                       svc: ExpenseService = Depends(service)) -> dict:
    return checked(lambda: svc.set_classification(
        fingerprint, body.get("category_id")))
