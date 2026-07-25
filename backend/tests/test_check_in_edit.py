import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent
from app.domain.cost import MaintenanceItem

# Must match conftest.TEST_USER_ID (the user the TestClient authenticates as).
TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _dec(value: object) -> Decimal:
    """Parse a JSON-serialized amount (number or string) as an exact Decimal."""
    return Decimal(str(value))


def _make_asset(
    session: Session, user_id: uuid.UUID = TEST_USER_ID, name: str = "Asset"
) -> tuple[Asset, Bucket]:
    """Insert an active asset and its HUF bucket directly for precise seeding."""
    asset = Asset(user_id=user_id, type="vehicle", name=name, status="active")
    session.add(asset)
    session.flush()
    bucket = Bucket(asset_id=asset.id, currency="HUF")
    session.add(bucket)
    session.flush()
    return asset, bucket


def _add_posted_check_in(
    session: Session,
    asset_id: uuid.UUID,
    period_start: date,
    period_end: date,
    usage_start: int = 0,
    usage_end: int = 0,
    active_tire_type: str | None = None,
    notes: str | None = None,
) -> CheckIn:
    """Insert a posted check-in with an explicit period and usage span, bypassing the normal posting flow.

    Directly seeding lets these tests construct multi-period histories (impossible through the real
    posting endpoint in a single test run, since `period_end` can never exceed today) precisely.
    """
    check_in = CheckIn(
        asset_id=asset_id,
        period_start=period_start,
        period_end=period_end,
        usage_start=usage_start,
        usage_end=usage_end,
        usage_amount=usage_end - usage_start,
        active_tire_type=active_tire_type,
        notes=notes,
        status="posted",
    )
    session.add(check_in)
    session.flush()
    return check_in


def _add_allocation(
    session: Session, bucket_id: uuid.UUID, check_in_id: uuid.UUID, amount: str, event_date: date
) -> None:
    """Insert one posted allocation (inflow) event linked to `check_in_id`."""
    session.add(
        AllocationEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=event_date,
            source_type="time_based_cost",
            source_id=None,
            amount=Decimal(amount),
            metadata_json={"label": "Seed cost"},
        )
    )
    session.flush()


def _add_expense(
    session: Session,
    bucket_id: uuid.UUID,
    check_in_id: uuid.UUID,
    amount: str,
    event_date: date,
    paid_out_of_pocket: str = "0",
    comment: str | None = None,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
) -> ExpenseEvent:
    """Insert one posted expense (outflow) event linked to `check_in_id`."""
    expense = ExpenseEvent(
        bucket_id=bucket_id,
        check_in_id=check_in_id,
        event_date=event_date,
        kind="modeled" if source_type else "other",
        amount=Decimal(amount),
        paid_out_of_pocket=Decimal(paid_out_of_pocket),
        comment=comment,
        source_type=source_type,
        source_id=source_id,
    )
    session.add(expense)
    session.flush()
    return expense


def _add_maintenance_item(
    session: Session,
    asset_id: uuid.UUID,
    label: str = "Annual service",
    interval_km: int | None = 15000,
    last_serviced_at_date: date | None = None,
    last_serviced_at_odometer: int | None = None,
    tire_type: str | None = None,
) -> MaintenanceItem:
    """Insert a maintenance item directly, with an optional pre-seeded baseline."""
    item = MaintenanceItem(
        asset_id=asset_id,
        label=label,
        interval_km=interval_km,
        last_serviced_at_date=last_serviced_at_date,
        last_serviced_at_odometer=last_serviced_at_odometer,
        tire_type=tire_type,
    )
    session.add(item)
    session.flush()
    return item


def _get_maintenance_items(client: TestClient, asset_id: uuid.UUID) -> list[dict]:
    return client.get(f"/api/assets/{asset_id}").json()["maintenance_items"]


def _edit_body(expenses: list[dict] | None = None, notes: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {"expenses": expenses or []}
    if notes is not None:
        body["notes"] = notes
    return body


def test_editing_most_recent_check_in_persists_new_split_and_leaves_other_fields_unchanged(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="MostRecent")
    period_end = date.today()
    check_in = _add_posted_check_in(
        db_session, asset.id, period_start=period_end, period_end=period_end, usage_end=1000, notes="original note"
    )
    _add_allocation(db_session, bucket.id, check_in.id, "200.00", period_end)
    _add_expense(db_session, bucket.id, check_in.id, "200.00", period_end, paid_out_of_pocket="0.00", comment="Repair")

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in.id}",
        json=_edit_body(
            [{"kind": "other", "amount": "200.00", "comment": "Repair", "paid_out_of_pocket_override": "200.00"}]
        ),
    )

    assert result.status_code == 200
    body = result.json()
    assert body["check_in"]["period_end"] == period_end.isoformat()
    assert body["check_in"]["usage_end"] == 1000
    assert body["check_in"]["active_tire_type"] is None
    assert body["check_in"]["notes"] == "original note"
    assert len(body["expense_events"]) == 1
    assert _dec(body["expense_events"][0]["paid_out_of_pocket"]) == Decimal("200.00")
    assert _dec(body["expense_events"][0]["bucket_amount"]) == Decimal("0.00")


