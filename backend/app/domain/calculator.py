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


def _ratio(numerator: int | None, denominator: int | None) -> Decimal | None:
    """Return ``numerator / denominator`` as a ``Decimal``, or ``None`` when either is missing."""
    if numerator is None or denominator is None:
        return None
    return Decimal(numerator) / Decimal(denominator)
