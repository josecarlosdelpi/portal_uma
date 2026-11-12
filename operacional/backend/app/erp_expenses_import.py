"""Ingestao de despesas/pagamentos do ERP no contrato compartilhado.

Espelha a semantica de erp_import.import_erp_file (mesmos estados de lote:
RECEIVED/APPLIED/DUPLICATE/FAILED, mesmas fontes MANUAL_UPLOAD/DRIVE_SYNC e
deduplicacao por file_sha256 contra o ultimo lote aplicado), mas para o layout
de 9 colunas de Despesas.csv e para o modelo de snapshot completo do dominio
financeiro — linhas ficam vinculadas ao proprio lote (historico preservado;
o snapshot corrente e sempre o ultimo lote APPLIED de kind='DESPESAS').
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.erp_csv import KIND_DESPESAS
from app.erp_import import _latest_applied
from app.finance_domain import ImportFormatError, parse_despesas
from app.models import AuditEvent, ErpImportBatch, FinancialObligation, User

QUALITY_FLAGS_LIMIT = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def apply_despesas_file(
    db: Session, *,
    content: bytes,
    file_name: str,
    source: str,
    actor: User | None = None,
    drive_file_id: str | None = None,
) -> ErpImportBatch:
    """Aplica um snapshot de despesas; reimportar o mesmo arquivo nao altera
    os totais (lote marcado DUPLICATE)."""
    digest = hashlib.sha256(content).hexdigest()
    batch = ErpImportBatch(
        id=uuid4(), kind=KIND_DESPESAS, source=source, status="RECEIVED",
        file_name=(file_name or "Despesas.csv")[:150], file_sha256=digest,
        drive_file_id=drive_file_id, imported_by=actor.id if actor else None,
    )
    db.add(batch)

    previous = _latest_applied(db, KIND_DESPESAS)
    if previous is not None and previous.file_sha256 == digest:
        batch.status = "DUPLICATE"
        batch.applied_at = _utcnow()
        db.commit()
        return batch

    try:
        parsed = parse_despesas(content)
    except ImportFormatError as error:
        batch.status = "FAILED"
        batch.rows_rejected = 0
        batch.error_summary = {"errors": error.errors[:30], "quality_flags": []}
        batch.applied_at = _utcnow()
        db.commit()
        return batch

    db.add_all(
        FinancialObligation(
            id=uuid4(), batch_id=batch.id, source_row=row.source_row,
            supplier_doc=row.supplier_doc, supplier_name=row.supplier_name,
            amount=row.amount, due_date=row.due_date, paid_at=row.paid_at,
            category=row.category, store_code=row.store_code, status=row.status,
        )
        for row in parsed.rows
    )

    batch.status = "APPLIED"
    batch.rows_total = len(parsed.rows)
    batch.rows_applied = len(parsed.rows)
    batch.period_start = parsed.period_start
    batch.period_end = parsed.period_end
    batch.coverage = [{"mode": "full_snapshot"}]
    flags = [flag.as_dict() for flag in parsed.flags]
    batch.error_summary = {
        "errors": [], "warnings": [],
        "quality_flags": flags[:QUALITY_FLAGS_LIMIT],
        "quality_flag_count": len(flags),
    }
    batch.applied_at = _utcnow()
    db.add(AuditEvent(
        id=uuid4(), actor_id=actor.id if actor else None,
        actor_subject=actor.auth_subject if actor else "erp-drive-sync",
        action="erp.expenses.imported", entity_type="erp_import_batch",
        entity_id=str(batch.id),
        details={
            "kind": KIND_DESPESAS, "source": source, "file": batch.file_name,
            "sha256": digest[:16], "rows_applied": len(parsed.rows),
            "quality_flags": len(flags),
            "period": f"{parsed.period_start}/{parsed.period_end}",
        },
    ))
    db.commit()
    return batch


def expenses_handlers(db: Session) -> dict:
    """Handlers no mesmo formato de sales_handlers — um so sincronizador."""

    def handle(content: bytes, file_name: str, drive_file_id: str) -> ErpImportBatch:
        return apply_despesas_file(
            db, content=content, file_name=file_name,
            source="DRIVE_SYNC", actor=None, drive_file_id=drive_file_id,
        )

    return {KIND_DESPESAS: handle}
