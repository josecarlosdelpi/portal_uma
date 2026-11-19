"""Ingestao de snapshots ERP comerciais com idempotencia e auditoria.

Sem identificadores transacionais no ERP: o arquivo representa o estado da
janela que cobre. A substituicao ocorre por cobertura (loja x intervalo de
datas), dentro de uma unica transacao, preservando linhas fora da janela.
Linhas integralmente iguais sao mantidas — cardinalidade nunca e reduzida.
"""
import hashlib
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.erp_csv import KIND_DEVOLUCOES, KIND_VENDAS, KINDS, ParsedRow, parse_erp_csv
from app.models import (
    AuditEvent, ErpImportBatch, ErpReturnRow, ErpSaleRow, User,
)

ROW_MODEL = {KIND_VENDAS: ErpSaleRow, KIND_DEVOLUCOES: ErpReturnRow}
AUDIT_ACTION = {KIND_VENDAS: "erp.sales.imported", KIND_DEVOLUCOES: "erp.returns.imported"}


class ErpImportError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coverage(rows: list[ParsedRow]) -> list[dict]:
    """Janela contigua por loja declarada pelo snapshot."""
    windows: dict[str, list] = {}
    for row in rows:
        span = windows.setdefault(row.store_code, [row.sale_date, row.sale_date])
        span[0] = min(span[0], row.sale_date)
        span[1] = max(span[1], row.sale_date)
    return [
        {"store_code": code, "first_date": span[0].isoformat(), "last_date": span[1].isoformat()}
        for code, span in sorted(windows.items())
    ]


def _latest_applied(db: Session, kind: str) -> ErpImportBatch | None:
    return db.scalar(
        select(ErpImportBatch)
        .where(ErpImportBatch.kind == kind, ErpImportBatch.status == "APPLIED")
        .order_by(ErpImportBatch.applied_at.desc(), ErpImportBatch.created_at.desc())
        .limit(1)
    )


def import_erp_file(
    db: Session, *,
    kind: str,
    content: bytes,
    file_name: str,
    source: str,
    actor: User | None,
    drive_file_id: str | None = None,
) -> ErpImportBatch:
    """Aplica um snapshot; reimportar o mesmo arquivo nao altera os totais."""
    if kind not in KINDS:
        raise ErpImportError(422, "Tipo de arquivo desconhecido.")
    digest = hashlib.sha256(content).hexdigest()
    batch = ErpImportBatch(
        id=uuid4(), kind=kind, source=source, status="RECEIVED",
        file_name=(file_name or "arquivo.csv")[:150], file_sha256=digest,
        drive_file_id=drive_file_id, imported_by=actor.id if actor else None,
    )
    db.add(batch)

    previous = _latest_applied(db, kind)
    if previous and previous.file_sha256 == digest:
        batch.status = "DUPLICATE"
        batch.applied_at = _utcnow()
        db.commit()
        return batch

    parsed = parse_erp_csv(content)
    batch.rows_total = parsed.total_lines
    batch.rows_rejected = parsed.total_lines - len(parsed.rows)
    if parsed.errors or not parsed.rows:
        batch.status = "FAILED"
        batch.error_summary = {
            "errors": parsed.errors[:30],
            "warnings": parsed.warnings[:30],
        }
        db.commit()
        return batch

    coverage = _coverage(parsed.rows)
    model = ROW_MODEL[kind]
    period_start = min(span["first_date"] for span in coverage)
    period_end = max(span["last_date"] for span in coverage)

    for span in coverage:
        db.execute(
            delete(model).where(
                model.store_code == span["store_code"],
                model.sale_date >= date.fromisoformat(span["first_date"]),
                model.sale_date <= date.fromisoformat(span["last_date"]),
            )
        )
    db.add_all(
        model(
            id=uuid4(), batch_id=batch.id, sale_date=row.sale_date,
            store_code=row.store_code, seller_code=row.seller_code,
            customer_cnpj=row.customer_cnpj, customer_name=row.customer_name,
            product_code=row.product_code, quantity=row.quantity,
            unit_price=row.unit_price, total=row.total, row_hash=row.row_hash,
        )
        for row in parsed.rows
    )

    batch.status = "APPLIED"
    batch.rows_applied = len(parsed.rows)
    batch.period_start = date.fromisoformat(period_start)
    batch.period_end = date.fromisoformat(period_end)
    batch.coverage = coverage
    batch.applied_at = _utcnow()
    if parsed.warnings:
        batch.error_summary = {"errors": [], "warnings": parsed.warnings[:30]}
    db.add(AuditEvent(
        id=uuid4(), actor_id=actor.id if actor else None,
        actor_subject=actor.auth_subject if actor else "erp-drive-sync",
        action=AUDIT_ACTION[kind], entity_type="erp_import_batch",
        entity_id=str(batch.id),
        details={
            "kind": kind, "source": source, "file": batch.file_name,
            "sha256": digest[:16], "rows_applied": len(parsed.rows),
            "rows_rejected": batch.rows_rejected,
            "period": f"{period_start}/{period_end}",
        },
    ))
    db.commit()
    return batch