def test_editing_older_check_in_without_breaking_later_balance_updates_history(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="OlderSafe")
    period1_end = date.today() - timedelta(days=30)
    period2_end = date.today()
    check_in_1 = _add_posted_check_in(db_session, asset.id, period_start=period1_end, period_end=period1_end)
    _add_allocation(db_session, bucket.id, check_in_1.id, "100.00", period1_end)
    _add_expense(db_session, bucket.id, check_in_1.id, "50.00", period1_end, comment="Original expense")
    check_in_2 = _add_posted_check_in(db_session, asset.id, period_start=period1_end, period_end=period2_end)
    _add_allocation(db_session, bucket.id, check_in_2.id, "100.00", period2_end)

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in_1.id}",
        json=_edit_body([{"kind": "other", "amount": "30.00", "comment": "Corrected expense"}]),
    )
    assert result.status_code == 200

    history = client.get(f"/api/assets/{asset.id}/check-in-history").json()["rows"]
    row1, row2 = history
    assert row1["check_in_id"] == str(check_in_1.id)
    assert _dec(row1["expense"]) == Decimal("30.00")
    assert _dec(row1["balance"]) == Decimal("70.00")
    assert _dec(row2["balance"]) == Decimal("170.00")


def test_edit_that_breaks_a_later_periods_balance_is_rejected_and_leaves_no_side_effects(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="BreaksLater")
    period1_end = date.today() - timedelta(days=30)
    period2_end = date.today()
    check_in_1 = _add_posted_check_in(db_session, asset.id, period_start=period1_end, period_end=period1_end)
    _add_allocation(db_session, bucket.id, check_in_1.id, "100.00", period1_end)
    # Fully paid out of pocket today, so the bucket keeps its full 100.00 allocation.
    _add_expense(
        db_session, bucket.id, check_in_1.id, "100.00", period1_end, paid_out_of_pocket="100.00", comment="Manual"
    )
    check_in_2 = _add_posted_check_in(db_session, asset.id, period_start=period1_end, period_end=period2_end)
    # No new allocation this period; an expense fully draws down the balance carried from period 1.
    _add_expense(db_session, bucket.id, check_in_2.id, "100.00", period2_end, comment="Drains balance")

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in_1.id}",
        # Dropping the override lets the natural split fully cover it from the bucket instead,
        # retroactively consuming the 100.00 that check_in_2 already depends on.
        json=_edit_body([{"kind": "other", "amount": "100.00", "comment": "Manual"}]),
    )

    assert result.status_code == 422
    assert period2_end.isoformat() in result.json()["detail"]

    unchanged = client.get(f"/api/assets/{asset.id}/check-ins/{check_in_1.id}").json()
    assert len(unchanged["expense_lines"]) == 1
    assert _dec(unchanged["expense_lines"][0]["paid_out_of_pocket"]) == Decimal("100.00")


def test_preview_edit_also_catches_the_break_without_writing_anything(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="PreviewBreaksLater")
    period1_end = date.today() - timedelta(days=30)
    period2_end = date.today()
    check_in_1 = _add_posted_check_in(db_session, asset.id, period_start=period1_end, period_end=period1_end)
    _add_allocation(db_session, bucket.id, check_in_1.id, "100.00", period1_end)
    _add_expense(
        db_session, bucket.id, check_in_1.id, "100.00", period1_end, paid_out_of_pocket="100.00", comment="Manual"
    )
    check_in_2 = _add_posted_check_in(db_session, asset.id, period_start=period1_end, period_end=period2_end)
    _add_expense(db_session, bucket.id, check_in_2.id, "100.00", period2_end, comment="Drains balance")

    result = client.post(
        f"/api/assets/{asset.id}/check-ins/{check_in_1.id}/preview",
        json=_edit_body([{"kind": "other", "amount": "100.00", "comment": "Manual"}]),
    )

    assert result.status_code == 200
    body = result.json()
    assert body["is_valid"] is False
    assert body["first_invalid_check_in_id"] == str(check_in_2.id)
    assert body["first_invalid_period_end"] == period2_end.isoformat()
    # The preview also mirrors the check-in's own immutable, unrecomputed fields (mirrors
    # CheckInPreviewResponse minus asset_id/period_start/usage_start), so the frontend can reuse the
    # same rendering it already has for a new check-in's preview.
    assert body["period_end"] == period1_end.isoformat()
    assert _dec(body["total_allocation"]) == Decimal("100.00")
    assert len(body["allocation_lines"]) == 1

    unchanged = client.get(f"/api/assets/{asset.id}/check-ins/{check_in_1.id}").json()
    assert _dec(unchanged["expense_lines"][0]["paid_out_of_pocket"]) == Decimal("100.00")


