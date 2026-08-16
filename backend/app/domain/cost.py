"""Cost aggregate ORM models: time-based, usage-based, and maintenance cost rows."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TimeBasedCost(Base):
    """Recurring cost driven by elapsed time; active rows drive future calculations."""

    __tablename__ = "time_based_costs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    technical_key: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_unit: Mapped[str] = mapped_column(String, nullable=False)
    first_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class UsageBasedCost(Base):
    """One usage-based cost component of an asset; an asset may hold several active rows, each accruing its `amount_per_unit` per unit of usage."""

    __tablename__ = "usage_based_costs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    technical_key: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    usage_unit: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'km'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class MaintenanceItem(Base):
    """Tracked maintenance/replacement item; needs a km or month interval unless it is the `other` catch-all."""

    __tablename__ = "maintenance_items"
    __table_args__ = (
        CheckConstraint(
            "interval_km IS NOT NULL OR interval_months IS NOT NULL OR technical_key = 'other'",
            name="ck_maintenance_items_interval_present",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    technical_key: Mapped[str | None] = mapped_column(String, nullable=True)
    interval_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_serviced_at_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_serviced_at_odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tire_type: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
