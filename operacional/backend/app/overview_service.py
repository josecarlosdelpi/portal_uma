"""Leitura segura de indicadores comerciais com fonte oficial em homologacao.

A ausencia de fonte oficial e representada por null, nunca por um valor
inventado ou por zero. Os numeros vindos do piloto ERP sao identificados
como dados em fase de testes ate a reconciliacao com os relatorios do ERP.
"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.erp_sales_service import month_bounds, pilot_sales_status, store_totals
from app.models import ErpSaleRow, MonthlySalesTarget, User
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
    first, last = month_bounds(year, month)
    prev_first, prev_last = month_bounds(year if month > 1 else year - 1,
                                         month - 1 if month > 1 else 12)
    revenue = store_totals(db, ErpSaleRow, stores, first, last)
    previous = store_totals(db, ErpSaleRow, stores, prev_first, prev_last)
    result = []
    for code in stores:
        # Permissao do modulo nao autoriza automaticamente os indicadores.
        can_target = (
            can_access(principal, "sales.target.view", code)
            or can_access(principal, "targets.view", code)
        )
        can_revenue = can_access(principal, "sales.revenue.view", code)
        can_attainment = can_access(principal, "sales.attainment.view", code)
        can_previous = can_access(principal, "sales.previous_month.view", code)
        store_revenue = revenue.get(code, {}).get("revenue") if can_revenue else None
        target = Decimal(amounts[code]) if can_target and amounts[code] is not None else None
        attainment = (
            (store_revenue / target * 100).quantize(Decimal("0.1"))
            if can_attainment and store_revenue is not None and target and target > 0
            else None
        )
        prev_revenue = previous.get(code, {}).get("revenue") if can_previous else None
        change = (
            ((store_revenue - prev_revenue) / prev_revenue * 100).quantize(Decimal("0.1"))
            if store_revenue is not None and prev_revenue
            else None
        )
        result.append({
            "code": code,
            "name": STORE_NAMES[code],
            "target": amounts[code] if can_target else None,
            "target_visibility": "allowed" if can_target else "restricted",
            "revenue": str(store_revenue) if store_revenue is not None else None,
            "attainment_percent": str(attainment) if attainment is not None else None,
            "previous_month_change_percent": str(change) if change is not None else None,
            "previous_year_change_percent": None,
        })
    # Consolidado somente quando o usuario esta autorizado nas tres lojas;
    # cada indicador continua exigindo sua propria concessao.
    full_consolidation = set(stores) == STORE_CODES
    all_targets = all(x["target_visibility"] == "allowed" and x["target"] is not None for x in result)
    goal = (
        str(sum((Decimal(x["target"]) for x in result), start=Decimal("0.00")))
        if all_targets else None
    )
    total_revenue = sum(
        (Decimal(x["revenue"]) for x in result if x["revenue"] is not None),
        start=Decimal("0"),
    )
    has_revenue = any(x["revenue"] is not None for x in result)
    status = pilot_sales_status(db)

    return {
        "year": year, "month": month,
        "scope": "consolidated" if full_consolidation else "store",
        "stores": result,
        "summary": {
            "monthly_target": goal,
            "revenue": str(total_revenue) if has_revenue else None,
            "attainment_percent": (
                str((total_revenue / Decimal(goal) * 100).quantize(Decimal("0.1")))
                if goal and Decimal(goal) > 0 and has_revenue else None
            ),
            "previous_month_change_percent": None,
            "previous_year_change_percent": None,
        },
        "source": {
            "sales_status": status["status"],
            "sales_updated_at": status["sales_updated_at"],
            "message": status["message"],
        },
    }


def consolidated_target_snapshot(db: Session, year: int, month: int) -> dict:
    """Somente usado dentro da area consolidada restrita a administradores."""
    amounts = store_targets(db, year, month, STORE_CODES)
    all_goals = all(amounts[code] is not None for code in STORE_CODES)
    first, last = month_bounds(year, month)
    revenue = store_totals(db, ErpSaleRow, STORE_CODES, first, last)
    status = pilot_sales_status(db)
    stores = []
    total_revenue = Decimal("0")
    has_revenue = False
    for code in ["JOINVILLE", "TUBARAO", "ITAJAI"]:
        store_revenue = revenue.get(code, {}).get("revenue")
        target = Decimal(amounts[code]) if amounts[code] is not None else None
        attainment = (
            (store_revenue / target * 100).quantize(Decimal("0.1"))
            if store_revenue is not None and target and target > 0 else None
        )
        if store_revenue is not None:
            total_revenue += store_revenue
            has_revenue = True
        stores.append({
            "code": code, "name": STORE_NAMES[code], "target": amounts[code],
            "revenue": str(store_revenue) if store_revenue is not None else None,
            "attainment_percent": str(attainment) if attainment is not None else None,
            "change_percent": None,
        })
    total_target = (
        str(sum((Decimal(x) for x in amounts.values()), Decimal("0.00")))
        if all_goals else None
    )
    return {
        "stores": stores,
        "total_target": total_target,
        "revenue": str(total_revenue) if has_revenue else None,
        "attainment_percent": (
            str((total_revenue / Decimal(total_target) * 100).quantize(Decimal("0.1")))
            if total_target and Decimal(total_target) > 0 and has_revenue else None
        ),
        "previous_month_change_percent": None,
        "previous_year_change_percent": None,
        "source": {"status": status["status"], "sales_updated_at": status["sales_updated_at"]},
    }
