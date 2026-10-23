"""Goals preserve the business-calendar semantics approved in demo v5.1."""
from datetime import date
from decimal import Decimal
from app.targets_domain import business_days, dynamic_day_target, dynamic_plan, preview_distribution


def test_weekdays_only_without_automatic_holidays():
    days = business_days(2026, 10)
    assert all(d.weekday() < 5 for d in days)
    assert date(2026, 10, 12) in days  # Exclusion is only by explicit store calendar.
    assert date(2026, 10, 10) not in days


def test_store_closures_remove_only_explicit_dates():
    days = business_days(2026, 10, {date(2026, 10, 12)})
    assert date(2026, 10, 12) not in days
    assert date(2026, 10, 13) in days


def test_preview_distributes_exact_cents_without_rounding_loss():
    dates = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)]
    result = preview_distribution(Decimal("100.01"), dates)
    assert [row["base_daily_target"] for row in result] == ["33.34", "33.34", "33.33"]
    assert sum(Decimal(row["base_daily_target"]) for row in result) == Decimal("100.01")


def test_no_target_never_invents_amounts():
    assert preview_distribution(None, [date(2026, 10, 1)])[0]["base_daily_target"] is None


def test_dynamic_goal_uses_sales_before_date_and_days_remaining():
    assert dynamic_day_target(Decimal("10000"), Decimal("4000"), 3, Decimal("500")) == Decimal("2000.00")
    assert dynamic_day_target(Decimal("10000"), Decimal("10000"), 3, Decimal("500")) == Decimal("500")
    assert dynamic_day_target(Decimal("10000"), Decimal("10000"), 3, None) is None
    assert dynamic_day_target(Decimal("10000"), Decimal("10000"), 0, Decimal("500")) is None


def test_dynamic_plan_counts_weekend_sales_prior_to_open_day():
    days = [date(2026, 10, 9), date(2026, 10, 12)]
    sales = {
        date(2026, 10, 9): Decimal("400"),
        date(2026, 10, 10): Decimal("700"),
    }
    plan = dynamic_plan(Decimal("1000"), days, sales, Decimal("200"))
    assert plan[0]["sales_before"] == Decimal("0")
    assert plan[0]["daily_target"] == Decimal("500.00")
    assert plan[1]["sales_before"] == Decimal("1100")
    assert plan[1]["daily_target"] == Decimal("200")
