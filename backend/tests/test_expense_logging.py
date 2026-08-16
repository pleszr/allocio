import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.asset import Bucket
from app.domain.check_in import AllocationEvent, CheckIn
from app.domain.vehicle_defaults import vehicle_catalog_keys

# Expense logging references seeded source rows, so clone the full catalog at creation.
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
    "selected_cost_keys": sorted(vehicle_catalog_keys()),
}


def _create_vehicle(client: TestClient) -> dict[str, object]:
    """Create a vehicle and return its full created record set, including seeded cost rows."""
    response = client.post("/api/assets", json=VALID_VEHICLE)
    assert response.status_code == 201
    return response.json()


def _fund_bucket(session: Session, asset_id: str, amount: str, event_date: date) -> None:
    """Seed one dated allocation so standalone expense coverage can be tested precisely."""
    bucket = session.scalars(select(Bucket).where(Bucket.asset_id == uuid.UUID(asset_id))).one()
    check_in = CheckIn(
        asset_id=uuid.UUID(asset_id),
        period_start=event_date,
        period_end=event_date,
        usage_start=0,
        usage_end=0,
        usage_amount=0,
        status="posted",
    )
    session.add(check_in)
    session.flush()
    session.add(
        AllocationEvent(
            bucket_id=bucket.id,
            check_in_id=check_in.id,
            event_date=event_date,
            source_type="time_based_cost",
            source_id=None,
            amount=Decimal(amount),
        )
    )
    session.flush()


def test_log_other_expense_and_list(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    body = {"kind": "other", "amount": "15000.00", "comment": "car wash"}
    response = client.post(f"/api/assets/{asset_id}/expenses", json=body)

    assert response.status_code == 201
    row = response.json()
    assert row["kind"] == "other"
    assert row["source_type"] is None
    assert row["source_id"] is None
    assert row["comment"] == "car wash"
    assert Decimal(row["bucket_amount"]) == Decimal("0")
    assert Decimal(row["paid_out_of_pocket"]) == Decimal("15000.00")
    assert response.headers["Location"] == f"/api/assets/{asset_id}/expenses/{row['id']}"

    listed = client.get(f"/api/assets/{asset_id}/expenses").json()
    assert any(r["id"] == row["id"] for r in listed)


def test_standalone_expense_splits_against_balance_on_event_date(
    client: TestClient, db_session: Session
) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    _fund_bucket(db_session, asset_id, "100.00", date.today())

    row = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "other", "amount": "150.00", "comment": "Repair"},
    ).json()

    assert Decimal(row["amount"]) == Decimal("150.00")
    assert Decimal(row["bucket_amount"]) == Decimal("100.00")
    assert Decimal(row["paid_out_of_pocket"]) == Decimal("50.00")
    overview_asset = next(item for item in client.get("/api/assets").json()["assets"] if item["id"] == asset_id)
    assert Decimal(overview_asset["balance"]) == Decimal("0.00")


def test_backdated_standalone_expense_cannot_use_later_allocation(
    client: TestClient, db_session: Session
) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    _fund_bucket(db_session, asset_id, "100.00", date.today())
    yesterday = date.today() - timedelta(days=1)

    row = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "other", "amount": "40.00", "event_date": yesterday.isoformat()},
    ).json()

    assert Decimal(row["bucket_amount"]) == Decimal("0.00")
    assert Decimal(row["paid_out_of_pocket"]) == Decimal("40.00")


def test_standalone_override_above_natural_shortfall_reduces_bucket_draw(
    client: TestClient, db_session: Session
) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    _fund_bucket(db_session, asset_id, "100.00", date.today())

    row = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={
            "kind": "other",
            "amount": "50.00",
            "comment": "Door repair",
            "paid_out_of_pocket_override": "50.00",
        },
    ).json()

    assert Decimal(row["bucket_amount"]) == Decimal("0.00")
    assert Decimal(row["paid_out_of_pocket"]) == Decimal("50.00")


def test_standalone_override_below_natural_shortfall_is_clamped_to_natural(
    client: TestClient, db_session: Session
) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    _fund_bucket(db_session, asset_id, "100.00", date.today())

    row = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={
            "kind": "other",
            "amount": "150.00",
            "comment": "Large repair",
            "paid_out_of_pocket_override": "10.00",
        },
    ).json()

    # Natural shortfall is 50.00; the caller's lower 10.00 request never lowers it.
    assert Decimal(row["bucket_amount"]) == Decimal("100.00")
    assert Decimal(row["paid_out_of_pocket"]) == Decimal("50.00")


def test_standalone_omitted_override_is_byte_for_byte_identical_to_derived_only(
    client: TestClient, db_session: Session
) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    _fund_bucket(db_session, asset_id, "100.00", date.today())

    without_override = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "other", "amount": "150.00", "comment": "Repair"},
    ).json()

    _fund_bucket(db_session, asset_id, "100.00", date.today())
    with_null_override = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "other", "amount": "150.00", "comment": "Repair", "paid_out_of_pocket_override": None},
    ).json()

    assert without_override["bucket_amount"] == with_null_override["bucket_amount"]
    assert without_override["paid_out_of_pocket"] == with_null_override["paid_out_of_pocket"]


