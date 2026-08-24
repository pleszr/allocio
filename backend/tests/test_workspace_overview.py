import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.calculator import quantize_currency, time_based_monthly_accrual
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent
from app.domain.cost import TimeBasedCost, UsageBasedCost
from app.domain.vehicle_defaults import DEFAULT_TIME_BASED_COSTS, vehicle_catalog_keys

# Must match conftest.TEST_USER_ID (the user the TestClient authenticates as).
TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

# The recommended-allocation assertion sums the full seeded time-based set, so select every key.
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
    "selected_cost_keys": sorted(vehicle_catalog_keys()),
}


def _dec(value: object) -> Decimal:
    """Parse a JSON-serialized amount (number or string) as an exact Decimal."""
    return Decimal(str(value))


def _make_asset(
    session: Session,
    user_id: uuid.UUID = TEST_USER_ID,
    name: str = "Asset",
    with_bucket: bool = True,
) -> tuple[Asset, Bucket | None]:
    """Insert an active asset (and, by default, its HUF bucket) directly for precise seeding."""
    asset = Asset(user_id=user_id, type="vehicle", name=name, status="active")
    session.add(asset)
    session.flush()
    bucket = None
    if with_bucket:
        bucket = Bucket(asset_id=asset.id, currency="HUF")
        session.add(bucket)
        session.flush()
    return asset, bucket


def _add_time_based(
    session: Session, asset_id: uuid.UUID, amount: str, interval_value: int, unit: str, is_active: bool = True
) -> TimeBasedCost:
    cost = TimeBasedCost(
        asset_id=asset_id,
        label=f"tb-{amount}",
        amount=Decimal(amount),
        interval_value=interval_value,
        interval_unit=unit,
        is_active=is_active,
    )
    session.add(cost)
    session.flush()
    return cost


def _add_usage_based(session: Session, asset_id: uuid.UUID, amount_per_unit: str) -> UsageBasedCost:
    cost = UsageBasedCost(
        asset_id=asset_id, label="usage", amount_per_unit=Decimal(amount_per_unit), usage_unit="km", currency="HUF"
    )
    session.add(cost)
    session.flush()
    return cost


def _add_posted_check_in(
    session: Session, asset_id: uuid.UUID, usage_amount: int, period_start: date, period_end: date
) -> CheckIn:
    check_in = CheckIn(
        asset_id=asset_id,
        period_start=period_start,
        period_end=period_end,
        usage_start=0,
        usage_end=usage_amount,
        usage_amount=usage_amount,
        status="posted",
    )
    session.add(check_in)
    session.flush()
    return check_in


def _set_balance(session: Session, bucket_id: uuid.UUID, check_in_id: uuid.UUID, allocation: str, expense: str) -> None:
    """Seed one allocation and one expense event so the derived balance is allocation - expense."""
    session.add(
        AllocationEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=date.today(),
            source_type="time_based_cost",
            source_id=None,
            amount=Decimal(allocation),
        )
    )
    session.add(
        ExpenseEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=date.today(),
            kind="other",
            amount=Decimal(expense),
        )
    )
    session.flush()


def _asset_by_id(body: dict, asset_id: uuid.UUID) -> dict:
    return next(item for item in body["assets"] if item["id"] == str(asset_id))


def test_empty_workspace_returns_zeroed_totals(client: TestClient) -> None:
    response = client.get("/api/assets")

    assert response.status_code == 200
    body = response.json()
    assert body["assets"] == []
    assert _dec(body["totals"]["total_balance"]) == Decimal("0")
    assert _dec(body["totals"]["total_recommended_monthly_allocation"]) == Decimal("0")
    assert "alert_count" not in body["totals"]


def test_created_vehicle_recommended_matches_seeded_time_based(client: TestClient) -> None:
    created = client.post("/api/assets", json=VALID_VEHICLE).json()
    asset_id = created["asset"]["id"]

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, uuid.UUID(asset_id))

    # No check-ins yet: balance is zero and usage-based monthly contributes nothing.
    assert _dec(summary["balance"]) == Decimal("0")
    expected_time_based = sum(
        (
            time_based_monthly_accrual(t.amounts["HUF"], t.interval_value, t.interval_unit)
            for t in DEFAULT_TIME_BASED_COSTS
        ),
        Decimal(0),
    )
    assert _dec(summary["recommended_monthly_allocation"]) == quantize_currency(expected_time_based, "HUF")


def test_created_house_recommended_includes_template_manual_extra(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/assets",
        json={
            "name": "My House",
            "template": "house",
            "selected_cost_keys": [
                "building_tax",
                "home_insurance",
                "boiler_cleaning",
                "air_conditioner_cleaning",
            ],
        },
    ).json()

    summary = _asset_by_id(
        client.get("/api/assets").json(),
        uuid.UUID(created["asset"]["id"]),
    )

    assert _dec(summary["recommended_monthly_allocation"]) == Decimal("34500.00")


def test_balance_is_event_derived(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Balance")
    check_in = _add_posted_check_in(db_session, asset.id, 0, date(2026, 1, 1), date(2026, 2, 1))
    _set_balance(db_session, bucket.id, check_in.id, allocation="9000.00", expense="2000.00")

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, asset.id)

    assert _dec(summary["balance"]) == Decimal("7000.00")


