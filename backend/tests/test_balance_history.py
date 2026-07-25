import calendar
import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain import calculator
from app.domain.asset import Asset, Bucket
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent

# Must match conftest.TEST_USER_ID (the user the TestClient authenticates as).
TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _dec(value: object) -> Decimal:
    """Parse a JSON-serialized amount (number or string) as an exact Decimal."""
    return Decimal(str(value))


def _months_ago(n: int) -> date:
    """Return today's date shifted back `n` whole calendar months, clamped to the target month's length."""
    today = date.today()
    month_index = today.year * 12 + (today.month - 1) - n
    year, month = divmod(month_index, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(today.day, last_day))


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


def _add_posted_check_in(session: Session, asset_id: uuid.UUID) -> CheckIn:
    """Insert a posted check-in whose id can back the NOT NULL `AllocationEvent.check_in_id`."""
    check_in = CheckIn(
        asset_id=asset_id,
        period_start=_months_ago(12),
        period_end=date.today(),
        usage_start=0,
        usage_end=0,
        usage_amount=0,
        status="posted",
    )
    session.add(check_in)
    session.flush()
    return check_in


def _add_allocation(
    session: Session, bucket_id: uuid.UUID, check_in_id: uuid.UUID, amount: str, event_date: date
) -> None:
    """Insert one posted allocation (inflow) event dated `event_date`."""
    session.add(
        AllocationEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=event_date,
            source_type="time_based_cost",
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
    check_in_id: uuid.UUID | None = None,
    paid_out_of_pocket: str = "0",
) -> None:
    """Insert one posted expense with an explicit funding split."""
    session.add(
        ExpenseEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=event_date,
            kind="other",
            amount=Decimal(amount),
            paid_out_of_pocket=Decimal(paid_out_of_pocket),
        )
    )
    session.flush()


def _get_history(client: TestClient, asset_id: uuid.UUID, months: int | None = None) -> dict:
    url = f"/api/assets/{asset_id}/balance-history"
    if months is not None:
        url += f"?months={months}"
    return client.get(url)


def _point_for_month(body: dict, when: date) -> dict:
    return next(point for point in body["points"] if point["month"] == when.strftime("%Y-%m"))


def test_empty_history_returns_single_zero_point(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="Empty")

    response = _get_history(client, asset.id)

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "HUF"
    assert len(body["points"]) == 1
    assert body["points"][0]["month"] == date.today().strftime("%Y-%m")
    assert _dec(body["points"][0]["balance"]) == Decimal("0")


def test_points_ordered_oldest_to_newest(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Ordered")
    check_in = _add_posted_check_in(db_session, asset.id)
    for months_back, amount in ((4, "100"), (2, "200"), (1, "300")):
        _add_allocation(db_session, bucket.id, check_in.id, amount, _months_ago(months_back))

    body = _get_history(client, asset.id).json()

    months = [point["month"] for point in body["points"]]
    assert months == sorted(months)
    assert len(set(months)) == len(months)  # strictly ascending, no duplicates
    assert months[-1] == date.today().strftime("%Y-%m")


def test_running_balance_is_cumulative(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Cumulative")
    check_in = _add_posted_check_in(db_session, asset.id)
    _add_allocation(db_session, bucket.id, check_in.id, "9000.00", _months_ago(2))
    _add_expense(db_session, bucket.id, "2000.00", _months_ago(1))

    body = _get_history(client, asset.id).json()

    assert _dec(_point_for_month(body, _months_ago(2))["balance"]) == Decimal("9000.00")
    assert _dec(_point_for_month(body, _months_ago(1))["balance"]) == Decimal("7000.00")
    assert _dec(_point_for_month(body, date.today())["balance"]) == Decimal("7000.00")


def test_history_never_presents_a_negative_bucket(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="NonNegative")
    check_in = _add_posted_check_in(db_session, asset.id)
    _add_allocation(db_session, bucket.id, check_in.id, "100.00", date.today())
    _add_expense(db_session, bucket.id, "150.00", date.today())

    body = _get_history(client, asset.id).json()

    assert _dec(body["points"][-1]["balance"]) == Decimal("0.00")


def test_last_point_equals_current_balance_no_drift(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="NoDrift")
    check_in = _add_posted_check_in(db_session, asset.id)
    allocation_amounts = [Decimal("5000.00"), Decimal("3000.00"), Decimal("1500.00")]
    expense_amounts = [Decimal("1200.00"), Decimal("800.00")]
    _add_allocation(db_session, bucket.id, check_in.id, "5000.00", _months_ago(5))
    _add_allocation(db_session, bucket.id, check_in.id, "3000.00", _months_ago(3))
    _add_allocation(db_session, bucket.id, check_in.id, "1500.00", date.today())
    _add_expense(db_session, bucket.id, "1200.00", _months_ago(4))
    _add_expense(db_session, bucket.id, "800.00", _months_ago(1))

    body = _get_history(client, asset.id).json()

    expected = calculator.bucket_balance(allocation_amounts, expense_amounts)
    assert _dec(body["points"][-1]["balance"]) == expected


def test_check_in_expense_moves_bucket_at_period_end_and_only_by_covered_amount(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="EffectiveDate")
    check_in = _add_posted_check_in(db_session, asset.id)
    earlier = _months_ago(1)
    _add_allocation(db_session, bucket.id, check_in.id, "10.00", earlier)
    _add_allocation(db_session, bucket.id, check_in.id, "100.00", date.today())
    _add_expense(
        db_session,
        bucket.id,
        "150.00",
        earlier,
        check_in_id=check_in.id,
        paid_out_of_pocket="50.00",
    )

    body = _get_history(client, asset.id).json()

    assert _dec(_point_for_month(body, earlier)["balance"]) == Decimal("10.00")
    assert _dec(_point_for_month(body, date.today())["balance"]) == Decimal("10.00")


def test_asset_younger_than_window_returns_short_series(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Young")
    check_in = _add_posted_check_in(db_session, asset.id)
    _add_allocation(db_session, bucket.id, check_in.id, "1000.00", _months_ago(3))

    body = _get_history(client, asset.id).json()  # default window (12), omitted param

    # First event 3 months ago -> Apr..Jul style window of 4 points, not padded to 12.
    assert len(body["points"]) == 4


def test_default_window_is_12_months(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="FullYear")
    check_in = _add_posted_check_in(db_session, asset.id)
    _add_allocation(db_session, bucket.id, check_in.id, "1000.00", _months_ago(13))
    _add_allocation(db_session, bucket.id, check_in.id, "500.00", _months_ago(6))

    body = _get_history(client, asset.id).json()

    assert len(body["points"]) == 12
    # Oldest point (11 months ago) already includes the 13-months-ago event.
    assert _dec(body["points"][0]["balance"]) == Decimal("1000.00")
    assert _dec(body["points"][-1]["balance"]) == Decimal("1500.00")


def test_months_query_param_caps_window(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Capped")
    check_in = _add_posted_check_in(db_session, asset.id)
    _add_allocation(db_session, bucket.id, check_in.id, "1000.00", _months_ago(8))

    body = _get_history(client, asset.id, months=6).json()

    assert len(body["points"]) == 6


def test_months_query_param_out_of_range_returns_422(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="BadParam")

    assert _get_history(client, asset.id, months=0).status_code == 422


def test_unowned_asset_returns_404(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, user_id=OTHER_USER_ID, name="Theirs")

    assert _get_history(client, asset.id).status_code == 404


def test_unknown_asset_returns_404(client: TestClient) -> None:
    assert _get_history(client, uuid.uuid4()).status_code == 404