def test_log_modeled_expense_echoes_source(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    source = created["time_based_costs"][0]

    body = {
        "kind": "modeled",
        "amount": "40000.00",
        "source_type": "time_based_cost",
        "source_id": source["id"],
    }
    response = client.post(f"/api/assets/{asset_id}/expenses", json=body)

    assert response.status_code == 201
    row = response.json()
    assert row["kind"] == "modeled"
    assert row["source_type"] == "time_based_cost"
    assert row["source_id"] == source["id"]


def test_modeled_expense_with_foreign_source_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    body = {
        "kind": "modeled",
        "amount": "40000.00",
        "source_type": "time_based_cost",
        "source_id": str(uuid.uuid4()),
    }
    response = client.post(f"/api/assets/{asset_id}/expenses", json=body)
    assert response.status_code == 422


def test_modeled_expense_missing_source_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    no_type = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "modeled", "amount": "1000.00", "source_id": str(uuid.uuid4())},
    )
    assert no_type.status_code == 422

    no_id = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "modeled", "amount": "1000.00", "source_type": "time_based_cost"},
    )
    assert no_id.status_code == 422


def test_other_expense_with_source_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    source = created["time_based_costs"][0]

    body = {
        "kind": "other",
        "amount": "1000.00",
        "source_type": "time_based_cost",
        "source_id": source["id"],
    }
    response = client.post(f"/api/assets/{asset_id}/expenses", json=body)
    assert response.status_code == 422


def test_event_date_defaults_to_today_or_persists_verbatim(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    defaulted = client.post(
        f"/api/assets/{asset_id}/expenses", json={"kind": "other", "amount": "500.00"}
    ).json()
    assert defaulted["event_date"] == date.today().isoformat()

    backdated = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "other", "amount": "500.00", "event_date": "2025-01-15"},
    ).json()
    assert backdated["event_date"] == "2025-01-15"


def test_usage_counter_persisted(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    row = client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "other", "amount": "500.00", "usage_counter_at_event": 130000},
    ).json()
    assert row["usage_counter_at_event"] == 130000


def test_non_positive_amount_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    zero = client.post(f"/api/assets/{asset_id}/expenses", json={"kind": "other", "amount": "0"})
    assert zero.status_code == 422

    negative = client.post(f"/api/assets/{asset_id}/expenses", json={"kind": "other", "amount": "-10.00"})
    assert negative.status_code == 422


def test_log_against_unknown_asset_is_404(client: TestClient) -> None:
    _create_vehicle(client)
    stranger_asset = uuid.uuid4()

    response = client.post(
        f"/api/assets/{stranger_asset}/expenses", json={"kind": "other", "amount": "500.00"}
    )
    assert response.status_code == 404


def test_list_expenses_returns_logged_and_empty(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    empty = client.get(f"/api/assets/{asset_id}/expenses")
    assert empty.status_code == 200
    assert empty.json() == []

    client.post(f"/api/assets/{asset_id}/expenses", json={"kind": "other", "amount": "500.00"})
    client.post(f"/api/assets/{asset_id}/expenses", json={"kind": "other", "amount": "600.00"})

    listed = client.get(f"/api/assets/{asset_id}/expenses").json()
    assert len(listed) == 2


def test_list_time_based_cost_expenses_only_returns_that_cost(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    cost_a, cost_b = created["time_based_costs"][0], created["time_based_costs"][1]

    for amount, event_date in (("40000.00", "2025-01-15"), ("42000.00", "2026-01-15")):
        client.post(
            f"/api/assets/{asset_id}/expenses",
            json={
                "kind": "modeled",
                "amount": amount,
                "event_date": event_date,
                "source_type": "time_based_cost",
                "source_id": cost_a["id"],
            },
        )
    client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "modeled", "amount": "1000.00", "source_type": "time_based_cost", "source_id": cost_b["id"]},
    )

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs/{cost_a['id']}/expenses")
    assert listed.status_code == 200
    rows = listed.json()
    assert [r["amount"] for r in rows] == ["40000.00", "42000.00"]  # ascending by event_date
    assert all(r["source_id"] == cost_a["id"] for r in rows)


def test_list_source_expenses_empty_for_unpaid_cost(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    cost = created["time_based_costs"][0]

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs/{cost['id']}/expenses")
    assert listed.status_code == 200
    assert listed.json() == []


def test_list_usage_and_maintenance_source_expenses(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    usage = created["usage_based_costs"][0]
    maint = created["maintenance_items"][0]

    client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "modeled", "amount": "8000.00", "source_type": "usage_based_cost", "source_id": usage["id"]},
    )
    client.post(
        f"/api/assets/{asset_id}/expenses",
        json={"kind": "modeled", "amount": "30000.00", "source_type": "maintenance_item", "source_id": maint["id"]},
    )

    usage_rows = client.get(f"/api/assets/{asset_id}/usage-based-costs/{usage['id']}/expenses").json()
    assert [r["source_type"] for r in usage_rows] == ["usage_based_cost"]
    maint_rows = client.get(f"/api/assets/{asset_id}/maintenance-items/{maint['id']}/expenses").json()
    assert [r["source_type"] for r in maint_rows] == ["maintenance_item"]


def test_list_source_expenses_unknown_cost_is_404(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    response = client.get(f"/api/assets/{asset_id}/time-based-costs/{uuid.uuid4()}/expenses")
    assert response.status_code == 404


def test_list_source_expenses_unknown_asset_is_404(client: TestClient) -> None:
    created = _create_vehicle(client)
    cost = created["time_based_costs"][0]

    response = client.get(f"/api/assets/{uuid.uuid4()}/time-based-costs/{cost['id']}/expenses")
    assert response.status_code == 404
