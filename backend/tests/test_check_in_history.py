import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent

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
) -> CheckIn:
    """Insert a posted check-in with an explicit period and usage span."""
    check_in = CheckIn(
        asset_id=asset_id,
        period_start=period_start,
        period_end=period_end,
        usage_start=usage_start,
        usage_end=usage_end,
        usage_amount=usage_end - usage_start,
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
) -> None:
    """Insert one posted expense (outflow) event linked to `check_in_id`."""
    session.add(
        ExpenseEvent(
            bucket_id=bucket_id,
            check_in_id=check_in_id,
            event_date=event_date,
            kind="other",
            amount=Decimal(amount),
            paid_out_of_pocket=Decimal(paid_out_of_pocket),
            comment=comment,
        )
    )
    session.flush()


def _get_history(client: TestClient, asset_id: uuid.UUID) -> dict:
    return client.get(f"/api/assets/{asset_id}/check-in-history")


def test_no_check_ins_returns_empty_rows(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, name="Empty")

    response = _get_history(client, asset.id)

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "HUF"
    assert body["rows"] == []


def test_baseline_check_in_returns_one_row(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="Baseline")
    today = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=today, period_end=today, usage_end=1000)
    _add_allocation(db_session, bucket.id, check_in.id, "0.00", today)

    body = _get_history(client, asset.id).json()

    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["check_in_id"] == str(check_in.id)
    assert row["elapsed_days"] == 0
    assert row["usage_end"] == 1000
    assert row["usage_since_last"] == 1000
    assert _dec(row["allocated"]) == Decimal("0.00")
    assert _dec(row["expense"]) == Decimal("0")
    assert _dec(row["bucket_expense"]) == Decimal("0")
    assert _dec(row["paid_out_of_pocket"]) == Decimal("0")
    assert _dec(row["net"]) == Decimal("0.00")
    assert _dec(row["balance"]) == Decimal("0.00")


def test_two_check_ins_ordered_with_running_balance(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="TwoRows")
    period1_start = date.today() - timedelta(days=60)
    period1_end = date.today() - timedelta(days=30)
    period2_end = date.today()

    check_in_1 = _add_posted_check_in(
        db_session, asset.id, period_start=period1_start, period_end=period1_end, usage_start=0, usage_end=500
    )
    _add_allocation(db_session, bucket.id, check_in_1.id, "300.00", period1_end)

    check_in_2 = _add_posted_check_in(
        db_session, asset.id, period_start=period1_end, period_end=period2_end, usage_start=500, usage_end=900
    )
    _add_allocation(db_session, bucket.id, check_in_2.id, "250.00", period2_end)
    _add_expense(db_session, bucket.id, check_in_2.id, "100.00", period2_end)

    body = _get_history(client, asset.id).json()

    assert len(body["rows"]) == 2
    # Rows are returned newest-first: check_in_2 (the later period) comes before check_in_1.
    row1, row2 = body["rows"]
    assert row1["check_in_id"] == str(check_in_2.id)
    assert row2["check_in_id"] == str(check_in_1.id)
    assert row2["elapsed_days"] == 30
    assert row2["usage_since_last"] == 500
    assert _dec(row2["balance"]) == Decimal("300.00")
    assert row1["usage_since_last"] == 400
    assert _dec(row1["net"]) == Decimal("150.00")
    # Running total, not per-row: 300 (check_in_1) + 150 (check_in_2's own net) = 450.
    assert _dec(row1["balance"]) == Decimal("450.00")


def test_history_separates_full_bucket_and_out_of_pocket_expense(
    client: TestClient, db_session: Session
) -> None:
    asset, bucket = _make_asset(db_session, name="FundingSplit")
    today = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=today, period_end=today)
    _add_allocation(db_session, bucket.id, check_in.id, "100.00", today)
    _add_expense(db_session, bucket.id, check_in.id, "150.00", today, paid_out_of_pocket="50.00")

    row = _get_history(client, asset.id).json()["rows"][0]

    assert _dec(row["expense"]) == Decimal("150.00")
    assert _dec(row["bucket_expense"]) == Decimal("100.00")
    assert _dec(row["paid_out_of_pocket"]) == Decimal("50.00")
    assert _dec(row["net"]) == Decimal("0.00")
    assert _dec(row["balance"]) == Decimal("0.00")


def test_check_in_with_no_expense_reports_zero(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="NoExpense")
    today = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=today, period_end=today, usage_end=100)
    _add_allocation(db_session, bucket.id, check_in.id, "50.00", today)

    body = _get_history(client, asset.id).json()

    assert _dec(body["rows"][0]["expense"]) == Decimal("0")
    assert body["rows"][0]["expenses"] == []


def test_check_in_with_one_expense_returns_its_line_details(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="ExpenseLine")
    today = date.today()
    check_in = _add_posted_check_in(db_session, asset.id, period_start=today, period_end=today)
    _add_allocation(db_session, bucket.id, check_in.id, "100.00", today)
    _add_expense(
        db_session,
        bucket.id,
        check_in.id,
        "150.00",
        today,
        paid_out_of_pocket="50.00",
        comment="Winter tires",
    )

    body = _get_history(client, asset.id).json()

    expenses = body["rows"][0]["expenses"]
    assert len(expenses) == 1
    line = expenses[0]
    assert line["kind"] == "other"
    assert _dec(line["amount"]) == Decimal("150.00")
    assert _dec(line["bucket_amount"]) == Decimal("100.00")
    assert _dec(line["paid_out_of_pocket"]) == Decimal("50.00")
    assert line["event_date"] == today.isoformat()
    assert line["comment"] == "Winter tires"


def test_check_in_expenses_ordered_oldest_event_date_first(client: TestClient, db_session: Session) -> None:
    asset, bucket = _make_asset(db_session, name="ExpenseOrder")
    today = date.today()
    earlier = today - timedelta(days=5)
    check_in = _add_posted_check_in(db_session, asset.id, period_start=earlier, period_end=today)
    _add_allocation(db_session, bucket.id, check_in.id, "0.00", today)
    # Insert newer-dated expense first so insertion order differs from event_date order.
    _add_expense(db_session, bucket.id, check_in.id, "20.00", today, comment="Later expense")
    _add_expense(db_session, bucket.id, check_in.id, "10.00", earlier, comment="Earlier expense")

    body = _get_history(client, asset.id).json()

    expenses = body["rows"][0]["expenses"]
    assert [line["comment"] for line in expenses] == ["Earlier expense", "Later expense"]


def test_unowned_asset_returns_404(client: TestClient, db_session: Session) -> None:
    asset, _bucket = _make_asset(db_session, user_id=OTHER_USER_ID, name="Theirs")

    assert _get_history(client, asset.id).status_code == 404


def test_unknown_asset_returns_404(client: TestClient) -> None:
    assert _get_history(client, uuid.uuid4()).status_code == 404
