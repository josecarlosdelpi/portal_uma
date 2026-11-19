"""Ingestao de snapshots ERP comerciais com idempotencia e auditoria.

O arquivo CSV e a fonte oficial: cada versao validada substitui
INTEGRALMENTE o conjunto ativo do seu tipo, dentro de uma unica transacao.
Linhas ausentes no arquivo novo deixam de aparecer nos indicadores —
refletindo correcoes e cancelamentos feitos no ERP. Periodos sem registros
significam "sem dados no arquivo atual", nunca zero automatico.

Protecao de historico: linhas substituidas recebem superseded_at (soft-
delete recuperavel) e continuam no banco para auditoria, sem alimentar os
paineis. Um arquivo invalido nao toca o conjunto ativo, mas marca a fonte
como indisponivel ate chegar uma versao valida.
"""
import hashlib
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
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


def latest_batch(db: Session, kind: str) -> ErpImportBatch | None:
    """Lote mais recente do tipo, qualquer que seja o status.

    created_at e gravado com precisao de microssegundos pelos importadores
    (valor do cliente), o que torna a ordenacao deterministica.
    """
    return db.scalar(
        select(ErpImportBatch)
        .where(ErpImportBatch.kind == kind)
        .order_by(ErpImportBatch.created_at.desc(), ErpImportBatch.id.desc())
        .limit(1)
    )


def kind_availability(db: Session, kind: str) -> str:
    """Disponibilidade da fonte para os paineis.

    unavailable: o arquivo mais recente do tipo falhou na validacao — os
    dados vigentes nao representam mais o arquivo atual e nao devem ser
    exibidos como atuais;
    never_imported: nenhum lote registrado para o tipo;
    current: o arquivo vigente esta validado e aplicado (DUPLICATE conta
    como vigente porque o conteudo e identico ao aplicado).
    """
    latest = latest_batch(db, kind)
    if latest is None:
        return "never_imported"
    if latest.status == "FAILED":
        return "unavailable"
    return "current"


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
        created_at=_utcnow(),
    )
    db.add(batch)

    previous = _latest_applied(db, kind)
    if previous and previous.file_sha256 == digest:
        batch.status = "DUPLICATE"
        batch.applied_at = _utcnow()
        db.commit()
        return batch

    parsed = parse_erp_csv(content, kind)
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

    # Substituicao integral e atomica: o arquivo vigente e a unica fonte
    # ativa do tipo; copias anteriores ficam como superseded (auditoria).
    superseded = db.execute(
        update(model)
        .where(model.superseded_at.is_(None))
        .values(superseded_at=_utcnow())
    ).rowcount or 0
    db.add_all(
        model(
            id=uuid4(), batch_id=batch.id, sale_date=row.sale_date,
            store_code=row.store_code, seller_code=row.seller_code,
            customer_cnpj=row.customer_cnpj, customer_name=row.customer_name,
            product_code=row.product_code, quantity=row.quantity,
            unit_price=row.unit_price, total=row.total, row_hash=row.row_hash,
            seller_name=row.seller_name,
            product_description=row.product_description,
            product_unit=row.product_unit, unit_cost=row.unit_cost,
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
            "rows_superseded": superseded,
            "period": f"{period_start}/{period_end}",
        },
    ))
    db.commit()
    return batch
