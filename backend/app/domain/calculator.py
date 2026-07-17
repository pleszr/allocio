"""Pure, asset-agnostic calculation engine for accrual, balance, and maintenance status.

Every function here is deterministic and side-effect free: it takes primitives or plain
value tuples and returns a `Decimal` or a status literal. The module imports only the
stdlib so it stays free of SQLAlchemy, FastAPI, and the persistence layer, which lets both
check-in preview and posting share one calculation basis (see `docs/vehicle-rules.md`).

The agnostic core (time-based accrual, usage-based accrual, balance) knows nothing about
vehicles. The vehicle add-on (maintenance status, reserve recommendation) is still pure; it
is simply only meaningful for assets that carry maintenance items, and its callers decide
when to invoke it.
"""

import calendar
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, TypeAlias

IntervalUnit: TypeAlias = Literal["months", "years"]
MaintenanceStatus: TypeAlias = Literal["ok", "soon", "due", "overdue"]
ReserveGuidance: TypeAlias = Literal["low", "reasonable", "high"]
HealthStatus: TypeAlias = Literal["underfunded", "healthy", "overflowing"]

DAYS_PER_YEAR: Decimal = Decimal(365)
INTERVAL_UNITS: frozenset[str] = frozenset({"months", "years"})

_MONTHS_PER_YEAR: Decimal = Decimal(12)
_CENT: Decimal = Decimal("0.01")
_OVERDUE_RATIO: Decimal = Decimal("1.05")
_DUE_RATIO: Decimal = Decimal("0.90")
_SOON_RATIO: Decimal = Decimal("0.80")
_GUIDANCE_LOW: Decimal = Decimal("0.9")
_GUIDANCE_HIGH: Decimal = Decimal("1.1")


def interval_years(interval_value: int, interval_unit: IntervalUnit) -> Decimal:
    """Convert a cost interval to whole/fractional years.

    Args:
        interval_value: Positive number of units in one interval.
        interval_unit: Either ``"months"`` or ``"years"``.

    Returns:
        The interval length expressed in years as an exact ``Decimal``.

    Raises:
        ValueError: If ``interval_value`` is not positive or ``interval_unit`` is unknown.
    """
    if interval_value <= 0:
        raise ValueError("interval_value must be positive.")
    if interval_unit == "years":
        return Decimal(interval_value)
    if interval_unit == "months":
        return Decimal(interval_value) / _MONTHS_PER_YEAR
    raise ValueError(f"Unknown interval_unit: {interval_unit!r}.")


def next_due_date(
    anchor: date | None, interval_value: int, interval_unit: IntervalUnit, today: date
) -> date | None:
    """Compute the next occurrence of a time-based cost on or after today.

    Rolls the interval forward from a known anchor occurrence to the first occurrence that is on
    or after ``today``. This is informational only; it never influences accrual.

    Args:
        anchor: A known occurrence date, or ``None`` when no anchor is set.
        interval_value: Positive number of units in one interval.
        interval_unit: Either ``"months"`` or ``"years"``.
        today: The reference date the occurrence is rolled forward past.

    Returns:
        ``None`` when ``anchor`` is ``None``; the anchor itself when it is on or after ``today``;
        otherwise the first rolled-forward occurrence on or after ``today``.

    Raises:
        ValueError: If ``interval_value`` is not positive (validated first, before any short-circuit
            or loop, so a zero interval can never spin the non-advancing roll-forward loop).
    """
    if interval_value <= 0:
        raise ValueError("interval_value must be positive.")
    if anchor is None:
        return None
    if anchor >= today:
        return anchor
    interval_months = interval_value if interval_unit == "months" else interval_value * 12
    step = 0
    while _add_months(anchor, step * interval_months) < today:
        step += 1
    return _add_months(anchor, step * interval_months)


def reference_amount(
    baseline: Decimal, linked_expenses: Sequence[tuple[date, Decimal]], period_start: date
) -> Decimal:
    """Resolve the amount a time-based cost accrues from for a period.

    The latest modeled expense whose ``event_date`` is on or before ``period_start`` supersedes
    the baseline (latest-cost rollover). With no qualifying expense the baseline stands.

    Args:
        baseline: The cost row's stored ``amount``.
        linked_expenses: ``(event_date, amount)`` pairs of modeled expenses linked to the cost.
        period_start: Start date of the period being accrued.

    Returns:
        The reference amount to annualize for this period.
    """
    qualifying = [(event_date, amount) for event_date, amount in linked_expenses if event_date <= period_start]
    if not qualifying:
        return baseline
    return max(qualifying, key=lambda pair: pair[0])[1]


