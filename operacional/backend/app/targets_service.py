"""Casos de uso: metas por loja, previas e calendario sem dados ficticios."""
from datetime import date
from decimal import Decimal
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.erp_sales_service import month_bounds, sales_by_date_for_store
from app.models import User
from app.policy import STORE_CODES, can_access
from app.repositories import load_principal
from app.targets_domain import business_days, dynamic_plan, preview_distribution
from app.targets_repository import TargetRepository


class TargetError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class TargetService:
    def __init__(self, session: Session, user: User):
        self.repo = TargetRepository(session)
        self.user = user
        self.principal = load_principal(session, user)

    def _authorize(self, store_code: str, permission: str) -> None:
        if store_code not in STORE_CODES:
            raise TargetError(404, "Loja inexistente")
        if not can_access(self.principal, permission, store_code):
            raise TargetError(403, "Acesso negado")

    @staticmethod
    def _period(year: int, month: int) -> None:
        if not (2020 <= year <= 2100 and 1 <= month <= 12):
            raise TargetError(422, "Competencia invalida")

    @staticmethod
    def _revision(actual: int, expected: int) -> None:
        if actual != expected:
            raise TargetError(409, "Informacoes alteradas por outro usuario. Atualize antes de salvar.")

    def _commit(self) -> None:
        try:
            self.repo.commit()
        except (IntegrityError, DBAPIError) as exc:
            self.repo.rollback()
            raise TargetError(409, "Nao foi possivel gravar. Atualize e tente novamente.") from exc

    def get(self, store_code: str, year: int, month: int) -> dict:
        self._authorize(store_code, "targets.view")
        self._period(year, month)
        row = self.repo.month(store_code, year, month)
        settings = self.repo.settings(store_code)
        days_off = set(date.fromisoformat(day) for day in (row.days_off if row else []))
        days = business_days(year, month, days_off)
        target = row.amount if row else None
        daily_base = preview_distribution(target, days)
        first, last = month_bounds(year, month)
        can_revenue = (
            self.principal.is_superadmin or self.principal.profile == "administrator"
            or can_access(self.principal, "sales.revenue.view", store_code)
        )
        sales_by_date = (
            sales_by_date_for_store(self.repo.session, store_code, first, last)
            if can_revenue else {}
        )
        monthly_revenue = sum(sales_by_date.values(), Decimal("0"))
        has_sales = bool(sales_by_date)
        minimum = settings.minimum_daily if settings else None
        plan = (
            dynamic_plan(target, days, sales_by_date, minimum)
            if target is not None and has_sales else None
        )
        attainment = (
            (monthly_revenue / target * 100).quantize(Decimal("0.1"))
            if target and target > 0 and has_sales else None
        )
        return {
            "store_code": store_code,
            "year": year,
            "month": month,
            "target": {
                "amount": str(row.amount) if row and row.amount is not None else None,
                "revision": row.revision if row else 0,
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            },
            "minimum": {
                "amount": str(settings.minimum_daily) if settings else None,
                "revision": settings.revision if settings else 0,
            },
            "days_off": sorted(d.isoformat() for d in days_off),
            "working_day_count": len(days),
            "base_plan": daily_base,
            "sales": {
                "status": "pilot_unverified" if has_sales else "awaiting_official_import",
                "monthly_revenue": str(monthly_revenue) if has_sales else None,
                "attainment_percent": str(attainment) if attainment is not None else None,
                "dynamic_day_plan": (
                    [
                        {
                            "date": item["date"],
                            "daily_target": (
                                str(item["daily_target"])
                                if item["daily_target"] is not None else None
                            ),
                            "sales_before": str(item["sales_before"]),
                        }
                        for item in plan
                    ]
                    if plan else None
                ),
                "daily_sales": [
                    {"date": day.isoformat(), "revenue": str(value)}
                    for day, value in sorted(sales_by_date.items())
                ],
            },
        }

    def save_goal(self, store_code: str, year: int, month: int, *,
                  amount: Decimal, expected_revision: int) -> dict:
        self._authorize(store_code, "targets.edit")
        self._period(year, month)
        row = self.repo.month(store_code, year, month, lock=True)
        self._revision(row.revision if row else 0, expected_revision)
        if not business_days(year, month, set(date.fromisoformat(x) for x in (row.days_off if row else []))):
            raise TargetError(422, "Nenhum dia de expediente configurado para este mes.")
        previous = str(row.amount) if row and row.amount is not None else None
        if row is not None and row.amount == amount:
            return self.get(store_code, year, month)
        if row is None:
            row = self.repo.add_month(store_code, year, month, self.user.id)
        else:
            row.revision += 1
            row.updated_by = self.user.id
        row.amount = amount
        self.repo.log(
            self.user, "target.goal.updated", "monthly_target",
            f"{store_code}|{year:04d}-{month:02d}",
            {"store": store_code, "period": f"{year:04d}-{month:02d}", "before": previous, "after": str(amount)},
        )
        self._commit()
        return self.get(store_code, year, month)

    def save_minimum(self, store_code: str, *, amount: Decimal, expected_revision: int) -> dict:
        self._authorize(store_code, "targets.edit")
        settings = self.repo.settings(store_code, lock=True)
        self._revision(settings.revision if settings else 0, expected_revision)
        previous = str(settings.minimum_daily) if settings else None
        if settings is not None and settings.minimum_daily == amount:
            return {"store_code": store_code, "amount": previous, "revision": settings.revision}
        if settings is None:
            settings = self.repo.add_minimum(store_code, amount, self.user.id)
        else:
            settings.minimum_daily = amount
            settings.revision += 1
            settings.updated_by = self.user.id
        self.repo.log(self.user, "target.minimum.updated", "store_target_settings",
                      store_code, {"store": store_code, "before": previous, "after": str(amount)})
        self._commit()
        return {"store_code": store_code, "amount": str(settings.minimum_daily),
                "revision": settings.revision}

    def save_closed_days(self, store_code: str, year: int, month: int, *,
                         dates: list[date], expected_revision: int) -> dict:
        self._authorize(store_code, "targets.edit")
        self._period(year, month)
        if len(set(dates)) != len(dates):
            raise TargetError(422, "Datas de fechamento duplicadas")
        if any(d.year != year or d.month != month or d.weekday() >= 5 for d in dates):
            raise TargetError(422, "Informe apenas dias de segunda a sexta da competencia")
        row = self.repo.month(store_code, year, month, lock=True)
        self._revision(row.revision if row else 0, expected_revision)
        before = sorted(row.days_off) if row else []
        after = sorted(d.isoformat() for d in dates)
        if before == after:
            return self.get(store_code, year, month)
        if row and row.amount is not None and not business_days(year, month, set(dates)):
            raise TargetError(422, "Uma meta mensal precisa ter pelo menos um dia de expediente.")
        if row is None:
            row = self.repo.add_month(store_code, year, month, self.user.id)
        else:
            row.revision += 1
            row.updated_by = self.user.id
        row.days_off = after
        self.repo.log(self.user, "target.calendar.updated", "monthly_target",
                      f"{store_code}|{year:04d}-{month:02d}",
                      {"store": store_code, "period": f"{year:04d}-{month:02d}",
                       "before": before, "after": after})
        self._commit()
        return self.get(store_code, year, month)
