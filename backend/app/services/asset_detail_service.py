"""Asset detail read use case: compose one asset's dashboard payload from reused figures and events.

Read-only. Reuses `WorkspaceService` for balance/allocation/health, `CostService` for current usage
and maintenance status, and the check-in/expense repositories for the recent-activity feed. It never
commits or flushes; an unknown or unowned asset raises `NotFoundError`.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain import calculator
from app.repository import check_in_repository, expense_repository
from app.services.cost_service import CostService, MaintenanceItemView
from app.services.workspace_service import WorkspaceService

_ACTIVITY_LIMIT = 20


@dataclass(frozen=True)
class ActivityItem:
    """One recent bucket movement for the dashboard activity feed; `amount` is signed."""

    date: date
    kind: str
    label: str
    amount: Decimal


@dataclass(frozen=True)
class AssetDetail:
    """The composed detail payload for one asset's dashboard screen."""

    asset_id: uuid.UUID
    type: str
    name: str
    status: str
    currency: str
    balance: Decimal
    recommended_monthly_allocation: Decimal
    daily_accrual: Decimal
    health: str
    current_usage: int | None
    usage_since_last_check_in: int | None
    last_check_in_date: date | None
    maintenance_items: list[MaintenanceItemView]
    recent_activity: list[ActivityItem]


class AssetDetailService:
    """Assembles the read-only asset detail payload over a request-scoped session; never mutates."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspace = WorkspaceService(session)
        self._costs = CostService(session)

    def get_detail(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> AssetDetail:
        """Compose one owned asset's detail payload; raises `NotFoundError` when unknown or unowned."""
        summary = self._workspace.summarize_asset(user_id, asset_id)
        asset = check_in_repository.get_owned_asset(self._session, user_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        latest = check_in_repository.get_latest_posted_check_in(self._session, asset_id)
        return AssetDetail(
            asset_id=asset.id,
            type=summary.type,
            name=summary.name,
            status=summary.status,
            currency=summary.currency,
            balance=summary.balance,
            recommended_monthly_allocation=summary.recommended_monthly_allocation,
            daily_accrual=calculator.quantize_currency(summary.recommended_monthly_allocation * 12 / 365),
            health=summary.health,
            current_usage=self._costs.current_asset_usage(user_id, asset_id),
            usage_since_last_check_in=latest.usage_amount if latest is not None else None,
            last_check_in_date=latest.period_end if latest is not None else None,
            maintenance_items=self._costs.list_maintenance_item_views(user_id, asset_id),
            recent_activity=self._recent_activity(asset_id),
        )

    def _recent_activity(self, asset_id: uuid.UUID) -> list[ActivityItem]:
        """Merge posted allocations (inflow) and expenses (outflow) into a newest-first, capped feed."""
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return []
        items = self._allocation_items(bucket.id) + self._expense_items(bucket.id)
        items.sort(key=lambda item: item.date, reverse=True)
        return items[:_ACTIVITY_LIMIT]

    def _allocation_items(self, bucket_id: uuid.UUID) -> list[ActivityItem]:
        """Build positive-amount activity items from posted allocation events."""
        events = check_in_repository.list_allocation_events_for_bucket(self._session, bucket_id)
        return [
            ActivityItem(
                date=event.event_date,
                kind="allocation",
                label=self._allocation_label(event),
                amount=event.amount,
            )
            for event in events
        ]

    def _expense_items(self, bucket_id: uuid.UUID) -> list[ActivityItem]:
        """Build negative-amount activity items from posted expense events."""
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket_id)
        return [
            ActivityItem(
                date=expense.event_date,
                kind="expense",
                label=self._expense_label(expense),
                amount=-expense.amount,
            )
            for expense in expenses
        ]

    def _allocation_label(self, event: object) -> str:
        """Prefer the allocation's stored metadata label, else fall back to its source table."""
        metadata = getattr(event, "metadata_json", None)
        if isinstance(metadata, dict):
            label = metadata.get("label")
            if isinstance(label, str) and label:
                return label
        source_type = getattr(event, "source_type", None)
        return "Allocation" if not source_type else str(source_type).replace("_", " ").capitalize()

    def _expense_label(self, expense: object) -> str:
        """Prefer the expense comment, else fall back to a source-derived label."""
        comment = getattr(expense, "comment", None)
        if isinstance(comment, str) and comment:
            return comment
        source_type = getattr(expense, "source_type", None)
        return "Expense" if not source_type else str(source_type).replace("_", " ").capitalize()