def time_based_period_accrual(
    reference_amount: Decimal, interval_value: int, interval_unit: IntervalUnit, elapsed_days: int
) -> Decimal:
    """Accrue a time-based cost continuously across an elapsed period.

    Annualizes the reference amount over its interval, then spreads it evenly across days.
    The result is unrounded so no precision is lost before posting; call `quantize_currency`
    at the boundary for display or event amounts.

    Args:
        reference_amount: Amount to annualize (see `reference_amount`).
        interval_value: Positive number of units in one interval.
        interval_unit: Either ``"months"`` or ``"years"``.
        elapsed_days: Whole calendar days in the period; must not be negative.

    Returns:
        The unrounded accrual for the period.

    Raises:
        ValueError: If ``elapsed_days`` is negative (interval errors propagate from `interval_years`).
    """
    if elapsed_days < 0:
        raise ValueError("elapsed_days must not be negative.")
    annualized = reference_amount / interval_years(interval_value, interval_unit)
    daily_rate = annualized / DAYS_PER_YEAR
    return daily_rate * Decimal(elapsed_days)


def usage_based_period_accrual(usage_amount: int, amount_per_unit: Decimal) -> Decimal:
    """Accrue the usage-based reserve for a period.

    Args:
        usage_amount: Usage counted this period (e.g. kilometers for a vehicle); not negative.
        amount_per_unit: Reserve accrued per unit of usage.

    Returns:
        The reserve accrual for the period.

    Raises:
        ValueError: If ``usage_amount`` is negative.
    """
    if usage_amount < 0:
        raise ValueError("usage_amount must not be negative.")
    return Decimal(usage_amount) * amount_per_unit


def bucket_balance(allocation_amounts: Iterable[Decimal], expense_amounts: Iterable[Decimal]) -> Decimal:
    """Reconstruct a bucket balance from posted events.

    Args:
        allocation_amounts: Amounts of posted allocation (inflow) events.
        expense_amounts: Amounts of posted expense (outflow) events.

    Returns:
        ``sum(allocations) - sum(expenses)``; ``Decimal(0)`` for an empty history.
    """
    total_in = sum(allocation_amounts, Decimal(0))
    total_out = sum(expense_amounts, Decimal(0))
    return total_in - total_out


def month_anchor_dates(anchor: date, months: int, earliest_activity: date | None) -> list[date]:
    """Build the ordered as-of dates a monthly balance series is evaluated at.

    One as-of date per calendar month, oldest first. For every month except ``anchor``'s the as-of
    date is that month's last day; for the current month it is ``anchor`` itself, so the newest
    point is a live, partial-month snapshot. Equivalently ``as_of = min(last_day_of_month, anchor)``.

    The window shrinks for young assets: the number of points is counted with day-INSENSITIVE
    calendar-month arithmetic, ``(anchor.year - earliest.year) * 12 + (anchor.month - earliest.month)
    + 1``, capped at ``months``. This deliberately ignores day-of-month (unlike `whole_months`, which
    subtracts a month when ``end.day < start.day``), so an ``earliest`` late in its month is never
    dropped from the series.

    Args:
        anchor: The newest month's as-of date (typically today); also the series' final point.
        months: Maximum number of monthly points; must be at least one.
        earliest_activity: Date of the earliest event, or ``None`` when there is no activity.

    Returns:
        Ordered (oldest → newest) as-of dates. ``[anchor]`` when ``earliest_activity`` is ``None``.

    Raises:
        ValueError: If ``months`` is less than one.
    """
    if months < 1:
        raise ValueError("months must be at least 1.")
    if earliest_activity is None:
        return [anchor]
    span = (anchor.year - earliest_activity.year) * 12 + (anchor.month - earliest_activity.month) + 1
    point_count = min(months, span)
    oldest_index = point_count - 1
    return [_month_as_of(anchor, months_back) for months_back in range(oldest_index, -1, -1)]


