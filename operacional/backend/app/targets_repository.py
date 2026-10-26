"""Banco central e auditoria transacional das metas."""
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import AuditEvent, MonthlySalesTarget, StoreTargetSettings, User


class TargetRepository:
    def __init__(self, session: Session):
        self.session = session

    def month(self, store_code: str, year: int, month: int, *, lock: bool = False) -> MonthlySalesTarget | None:
        statement = select(MonthlySalesTarget).where(
            MonthlySalesTarget.store_code == store_code,
            MonthlySalesTarget.year == year,
            MonthlySalesTarget.month == month,
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def settings(self, store_code: str, *, lock: bool = False) -> StoreTargetSettings | None:
        statement = select(StoreTargetSettings).where(StoreTargetSettings.store_code == store_code)
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def add_month(self, store_code: str, year: int, month: int, actor_id: UUID) -> MonthlySalesTarget:
        row = MonthlySalesTarget(
            id=uuid4(), store_code=store_code, year=year, month=month, amount=None,
            days_off=[], revision=1, updated_by=actor_id,
        )
        self.session.add(row)
        return row

    def add_minimum(self, store_code: str, amount, actor_id: UUID) -> StoreTargetSettings:
        row = StoreTargetSettings(
            store_code=store_code, minimum_daily=amount,
            revision=1, updated_by=actor_id,
        )
        self.session.add(row)
        return row

    def log(self, actor: User, action: str, entity: str, identity: str, details: dict) -> None:
        self.session.add(AuditEvent(
            id=uuid4(), actor_id=actor.id, actor_subject=actor.auth_subject,
            action=action, entity_type=entity, entity_id=identity,
            details=details,
        ))

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
