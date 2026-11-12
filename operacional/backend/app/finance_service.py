"""Consultas e importacao do modulo Financeiro (Frente B: despesas e pagamentos).

Regras centrais:
- Consultas leem SOMENTE o snapshot corrente (erp_import_batches.is_current),
  escopado pelas lojas autorizadas do usuario. Lotes antigos ficam preservados.
- 'dt_vencimento' orienta compromissos; 'dt_pagamento' orienta pagamentos
  efetivos. Os dois eixos nunca sao somados no mesmo total.
- 'compra_revenda' nunca e tratada como despesa operacional nem como CMV.
- Sem IDs transacionais no ERP: linhas identicas sao lancamentos legitimos.
"""
from datetime import date, timedelta
from decimal import Decimal
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.erp_import_contract import (
    CHANNEL_MANUAL, COVERAGE_FULL_SNAPSHOT, DOMAIN_DESPESAS,
    QUALITY_FLAGS_LIMIT, STATUS_FAILED, STATUS_IMPORTED, file_sha256,
)
from app.finance_domain import ImportFormatError, parse_despesas
from app.models import AuditEvent, ErpImportBatch, FinancialObligation, User
from app.operations_service import OperationError
from app.policy import STORE_CODES, can_access
from app.repositories import load_principal

PAGE_SIZE_MAX = 100
PAGE_SIZE_DEFAULT = 25
BATCHES_LIMIT = 50
TOP_SUPPLIERS = 8

CATEGORIES = ("despesa", "compra_revenda")
STATUSES = ("aberto", "pago")

OBLIGATION_SORTS = {
    "due_date": FinancialObligation.due_date.asc(),
    "-due_date": FinancialObligation.due_date.desc(),
    "amount": FinancialObligation.amount.asc(),
    "-amount": FinancialObligation.amount.desc(),
    "supplier_name": FinancialObligation.supplier_name.asc(),
    "-supplier_name": FinancialObligation.supplier_name.desc(),
}
PAYMENT_SORTS = {
    "paid_at": FinancialObligation.paid_at.asc(),
    "-paid_at": FinancialObligation.paid_at.desc(),
    "amount": FinancialObligation.amount.asc(),
    "-amount": FinancialObligation.amount.desc(),
    "supplier_name": FinancialObligation.supplier_name.asc(),
    "-supplier_name": FinancialObligation.supplier_name.desc(),
}


def money(value: Decimal | int | float | None) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def parse_month(raw: str | None) -> tuple[int, int]:
    if raw is None:
        today = date.today()
        return today.year, today.month
    try:
        year, month = (int(part) for part in raw.split("-"))
        assert 2020 <= year <= 2100 and 1 <= month <= 12
        return year, month
    except (ValueError, AssertionError) as exc:
        raise OperationError(422, "Mes invalido; use o formato AAAA-MM") from exc


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return first, last


def parse_day(raw: str | None, field_name: str) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise OperationError(422, f"Data invalida em {field_name}; use AAAA-MM-DD") from exc


def due_flag(row: FinancialObligation, today: date) -> str:
    if row.status == "pago":
        return "quitado"
    if row.due_date < today:
        return "vencido"
    if row.due_date == today:
        return "hoje"
    return "a_vencer"


def item_public(row: FinancialObligation, today: date) -> dict:
    return {
        "id": str(row.id),
        "supplier_name": row.supplier_name,
        "supplier_doc": row.supplier_doc,
        "amount": money(row.amount),
        "due_date": row.due_date.isoformat(),
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "category": row.category,
        "store_code": row.store_code,
        "status": row.status,
        "due_flag": due_flag(row, today),
        "source_row": row.source_row,
    }