def balance_at_dates(events: Sequence[tuple[date, Decimal]], as_of_dates: Sequence[date]) -> list[Decimal]:
    """Compute the cumulative signed balance at each as-of date.

    Args:
        events: Signed net ``(event_date, amount)`` pairs (allocations positive, expenses negative).
            Input order does not matter; the balance is a sum, not an order-dependent running total.
        as_of_dates: The dates to evaluate the cumulative balance at.

    Returns:
        One balance per date in ``as_of_dates``: the sum of every event with ``event_date <= d``
        (inclusive). ``Decimal(0)`` for a date preceding all events, matching `bucket_balance`.
    """
    return [
        sum((amount for event_date, amount in events if event_date <= as_of), Decimal(0)) for as_of in as_of_dates
    ]


def quantize_currency(value: Decimal) -> Decimal:
    """Round a raw accrual to a 2-decimal currency amount using half-up rounding.

    The engine returns unrounded values; callers apply this only when building preview lines
    or posted event amounts.

    Args:
        value: An unrounded monetary value.

    Returns:
        ``value`` rounded to two decimal places, half-up.
    """
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def maintenance_progress(
    km_since_service: int | None,
    interval_km: int | None,
    months_since_service: int | None,
    interval_months: int | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Compute distance and time progress ratios for a maintenance item.

    A ratio is ``None`` when either its usage-since-service or its interval is missing. Callers
    pass a tire-aware ``km_since_service`` for tire-specific rows; this function does not resolve
    tire periods.

    Args:
        km_since_service: Distance since last service, or ``None``.
        interval_km: Service distance interval, or ``None``.
        months_since_service: Whole months since last service, or ``None``.
        interval_months: Service month interval, or ``None``.

    Returns:
        ``(km_progress, month_progress)`` where each is a ratio or ``None``.
    """
    km_progress = _ratio(km_since_service, interval_km)
    month_progress = _ratio(months_since_service, interval_months)
    return km_progress, month_progress


def maintenance_status(km_progress: Decimal | None, month_progress: Decimal | None) -> MaintenanceStatus:
    """Derive a maintenance status from present progress ratios (earlier threshold wins).

    Args:
        km_progress: Distance progress ratio, or ``None`` if not applicable.
        month_progress: Time progress ratio, or ``None`` if not applicable.

    Returns:
        ``"overdue"``, ``"due"``, ``"soon"``, or ``"ok"``. With both ratios ``None`` (e.g. the
        ``other`` catch-all), returns ``"ok"``.
    """
    ratios = [ratio for ratio in (km_progress, month_progress) if ratio is not None]
    if not ratios:
        return "ok"
    peak = max(ratios)
    if peak >= _OVERDUE_RATIO:
        return "overdue"
    if peak >= _DUE_RATIO:
        return "due"
    if peak >= _SOON_RATIO:
        return "soon"
    return "ok"


def reserve_recommendation(items: Sequence[tuple[Decimal, int]]) -> Decimal | None:
    """Sum per-unit reserve contributions from contributing maintenance items.

    Args:
        items: ``(estimated_cost, interval_km)`` pairs. Callers pre-filter to active items that
            have both an estimated cost and a distance interval and are tire-relevant.

    Returns:
        The recommended per-unit reserve rate, or ``None`` when ``items`` is empty.
    """
    if not items:
        return None
    return sum((estimated_cost / Decimal(interval_km) for estimated_cost, interval_km in items), Decimal(0))


def reserve_guidance(configured_rate: Decimal, recommended_rate: Decimal | None) -> ReserveGuidance | None:
    """Band a configured reserve rate against the recommendation.

    Args:
        configured_rate: The user's per-unit reserve rate.
        recommended_rate: The recommended rate, or ``None`` when nothing contributes.

    Returns:
        ``"low"`` below ``0.9x``, ``"high"`` above ``1.1x``, else ``"reasonable"``; ``None`` when
        ``recommended_rate`` is ``None``.
    """
    if recommended_rate is None:
        return None
    if configured_rate < _GUIDANCE_LOW * recommended_rate:
        return "low"
    if configured_rate > _GUIDANCE_HIGH * recommended_rate:
        return "high"
    return "reasonable"


def time_based_monthly_accrual(
    reference_amount: Decimal, interval_value: int, interval_unit: IntervalUnit
) -> Decimal:
    """Spread a time-based cost's reference amount into an even monthly accrual.

    The monthly form of the same annualize-then-spread math the check-in path uses via
    `time_based_period_accrual`: annualize over the interval, then divide by twelve. The result
    is unrounded so the service applies `quantize_currency` only at the boundary.

    Args:
        reference_amount: Amount to annualize (see `reference_amount`).
        interval_value: Positive number of units in one interval.
        interval_unit: Either ``"months"`` or ``"years"``.

    Returns:
        The unrounded monthly accrual (interval errors propagate from `interval_years`).
    """
    return reference_amount / interval_years(interval_value, interval_unit) / _MONTHS_PER_YEAR


def whole_months(start: date, end: date) -> int:
    """Count whole calendar months between two dates, never negative.

    A partial trailing month (when ``end.day`` precedes ``start.day``) does not count. Reversed
    dates clamp to ``0``. Used to size the trailing window for average usage.

    Args:
        start: Earlier date of the span.
        end: Later date of the span.

    Returns:
        Whole months from ``start`` to ``end``, clamped to ``0``.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def expected_monthly_usage(total_usage: int, months_span: int) -> Decimal:
    """Average usage per month over a trailing window.

    Args:
        total_usage: Total usage counted across the window; must not be negative.
        months_span: Whole months in the window; a span of ``0`` divides by one month.

    Returns:
        ``total_usage`` spread evenly per month, or ``Decimal(0)`` when there is no usage.

    Raises:
        ValueError: If ``total_usage`` is negative.
    """
    if total_usage < 0:
        raise ValueError("total_usage must not be negative.")
    if total_usage == 0:
        return Decimal(0)
    return Decimal(total_usage) / Decimal(max(months_span, 1))


def usage_based_monthly_accrual(amount_per_unit: Decimal, monthly_usage: Decimal) -> Decimal:
    """Accrue the usage-based reserve for one month of average usage.

    Separate from the int-based `usage_based_period_accrual` because `monthly_usage` is a
    fractional trailing average.

    Args:
        amount_per_unit: Reserve accrued per unit of usage.
        monthly_usage: Average usage per month (may be fractional).

    Returns:
        The unrounded monthly reserve accrual.
    """
    return amount_per_unit * monthly_usage


def health_status(balance: Decimal, expected_reserve: Decimal) -> HealthStatus:
    """Band a bucket balance against its expected reserve using the guidance ratios.

    Reuses the ``0.9``/``1.1`` bands already blessed for `reserve_guidance`, so no new magic
    numbers enter the engine. See `docs/vehicle-rules.md` for the v1 definition of
    ``expected_reserve`` (one recommended monthly allocation) and its documented limitation.

    Args:
        balance: The bucket's event-derived balance.
        expected_reserve: The target reserve to compare against; ``<= 0`` means nothing to fund.

    Returns:
        ``"underfunded"`` below ``0.9x``, ``"overflowing"`` above ``1.1x``, else ``"healthy"``;
        ``"healthy"`` whenever ``expected_reserve`` is non-positive.
    """
    if expected_reserve <= 0:
        return "healthy"
    if balance < _GUIDANCE_LOW * expected_reserve:
        return "underfunded"
    if balance > _GUIDANCE_HIGH * expected_reserve:
        return "overflowing"
    return "healthy"


def _month_as_of(anchor: date, months_back: int) -> date:
    """Return the as-of date of the month ``months_back`` before ``anchor``'s month.

    The anchor's own month (``months_back == 0``) resolves to ``anchor``; any earlier month resolves
    to its last calendar day.
    """
    if months_back == 0:
        return anchor
    month_index = anchor.year * 12 + (anchor.month - 1) - months_back
    year, month = divmod(month_index, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, last_day)


def _add_months(anchor: date, months: int) -> date:
    """Return ``anchor`` shifted by ``months``, clamping the day to the target month's last day.

    Mirrors `_month_as_of`'s ``calendar.monthrange`` clamp so a month-end anchor such as
    ``2025-01-31`` plus one month resolves to ``2025-02-28`` rather than overflowing.
    """
    month_index = anchor.year * 12 + (anchor.month - 1) + months
    year, month = divmod(month_index, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(anchor.day, last_day))


def _ratio(numerator: int | None, denominator: int | None) -> Decimal | None:
    """Return ``numerator / denominator`` as a ``Decimal``, or ``None`` when either is missing."""
    if numerator is None or denominator is None:
        return None
    return Decimal(numerator) / Decimal(denominator)