def test_new_maintenance_expense_on_latest_linking_check_in_updates_item_baseline(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="NewMaintenanceLink")
    item = _add_maintenance_item(db_session, asset.id, label="Annual service")
    period_end = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=period_end, period_end=period_end, usage_end=5000)
    _add_allocation(db_session, bucket.id, check_in.id, "50000.00", period_end)

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in.id}",
        json=_edit_body(
            [{"kind": "modeled", "amount": "25000.00", "source_type": "maintenance_item", "source_id": str(item.id)}]
        ),
    )

    assert result.status_code == 200
    refreshed = next(row for row in _get_maintenance_items(client, asset.id) if row["id"] == str(item.id))
    assert refreshed["last_serviced_at_date"] == period_end.isoformat()
    assert refreshed["last_serviced_at_odometer"] == 5000


def test_removing_maintenance_link_leaves_baseline_untouched_when_a_later_check_in_still_links(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="LaterStillLinks")
    period1_end = date.today() - timedelta(days=30)
    period2_end = date.today()
    item = _add_maintenance_item(
        db_session, asset.id, label="Annual service", last_serviced_at_date=period2_end, last_serviced_at_odometer=9000
    )
    check_in_1 = _add_posted_check_in(
        db_session, asset.id, period_start=period1_end, period_end=period1_end, usage_end=5000
    )
    _add_allocation(db_session, bucket.id, check_in_1.id, "30000.00", period1_end)
    _add_expense(
        db_session,
        bucket.id,
        check_in_1.id,
        "25000.00",
        period1_end,
        source_type="maintenance_item",
        source_id=item.id,
    )
    check_in_2 = _add_posted_check_in(
        db_session, asset.id, period_start=period1_end, period_end=period2_end, usage_start=5000, usage_end=9000
    )
    _add_allocation(db_session, bucket.id, check_in_2.id, "30000.00", period2_end)
    _add_expense(
        db_session,
        bucket.id,
        check_in_2.id,
        "25000.00",
        period2_end,
        source_type="maintenance_item",
        source_id=item.id,
    )

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in_1.id}",
        json=_edit_body([{"kind": "other", "amount": "25000.00", "comment": "No longer maintenance-linked"}]),
    )

    assert result.status_code == 200
    refreshed = next(row for row in _get_maintenance_items(client, asset.id) if row["id"] == str(item.id))
    # check_in_2 still links the item, so its baseline (not check_in_1's) keeps governing.
    assert refreshed["last_serviced_at_date"] == period2_end.isoformat()
    assert refreshed["last_serviced_at_odometer"] == 9000


def test_removing_the_only_maintenance_link_leaves_baseline_at_its_pre_edit_value(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="OnlyLinkRemoved")
    sentinel_date = date.today() - timedelta(days=400)
    sentinel_odometer = 55555
    item = _add_maintenance_item(
        db_session,
        asset.id,
        label="Annual service",
        last_serviced_at_date=sentinel_date,
        last_serviced_at_odometer=sentinel_odometer,
    )
    period_end = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=period_end, period_end=period_end, usage_end=7000)
    _add_allocation(db_session, bucket.id, check_in.id, "30000.00", period_end)
    _add_expense(
        db_session, bucket.id, check_in.id, "25000.00", period_end, source_type="maintenance_item", source_id=item.id
    )

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in.id}",
        json=_edit_body([{"kind": "other", "amount": "25000.00", "comment": "Unlinked from maintenance"}]),
    )

    assert result.status_code == 200
    refreshed = next(row for row in _get_maintenance_items(client, asset.id) if row["id"] == str(item.id))
    assert refreshed["last_serviced_at_date"] == sentinel_date.isoformat()
    assert refreshed["last_serviced_at_odometer"] == sentinel_odometer


def test_edit_on_another_users_check_in_is_404(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, user_id=OTHER_USER_ID, name="Theirs")
    period_end = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=period_end, period_end=period_end)
    _add_allocation(db_session, bucket.id, check_in.id, "100.00", period_end)

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in.id}",
        json=_edit_body([{"kind": "other", "amount": "10.00", "comment": "Should not apply"}]),
    )

    assert result.status_code == 404


def test_edit_on_unknown_check_in_is_404(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="UnknownCheckIn")

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{uuid.uuid4()}",
        json=_edit_body([{"kind": "other", "amount": "10.00", "comment": "Nothing to edit"}]),
    )

    assert result.status_code == 404


def test_edit_with_modeled_expense_missing_source_is_422(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="MissingSource")
    period_end = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=period_end, period_end=period_end)
    _add_allocation(db_session, bucket.id, check_in.id, "100.00", period_end)

    result = client.patch(
        f"/api/assets/{asset.id}/check-ins/{check_in.id}",
        json=_edit_body(
            [
                {
                    "kind": "modeled",
                    "amount": "40000.00",
                    "source_type": "time_based_cost",
                    "source_id": str(uuid.uuid4()),
                }
            ]
        ),
    )

    assert result.status_code == 422