def bucket_months(pairs: list[tuple[date, Decimal]]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for day, amount in pairs:
        key = month_key(day)
        entry = buckets.setdefault(key, {"month": key, "amount": Decimal(0), "count": 0})
        entry["amount"] += amount
        entry["count"] += 1
    return [
        {"month": entry["month"], "amount": money(entry["amount"]), "count": entry["count"]}
        for _, entry in sorted(buckets.items())
    ]


class FinanceService:
    def __init__(self, db: Session, actor: User):
        self.db = db
        self.actor = actor
        self.principal = load_principal(db, actor)

    # ---------- autorizacao ----------

    def stores_with(self, permission: str = "finance.view") -> list[str]:
        return sorted(
            store for store in STORE_CODES
            if can_access(self.principal, permission, store)
        )

    def require_view(self) -> list[str]:
        stores = self.stores_with("finance.view")
        if not stores:
            raise OperationError(403, "Acesso negado")
        return stores

    def _store_scope(self, requested: str | None) -> list[str]:
        allowed = self.require_view()
        if requested in (None, "", "TODAS"):
            return allowed
        if requested not in STORE_CODES:
            raise OperationError(404, "Loja desconhecida")
        if requested not in allowed:
            raise OperationError(403, "Acesso negado")
        return [requested]

    @staticmethod
    def _page(page: int, page_size: int) -> tuple[int, int]:
        page = max(1, page)
        page_size = min(max(1, page_size), PAGE_SIZE_MAX)
        return page, page_size

    def audit(self, action: str, identifier: str, details: dict) -> None:
        self.db.add(AuditEvent(
            id=uuid4(), actor_id=self.actor.id, actor_subject=self.actor.auth_subject,
            action=action, entity_type="erp_import_batch", entity_id=identifier,
            details=details,
        ))

    def commit(self) -> None:
        try:
            self.db.commit()
        except (IntegrityError, DBAPIError) as error:
            self.db.rollback()
            raise OperationError(409, "Registro já existe ou foi alterado. Atualize os dados.") from error

    # ---------- lote / importacao ----------

    def _current_batch(self) -> ErpImportBatch | None:
        return self.db.scalar(select(ErpImportBatch).where(
            ErpImportBatch.domain == DOMAIN_DESPESAS,
            ErpImportBatch.is_current.is_(True),
        ))

    def _batch_public(self, batch: ErpImportBatch, with_flags: bool = False) -> dict:
        data = {
            "id": str(batch.id),
            "domain": batch.domain,
            "channel": batch.channel,
            "file_name": batch.file_name,
            "sha256": batch.sha256,
            "row_count": batch.row_count,
            "coverage": batch.coverage,
            "period_start": batch.period_start.isoformat() if batch.period_start else None,
            "period_end": batch.period_end.isoformat() if batch.period_end else None,
            "status": batch.status,
            "is_current": batch.is_current,
            "error_detail": batch.error_detail,
            "quality_flag_count": batch.quality_flag_count,
            "imported_at": batch.imported_at.isoformat() if batch.imported_at else None,
            "duration_ms": batch.duration_ms,
        }
        if with_flags:
            data["quality_flags"] = batch.quality_flags
        return data

    def import_despesas(self, payload: bytes, file_name: str,
                        channel: str = CHANNEL_MANUAL,
                        drive_file_id: str | None = None) -> dict:
        if not can_access(self.principal, "finance.import", None):
            raise OperationError(403, "Acesso negado")
        digest = file_sha256(payload)
        existing = self.db.scalar(select(ErpImportBatch).where(
            ErpImportBatch.domain == DOMAIN_DESPESAS,
            ErpImportBatch.sha256 == digest,
        ))
        if existing is not None:
            return {"duplicated": True, "batch": self._batch_public(existing)}

        started = monotonic()
        try:
            parsed = parse_despesas(payload)
        except ImportFormatError as error:
            batch = ErpImportBatch(
                id=uuid4(), domain=DOMAIN_DESPESAS, channel=channel,
                drive_file_id=drive_file_id, file_name=file_name[:200],
                sha256=digest, byte_length=len(payload), row_count=0,
                coverage=COVERAGE_FULL_SNAPSHOT, status=STATUS_FAILED,
                is_current=False,
                error_detail=" | ".join(error.errors)[:600],
                quality_flags=[], quality_flag_count=0,
                payload=payload, imported_by=self.actor.id,
                duration_ms=int((monotonic() - started) * 1000),
            )
            self.db.add(batch)
            self.audit("finance.import.failed", str(batch.id),
                       {"file_name": file_name[:200], "errors": error.errors[:10]})
            self.commit()
            detail = error.errors[0]
            if len(error.errors) > 1:
                detail += f" (+{len(error.errors) - 1} problemas)"
            raise OperationError(422, detail) from error

        batch = ErpImportBatch(
            id=uuid4(), domain=DOMAIN_DESPESAS, channel=channel,
            drive_file_id=drive_file_id, file_name=file_name[:200],
            sha256=digest, byte_length=len(payload),
            row_count=len(parsed.rows), coverage=COVERAGE_FULL_SNAPSHOT,
            period_start=parsed.period_start, period_end=parsed.period_end,
            status=STATUS_IMPORTED, is_current=True, error_detail=None,
            quality_flags=[flag.as_dict() for flag in parsed.flags[:QUALITY_FLAGS_LIMIT]],
            quality_flag_count=len(parsed.flags),
            payload=payload, imported_by=self.actor.id,
            duration_ms=int((monotonic() - started) * 1000),
        )
        previous = self._current_batch()
        if previous is not None:
            previous.is_current = False
        self.db.add(batch)
        self.db.flush()
        self.db.add_all(
            FinancialObligation(
                id=uuid4(), batch_id=batch.id, source_row=row.source_row,
                supplier_doc=row.supplier_doc, supplier_name=row.supplier_name,
                amount=row.amount, due_date=row.due_date, paid_at=row.paid_at,
                category=row.category, store_code=row.store_code, status=row.status,
            )
            for row in parsed.rows
        )
        self.audit("finance.imported", str(batch.id), {
            "file_name": file_name[:200], "sha256": digest[:12],
            "row_count": len(parsed.rows), "quality_flags": len(parsed.flags),
            "period_start": parsed.period_start.isoformat(),
            "period_end": parsed.period_end.isoformat(),
        })
        self.commit()
        return {"duplicated": False, "batch": self._batch_public(batch)}

    def list_batches(self) -> dict:
        self.require_view()
        rows = self.db.scalars(
            select(ErpImportBatch)
            .where(ErpImportBatch.domain == DOMAIN_DESPESAS)
            .order_by(ErpImportBatch.imported_at.desc())
            .limit(BATCHES_LIMIT)
        ).all()
        return {"items": [self._batch_public(row) for row in rows]}

    def batch_detail(self, batch_id: UUID) -> dict:
        self.require_view()
        row = self.db.scalar(select(ErpImportBatch).where(
            ErpImportBatch.id == batch_id,
            ErpImportBatch.domain == DOMAIN_DESPESAS,
        ))
        if row is None:
            raise OperationError(404, "Lote nao localizado")
        return self._batch_public(row, with_flags=True)

    # ---------- consultas do snapshot corrente ----------

    @staticmethod
    def _conditions(batch: ErpImportBatch, stores: list[str], category=None,
                    status=None, supplier=None, date_field=None,
                    start: date | None = None, end: date | None = None) -> list:
        """Clausulas compartilhadas entre listagem, contagem e agregados."""
        conds = [
            FinancialObligation.batch_id == batch.id,
            FinancialObligation.store_code.in_(stores),
        ]
        if category in CATEGORIES:
            conds.append(FinancialObligation.category == category)
        if status in STATUSES:
            conds.append(FinancialObligation.status == status)
        if supplier:
            conds.append(FinancialObligation.supplier_name.ilike(
                f"%{supplier.strip()[:60]}%"))
        if date_field is not None and start is not None:
            conds.append(date_field >= start)
        if date_field is not None and end is not None:
            conds.append(date_field <= end)
        return conds

    def _last_import_public(self, batch: ErpImportBatch | None) -> dict | None:
        if batch is None:
            return None
        return {
            "imported_at": batch.imported_at.isoformat() if batch.imported_at else None,
            "file_name": batch.file_name,
            "row_count": batch.row_count,
            "period_start": batch.period_start.isoformat() if batch.period_start else None,
            "period_end": batch.period_end.isoformat() if batch.period_end else None,
        }

    def overview(self, store: str | None, month: str | None, today: date | None = None) -> dict:
        today = today or date.today()
        year, month_num = parse_month(month)
        first, last = month_bounds(year, month_num)
        stores = self._store_scope(store)
        batch = self._current_batch()

        empty = {
            "as_of": today.isoformat(), "month": f"{year:04d}-{month_num:02d}",
            "has_data": False, "last_import": self._last_import_public(batch),
            "kpis": {}, "monthly_due": [], "by_store": [], "by_category": {},
        }
        if batch is None:
            return empty

        open_rows = self.db.execute(
            select(
                FinancialObligation.due_date, FinancialObligation.amount,
                FinancialObligation.store_code, FinancialObligation.category,
            ).where(
                FinancialObligation.batch_id == batch.id,
                FinancialObligation.store_code.in_(stores),
                FinancialObligation.status == "aberto",
            )
        ).all()
        paid_month = self.db.execute(
            select(
                FinancialObligation.amount,
                FinancialObligation.store_code, FinancialObligation.category,
            ).where(
                FinancialObligation.batch_id == batch.id,
                FinancialObligation.store_code.in_(stores),
                FinancialObligation.status == "pago",
                FinancialObligation.paid_at >= first,
                FinancialObligation.paid_at <= last,
            )
        ).all()

        limit_7 = today + timedelta(days=7)
        limit_30 = today + timedelta(days=30)
        open_amount = sum(row.amount for row in open_rows)
        overdue = [row for row in open_rows if row.due_date < today]
        due_7 = [row for row in open_rows if today <= row.due_date <= limit_7]
        due_30 = [row for row in open_rows if today <= row.due_date <= limit_30]
        paid_amount = sum(row.amount for row in paid_month)

        by_store = []
        for code in sorted(set(stores) | {row.store_code for row in open_rows} |
                           {row.store_code for row in paid_month}):
            if code not in stores:
                continue
            store_open = [row for row in open_rows if row.store_code == code]
            store_paid = [row for row in paid_month if row.store_code == code]
            by_store.append({
                "store_code": code,
                "open_amount": money(sum(r.amount for r in store_open)),
                "open_count": len(store_open),
                "paid_month_amount": money(sum(r.amount for r in store_paid)),
                "paid_month_count": len(store_paid),
            })

        by_category = {}
        for category in CATEGORIES:
            cat_open = [row for row in open_rows if row.category == category]
            cat_paid = [row for row in paid_month if row.category == category]
            by_category[category] = {
                "open_amount": money(sum(r.amount for r in cat_open)),
                "open_count": len(cat_open),
                "paid_month_amount": money(sum(r.amount for r in cat_paid)),
                "paid_month_count": len(cat_paid),
            }

        return {
            "as_of": today.isoformat(),
            "month": f"{year:04d}-{month_num:02d}",
            "has_data": True,
            "last_import": self._last_import_public(batch),
            "kpis": {
                "open_amount": money(open_amount), "open_count": len(open_rows),
                "overdue_amount": money(sum(r.amount for r in overdue)),
                "overdue_count": len(overdue),
                "due_7d_amount": money(sum(r.amount for r in due_7)),
                "due_7d_count": len(due_7),
                "due_30d_amount": money(sum(r.amount for r in due_30)),
                "due_30d_count": len(due_30),
                "paid_month_amount": money(paid_amount),
                "paid_month_count": len(paid_month),
            },
            "monthly_due": bucket_months([(row.due_date, row.amount) for row in open_rows]),
            "by_store": by_store,
            "by_category": by_category,
        }

    def obligations(self, store, category, status, supplier,
                    due_from, due_to, sort, page, page_size,
                    today: date | None = None) -> dict:
        today = today or date.today()
        stores = self._store_scope(store)
        page, page_size = self._page(page, page_size)
        batch = self._current_batch()
        if batch is None:
            return {"items": [], "total": 0, "sum_amount": "0.00", "page": page,
                    "page_size": page_size, "has_data": False, "by_month": []}

        start = parse_day(due_from, "due_from")
        end = parse_day(due_to, "due_to")
        conds = self._conditions(
            batch, stores, category, status, supplier,
            FinancialObligation.due_date, start, end)

        total, sum_amount = self.db.execute(
            select(func.count(), func.coalesce(func.sum(FinancialObligation.amount), 0))
            .where(*conds)
        ).one()
        pairs = self.db.execute(
            select(FinancialObligation.due_date, FinancialObligation.amount)
            .where(*conds)
        ).all()

        ordered = select(FinancialObligation).where(*conds).order_by(
            OBLIGATION_SORTS.get(sort, OBLIGATION_SORTS["due_date"]),
            FinancialObligation.id,
        )
        rows = self.db.scalars(
            ordered.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {
            "items": [item_public(row, today) for row in rows],
            "total": total, "sum_amount": money(sum_amount),
            "page": page, "page_size": page_size, "has_data": True,
            "by_month": bucket_months(list(pairs)),
            "last_import": self._last_import_public(batch),
        }

    def payments(self, store, category, supplier, paid_from, paid_to,
                 sort, page, page_size, today: date | None = None) -> dict:
        today = today or date.today()
        stores = self._store_scope(store)
        page, page_size = self._page(page, page_size)
        batch = self._current_batch()
        if batch is None:
            return {"items": [], "total": 0, "sum_amount": "0.00", "page": page,
                    "page_size": page_size, "has_data": False,
                    "by_month": [], "by_store": [], "by_category": {}}

        start = parse_day(paid_from, "paid_from")
        end = parse_day(paid_to, "paid_to")
        conds = self._conditions(
            batch, stores, category, "pago", supplier,
            FinancialObligation.paid_at, start, end)

        total, sum_amount = self.db.execute(
            select(func.count(), func.coalesce(func.sum(FinancialObligation.amount), 0))
            .where(*conds)
        ).one()
        aggregates = self.db.execute(
            select(FinancialObligation.paid_at, FinancialObligation.amount,
                   FinancialObligation.store_code, FinancialObligation.category)
            .where(*conds)
        ).all()

        by_store_map: dict[str, dict] = {}
        by_category: dict[str, dict] = {}
        for row in aggregates:
            entry = by_store_map.setdefault(row.store_code, {"amount": Decimal(0), "count": 0})
            entry["amount"] += row.amount
            entry["count"] += 1
            cat = by_category.setdefault(row.category, {"amount": Decimal(0), "count": 0})
            cat["amount"] += row.amount
            cat["count"] += 1

        ordered = select(FinancialObligation).where(*conds).order_by(
            PAYMENT_SORTS.get(sort, PAYMENT_SORTS["-paid_at"]),
            FinancialObligation.id,
        )
        rows = self.db.scalars(
            ordered.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {
            "items": [item_public(row, today) for row in rows],
            "total": total, "sum_amount": money(sum_amount),
            "page": page, "page_size": page_size, "has_data": True,
            "by_month": bucket_months([(r.paid_at, r.amount) for r in aggregates]),
            "by_store": [
                {"store_code": code, "amount": money(v["amount"]), "count": v["count"]}
                for code, v in sorted(by_store_map.items())
            ],
            "by_category": {
                cat: {"amount": money(v["amount"]), "count": v["count"]}
                for cat, v in by_category.items()
            },
            "last_import": self._last_import_public(batch),
        }

    def purchases(self, store, supplier, page, page_size,
                  today: date | None = None) -> dict:
        today = today or date.today()
        stores = self._store_scope(store)
        page, page_size = self._page(page, page_size)
        batch = self._current_batch()
        empty = {
            "has_data": False, "items": [], "total": 0, "page": page,
            "page_size": page_size, "totals": {}, "by_store": [],
            "by_month": [], "top_suppliers": [],
            "last_import": self._last_import_public(batch),
        }
        if batch is None:
            return empty

        conds = self._conditions(
            batch, stores, "compra_revenda", None, supplier)

        aggregates = self.db.execute(
            select(FinancialObligation.due_date, FinancialObligation.amount,
                   FinancialObligation.store_code, FinancialObligation.status,
                   FinancialObligation.supplier_name)
            .where(*conds)
        ).all()

        total_amount = sum(row.amount for row in aggregates)
        paid_rows = [row for row in aggregates if row.status == "pago"]
        open_rows = [row for row in aggregates if row.status == "aberto"]
        by_store_map: dict[str, dict] = {}
        supplier_map: dict[str, dict] = {}
        for row in aggregates:
            entry = by_store_map.setdefault(row.store_code, {"amount": Decimal(0), "count": 0})
            entry["amount"] += row.amount
            entry["count"] += 1
            sup = supplier_map.setdefault(row.supplier_name, {"amount": Decimal(0), "count": 0})
            sup["amount"] += row.amount
            sup["count"] += 1
        top = sorted(supplier_map.items(), key=lambda kv: kv[1]["amount"], reverse=True)

        ordered = select(FinancialObligation).where(*conds).order_by(
            FinancialObligation.due_date.asc(), FinancialObligation.id)
        rows = self.db.scalars(
            ordered.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {
            "has_data": True,
            "items": [item_public(row, today) for row in rows],
            "total": len(aggregates), "page": page, "page_size": page_size,
            "totals": {
                "count": len(aggregates), "amount": money(total_amount),
                "paid_amount": money(sum(r.amount for r in paid_rows)),
                "paid_count": len(paid_rows),
                "open_amount": money(sum(r.amount for r in open_rows)),
                "open_count": len(open_rows),
            },
            "by_store": [
                {"store_code": code, "amount": money(v["amount"]), "count": v["count"]}
                for code, v in sorted(by_store_map.items())
            ],
            "by_month": bucket_months([(row.due_date, row.amount) for row in aggregates]),
            "top_suppliers": [
                {"supplier_name": name, "amount": money(v["amount"]), "count": v["count"]}
                for name, v in top[:TOP_SUPPLIERS]
            ],
            "last_import": self._last_import_public(batch),
        }
