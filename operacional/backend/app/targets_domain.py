"""Regras herdadas da demonstracao v5.1, sem gerar vendas ficticias.

Dias uteis: seg-sex, excluindo apenas dias explicitamente marcados sem expediente.
Previas dividem a meta exatamente em centavos. As metas dinamicas so serao
calculadas quando o historico diario de vendas oficial estiver integrado.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

CENT = Decimal("0.01")


def business_days(year: int, month: int, excluded: set[date] | None = None) -> list[date]:
    excluded = excluded or set()
    return [
        date(year, month, day)
        for day in range(1, monthrange(year, month)[1] + 1)
        if date(year, month, day).weekday() < 5 and date(year, month, day) not in excluded
    ]


def preview_distribution(amount: Decimal | None, dates: list[date]) -> list[dict]:
    """Allocates every cent exactly once; never represents these as actual sales."""
    if amount is None or not dates:
        return [
            {"date": day.isoformat(), "weekday": day.weekday(), "base_daily_target": None}
            for day in dates
        ]
    cents = int((amount * 100).to_integral_exact())
    quotient, remainder = divmod(cents, len(dates))
    return [
        {
            "date": day.isoformat(),
            "weekday": day.weekday(),
            "base_daily_target": str(
                (Decimal(quotient + (1 if i < remainder else 0)) / 100).quantize(CENT)
            ),
        }
        for i, day in enumerate(dates)
    ]


def dynamic_day_target(
    amount: Decimal,
    sales_before: Decimal,
    remaining_open_days: int,
    minimum_after_goal: Decimal | None,
) -> Decimal | None:
    """The v5.1 rule, ready for verified daily sales when ERP import exists."""
    if remaining_open_days < 1:
        return None
    if sales_before >= amount:
        return minimum_after_goal
    return (max(Decimal("0"), amount - sales_before) / remaining_open_days).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def dynamic_plan(
    amount: Decimal,
    dates: list[date],
    sales_by_date: Mapping[date, Decimal],
    minimum_after_goal: Decimal | None,
) -> list[dict]:
    """Only use after sales data has been loaded from a verified official source.

    Sales from all calendar days, including Saturdays and closures, contribute
    to the amount sold before any given open date, as in the v5.1 prototype.
    """
    plan = []
    for i, day in enumerate(dates):
        before = sum((value for sale_day, value in sales_by_date.items() if sale_day < day),
                     start=Decimal("0"))
        plan.append({
            "date": day.isoformat(),
            "daily_target": dynamic_day_target(
                amount, before, len(dates) - i, minimum_after_goal
            ),
            "sales_before": before,
        })
    return plan
