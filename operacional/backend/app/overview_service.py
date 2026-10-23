"""Leitura segura de indicadores comerciais com fonte oficial ainda pendente.

Nao existe linha de vendas no esquema operacional. A ausencia de fonte oficial
e representada por null, nunca por um valor inventado ou por zero.
"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MonthlySalesTarget, User
from app.policy import STORE_CODES, can_access, visible_stores
from app.repositories import load_principal

STORE_NAMES = {"JOINVILLE": "Joinville", "TUBARAO": "Tubarão", "ITAJAI": "Itajaí"}


class OverviewError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def store_targets(db: Session, year: int, month: int, codes: set[str] | frozenset[str]) -> dict[str, str | None]:
    if not codes:
        return {}
    amounts = {code: None for code in codes}
    rows = db.scalars(
        select(MonthlySalesTarget).where(
            MonthlySalesTarget.year == year,
            MonthlySalesTarget.month == month,
            MonthlySalesTarget.store_code.in_(codes),
        )
    ).all()
    for row in rows:
        amounts[row.store_code] = str(row.amount) if row.amount is not None else None
    return amounts


def overview_for_user(db: Session, user: User, year: int, month: int) -> dict:
    if not 2020 <= year <= 2100 or not 1 <= month <= 12:
        raise OverviewError(422, "Competência inválida")
    principal = load_principal(db, user)
    stores = sorted(
        s for s in visible_stores(principal)
        if can_access(principal, "overview.view", s)
    )
    if not stores:
        raise OverviewError(403, "Acesso negado")

    amounts = store_targets(db, year, month, frozenset(stores))
    result = []
    for code in stores:
        # Permissao do modulo nao autoriza automaticamente os indicadores.
        can_target = (
            principal.profile == "administrator" or principal.is_superadmin
            or can_access(principal, "sales.target.view", code)
            or can_access(principal, "targets.view", code)
        )
        result.append({
            "code": code,
            "name": STORE_NAMES[code],
            "target": amounts[code] if can_target else None,
            "target_visibility": "allowed" if can_target else "restricted",
            "revenue": None,
            "attainment_percent": None,
            "previous_month_change_percent": None,
            "previous_year_change_percent": None,
        })
    full_consolidation = (principal.is_superadmin or principal.profile == "administrator") and set(stores) == STORE_CODES
    all_targets = all(x["target_visibility"] == "allowed" and x["target"] is not None for x in result)
    goal = (
        str(sum((Decimal(x["target"]) for x in result), start=Decimal("0.00")))
        if all_targets else None
    )

    return {
        "year": year, "month": month,
        "scope": "consolidated" if full_consolidation else "store",
        "stores": result,
        "summary": {
            "monthly_target": goal,
            "revenue": None,
            "attainment_percent": None,
            "previous_month_change_percent": None,
            "previous_year_change_percent": None,
        },
        "source": {
            "sales_status": "awaiting_erp_integration",
            "sales_updated_at": None,
            "message": "Faturamento oficial ainda não integrado. Metas são independentes das vendas.",
        },
    }


def consolidated_target_snapshot(db: Session, year: int, month: int) -> dict:
    """Somente usado dentro da area consolidada restrita a administradores."""
    amounts = store_targets(db, year, month, STORE_CODES)
    all_goals = all(amounts[code] is not None for code in STORE_CODES)
    return {
        "stores": [
            {"code": code, "name": STORE_NAMES[code], "target": amounts[code],
             "revenue": None, "attainment_percent": None, "change_percent": None}
            for code in ["JOINVILLE", "TUBARAO", "ITAJAI"]
        ],
        "total_target": str(sum((Decimal(x) for x in amounts.values()), Decimal("0.00"))) if all_goals else None,
        "revenue": None,
        "attainment_percent": None,
        "previous_month_change_percent": None,
        "previous_year_change_percent": None,
        "source": {"status": "awaiting_erp_integration", "sales_updated_at": None},
    }
