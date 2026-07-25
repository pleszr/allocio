"""Pure, shared check-in computation: assembles preview/posting figures from calculator primitives.

Both check-in preview and posting call `compute_check_in` with the same mapped inputs, so posted
amounts always equal the immediately preceding preview for the same stored state (see
`docs/vehicle-rules.md`, "Check-In Posting"). The module imports only the stdlib and the pure
`app.domain.calculator`, staying free of SQLAlchemy and FastAPI: the service maps DB rows into the
plain value objects below before calling in.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.calculator import (
    IntervalUnit,
    bucket_balance,
    quantize_currency,
    reference_amount,
    time_based_period_accrual,
    usage_based_period_accrual,
)


@dataclass(frozen=True)
class TimeBasedCostInput:
    """An active time-based cost row mapped to the primitives its accrual needs."""

    source_id: uuid.UUID
    label: str
    baseline_amount: Decimal
    interval_value: int
    interval_unit: IntervalUnit
    linked_expenses: Sequence[tuple[date, Decimal]]


@dataclass(frozen=True)
class UsageBasedCostInput:
    """One active usage-based cost component mapped to its per-unit rate."""

    source_id: uuid.UUID
    label: str
    amount_per_unit: Decimal


@dataclass(frozen=True)
class ExpenseDraftInput:
    """One expense submitted with the check-in, its `event_date` already resolved."""

    kind: str
    amount: Decimal
    event_date: date
    comment: str | None
    source_type: str | None
    source_id: uuid.UUID | None
    usage_counter_at_event: int | None
    paid_out_of_pocket_override: Decimal | None


@dataclass(frozen=True)
class AllocationLine:
    """One computed allocation (inflow) line: a time-based cost or a usage-based cost component."""

    source_type: str
    source_id: uuid.UUID | None
    label: str
    amount: Decimal


@dataclass(frozen=True)
class ExpenseLine:
    """One computed expense split into its bucket-covered and out-of-pocket portions."""

    kind: str
    amount: Decimal
    bucket_amount: Decimal
    paid_out_of_pocket: Decimal
    event_date: date
    comment: str | None
    source_type: str | None
    source_id: uuid.UUID | None
    usage_counter_at_event: int | None


@dataclass(frozen=True)
class CheckInComputation:
    """The full financial result of a check-in period, shared by preview and posting."""

    elapsed_days: int
    usage_amount: int
    allocation_lines: Sequence[AllocationLine]
    expense_lines: Sequence[ExpenseLine]
    balance_before: Decimal
    total_allocation: Decimal
    total_expense: Decimal
    total_bucket_expense: Decimal
    paid_out_of_pocket: Decimal
    net_bucket_change: Decimal
    balance_after: Decimal


def compute_check_in(
    *,
    period_start: date,
    period_end: date,
    usage_start: int,
    usage_end: int,
    time_based_costs: Sequence[TimeBasedCostInput],
    usage_based_costs: Sequence[UsageBasedCostInput],
    manual_extra_monthly: Decimal,
    expense_drafts: Sequence[ExpenseDraftInput],
    prior_allocation_amounts: Sequence[Decimal],
    prior_expense_amounts: Sequence[Decimal],
) -> CheckInComputation:
    """Compute a period's allocation lines, expense lines, and balance totals from stored state.

    Uses `app.domain.calculator` for every amount so preview and posting share one basis. All figures
    are deterministic for the same inputs; the function performs no I/O and mutates nothing.

    Each usage-based component emits its own allocation line, quantized independently and then summed
    (``Σ quantize``), mirroring how each time-based line is rounded before summing. With exactly one
    active usage component ``Σ quantize`` collapses to the old ``quantize(usage × rate)``, so the
    single-row path reconciles byte-for-byte with prior behavior. This per-line rounding intentionally
    differs from the workspace recommended-monthly figure, which rounds the combined total once
    (``quantize(Σ)`` — see `workspace_service._recommended_monthly_allocation`); both are pre-existing,
    internally-correct patterns.

    Args:
        period_start: Derived start of the period (previous period end, or first-check-in start).
        period_end: Requested end of the period; must be later than ``period_start``.
        usage_start: Derived usage counter at period start.
        usage_end: Requested usage counter at period end; must be ``>= usage_start``.
        time_based_costs: Active time-based cost rows to accrue.
        usage_based_costs: Active usage-based cost components to accrue; empty when the asset has none.
        manual_extra_monthly: Configured flat monthly buffer, prorated across the elapsed period.
        expense_drafts: Expenses submitted for the period, each with a resolved ``event_date``. Each
            draft's ``paid_out_of_pocket_override`` may raise its ``paid_out_of_pocket`` above the
            derived bucket-shortfall floor (never below it); omit or ``None`` to keep the fully-derived
            split.
        prior_allocation_amounts: Amounts of already-posted allocation events (for the opening balance).
        prior_expense_amounts: Bucket-covered amounts of already-posted expenses (for the opening balance).

    Returns:
        The assembled `CheckInComputation`.
    """
    elapsed_days = (period_end - period_start).days
    usage_amount = usage_end - usage_start

    allocation_lines = _time_based_lines(time_based_costs, period_start, elapsed_days)
    allocation_lines.extend(_usage_based_lines(usage_based_costs, usage_amount))
    manual_extra_line = _manual_extra_line(manual_extra_monthly, elapsed_days)
    if manual_extra_line is not None:
        allocation_lines.append(manual_extra_line)

    total_allocation = sum((line.amount for line in allocation_lines), Decimal(0))
    balance_before = max(bucket_balance(prior_allocation_amounts, prior_expense_amounts), Decimal(0))
    available = max(balance_before + total_allocation, Decimal(0))
    expense_lines = _expense_lines(expense_drafts, available)
    total_expense = sum((line.amount for line in expense_lines), Decimal(0))
    total_bucket_expense = sum((line.bucket_amount for line in expense_lines), Decimal(0))
    paid_out_of_pocket = sum((line.paid_out_of_pocket for line in expense_lines), Decimal(0))
    net_bucket_change = total_allocation - total_bucket_expense
    balance_after = max(balance_before + net_bucket_change, Decimal(0))

    return CheckInComputation(
        elapsed_days=elapsed_days,
        usage_amount=usage_amount,
        allocation_lines=allocation_lines,
        expense_lines=expense_lines,
        balance_before=balance_before,
        total_allocation=total_allocation,
        total_expense=total_expense,
        total_bucket_expense=total_bucket_expense,
        paid_out_of_pocket=paid_out_of_pocket,
        net_bucket_change=net_bucket_change,
        balance_after=balance_after,
    )


def _time_based_lines(
    costs: Sequence[TimeBasedCostInput], period_start: date, elapsed_days: int
) -> list[AllocationLine]:
    """Build one rounded allocation line per active time-based cost, applying the reference-amount rollover."""
    lines: list[AllocationLine] = []
    for cost in costs:
        reference = reference_amount(cost.baseline_amount, cost.linked_expenses, period_start)
        accrual = time_based_period_accrual(reference, cost.interval_value, cost.interval_unit, elapsed_days)
        lines.append(
            AllocationLine(
                source_type="time_based_cost",
                source_id=cost.source_id,
                label=cost.label,
                amount=quantize_currency(accrual),
            )
        )
    return lines


def _usage_based_lines(costs: Sequence[UsageBasedCostInput], usage_amount: int) -> list[AllocationLine]:
    """Build one independently-rounded allocation line per active usage-based component (`Σ quantize`)."""
    lines: list[AllocationLine] = []
    for cost in costs:
        accrual = usage_based_period_accrual(usage_amount, cost.amount_per_unit)
        lines.append(
            AllocationLine(
                source_type="usage_based_cost",
                source_id=cost.source_id,
                label=cost.label,
                amount=quantize_currency(accrual),
            )
        )
    return lines


def _manual_extra_line(manual_extra_monthly: Decimal, elapsed_days: int) -> AllocationLine | None:
    """Prorate the configured monthly buffer over the period and emit one auditable line."""
    if manual_extra_monthly <= 0 or elapsed_days <= 0:
        return None
    annualized_amount = manual_extra_monthly * Decimal(12)
    amount = quantize_currency(time_based_period_accrual(annualized_amount, 1, "years", elapsed_days))
    return AllocationLine(source_type="manual_extra", source_id=None, label="Manual extra", amount=amount)


def _expense_lines(drafts: Sequence[ExpenseDraftInput], available: Decimal) -> list[ExpenseLine]:
    """Split drafts in submitted order, consuming the available bucket amount once.

    An override can only raise ``paid_out_of_pocket`` above the natural bucket-shortfall split, never
    lower it — see `resolve_paid_out_of_pocket`.
    """
    remaining = available
    lines: list[ExpenseLine] = []
    for draft in drafts:
        natural_bucket_amount = min(draft.amount, remaining)
        natural_paid_out_of_pocket = draft.amount - natural_bucket_amount
        paid_out_of_pocket = resolve_paid_out_of_pocket(
            draft.amount, natural_paid_out_of_pocket, draft.paid_out_of_pocket_override
        )
        bucket_amount = draft.amount - paid_out_of_pocket
        lines.append(
            ExpenseLine(
                kind=draft.kind,
                amount=draft.amount,
                bucket_amount=bucket_amount,
                paid_out_of_pocket=paid_out_of_pocket,
                event_date=draft.event_date,
                comment=draft.comment,
                source_type=draft.source_type,
                source_id=draft.source_id,
                usage_counter_at_event=draft.usage_counter_at_event,
            )
        )
        remaining -= bucket_amount
    return lines


def resolve_paid_out_of_pocket(amount: Decimal, natural: Decimal, override: Decimal | None) -> Decimal:
    """Clamp a caller-supplied override into `[natural, amount]`; `None` keeps the fully-derived split.

    Shared by check-in computation and standalone expense logging so both paths apply the same
    non-negative bucket invariant (see `docs/vehicle-rules.md`).
    """
    if override is None:
        return natural
    return max(natural, min(override, amount))
