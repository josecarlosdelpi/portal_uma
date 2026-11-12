"""Consultas comerciais do piloto ERP e orquestracao da sincronizacao.

Regras: devolucoes nunca abatem vendas; ausencia de dados e null, nao zero;
receita exige sales.revenue.view; CNPJ de cliente so para administracao.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.erp_csv import KIND_DESPESAS, KIND_DEVOLUCOES, KIND_VENDAS
from app.erp_expenses_import import expenses_handlers
from app.erp_drive import EXPECTED_FILES, DriveClient, DriveError, load_service_account, sync_sources
from app.erp_import import import_erp_file
from app.models import (
    ErpImportBatch, ErpReturnRow, ErpSaleRow, ErpSourceFile, User,
)
from app.policy import can_access, visible_stores
from app.repositories import load_principal

MAX_RANGE_DAYS = 400
TOP_LIMIT = 25


class SalesError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


# ---- helpers compartilhados com visao geral, metas e fechamento ----

def month_bounds(year: int, month: int) -> tuple[date, date]:
    from calendar import monthrange
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def store_totals(
    db: Session, model, codes: Iterable[str], first: date, last: date,
) -> dict[str, dict]:
    codes = list(codes)
    if not codes:
        return {}
    rows = db.execute(
        select(
            model.store_code,
            func.coalesce(func.sum(model.total), 0),
            func.coalesce(func.sum(model.quantity), 0),
            func.count(),
        )
        .where(
            model.store_code.in_(codes),
            model.sale_date >= first,
            model.sale_date <= last,
        )
        .group_by(model.store_code)
    ).all()
    return {
        code: {"revenue": revenue, "quantity": quantity, "rows": count}
        for code, revenue, quantity, count in rows
    }


def daily_totals(
    db: Session, model, codes: Iterable[str], first: date, last: date,
) -> dict[tuple[str, date], dict]:
    codes = list(codes)
    if not codes:
        return {}
    rows = db.execute(
        select(
            model.sale_date, model.store_code,
            func.coalesce(func.sum(model.total), 0),
            func.coalesce(func.sum(model.quantity), 0),
        )
        .where(
            model.store_code.in_(codes),
            model.sale_date >= first,
            model.sale_date <= last,
        )
        .group_by(model.sale_date, model.store_code)
    ).all()
    return {(code, day): {"revenue": revenue, "quantity": qty}
            for day, code, revenue, qty in rows}


def latest_applied(db: Session, kind: str) -> ErpImportBatch | None:
    return db.scalar(
        select(ErpImportBatch)
        .where(ErpImportBatch.kind == kind, ErpImportBatch.status == "APPLIED")
        .order_by(ErpImportBatch.applied_at.desc())
        .limit(1)
    )


def pilot_sales_status(db: Session) -> dict:
    """Origem oficial em fase de testes: sempre identificada como piloto."""
    batch = latest_applied(db, KIND_VENDAS)
    if batch is None:
        return {
            "status": "awaiting_erp_integration",
            "sales_updated_at": None,
            "message": "Faturamento oficial ainda não importado.",
        }
    return {
        "status": "pilot_unverified",
        "sales_updated_at": batch.applied_at.isoformat() if batch.applied_at else None,
        "message": "Dados do ERP em fase de testes — conferir com os relatórios oficiais.",
    }


def sales_by_date_for_store(
    db: Session, store_code: str, first: date, last: date,
) -> dict[date, Decimal]:
    rows = db.execute(
        select(ErpSaleRow.sale_date, func.coalesce(func.sum(ErpSaleRow.total), 0))
        .where(
            ErpSaleRow.store_code == store_code,
            ErpSaleRow.sale_date >= first,
            ErpSaleRow.sale_date <= last,
        )
        .group_by(ErpSaleRow.sale_date)
    ).all()
    return {day: revenue for day, revenue in rows}


# ---- sincronizacao Google Drive (contrato compartilhado) ----

def sales_handlers(db: Session) -> dict:
    def make(kind: str):
        def handle(content: bytes, file_name: str, drive_file_id: str):
            return import_erp_file(
                db, kind=kind, content=content, file_name=file_name,
                source="DRIVE_SYNC", actor=None, drive_file_id=drive_file_id,
            )
        return handle
    return {KIND_VENDAS: make(KIND_VENDAS), KIND_DEVOLUCOES: make(KIND_DEVOLUCOES)}


def run_drive_sync(db: Session) -> list[dict]:
    settings = get_settings()
    expected = {
        KIND_VENDAS: settings.erp_drive_vendas_name,
        KIND_DEVOLUCOES: settings.erp_drive_devolucoes_name,
        KIND_DESPESAS: settings.erp_drive_despesas_name,
    }
    handlers = {**sales_handlers(db), **expenses_handlers(db)}
    if not settings.erp_sync_enabled or not settings.google_drive_folder_id:
        return sync_sources(db, handlers=handlers, expected_files=expected)
    try:
        service_account = load_service_account(settings.google_service_account_json)
    except DriveError as exc:
        for key in expected:
            state = db.get(ErpSourceFile, key)
            if state is None:
                state = ErpSourceFile(file_key=key)
                db.add(state)
            state.last_check_at = datetime.now(timezone.utc)
            state.last_status = "FAILED"
            state.last_error = str(exc)[:500]
            state.consecutive_failures += 1
        db.commit()
        return [{"file_key": k, "status": "FAILED", "last_error": str(exc)} for k in expected]
    client = DriveClient(service_account, settings.google_drive_folder_id)
    return sync_sources(
        db, handlers=handlers, expected_files=expected, client=client,
    )


# ---- servico de consulta ----

class SalesService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.principal = load_principal(db, user)

    def _allowed(self, permission: str) -> list[str]:
        return sorted(
            code for code in visible_stores(self.principal)
            if can_access(self.principal, permission, code)
        )

    def _scope(self, store_code: str | None, permission: str = "sales.view") -> list[str]:
        allowed = self._allowed(permission)
        if not allowed:
            raise SalesError(403, "Acesso negado")
        if store_code is None:
            return allowed
        if store_code not in allowed:
            raise SalesError(403, "Acesso negado para esta loja")
        return [store_code]

    @staticmethod
    def _range(first: date, last: date) -> None:
        if first > last:
            raise SalesError(422, "Período inicial maior que o final.")
        if (last - first).days > MAX_RANGE_DAYS:
            raise SalesError(422, f"Período máximo de {MAX_RANGE_DAYS} dias.")

    def _revenue_map(self, codes: list[str]) -> dict[str, bool]:
        return {code: can_access(self.principal, "sales.revenue.view", code) for code in codes}

    def require_write(self) -> None:
        """Importacao e sincronizacao exigem sales.import (administracao)."""
        if not can_access(self.principal, "sales.import"):
            raise SalesError(403, "Acesso negado")

    # -- status e lotes --

    def status(self) -> dict:
        self._scope(None)
        kinds = []
        for kind in (KIND_VENDAS, KIND_DEVOLUCOES):
            batch = latest_applied(self.db, kind)
            kinds.append({
                "kind": kind,
                "last_applied_at": batch.applied_at.isoformat() if batch and batch.applied_at else None,
                "file_name": batch.file_name if batch else None,
                "rows_applied": batch.rows_applied if batch else 0,
                "period_start": batch.period_start.isoformat() if batch and batch.period_start else None,
                "period_end": batch.period_end.isoformat() if batch and batch.period_end else None,
            })
        sources = self.db.scalars(select(ErpSourceFile)).all()
        settings = get_settings()
        return {
            "kinds": kinds,
            "drive": {
                "enabled": settings.erp_sync_enabled and bool(settings.google_drive_folder_id),
                "interval_seconds": settings.erp_sync_interval_seconds,
                "files": [
                    {
                        "file_key": item.file_key,
                        "file_name": item.drive_file_name,
                        "last_check_at": item.last_check_at.isoformat() if item.last_check_at else None,
                        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
                        "remote_modified_at": item.remote_modified_at.isoformat() if item.remote_modified_at else None,
                        "last_status": item.last_status,
                        "last_error": item.last_error,
                        "consecutive_failures": item.consecutive_failures,
                    }
                    for item in sources
                ],
            },
        }

    def batches(self, limit: int = 30) -> list[dict]:
        self._scope(None)
        rows = self.db.scalars(
            select(ErpImportBatch)
            .order_by(ErpImportBatch.created_at.desc())
            .limit(min(limit, 100))
        ).all()
        return [
            {
                "id": str(batch.id), "kind": batch.kind, "source": batch.source,
                "status": batch.status, "file_name": batch.file_name,
                "rows_total": batch.rows_total, "rows_applied": batch.rows_applied,
                "rows_rejected": batch.rows_rejected,
                "period_start": batch.period_start.isoformat() if batch.period_start else None,
                "period_end": batch.period_end.isoformat() if batch.period_end else None,
                "error_summary": batch.error_summary,
                "created_at": batch.created_at.isoformat() if batch.created_at else None,
                "applied_at": batch.applied_at.isoformat() if batch.applied_at else None,
            }
            for batch in rows
        ]

    def sync_now(self) -> list[dict]:
        self.require_write()
        return run_drive_sync(self.db)

    # -- indicadores --

    def summary(self, first: date, last: date, store_code: str | None) -> dict:
        self._range(first, last)
        codes = self._scope(store_code)
        revenue_ok = self._revenue_map(codes)
        sales = store_totals(self.db, ErpSaleRow, codes, first, last)
        returns = store_totals(self.db, ErpReturnRow, codes, first, last)
        stores = []
        totals = {"revenue": Decimal("0"), "quantity": Decimal("0"), "rows": 0,
                  "returns_revenue": Decimal("0"), "returns_quantity": Decimal("0"), "returns_rows": 0}
        for code in codes:
            sale = sales.get(code, {"revenue": Decimal(0), "quantity": Decimal(0), "rows": 0})
            ret = returns.get(code, {"revenue": Decimal(0), "quantity": Decimal(0), "rows": 0})
            can_revenue = revenue_ok[code]
            stores.append({
                "code": code,
                "revenue": str(sale["revenue"]) if can_revenue else None,
                "revenue_visibility": "allowed" if can_revenue else "restricted",
                "quantity": str(sale["quantity"]),
                "rows": sale["rows"],
                "returns_revenue": str(ret["revenue"]) if can_revenue else None,
                "returns_quantity": str(ret["quantity"]),
                "returns_rows": ret["rows"],
            })
            totals["revenue"] += sale["revenue"] if can_revenue else Decimal(0)
            totals["quantity"] += sale["quantity"]
            totals["rows"] += sale["rows"]
            totals["returns_revenue"] += ret["revenue"] if can_revenue else Decimal(0)
            totals["returns_quantity"] += ret["quantity"]
            totals["returns_rows"] += ret["rows"]
        return {
            "from": first.isoformat(), "to": last.isoformat(), "stores": stores,
            "totals": {key: str(value) for key, value in totals.items()},
        }

    def daily(self, first: date, last: date, store_code: str | None) -> dict:
        self._range(first, last)
        codes = self._scope(store_code)
        revenue_ok = self._revenue_map(codes)
        sales = daily_totals(self.db, ErpSaleRow, codes, first, last)
        returns = daily_totals(self.db, ErpReturnRow, codes, first, last)
        days: dict[tuple[str, str], dict] = {}
        for (code, day), sale in sales.items():
            entry = days.setdefault((day.isoformat(), code), {
                "date": day.isoformat(), "store_code": code,
                "revenue": "0", "quantity": "0",
                "returns_revenue": "0", "returns_quantity": "0",
            })
            if revenue_ok[code]:
                entry["revenue"] = str(sale["revenue"])
            entry["quantity"] = str(sale["quantity"])
        for (code, day), ret in returns.items():
            entry = days.setdefault((day.isoformat(), code), {
                "date": day.isoformat(), "store_code": code,
                "revenue": "0", "quantity": "0",
                "returns_revenue": "0", "returns_quantity": "0",
            })
            if revenue_ok[code]:
                entry["returns_revenue"] = str(ret["revenue"])
            entry["returns_quantity"] = str(ret["quantity"])
        return {
            "from": first.isoformat(), "to": last.isoformat(),
            "days": [days[key] for key in sorted(days)],
        }

    def top(
        self, dimension: str, first: date, last: date,
        store_code: str | None, limit: int = 10, sort: str = "revenue",
    ) -> dict:
        self._range(first, last)
        codes = self._scope(store_code)
        revenue_ok = self._revenue_map(codes)
        limit = max(1, min(limit, TOP_LIMIT))
        if sort not in ("revenue", "quantity"):
            raise SalesError(422, "Ordenação desconhecida.")
        is_admin = self.principal.is_superadmin or self.principal.profile == "administrator"

        if dimension == "products":
            group_col = ErpSaleRow.product_code
        elif dimension == "sellers":
            group_col = ErpSaleRow.seller_code
        elif dimension == "customers":
            group_col = ErpSaleRow.customer_name
        else:
            raise SalesError(422, "Dimensão desconhecida.")

        rows = self.db.execute(
            select(
                group_col, ErpSaleRow.store_code,
                func.coalesce(func.sum(ErpSaleRow.total), 0),
                func.coalesce(func.sum(ErpSaleRow.quantity), 0),
                func.count(),
            )
            .where(
                ErpSaleRow.store_code.in_(codes),
                ErpSaleRow.sale_date >= first,
                ErpSaleRow.sale_date <= last,
            )
            .group_by(group_col, ErpSaleRow.store_code)
        ).all()

        STORE_NAMES = {"JOINVILLE": "Joinville", "TUBARAO": "Tubarão", "ITAJAI": "Itajaí"}
        merged: dict[str, dict] = {}
        for key, code, revenue, qty, count in rows:
            # Vendedor: o codigo do ERP pode se repetir entre lojas — nao fundir.
            merge_key = f"{key}|{code}" if dimension == "sellers" else key
            label = (
                f"{key} · {STORE_NAMES.get(code, code)}" if dimension == "sellers" else key
            )
            item = merged.setdefault(merge_key, {
                "key": label, "revenue": Decimal(0), "quantity": Decimal(0), "rows": 0,
                "stores": set(),
            })
            if revenue_ok[code]:
                item["revenue"] += revenue
            item["quantity"] += qty
            item["rows"] += count
            item["stores"].add(code)

        if dimension == "customers" and is_admin:
            cnpjs = self.db.execute(
                select(ErpSaleRow.customer_name, ErpSaleRow.customer_cnpj)
                .where(
                    ErpSaleRow.store_code.in_(codes),
                    ErpSaleRow.sale_date >= first,
                    ErpSaleRow.sale_date <= last,
                )
                .distinct()
            ).all()
            by_name: dict[str, str] = {}
            for name, cnpj in cnpjs:
                by_name.setdefault(name, cnpj)
        else:
            by_name = {}

        items = sorted(
            merged.values(), key=lambda item: (item[sort], item["revenue"]), reverse=True
        )[:limit]
        return {
            "dimension": dimension,
            "from": first.isoformat(), "to": last.isoformat(),
            "items": [
                {
                    "key": item["key"],
                    "customer_cnpj": by_name.get(item["key"]) if dimension == "customers" else None,
                    "revenue": str(item["revenue"]),
                    "quantity": str(item["quantity"]),
                    "rows": item["rows"],
                    "stores": sorted(item["stores"]),
                }
                for item in items
            ],
        }