def test_legacy_negative_event_total_is_presented_as_zero(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="Legacy")
    check_in = _add_posted_check_in(db_session, asset.id, 0, date(2026, 1, 1), date(2026, 2, 1))
    _set_balance(db_session, bucket.id, check_in.id, allocation="100.00", expense="150.00")

    summary = _asset_by_id(client.get("/api/assets").json(), asset.id)

    assert _dec(summary["balance"]) == Decimal("0.00")


def test_usage_based_monthly_uses_trailing_average(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="Usage")
    _add_usage_based(db_session, asset.id, amount_per_unit="10")
    # 900 km over 3 whole months -> 300 km/month -> 10 * 300 = 3000.
    _add_posted_check_in(db_session, asset.id, usage_amount=900, period_start=date(2026, 1, 10), period_end=date(2026, 4, 10))

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, asset.id)

    assert _dec(summary["recommended_monthly_allocation"]) == Decimal("3000.00")


def test_usage_based_monthly_ignores_check_ins_older_than_12_months(
    client: TestClient, db_session: Session
) -> None:
    """The trailing usage average only looks at the last 12 months, not the asset's full history."""
    asset, _bucket = _make_asset(db_session, name="Old usage")
    _add_usage_based(db_session, asset.id, amount_per_unit="10")
    # Ancient check-in, years outside the trailing window: must not dilute the average.
    _add_posted_check_in(db_session, asset.id, usage_amount=100000, period_start=date(2023, 1, 10), period_end=date(2023, 4, 10))
    # Same in-window check-in as the sibling test above: 900 km over 3 whole months -> 300 km/month.
    _add_posted_check_in(db_session, asset.id, usage_amount=900, period_start=date(2026, 1, 10), period_end=date(2026, 4, 10))

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, asset.id)

    assert _dec(summary["recommended_monthly_allocation"]) == Decimal("3000.00")


def test_usage_based_monthly_sums_active_rows(client: TestClient, db_session: Session) -> None:
    # Bare asset (no seeded usage row) with exactly two active usage components, rates 10 and 6.
    asset, _bucket = _make_asset(db_session, name="MultiUsage")
    _add_usage_based(db_session, asset.id, amount_per_unit="10")
    _add_usage_based(db_session, asset.id, amount_per_unit="6")
    # 900 km over 3 whole months -> 300 km/month; usage monthly = 300 * (10 + 6) = 4800.
    _add_posted_check_in(db_session, asset.id, usage_amount=900, period_start=date(2026, 1, 10), period_end=date(2026, 4, 10))

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, asset.id)

    # No time-based rows on this bare asset, so recommended monthly is the usage sum across both rows.
    assert _dec(summary["recommended_monthly_allocation"]) == quantize_currency(Decimal("300") * Decimal("16"), "HUF")


def test_health_and_alert_fields_are_absent(client: TestClient, db_session: Session) -> None:
    balances = {"a": "500.00", "b": "1000.00", "c": "2000.00"}
    for name, allocation in balances.items():
        asset, bucket = _make_asset(db_session, name=name)
        _add_time_based(db_session, asset.id, amount="12000", interval_value=12, unit="months")
        check_in = _add_posted_check_in(db_session, asset.id, 0, date(2026, 1, 1), date(2026, 2, 1))
        _set_balance(db_session, bucket.id, check_in.id, allocation=allocation, expense="0")

    body = client.get("/api/assets").json()
    totals = body["totals"]

    assert _dec(totals["total_balance"]) == Decimal("3500.00")
    assert _dec(totals["total_recommended_monthly_allocation"]) == Decimal("3000.00")
    assert "alert_count" not in totals
    assert all("health" not in summary for summary in body["assets"])


def test_inactive_time_based_cost_is_excluded(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="Mixed")
    _add_time_based(db_session, asset.id, amount="12000", interval_value=12, unit="months", is_active=True)
    _add_time_based(db_session, asset.id, amount="999999", interval_value=12, unit="months", is_active=False)

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, asset.id)

    # Only the active row's 1000/month is counted; the inactive row is excluded.
    assert _dec(summary["recommended_monthly_allocation"]) == Decimal("1000.00")
    assert _dec(body["totals"]["total_recommended_monthly_allocation"]) == Decimal("1000.00")


def test_manual_extra_monthly_folds_into_recommended_allocation(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="ManualExtra")
    _add_time_based(db_session, asset.id, amount="12000", interval_value=12, unit="months")
    asset.manual_extra_monthly = Decimal("1500.00")
    db_session.flush()

    body = client.get("/api/assets").json()
    summary = _asset_by_id(body, asset.id)

    # 12000/12mo = 1000/mo time-based, plus the 1500 manual extra buffer.
    assert _dec(summary["recommended_monthly_allocation"]) == Decimal("2500.00")


def test_assets_of_other_users_are_absent(client: TestClient, db_session: Session) -> None:
    mine, _bucket = _make_asset(db_session, user_id=TEST_USER_ID, name="Mine")
    theirs, _theirs_bucket = _make_asset(db_session, user_id=OTHER_USER_ID, name="Theirs")

    body = client.get("/api/assets").json()
    returned_ids = {item["id"] for item in body["assets"]}

    assert str(mine.id) in returned_ids
    assert str(theirs.id) not in returned_ids
