import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import ExpenseEvent
from app.domain.cost import TimeBasedCost

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


def _add_time_based_cost(session: Session, asset_id: uuid.UUID, label: str) -> TimeBasedCost:
    """Insert a minimal active time-based cost row to resolve an expense's source label from."""
    cost = TimeBasedCost(
        asset_id=asset_id,
        label=label,
        amount=Decimal("0"),
        interval_value=1,
        interval_unit="years",
    )
    session.add(cost)
    session.flush()
    return cost


def _add_expense(
    session: Session,
    bucket_id: uuid.UUID,
    amount: str,
    event_date: date,
    kind: str = "other",
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    comment: str | None = None,
) -> None:
    """Insert one standalone posted expense event (not linked to a check-in)."""
    session.add(
        ExpenseEvent(
            bucket_id=bucket_id,
            check_in_id=None,
            event_date=event_date,
            kind=kind,
            amount=Decimal(amount),
            source_type=source_type,
            source_id=source_id,
            comment=comment,
        )
    )
    session.flush()


def _get_distribution(client: TestClient, asset_id: uuid.UUID, months: int | None = None) -> dict:
    url = f"/api/assets/{asset_id}/cost-distribution"
    if months is not None:
        url += f"?months={months}"
    return client.get(url)


def test_no_expenses_returns_empty_slices(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="Empty")

    response = _get_distribution(client, asset.id)

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "HUF"
    assert body["slices"] == []
    assert _dec(body["total"]) == Decimal("0")
    assert body["months_with_data"] == 0


def test_expenses_group_by_resolved_source_label(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Grouped")
    insurance = _add_time_based_cost(db_session, asset.id, "Insurance")
    today = date.today()
    _add_expense(db_session, bucket.id, "100.00", today, kind="modeled", source_type="time_based_cost", source_id=insurance.id)
    _add_expense(
        db_session,
        bucket.id,
        "50.00",
        today - timedelta(days=10),
        kind="modeled",
        source_type="time_based_cost",
        source_id=insurance.id,
        comment="top-up",
    )

    body = _get_distribution(client, asset.id).json()

    assert len(body["slices"]) == 1
    slice_ = body["slices"][0]
    assert slice_["label"] == "Insurance"
    assert slice_["source_type"] == "time_based_cost"
    assert _dec(slice_["amount"]) == Decimal("150.00")
    assert _dec(body["total"]) == Decimal("150.00")


def test_manual_expenses_group_by_comment_and_fall_back_when_absent(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="Manual")
    today = date.today()
    _add_expense(db_session, bucket.id, "30.00", today, comment="Parking fine")
    _add_expense(db_session, bucket.id, "20.00", today)

    body = _get_distribution(client, asset.id).json()

    labels = {s["label"]: _dec(s["amount"]) for s in body["slices"]}
    assert labels["Parking fine"] == Decimal("30.00")
    assert labels["Manual expense"] == Decimal("20.00")


def test_slices_ordered_largest_amount_first(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Ordered")
    today = date.today()
    _add_expense(db_session, bucket.id, "10.00", today, comment="Small")
    _add_expense(db_session, bucket.id, "90.00", today, comment="Big")

    body = _get_distribution(client, asset.id).json()

    assert [s["label"] for s in body["slices"]] == ["Big", "Small"]


def test_expense_outside_window_is_excluded(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Windowed")
    today = date.today()
    _add_expense(db_session, bucket.id, "10.00", today, comment="Recent")
    _add_expense(db_session, bucket.id, "999.00", today - timedelta(days=400), comment="Old")

    body = _get_distribution(client, asset.id, months=12).json()

    assert [s["label"] for s in body["slices"]] == ["Recent"]
    assert _dec(body["total"]) == Decimal("10.00")


def test_months_with_data_counts_distinct_calendar_months(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="MonthsSpan")
    today = date.today()
    _add_expense(db_session, bucket.id, "10.00", today, comment="A")
    _add_expense(db_session, bucket.id, "10.00", today, comment="B")
    _add_expense(db_session, bucket.id, "10.00", today - timedelta(days=60), comment="C")

    body = _get_distribution(client, asset.id).json()

    assert body["months_with_data"] == 2


def test_months_query_param_out_of_range_returns_422(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="Range")

    assert _get_distribution(client, asset.id, months=0).status_code == 422


def test_unowned_asset_returns_404(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, user_id=OTHER_USER_ID, name="Theirs")

    assert _get_distribution(client, asset.id).status_code == 404


def test_unknown_asset_returns_404(client: TestClient) -> None:
    assert _get_distribution(client, uuid.uuid4()).status_code == 404
