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


def test_balance_at_dates_is_inclusive_running_sum():
    events = [
        (date(2026, 1, 10), Decimal("100")),
        (date(2026, 2, 10), Decimal("-30")),
        (date(2026, 3, 10), Decimal("50")),
    ]
    as_of_dates = [date(2026, 1, 10), date(2026, 2, 9), date(2026, 3, 10)]

    # A boundary date equal to an event_date includes it (Jan 10, Mar 10); Feb 9 precedes the Feb 10 event.
    assert calculator.balance_at_dates(events, as_of_dates) == [Decimal("100"), Decimal("100"), Decimal("120")]


def test_balance_at_dates_empty_events_returns_zeros():
    as_of_dates = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]

    assert calculator.balance_at_dates([], as_of_dates) == [Decimal(0), Decimal(0), Decimal(0)]


def test_balance_at_dates_is_order_independent():
    events = [
        (date(2026, 1, 10), Decimal("100")),
        (date(2026, 2, 10), Decimal("-30")),
        (date(2026, 3, 10), Decimal("50")),
    ]
    as_of_dates = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]

    assert calculator.balance_at_dates(list(reversed(events)), as_of_dates) == calculator.balance_at_dates(
        events, as_of_dates
    )


def test_month_anchor_dates_full_window_ascending_last_days():
    anchor = date(2026, 7, 17)
    dates = calculator.month_anchor_dates(anchor, 12, date(2024, 1, 1))

    assert len(dates) == 12
    assert dates == sorted(dates)
    assert dates[-1] == anchor
    # Every earlier point is its month's last day.
    assert dates[-2] == date(2026, 6, 30)
    assert dates[0] == date(2025, 8, 31)


def test_month_anchor_dates_young_asset_returns_short_series():
    anchor = date(2026, 7, 17)
    dates = calculator.month_anchor_dates(anchor, 12, date(2026, 4, 5))

    # Apr, May, Jun, Jul -> 4 points, not padded to 12.
    assert len(dates) == 4
    assert dates[-1] == anchor


def test_month_anchor_dates_caps_at_months():
    anchor = date(2026, 7, 17)
    dates = calculator.month_anchor_dates(anchor, 6, date(2025, 4, 1))

    assert len(dates) == 6
    assert dates[-1] == anchor


def test_month_anchor_dates_no_activity_returns_single_anchor():
    anchor = date(2026, 7, 17)

    assert calculator.month_anchor_dates(anchor, 12, None) == [anchor]


def test_month_anchor_dates_rejects_non_positive_months():
    with pytest.raises(ValueError):
        calculator.month_anchor_dates(date(2026, 7, 17), 0, date(2026, 1, 1))


def test_month_anchor_dates_count_ignores_day_of_month():
    # Regression: a day-aware count (like whole_months) would drop January here.
    anchor = date(2026, 4, 10)
    earliest = date(2026, 1, 20)  # earliest.day > anchor.day

    dates = calculator.month_anchor_dates(anchor, 12, earliest)

    assert len(dates) == 4  # (4 - 1) + 1 = Jan/Feb/Mar/Apr
    assert [d.strftime("%Y-%m") for d in dates] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert dates[-1] == anchor


def test_next_due_date_none_anchor_returns_none():
    assert calculator.next_due_date(None, 1, "months", date(2026, 7, 17)) is None


def test_next_due_date_future_anchor_returns_anchor():
    anchor = date(2026, 12, 1)
    assert calculator.next_due_date(anchor, 6, "months", date(2026, 7, 17)) == anchor


def test_next_due_date_anchor_today_returns_today():
    today = date(2026, 7, 17)
    assert calculator.next_due_date(today, 1, "months", today) == today


def test_next_due_date_one_step_forward():
    # Anchor exactly one interval in the past rolls forward one step to an occurrence >= today.
    today = date(2026, 7, 17)
    anchor = date(2026, 6, 17)  # one month before today
    result = calculator.next_due_date(anchor, 1, "months", today)
    assert result == date(2026, 7, 17)
    assert result >= today


def test_next_due_date_rolls_across_many_periods_without_overshoot():
    today = date(2026, 7, 17)
    anchor = date(2020, 1, 15)  # several years in the past
    result = calculator.next_due_date(anchor, 6, "months", today)
    assert result >= today
    # The previous occurrence (one interval earlier) must be strictly before today: no overshoot.
    assert calculator._add_months(result, -6) < today


def test_next_due_date_years_unit_rolls_forward():
    today = date(2026, 7, 17)
    anchor = date(2020, 3, 1)
    one_year = calculator.next_due_date(anchor, 1, "years", today)
    assert one_year == date(2027, 3, 1)
    assert one_year >= today

    two_years = calculator.next_due_date(anchor, 2, "years", today)
    assert two_years >= today
    assert calculator._add_months(two_years, -24) < today


def test_next_due_date_clamps_month_end_anchor():
    result = calculator.next_due_date(date(2025, 1, 31), 1, "months", date(2025, 2, 15))
    assert result == date(2025, 2, 28)


def test_next_due_date_rejects_non_positive_interval():
    past_anchor = date(2020, 1, 1)  # past anchor exercises the guard regardless of ordering
    with pytest.raises(ValueError):
        calculator.next_due_date(past_anchor, 0, "months", date(2026, 7, 17))
    with pytest.raises(ValueError):
        calculator.next_due_date(past_anchor, -3, "months", date(2026, 7, 17))
