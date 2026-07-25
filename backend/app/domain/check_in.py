"""Check-in and posted-event ORM models: check-ins plus immutable allocation and expense events."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CheckIn(Base):
    """Monthly review record for one asset; posting it creates the period's auditable events."""

    __tablename__ = "check_ins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_tire_type: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'draft'"))


class AllocationEvent(Base):
    """Immutable posted inflow moving value into the bucket."""

    __tablename__ = "allocation_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buckets.id"), nullable=False, index=True
    )
    check_in_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("check_ins.id"), nullable=False, index=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ExpenseEvent(Base):
    """Posted expense split between bucket-covered and out-of-pocket funding."""

    __tablename__ = "expense_events"
    __table_args__ = (
        CheckConstraint("paid_out_of_pocket >= 0", name="ck_expense_paid_out_of_pocket_nonnegative"),
        CheckConstraint("paid_out_of_pocket <= amount", name="ck_expense_paid_out_of_pocket_lte_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buckets.id"), nullable=False, index=True
    )
    check_in_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("check_ins.id"), nullable=True, index=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    usage_counter_at_event: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_out_of_pocket: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0"), default=Decimal(0)
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    @property
    def bucket_amount(self) -> Decimal:
        """Return the portion of the full expense funded by the virtual bucket."""
        return self.amount - self.paid_out_of_pocket

    def resolved_label(self, source_label: str | None) -> str:
        """Compose a display label from a resolved source name plus this event's own comment.

        Combines both when present (e.g. "Tires — replaced front pair"), falls back to whichever
        one exists, then to a humanized `source_type`, then to a generic "Expense".
        """
        if source_label and self.comment:
            return f"{source_label} — {self.comment}"
        if source_label:
            return source_label
        if self.comment:
            return self.comment
        if self.source_type:
            return self.source_type.replace("_", " ").capitalize()
        return "Expense"
