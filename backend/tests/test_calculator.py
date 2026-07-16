import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain import calculator  # noqa: E402


def test_usage_based_accrual_matches_workbook_example_1():
    # docs/vehicle-rules.md Example 1: 900 km at 10 HUF/km.
    assert calculator.usage_based_period_accrual(900, Decimal("10")) == Decimal("9000")


def test_usage_based_accrual_rejects_negative_usage():
    with pytest.raises(ValueError):
        calculator.usage_based_period_accrual(-1, Decimal("10"))


def test_interval_years_months_and_years_equivalent():
    assert calculator.interval_years(12, "months") == calculator.interval_years(1, "years")
    assert calculator.interval_years(6, "months") == Decimal("0.5")


def test_interval_years_rejects_bad_input():
    with pytest.raises(ValueError):
        calculator.interval_years(0, "years")
    with pytest.raises(ValueError):
        calculator.interval_years(12, "weeks")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("amount", "interval_value", "interval_unit", "expected"),
    [
        # docs/vehicle-rules.md Example 2, elapsed_days = 30, quantized to 2dp.
        (Decimal("49900"), 1, "years", Decimal("4101.37")),
        (Decimal("14000"), 6, "months", Decimal("2301.37")),
        (Decimal("41500"), 2, "years", Decimal("1705.48")),
    ],
)
def test_time_based_accrual_matches_workbook_example_2(amount, interval_value, interval_unit, expected):
    accrual = calculator.time_based_period_accrual(amount, interval_value, interval_unit, 30)
    assert calculator.quantize_currency(accrual) == expected


def test_time_based_accrual_rejects_negative_days():
    with pytest.raises(ValueError):
        calculator.time_based_period_accrual(Decimal("49900"), 1, "years", -1)


def test_reference_amount_rolls_over_to_latest_qualifying_expense():
    # docs/vehicle-rules.md latest-cost rollover example.
    baseline = Decimal("49900")
    expenses = [(date(2025, 6, 1), Decimal("49900")), (date(2026, 6, 1), Decimal("56000"))]

    assert calculator.reference_amount(baseline, expenses, date(2025, 3, 1)) == Decimal("49900")
    assert calculator.reference_amount(baseline, expenses, date(2025, 8, 1)) == Decimal("49900")
    assert calculator.reference_amount(baseline, expenses, date(2026, 6, 1)) == Decimal("56000")
    assert calculator.reference_amount(baseline, expenses, date(2026, 9, 1)) == Decimal("56000")


def test_reference_amount_falls_back_to_baseline_without_expenses():
    assert calculator.reference_amount(Decimal("49900"), [], date(2026, 1, 1)) == Decimal("49900")


def test_maintenance_status_matches_workbook_example_3():
    # km_progress 0.875, month_progress 0.75 -> soon.
    km_progress, month_progress = calculator.maintenance_progress(10_500, 12_000, 9, 12)
    assert km_progress == Decimal("10500") / Decimal("12000")
    assert calculator.maintenance_status(km_progress, month_progress) == "soon"


@pytest.mark.parametrize(
    ("peak", "expected"),
    [
        (Decimal("0.79"), "ok"),
        (Decimal("0.80"), "soon"),
        (Decimal("0.89"), "soon"),
        (Decimal("0.90"), "due"),
        (Decimal("1.04"), "due"),
        (Decimal("1.05"), "overdue"),
    ],
)
def test_maintenance_status_thresholds(peak, expected):
    assert calculator.maintenance_status(peak, None) == expected


def test_maintenance_status_ok_when_no_intervals():
    km_progress, month_progress = calculator.maintenance_progress(None, None, None, None)
    assert (km_progress, month_progress) == (None, None)
    assert calculator.maintenance_status(km_progress, month_progress) == "ok"


def test_reserve_recommendation_matches_workbook_example_4():
    items = [(Decimal("60000"), 100_000), (Decimal("36000"), 45_000), (Decimal("140000"), 50_000)]
    assert calculator.reserve_recommendation(items) == Decimal("4.20")


def test_reserve_recommendation_none_when_empty():
    assert calculator.reserve_recommendation([]) is None


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(Decimal("3.5"), "low"), (Decimal("4.2"), "reasonable"), (Decimal("5.0"), "high")],
)
def test_reserve_guidance_bands(configured, expected):
    assert calculator.reserve_guidance(configured, Decimal("4.20")) == expected


def test_reserve_guidance_none_without_recommendation():
    assert calculator.reserve_guidance(Decimal("4.2"), None) is None


def test_bucket_balance_sums_events():
    allocations = [Decimal("9000"), Decimal("4101.37")]
    expenses = [Decimal("2000")]
    assert calculator.bucket_balance(allocations, expenses) == Decimal("11101.37")


def test_bucket_balance_empty_history_is_zero():
    assert calculator.bucket_balance([], []) == Decimal("0")


@pytest.mark.parametrize(
    ("amount", "interval_value", "interval_unit", "expected"),
    [
        (Decimal("120000"), 12, "months", Decimal("10000")),
        (Decimal("120000"), 1, "years", Decimal("10000")),
        (Decimal("14000"), 6, "months", Decimal("14000") / Decimal("0.5") / Decimal("12")),
    ],
)
def test_time_based_monthly_accrual(amount, interval_value, interval_unit, expected):
    assert calculator.time_based_monthly_accrual(amount, interval_value, interval_unit) == expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 1, 10), date(2026, 1, 25), 0),  # same month
        (date(2026, 1, 10), date(2026, 4, 10), 3),  # exact month boundaries
        (date(2026, 1, 10), date(2026, 4, 9), 2),  # end.day < start.day drops the partial month
        (date(2026, 4, 10), date(2026, 1, 10), 0),  # reversed dates clamp to 0
    ],
)
def test_whole_months(start, end, expected):
    assert calculator.whole_months(start, end) == expected


def test_expected_monthly_usage_zero_usage_is_zero():
    assert calculator.expected_monthly_usage(0, 5) == Decimal("0")


def test_expected_monthly_usage_normal_case():
    assert calculator.expected_monthly_usage(1200, 6) == Decimal("200")


def test_expected_monthly_usage_zero_span_divides_by_one():
    assert calculator.expected_monthly_usage(300, 0) == Decimal("300")


def test_expected_monthly_usage_rejects_negative_usage():
    with pytest.raises(ValueError):
        calculator.expected_monthly_usage(-1, 3)


def test_usage_based_monthly_accrual_handles_fractional_usage():
    assert calculator.usage_based_monthly_accrual(Decimal("10"), Decimal("150.5")) == Decimal("1505.0")


@pytest.mark.parametrize(
    ("balance", "expected_reserve", "expected"),
    [
        (Decimal("100"), Decimal("0"), "healthy"),  # nothing to fund
        (Decimal("89"), Decimal("100"), "underfunded"),  # below 0.9x
        (Decimal("90"), Decimal("100"), "healthy"),  # exact 0.9x boundary is healthy
        (Decimal("100"), Decimal("100"), "healthy"),
        (Decimal("110"), Decimal("100"), "healthy"),  # exact 1.1x boundary is healthy
        (Decimal("111"), Decimal("100"), "overflowing"),  # above 1.1x
    ],
)
def test_health_status_bands(balance, expected_reserve, expected):
    assert calculator.health_status(balance, expected_reserve) == expected
