"""Monthly review workflow, versioned draft and frozen archive snapshots.

Only administrators can open *consolidated* commercial reports. Sellers must
never learn another store's figures through the closing presentation endpoint.
"""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.closing_schema import ClosingContent, DURATIONS
from app.models import AuditEvent, MonthlyClosingArchive, MonthlyClosingDraft, User
from app.overview_service import consolidated_target_snapshot
from app.policy import can_access
from app.repositories import load_principal


class ClosingError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class ClosingService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.principal = load_principal(db, user)

    def require(self, permission: str) -> None:
        # Consolidated report discloses all three stores: seller login never
        # receives it even when one store grants a monthly_closing permission.
        if (
            not self.principal.active
            or (not self.principal.is_superadmin and self.principal.profile != "administrator")
            or not can_access(self.principal, permission)
        ):
            raise ClosingError(403, "Fechamento consolidado restrito aos administradores")

    @staticmethod
    def _validate_month(year: int, month: int) -> None:
        if not 2020 <= year <= 2100 or not 1 <= month <= 12:
            raise ClosingError(422, "Competência inválida")

    def _draft(self, year: int, month: int, lock: bool = False) -> MonthlyClosingDraft | None:
        query = select(MonthlyClosingDraft).where(
            MonthlyClosingDraft.year == year, MonthlyClosingDraft.month == month
        )
        if lock:
            query = query.with_for_update()
        return self.db.scalar(query)

    def _latest(self, year: int, month: int) -> MonthlyClosingArchive | None:
        return self.db.scalar(
            select(MonthlyClosingArchive).where(
                MonthlyClosingArchive.year == year, MonthlyClosingArchive.month == month
            ).order_by(MonthlyClosingArchive.version.desc()).limit(1)
        )

    @staticmethod
    def _prior(year: int, month: int) -> tuple[int, int]:
        return (year - 1, 12) if month == 1 else (year, month - 1)

    def _pending_last_month(self, year: int, month: int) -> list[dict]:
        prior_year, prior_month = self._prior(year, month)
        archived = self._latest(prior_year, prior_month)
        if archived:
            priorities = archived.snapshot.get("draft", {}).get("priorities", [])
        else:
            prior = self._draft(prior_year, prior_month)
            priorities = prior.content.get("priorities", []) if prior else []
        return [p for p in priorities if p.get("status") != "concluida"][:3]

    def _audit(self, action: str, key: str, details: dict) -> None:
        self.db.add(AuditEvent(
            id=uuid4(), actor_id=self.user.id, actor_subject=self.user.auth_subject,
            action=action, entity_type="monthly_closing", entity_id=key,
            details=details,
        ))

    def _commit(self) -> None:
        try:
            self.db.commit()
        except (IntegrityError, DBAPIError) as exc:
            self.db.rollback()
            raise ClosingError(409, "Registro alterado em outra sessão; atualize e tente novamente") from exc

    def get(self, year: int, month: int) -> dict:
        self.require("monthly_closing.view")
        self._validate_month(year, month)
        draft = self._draft(year, month)
        latest = self._latest(year, month)
        return {
            "year": year, "month": month,
            "draft": draft.content if draft else ClosingContent().model_dump(mode="json"),
            "revision": draft.revision if draft else 0,
            "updated_at": draft.updated_at.isoformat() if draft and draft.updated_at else None,
            "data": consolidated_target_snapshot(self.db, year, month),
            "previous_pending": self._pending_last_month(year, month),
            "last_archive": {
                "id": str(latest.id), "version": latest.version,
                "created_at": latest.created_at.isoformat(),
            } if latest else None,
            "durations": DURATIONS,
            "sales_data_complete": False,
        }

    def save(self, year: int, month: int, content: ClosingContent,
             expected_revision: int) -> dict:
        self.require("monthly_closing.edit")
        self._validate_month(year, month)
        row = self._draft(year, month, lock=True)
        actual = row.revision if row else 0
        if actual != expected_revision:
            raise ClosingError(409, "Rascunho alterado por outro usuário; recarregue antes de salvar")
        normalized = content.model_dump(mode="json")
        if row and row.content == normalized:
            return self.get(year, month)
        if row is None:
            row = MonthlyClosingDraft(
                id=uuid4(), year=year, month=month, revision=1,
                content=normalized, updated_by=self.user.id,
            )
            self.db.add(row)
        else:
            row.revision += 1
            row.content = normalized
            row.updated_by = self.user.id
        self._audit(
            "closing.draft.updated", f"{year:04d}-{month:02d}",
            {
                "before_revision": actual, "after_revision": row.revision,
                "priority_count": len(normalized["priorities"]),
            }
        )
        self._commit()
        return self.get(year, month)

    def archive(self, year: int, month: int, expected_revision: int) -> dict:
        self.require("monthly_closing.archive")
        self._validate_month(year, month)
        draft = self._draft(year, month, lock=True)
        if draft is None:
            raise ClosingError(422, "Salve o rascunho antes de arquivar")
        if expected_revision != draft.revision:
            raise ClosingError(409, "Rascunho desatualizado; recarregue antes de arquivar")
        content = ClosingContent.model_validate(draft.content)
        if not 3 <= len(content.priorities) <= 5:
            raise ClosingError(422, "Cadastre entre três e cinco prioridades antes de arquivar")

        latest = self._latest(year, month)
        version = latest.version + 1 if latest else 1
        snapshot = {
            "period": f"{year:04d}-{month:02d}",
            "draft": content.model_dump(mode="json"),
            "data": consolidated_target_snapshot(self.db, year, month),
            "previous_pending": self._pending_last_month(year, month),
            "durations": DURATIONS,
            "state": "partial_sales_pending",  # No verified ERP data yet.
            "source": "Portal UMA — metas cadastradas; faturamento ERP pendente",
        }
        archived = MonthlyClosingArchive(
            id=uuid4(), year=year, month=month, version=version,
            snapshot=snapshot, archived_by=self.user.id,
        )
        self.db.add(archived)
        self._audit(
            "closing.archived", f"{year:04d}-{month:02d}",
            {"version": version, "archive_id": str(archived.id), "sales_data_complete": False},
        )
        self._commit()
        return {
            "id": str(archived.id),
            "version": version,
            "snapshot": snapshot,
            "created_at": archived.created_at.isoformat(),
        }

    def archive_list(self, year: int, month: int) -> list[dict]:
        self.require("monthly_closing.view")
        self._validate_month(year, month)
        rows = self.db.scalars(
            select(MonthlyClosingArchive).where(
                MonthlyClosingArchive.year == year,
                MonthlyClosingArchive.month == month,
            ).order_by(MonthlyClosingArchive.version.desc())
        ).all()
        return [{
            "id": str(row.id),
            "version": row.version,
            "state": row.snapshot.get("state", "unknown"),
            "created_at": row.created_at.isoformat(),
        } for row in rows]

    def archived(self, year: int, month: int, archive_id: UUID) -> dict:
        self.require("monthly_closing.view")
        self._validate_month(year, month)
        row = self.db.scalar(select(MonthlyClosingArchive).where(
            MonthlyClosingArchive.id == archive_id,
            MonthlyClosingArchive.year == year,
            MonthlyClosingArchive.month == month,
        ))
        if row is None:
            raise ClosingError(404, "Arquivo não encontrado")
        return {"id": str(row.id), "version": row.version,
                "snapshot": row.snapshot, "created_at": row.created_at.isoformat()}
