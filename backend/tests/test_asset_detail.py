"""GET /api/assets/{asset_id} composes one asset's dashboard payload (issue #23)."""
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent
from app.domain.vehicle_defaults import vehicle_catalog_keys
from app.services.asset_detail_service import AssetDetailService

# The detail payload asserts over the full seeded maintenance/cost set, so select every key.
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000, "manufacture_year": 2020},
    "selected_cost_keys": sorted(vehicle_catalog_keys()),
}
STARTING_ODOMETER = 120000
# The asset is backdated 90 days (see `_create_vehicle`) so this period can end in the past.
PERIOD_END = str(date.today() - timedelta(days=60))


def _create_vehicle(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> str:
    asset_id = client.post("/api/assets", json=VALID_VEHICLE).json()["asset"]["id"]
    backdate_asset_creation(asset_id)
    return asset_id


def _post_check_in(client: TestClient, asset_id: str, usage_end: int, expenses: list | None = None) -> dict:
    body = {"period_end": PERIOD_END, "usage_end": usage_end, "expenses": expenses or []}
    response = client.post(f"/api/assets/{asset_id}/check-ins", json=body)
    assert response.status_code == 201
    return response.json()


def test_detail_composes_derived_figures_and_usage(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_vehicle(client, backdate_asset_creation)
    posted = _post_check_in(
        client, asset_id, usage_end=130000, expenses=[{"kind": "other", "amount": 100, "comment": "Wipers"}]
    )

    detail = client.get(f"/api/assets/{asset_id}")
    assert detail.status_code == 200
    body = detail.json()

    assert body["id"] == asset_id
    assert body["type"] == "vehicle"
    assert body["current_usage"] == 130000
    assert body["usage_since_last_check_in"] == 130000 - STARTING_ODOMETER
    assert body["last_check_in_date"] == PERIOD_END
    assert "health" not in body

    # daily_accrual = recommended_monthly_allocation * 12 / 365, quantized to cents.
    monthly = Decimal(body["recommended_monthly_allocation"])
    expected_daily = (monthly * 12 / 365).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert Decimal(body["daily_accrual"]) == expected_daily

    # balance = sum(posted allocations) - the 100 expense.
    allocated = sum(Decimal(a["amount"]) for a in posted["allocation_events"])
    assert Decimal(body["balance"]) == allocated - Decimal("100")
    assert body["average_allocation"]["months"] == 3
    assert Decimal(body["average_allocation"]["amount"]) == allocated


def test_detail_maintenance_items_carry_status(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_vehicle(client, backdate_asset_creation)
    body = client.get(f"/api/assets/{asset_id}").json()
    assert len(body["maintenance_items"]) > 0  # vehicle template seeds maintenance rows
    assert all(item["status"] in {"ok", "soon", "due", "overdue"} for item in body["maintenance_items"])


def test_detail_recent_activity_merges_inflows_and_outflows(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_vehicle(client, backdate_asset_creation)
    _post_check_in(
        client, asset_id, usage_end=130000, expenses=[{"kind": "other", "amount": 250, "comment": "Brake job"}]
    )

    activity = client.get(f"/api/assets/{asset_id}").json()["recent_activity"]
    kinds = {item["kind"] for item in activity}
    assert "allocation" in kinds and "expense" in kinds
    # allocations are positive inflows, the expense is a negative outflow.
    assert any(item["kind"] == "allocation" and Decimal(item["amount"]) > 0 for item in activity)
    expense = next(item for item in activity if item["kind"] == "expense")
    assert Decimal(expense["amount"]) == Decimal("-250")
    assert Decimal(expense["paid_out_of_pocket"]) == Decimal("0")
    assert expense["label"] == "Brake job"
    # newest first.
    dates = [item["event_date"] for item in activity]
    assert dates == sorted(dates, reverse=True)


def test_detail_recent_activity_explains_out_of_pocket_funding(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_vehicle(client, backdate_asset_creation)
    base = {"period_end": PERIOD_END, "usage_end": 130000, "expenses": []}
    available = Decimal(client.post(f"/api/assets/{asset_id}/check-ins/preview", json=base).json()["total_allocation"])
    _post_check_in(
        client,
        asset_id,
        usage_end=130000,
        expenses=[{"kind": "other", "amount": str(available + Decimal("25.00")), "comment": "Engine"}],
    )

    expense = next(
        item
        for item in client.get(f"/api/assets/{asset_id}").json()["recent_activity"]
        if item["kind"] == "expense"
    )

    assert Decimal(expense["amount"]) == -available
    assert Decimal(expense["paid_out_of_pocket"]) == Decimal("25.00")


def test_detail_non_vehicle_has_null_usage(client: TestClient) -> None:
    asset_id = client.post("/api/assets", json={"name": "Cedar St.", "type": "house"}).json()["asset"]["id"]

    detail = client.get(f"/api/assets/{asset_id}").json()
    assert "subtitle" not in detail
    assert "attributes" not in detail
    assert detail["current_usage"] is None
    assert detail["usage_since_last_check_in"] is None
    assert detail["last_check_in_date"] is None
    assert detail["maintenance_items"] == []
    assert detail["recent_activity"] == []
    assert detail["upcoming_expenses"] == []
    assert detail["average_allocation"] == {"months": 3, "amount": None}
    assert detail["vehicle_age_years"] is None
    assert Decimal(detail["average_monthly_cost"]) == Decimal("0.00")
    assert detail["next_maintenance"] is None


def test_detail_unknown_asset_is_404(client: TestClient) -> None:
    assert client.get(f"/api/assets/{uuid.uuid4()}").status_code == 404


# ── Upcoming expenses (issue #87) ───────────────────────────────────────
# Bare vehicle with no template rows selected, so only the custom rows each test adds can appear
# in the forecast — the template's own rows are seeded with a null `first_due_date` anchor (never
# time-based-forecastable) but could still add maintenance-status noise if cloned.
BARE_VEHICLE = {"name": "Bare Car", "template": "vehicle", "vehicle": {"starting_odometer": 120000}}


def _create_bare_vehicle(client: TestClient, backdate_asset_creation: Callable[[str], None], days: int = 90) -> str:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]
    backdate_asset_creation(asset_id, days=days)
    return asset_id


def _add_time_based(client: TestClient, asset_id: str, **body: object) -> dict[str, object]:
    payload = {"label": "Cost", "amount": "100.00", "interval_value": 1, "interval_unit": "years", **body}
    response = client.post(f"/api/assets/{asset_id}/time-based-costs", json=payload)
    assert response.status_code == 201
    return response.json()


def _add_maintenance(client: TestClient, asset_id: str, **body: object) -> dict[str, object]:
    response = client.post(f"/api/assets/{asset_id}/maintenance-items", json={"label": "Item", **body})
    assert response.status_code == 201
    return response.json()


def _upcoming(client: TestClient, asset_id: str) -> list[dict[str, object]]:
    return client.get(f"/api/assets/{asset_id}").json()["upcoming_expenses"]


def test_time_based_cost_due_within_horizon_appears(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    due_soon = str(date.today() + timedelta(days=30))
    _add_time_based(client, asset_id, label="Insurance", amount="1200.00", first_due_date=due_soon)

    upcoming = _upcoming(client, asset_id)

    assert len(upcoming) == 1
    assert upcoming[0]["name"] == "Insurance"
    assert upcoming[0]["category"] == "time_based"
    assert upcoming[0]["days_until"] == 30
    assert Decimal(upcoming[0]["amount"]) == Decimal("1200.00")
    assert upcoming[0]["overdue"] is False


def test_time_based_cost_beyond_horizon_or_inactive_excluded(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    too_far = _add_time_based(client, asset_id, label="Far off", first_due_date=str(date.today() + timedelta(days=120)))
    deactivated = _add_time_based(
        client, asset_id, label="Deactivated", first_due_date=str(date.today() + timedelta(days=10))
    )
    client.patch(f"/api/assets/{asset_id}/time-based-costs/{deactivated['id']}", json={"is_active": False})

    names = {item["name"] for item in _upcoming(client, asset_id)}
    assert "Far off" not in names
    assert "Deactivated" not in names
    assert too_far["id"]  # sanity: row was created even though it's excluded from the forecast


def test_overdue_maintenance_item_appears_with_zero_days(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    _post_check_in(client, asset_id, usage_end=130000)
    _add_maintenance(
        client, asset_id, label="Brakes", interval_km=10000, last_serviced_at_odometer=119000, estimated_cost="250.00"
    )  # 1.10 progress -> overdue

    upcoming = _upcoming(client, asset_id)

    assert len(upcoming) == 1
    assert upcoming[0]["name"] == "Brakes"
    assert upcoming[0]["category"] == "maintenance"
    assert upcoming[0]["days_until"] == 0
    assert upcoming[0]["overdue"] is True
    assert Decimal(upcoming[0]["amount"]) == Decimal("250.00")


def test_soon_maintenance_item_projects_days_from_usage_rate(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation, days=100)
    # Two posted check-ins spanning the full backdated 100 days, 10000 km total -> 100 km/day.
    first_end = str(date.today() - timedelta(days=50))
    client.post(f"/api/assets/{asset_id}/check-ins", json={"period_end": first_end, "usage_end": 121000, "expenses": []})
    client.post(
        f"/api/assets/{asset_id}/check-ins",
        json={"period_end": str(date.today()), "usage_end": 130000, "expenses": []},
    )
    _add_maintenance(
        client, asset_id, label="Tires", interval_km=10000, last_serviced_at_odometer=121500, estimated_cost="300.00"
    )  # 0.85 progress -> soon, remaining_km 1500

    upcoming = _upcoming(client, asset_id)

    assert len(upcoming) == 1
    assert upcoming[0]["name"] == "Tires"
    assert upcoming[0]["days_until"] == 15  # round(1500 / 100 km/day)
    assert upcoming[0]["overdue"] is False


def test_soon_maintenance_item_excluded_without_posted_usage(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    # No check-in posted: current usage falls back to starting_odometer (120000), so status is still
    # derivable, but there's no posted-usage span to project a days-until estimate from.
    _add_maintenance(
        client, asset_id, label="Tires", interval_km=10000, last_serviced_at_odometer=111500
    )  # 0.85 progress -> soon

    assert _upcoming(client, asset_id) == []


def test_inactive_maintenance_item_excluded(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    _post_check_in(client, asset_id, usage_end=130000)
    overdue = _add_maintenance(
        client, asset_id, label="Brakes", interval_km=10000, last_serviced_at_odometer=119000
    )
    client.patch(f"/api/assets/{asset_id}/maintenance-items/{overdue['id']}", json={"is_active": False})

    assert _upcoming(client, asset_id) == []


def test_upcoming_expenses_ordered_by_days_until(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    _post_check_in(client, asset_id, usage_end=130000)
    _add_time_based(client, asset_id, label="Later", first_due_date=str(date.today() + timedelta(days=45)))
    _add_maintenance(client, asset_id, label="Overdue now", interval_km=10000, last_serviced_at_odometer=119000)

    days = [item["days_until"] for item in _upcoming(client, asset_id)]
    assert days == sorted(days)
    assert days[0] == 0  # the overdue maintenance item sorts first


# ── Manual extra + average usage (issue #88) ────────────────────────────
def _add_posted_check_in(session: Session, asset_id: uuid.UUID, period_start: date, period_end: date) -> CheckIn:
    """Insert a posted check-in whose id can back the NOT NULL `AllocationEvent.check_in_id`."""
    check_in = CheckIn(
        asset_id=asset_id, period_start=period_start, period_end=period_end, status="posted"
    )
    session.add(check_in)
    session.flush()
    return check_in


def _add_allocation(
    session: Session,
    bucket_id: uuid.UUID,
    check_in_id: uuid.UUID,
    amount: str,
    event_date: date,
    source_type: str = "time_based_cost",
) -> None:
    session.add(
        AllocationEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=event_date,
            source_type=source_type,
            source_id=None,
            amount=Decimal(amount),
        )
    )
    session.flush()


def _add_expense(
    session: Session,
    bucket_id: uuid.UUID,
    amount: str,
    event_date: date,
    paid_out_of_pocket: str = "0.00",
) -> None:
    session.add(
        ExpenseEvent(
            bucket_id=bucket_id,
            check_in_id=None,
            event_date=event_date,
            kind="other",
            amount=Decimal(amount),
            paid_out_of_pocket=Decimal(paid_out_of_pocket),
        )
    )
    session.flush()


def _bucket_id(session: Session, asset_id: str) -> uuid.UUID:
    return session.query(Bucket).filter_by(asset_id=uuid.UUID(asset_id)).one().id


def _service_detail(db_session: Session, asset_id: str, as_of: date):
    asset_uuid = uuid.UUID(asset_id)
    asset = db_session.get(Asset, asset_uuid)
    assert asset is not None
    return AssetDetailService(db_session).get_detail(asset.user_id, asset_uuid, as_of=as_of)


def test_vehicle_lifecycle_signals_use_manufacture_year_and_complete_calendar_months(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=VALID_VEHICLE).json()["asset"]["id"]
    asset_uuid = uuid.UUID(asset_id)
    asset = db_session.get(Asset, asset_uuid)
    assert asset is not None
    asset.created_at = datetime(2024, 1, 31, 12, tzinfo=UTC)
    db_session.flush()

    detail = _service_detail(db_session, asset_id, date(2026, 2, 28))

    assert detail.vehicle_age_years == 6
    assert detail.tracked_in_app_months == 24


def test_vehicle_age_is_null_without_manufacture_year(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]

    detail = _service_detail(db_session, asset_id, date(2026, 2, 28))

    assert detail.vehicle_age_years is None


def test_average_monthly_cost_includes_all_allocations_and_only_out_of_pocket_expense(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json={"name": "Cost signal", "type": "house"}).json()["asset"]["id"]
    asset_uuid = uuid.UUID(asset_id)
    as_of = date(2026, 7, 25)
    check_in = _add_posted_check_in(db_session, asset_uuid, date(2026, 5, 1), as_of)
    bucket_id = _bucket_id(db_session, asset_id)
    _add_allocation(db_session, bucket_id, check_in.id, "120.00", date(2026, 6, 1))
    _add_allocation(
        db_session,
        bucket_id,
        check_in.id,
        "240.00",
        date(2026, 7, 1),
        source_type="manual_extra",
    )
    _add_expense(
        db_session,
        bucket_id,
        "1000.00",
        date(2026, 7, 2),
        paid_out_of_pocket="120.00",
    )

    detail = _service_detail(db_session, asset_id, as_of)

    assert detail.average_monthly_cost == Decimal("40.00")
    assert detail.avg_monthly_paid_out_of_pocket == Decimal("10.00")


def test_average_monthly_cost_uses_inclusive_clamped_window_and_excludes_outside_events(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json={"name": "Window signal", "type": "house"}).json()["asset"]["id"]
    asset_uuid = uuid.UUID(asset_id)
    as_of = date(2026, 2, 28)
    cutoff = date(2025, 2, 28)
    check_in = _add_posted_check_in(db_session, asset_uuid, date(2025, 1, 1), as_of)
    bucket_id = _bucket_id(db_session, asset_id)
    _add_allocation(db_session, bucket_id, check_in.id, "120.01", cutoff)
    _add_allocation(db_session, bucket_id, check_in.id, "119.99", as_of)
    _add_allocation(db_session, bucket_id, check_in.id, "9999.00", cutoff - timedelta(days=1))
    _add_allocation(db_session, bucket_id, check_in.id, "9999.00", as_of + timedelta(days=1))
    _add_expense(db_session, bucket_id, "500.00", as_of, paid_out_of_pocket="120.00")

    detail = _service_detail(db_session, asset_id, as_of)

    assert detail.average_monthly_cost == Decimal("30.00")
    assert detail.avg_monthly_paid_out_of_pocket == Decimal("10.00")


def test_average_monthly_cost_is_quantized_zero_without_history(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json={"name": "Empty signal", "type": "house"}).json()["asset"]["id"]

    detail = _service_detail(db_session, asset_id, date(2026, 7, 25))

    assert detail.average_monthly_cost == Decimal("0.00")
    assert detail.avg_monthly_paid_out_of_pocket == Decimal("0.00")


def test_next_maintenance_selects_nearest_active_comparable_item(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]
    _add_maintenance(
        client,
        asset_id,
        label="Far service",
        interval_km=10000,
        last_serviced_at_odometer=115000,
    )
    _add_maintenance(
        client,
        asset_id,
        label="Near service",
        interval_km=4000,
        last_serviced_at_odometer=117000,
    )
    inactive = _add_maintenance(
        client,
        asset_id,
        label="Inactive",
        interval_km=1000,
        last_serviced_at_odometer=120000,
    )
    client.patch(
        f"/api/assets/{asset_id}/maintenance-items/{inactive['id']}",
        json={"is_active": False},
    )
    _add_maintenance(client, asset_id, label="Month only", interval_months=12)
    _add_maintenance(client, asset_id, label="Missing baseline", interval_km=500)

    detail = _service_detail(db_session, asset_id, date.today())

    assert detail.next_maintenance is not None
    assert detail.next_maintenance.label == "Near service"
    assert detail.next_maintenance.remaining_km == 1000


def test_next_maintenance_breaks_equal_distance_ties_by_label(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]
    _add_maintenance(
        client,
        asset_id,
        label="Zulu",
        interval_km=10000,
        last_serviced_at_odometer=115000,
    )
    _add_maintenance(
        client,
        asset_id,
        label="alpha",
        interval_km=10000,
        last_serviced_at_odometer=115000,
    )

    detail = _service_detail(db_session, asset_id, date.today())

    assert detail.next_maintenance is not None
    assert detail.next_maintenance.label == "alpha"
    assert detail.next_maintenance.remaining_km == 5000


def test_next_maintenance_breaks_case_insensitive_label_ties_by_uuid(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]
    upper = _add_maintenance(
        client,
        asset_id,
        label="ALPHA",
        interval_km=10000,
        last_serviced_at_odometer=115000,
    )
    lower = _add_maintenance(
        client,
        asset_id,
        label="alpha",
        interval_km=10000,
        last_serviced_at_odometer=115000,
    )
    expected_label = "ALPHA" if str(upper["id"]) < str(lower["id"]) else "alpha"

    detail = _service_detail(db_session, asset_id, date.today())

    assert detail.next_maintenance is not None
    assert detail.next_maintenance.label == expected_label


def test_next_maintenance_returns_overdue_item_at_zero_km(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]
    _add_maintenance(
        client,
        asset_id,
        label="Overdue",
        interval_km=1000,
        last_serviced_at_odometer=118000,
    )

    detail = _service_detail(db_session, asset_id, date.today())

    assert detail.next_maintenance is not None
    assert detail.next_maintenance.remaining_km == 0


def test_next_maintenance_is_null_without_eligible_candidate(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json=BARE_VEHICLE).json()["asset"]["id"]
    _add_maintenance(client, asset_id, label="Month only", interval_months=12)
    _add_maintenance(client, asset_id, label="Missing baseline", interval_km=1000)

    detail = _service_detail(db_session, asset_id, date.today())

    assert detail.next_maintenance is None


def _average_for_rows(
    client: TestClient,
    db_session: Session,
    as_of: date,
    rows: list[tuple[date, str | None]],
) -> tuple[int, Decimal | None]:
    asset_id = client.post("/api/assets", json={"name": "Average test", "type": "house"}).json()["asset"]["id"]
    asset_uuid = uuid.UUID(asset_id)
    bucket_id = _bucket_id(db_session, asset_id)
    for period_end, amount in rows:
        check_in = _add_posted_check_in(
            db_session,
            asset_uuid,
            period_end - timedelta(days=30),
            period_end,
        )
        if amount is not None:
            _add_allocation(db_session, bucket_id, check_in.id, amount, period_end)

    asset = db_session.get(Asset, asset_uuid)
    assert asset is not None
    average = AssetDetailService(db_session).get_detail(asset.user_id, asset_uuid, as_of=as_of).average_allocation
    return average.months, average.amount


@pytest.mark.parametrize(
    ("rows", "expected_months", "expected_amount"),
    [
        (
            [
                (date(2026, 2, 28), "900.00"),
                (date(2026, 5, 31), "100.00"),
                (date(2026, 7, 31), "300.00"),
            ],
            3,
            Decimal("200.00"),
        ),
        (
            [
                (date(2026, 1, 31), "600.00"),
                (date(2026, 5, 31), "1200.00"),
                (date(2026, 7, 31), "1800.00"),
            ],
            6,
            Decimal("1200.00"),
        ),
        (
            [
                (date(2025, 7, 31), "1200.00"),
                (date(2026, 2, 28), "2400.00"),
                (date(2026, 7, 31), "3600.00"),
            ],
            12,
            Decimal("2400.00"),
        ),
    ],
)
def test_average_allocation_selects_longest_eligible_window(
    client: TestClient,
    db_session: Session,
    rows: list[tuple[date, str | None]],
    expected_months: int,
    expected_amount: Decimal,
) -> None:
    months, amount = _average_for_rows(client, db_session, date(2026, 7, 31), rows)

    assert months == expected_months
    assert amount == expected_amount


def test_average_allocation_clamps_month_end_and_includes_cutoff(
    client: TestClient, db_session: Session
) -> None:
    months, amount = _average_for_rows(
        client,
        db_session,
        date(2026, 3, 31),
        [(date(2025, 9, 30), "100.00"), (date(2026, 3, 31), "300.00")],
    )

    assert months == 6
    assert amount == Decimal("200.00")


def test_average_allocation_is_empty_without_posted_history(
    client: TestClient, db_session: Session
) -> None:
    months, amount = _average_for_rows(client, db_session, date(2026, 7, 31), [])

    assert months == 3
    assert amount is None


def test_average_allocation_counts_posted_check_in_without_allocations_as_zero(
    client: TestClient, db_session: Session
) -> None:
    months, amount = _average_for_rows(
        client,
        db_session,
        date(2026, 7, 31),
        [(date(2026, 5, 31), "300.00"), (date(2026, 7, 31), None)],
    )

    assert months == 3
    assert amount == Decimal("150.00")


def test_average_allocation_is_empty_when_all_history_predates_selected_window(
    client: TestClient, db_session: Session
) -> None:
    months, amount = _average_for_rows(
        client,
        db_session,
        date(2026, 7, 31),
        [(date(2024, 1, 31), "300.00")],
    )

    assert months == 12
    assert amount is None


def test_manual_extra_monthly_defaults_to_zero(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)

    body = client.get(f"/api/assets/{asset_id}").json()

    assert Decimal(body["manual_extra_monthly"]) == Decimal("0")
    assert Decimal(body["manual_extra_recommended"]) == Decimal("0")


def test_manual_extra_recommended_reflects_12_month_gap(
    client: TestClient, db_session: Session, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    check_in = _add_posted_check_in(db_session, uuid.UUID(asset_id), date.today() - timedelta(days=90), date.today())
    bucket_id = _bucket_id(db_session, asset_id)
    _add_allocation(db_session, bucket_id, check_in.id, "1000.00", date.today() - timedelta(days=30))
    _add_expense(db_session, bucket_id, "4000.00", date.today() - timedelta(days=20))

    body = client.get(f"/api/assets/{asset_id}").json()

    assert Decimal(body["manual_extra_recommended"]) == Decimal("3000.00")


def test_manual_extra_recommended_floors_at_zero(
    client: TestClient, db_session: Session, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    check_in = _add_posted_check_in(db_session, uuid.UUID(asset_id), date.today() - timedelta(days=90), date.today())
    bucket_id = _bucket_id(db_session, asset_id)
    _add_allocation(db_session, bucket_id, check_in.id, "5000.00", date.today() - timedelta(days=30))
    _add_expense(db_session, bucket_id, "1000.00", date.today() - timedelta(days=20))

    body = client.get(f"/api/assets/{asset_id}").json()

    assert Decimal(body["manual_extra_recommended"]) == Decimal("0")


def test_manual_extra_recommendation_excludes_events_older_than_12_months(
    client: TestClient, db_session: Session, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation, days=400)
    check_in = _add_posted_check_in(db_session, uuid.UUID(asset_id), date.today() - timedelta(days=400), date.today())
    bucket_id = _bucket_id(db_session, asset_id)
    # Outside the 365-day window: must not count toward the gap.
    _add_expense(db_session, bucket_id, "9000.00", date.today() - timedelta(days=380))

    body = client.get(f"/api/assets/{asset_id}").json()

    assert Decimal(body["manual_extra_recommended"]) == Decimal("0")


def test_update_manual_extra_persists_and_folds_into_recommended_allocation(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)
    before = Decimal(client.get(f"/api/assets/{asset_id}").json()["recommended_monthly_allocation"])

    response = client.put(f"/api/assets/{asset_id}/manual-extra", json={"amount": "5000.00"})
    assert response.status_code == 200
    assert Decimal(response.json()["manual_extra_monthly"]) == Decimal("5000.00")

    after = client.get(f"/api/assets/{asset_id}").json()
    assert Decimal(after["manual_extra_monthly"]) == Decimal("5000.00")
    assert Decimal(after["recommended_monthly_allocation"]) == before + Decimal("5000.00")


def test_update_manual_extra_rejects_negative_amount(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)

    assert client.put(f"/api/assets/{asset_id}/manual-extra", json={"amount": "-1"}).status_code == 422


def test_update_manual_extra_unknown_asset_is_404(client: TestClient) -> None:
    response = client.put(f"/api/assets/{uuid.uuid4()}/manual-extra", json={"amount": "10"})
    assert response.status_code == 404


def test_average_monthly_usage_zero_without_check_ins(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation)

    body = client.get(f"/api/assets/{asset_id}").json()

    assert Decimal(body["average_monthly_usage"]) == Decimal("0")


def test_average_monthly_usage_nonzero_with_posted_usage(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    asset_id = _create_bare_vehicle(client, backdate_asset_creation, days=100)
    first_end = str(date.today() - timedelta(days=50))
    client.post(f"/api/assets/{asset_id}/check-ins", json={"period_end": first_end, "usage_end": 121000, "expenses": []})
    client.post(
        f"/api/assets/{asset_id}/check-ins", json={"period_end": str(date.today()), "usage_end": 130000, "expenses": []}
    )

    body = client.get(f"/api/assets/{asset_id}").json()

    # 10,000 km over a ~3-whole-month window (see calculator.whole_months) -> nonzero average.
    assert Decimal(body["average_monthly_usage"]) > Decimal("0")
