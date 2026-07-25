"""Workspace overview use case: derive every owned asset's balance and monthly allocation in one read.

Read-only. The service reuses the pure `app.domain.calculator` helpers for all money math and the
existing single-asset repository functions per asset (N+1 by design at MVP scale — see the issue
spec). It never commits or flushes; an empty workspace is a valid, zeroed result, not a 404.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain import calculator
from app.domain.asset import Asset, Bucket
from app.repository import asset_repository, check_in_repository, cost_repository, expense_repository


@dataclass(frozen=True)
class AssetSummary:
    """One asset's derived figures for the workspace overview."""

    asset_id: uuid.UUID
    type: str
    name: str
    status: str
    currency: str
    balance: Decimal
    recommended_monthly_allocation: Decimal


@dataclass(frozen=True)
class WorkspaceTotals:
    """Workspace-wide aggregates the Home header renders."""

    total_balance: Decimal
    total_recommended_monthly_allocation: Decimal


@dataclass(frozen=True)
class WorkspaceOverview:
    """Every owned asset summary plus the workspace totals for one `GET /api/assets` call."""

    assets: list[AssetSummary]
    totals: WorkspaceTotals


class WorkspaceService:
    """Assembles the read-only workspace overview over a request-scoped session; never mutates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_workspace(self, user_id: uuid.UUID) -> WorkspaceOverview:
        """Summarize every owned asset and aggregate the workspace totals. Writes nothing."""
        assets = asset_repository.list_owned_assets(self._session, user_id)
        summaries = [self._summarize(asset) for asset in assets]
        return WorkspaceOverview(assets=summaries, totals=self._totals(summaries))

    def summarize_asset(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> AssetSummary:
        """Summarize one owned asset, reusing the same balance/allocation math as the overview.

        Raises `NotFoundError` for an unknown or unowned asset so single-asset reads never leak.
        """
        asset = check_in_repository.get_owned_asset(self._session, user_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return self._summarize(asset)

    def monthly_usage_rate(self, asset_id: uuid.UUID) -> Decimal:
        """Average usage per month across all posted check-ins, or zero without enough data.

        Shared by `_usage_based_monthly`'s accrual math and by callers (e.g. the Costs screen's
        "Est. per month" usage-based estimate) that need the raw trailing-average figure itself.
        """
        total_usage, first_start, last_end = check_in_repository.get_posted_usage_totals(self._session, asset_id)
        months = 0 if first_start is None else calculator.whole_months(first_start, last_end)
        return calculator.expected_monthly_usage(total_usage, months)

    def _summarize(self, asset: Asset) -> AssetSummary:
        """Compose one asset's balance and recommended monthly allocation."""
        bucket = expense_repository.get_bucket_for_asset(self._session, asset.id)
        if bucket is None:
            return self._summary_without_bucket(asset)
        balance = self._balance(bucket)
        monthly = self._recommended_monthly_allocation(asset, bucket)
        return AssetSummary(
            asset_id=asset.id,
            type=asset.type,
            name=asset.name,
            status=asset.status,
            currency=bucket.currency,
            balance=balance,
            recommended_monthly_allocation=monthly,
        )

    def _summary_without_bucket(self, asset: Asset) -> AssetSummary:
        """Fall back to zeroed figures for an asset that somehow has no bucket (should not happen)."""
        return AssetSummary(
            asset_id=asset.id,
            type=asset.type,
            name=asset.name,
            status=asset.status,
            currency="",
            balance=Decimal(0),
            recommended_monthly_allocation=Decimal(0),
        )

    def _balance(self, bucket: Bucket) -> Decimal:
        """Reconstruct the bucket balance from its posted allocation and expense events."""
        allocations = check_in_repository.list_posted_allocation_amounts(self._session, bucket.id)
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        return max(
            calculator.bucket_balance(allocations, [expense.bucket_amount for expense in expenses]),
            Decimal(0),
        )

    def _recommended_monthly_allocation(self, asset: Asset, bucket: Bucket) -> Decimal:
        """Sum the active time-based and usage-based monthly accruals, quantized to currency.

        This rounds the combined raw total once (`quantize(Σ)`), which intentionally differs from
        check-in accrual, where each allocation line is quantized before summing (`Σ quantize` — see
        `check_in_calc.compute_check_in`). Both are pre-existing, internally-correct patterns.
        """
        time_based = self._time_based_monthly(asset, bucket)
        usage_based = self._usage_based_monthly(asset)
        return calculator.quantize_currency(time_based + usage_based + asset.manual_extra_monthly)

    def _time_based_monthly(self, asset: Asset, bucket: Bucket) -> Decimal:
        """Accrue the monthly total across active time-based costs, applying latest-cost rollover."""
        posted_expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        total = Decimal(0)
        for cost in cost_repository.list_time_based_costs(self._session, asset.id):
            if not cost.is_active:
                continue
            linked = [
                (expense.event_date, expense.amount)
                for expense in posted_expenses
                if expense.source_type == "time_based_cost" and expense.source_id == cost.id
            ]
            reference = calculator.reference_amount(cost.amount, linked, date.today())
            total += calculator.time_based_monthly_accrual(reference, cost.interval_value, cost.interval_unit)
        return total

    def _usage_based_monthly(self, asset: Asset) -> Decimal:
        """Accrue every active usage-based component for a trailing-average month, or zero without any."""
        active_rows = cost_repository.list_active_usage_based_costs(self._session, asset.id)
        if not active_rows:
            return Decimal(0)
        monthly_usage = self.monthly_usage_rate(asset.id)
        return sum(
            (calculator.usage_based_monthly_accrual(row.amount_per_unit, monthly_usage) for row in active_rows),
            Decimal(0),
        )

    def _totals(self, summaries: list[AssetSummary]) -> WorkspaceTotals:
        """Sum balances and monthly allocations across all summaries.

        MVP assumes all buckets share one currency (HUF today), so totals are a plain sum.
        """
        return WorkspaceTotals(
            total_balance=sum((summary.balance for summary in summaries), Decimal(0)),
            total_recommended_monthly_allocation=sum(
                (summary.recommended_monthly_allocation for summary in summaries), Decimal(0)
            ),
        )
