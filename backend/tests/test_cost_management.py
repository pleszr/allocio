import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import calculator
from app.domain.asset import Bucket
from app.domain.check_in import ExpenseEvent
from app.domain.vehicle_defaults import vehicle_catalog_keys


def _seed_linked_payment(db_session: Session, asset_id: str, cost_id: str, event_date: date) -> None:
    """Record a modeled expense linked to a time-based cost (a real occurrence of it)."""
    bucket = db_session.execute(select(Bucket).where(Bucket.asset_id == uuid.UUID(asset_id))).scalar_one()
    db_session.add(
        ExpenseEvent(
            bucket_id=bucket.id,
            check_in_id=None,
            event_date=event_date,
            kind="modeled",
            amount=Decimal("194648.00"),
            source_type="time_based_cost",
            source_id=uuid.UUID(cost_id),
        )
    )
    db_session.flush()

# Cost-management scenarios edit the seeded rows, so clone the full catalog at creation.
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
    "selected_cost_keys": sorted(vehicle_catalog_keys()),
}


def _create_vehicle(client: TestClient) -> dict[str, object]:
    """Create a vehicle and return its full created record set."""
    response = client.post("/api/assets", json=VALID_VEHICLE)
    assert response.status_code == 201
    return response.json()


def test_list_time_based_costs_includes_inactive(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    target = created["time_based_costs"][0]

    deactivate = client.patch(
        f"/api/assets/{asset_id}/time-based-costs/{target['id']}", json={"is_active": False}
    )
    assert deactivate.status_code == 200

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 6
    by_id = {row["id"]: row for row in rows}
    assert by_id[target["id"]]["is_active"] is False
    assert sum(1 for row in rows if row["is_active"]) == 5


def test_create_custom_time_based_cost(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    body = {"label": "Car wash", "amount": "3000.00", "interval_value": 1, "interval_unit": "months", "notes": "monthly"}
    response = client.post(f"/api/assets/{asset_id}/time-based-costs", json=body)

    assert response.status_code == 201
    row = response.json()
    assert response.headers["Location"] == f"/api/assets/{asset_id}/time-based-costs/{row['id']}"
    assert row["technical_key"] is None
    assert row["is_active"] is True
    assert row["asset_id"] == asset_id
    assert row["label"] == "Car wash"

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs").json()
    assert any(r["id"] == row["id"] for r in listed)


def test_edit_time_based_cost_fields(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    target = created["time_based_costs"][0]

    response = client.patch(
        f"/api/assets/{asset_id}/time-based-costs/{target['id']}",
        json={"amount": "42000.00", "interval_value": 24, "notes": "revised"},
    )

    assert response.status_code == 200
    row = response.json()
    assert row["amount"] == "42000.00"
    assert row["interval_value"] == 24
    assert row["notes"] == "revised"
    assert row["label"] == target["label"]  # unset field unchanged
    assert row["technical_key"] == target["technical_key"]  # never touched


def test_deactivate_then_reactivate_round_trips(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    cost_id = created["time_based_costs"][0]["id"]
    url = f"/api/assets/{asset_id}/time-based-costs/{cost_id}"

    assert client.patch(url, json={"is_active": False}).json()["is_active"] is False
    assert client.patch(url, json={"is_active": True}).json()["is_active"] is True


def test_list_usage_based_costs_includes_inactive(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    seeded = client.get(f"/api/assets/{asset_id}/usage-based-costs")
    assert seeded.status_code == 200
    rows = seeded.json()
    assert len(rows) == 1  # the vehicle template seeds exactly one usage row
    seeded_id = rows[0]["id"]

    deactivate = client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{seeded_id}", json={"is_active": False}
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    listed = client.get(f"/api/assets/{asset_id}/usage-based-costs").json()
    assert len(listed) == 1
    assert listed[0]["is_active"] is False


def test_create_usage_based_cost(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    body = {"label": "Fuel", "amount_per_unit": "45.0000", "usage_unit": "km", "notes": "petrol"}
    response = client.post(f"/api/assets/{asset_id}/usage-based-costs", json=body)

    assert response.status_code == 201
    row = response.json()
    assert response.headers["Location"] == f"/api/assets/{asset_id}/usage-based-costs/{row['id']}"
    assert row["technical_key"] is None
    assert row["is_active"] is True
    assert row["currency"] == "HUF"  # derived from the bucket, not the request
    assert row["label"] == "Fuel"
    assert row["amount_per_unit"] == "45.0000"
    assert row["usage_unit"] == "km"


def test_multiple_active_usage_based_costs_coexist(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    for label, rate in (("Fuel", "45.0000"), ("Tire wear", "4.0000")):
        response = client.post(
            f"/api/assets/{asset_id}/usage-based-costs", json={"label": label, "amount_per_unit": rate}
        )
        assert response.status_code == 201

    listed = client.get(f"/api/assets/{asset_id}/usage-based-costs").json()
    active = [row for row in listed if row["is_active"]]
    assert len(active) == 3  # the seeded row plus the two added rows — no .one_or_none() blocker


def test_edit_and_deactivate_usage_based_cost(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    seeded_id = client.get(f"/api/assets/{asset_id}/usage-based-costs").json()[0]["id"]
    other = client.post(
        f"/api/assets/{asset_id}/usage-based-costs", json={"label": "Fuel", "amount_per_unit": "45.0000"}
    ).json()

    edited = client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{seeded_id}",
        json={"amount_per_unit": "12.5000", "label": "Reserve", "notes": "higher rate"},
    )
    assert edited.status_code == 200
    row = edited.json()
    assert row["amount_per_unit"] == "12.5000"
    assert row["label"] == "Reserve"
    assert row["notes"] == "higher rate"

    deactivated = client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{seeded_id}", json={"is_active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # Deactivating one row leaves the sibling active.
    rows = {r["id"]: r for r in client.get(f"/api/assets/{asset_id}/usage-based-costs").json()}
    assert rows[other["id"]]["is_active"] is True


def test_usage_based_cost_error_paths(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    seeded_id = client.get(f"/api/assets/{asset_id}/usage-based-costs").json()[0]["id"]
    stranger = uuid.uuid4()

    assert client.get(f"/api/assets/{stranger}/usage-based-costs").status_code == 404
    assert client.post(
        f"/api/assets/{stranger}/usage-based-costs", json={"label": "x", "amount_per_unit": "1"}
    ).status_code == 404
    assert client.patch(
        f"/api/assets/{stranger}/usage-based-costs/{seeded_id}", json={"amount_per_unit": "1"}
    ).status_code == 404
    assert client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{uuid.uuid4()}", json={"amount_per_unit": "1"}
    ).status_code == 404
    assert client.post(
        f"/api/assets/{asset_id}/usage-based-costs", json={"label": "x", "amount_per_unit": "-1"}
    ).status_code == 422
    assert client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{seeded_id}", json={"currency": "EUR"}
    ).status_code == 422
    assert client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{seeded_id}", json={"technical_key": "hax"}
    ).status_code == 422


def test_create_maintenance_item_requires_interval(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    ok = client.post(
        f"/api/assets/{asset_id}/maintenance-items", json={"label": "Brake pads", "interval_km": 40000}
    )
    assert ok.status_code == 201
    row = ok.json()
    assert row["technical_key"] is None
    assert row["interval_km"] == 40000
    assert row["is_active"] is True

    no_interval = client.post(f"/api/assets/{asset_id}/maintenance-items", json={"label": "Vague thing"})
    assert no_interval.status_code == 422


def test_maintenance_interval_rule_on_edit(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    items = created["maintenance_items"]

    with_interval = next(i for i in items if i["interval_km"] is not None or i["interval_months"] is not None)
    cleared = client.patch(
        f"/api/assets/{asset_id}/maintenance-items/{with_interval['id']}",
        json={"interval_km": None, "interval_months": None},
    )
    assert cleared.status_code == 422

    other = next(i for i in items if i["technical_key"] == "other")
    edited = client.patch(
        f"/api/assets/{asset_id}/maintenance-items/{other['id']}", json={"label": "Misc renamed"}
    )
    assert edited.status_code == 200
    assert edited.json()["label"] == "Misc renamed"


def test_ownership_returns_404_for_unknown_asset(client: TestClient) -> None:
    _create_vehicle(client)
    stranger_asset = uuid.uuid4()

    response = client.get(f"/api/assets/{stranger_asset}/time-based-costs")
    assert response.status_code == 404
    assert "id" not in response.json()


def test_not_found_404_for_unknown_row(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    cost = client.patch(
        f"/api/assets/{asset_id}/time-based-costs/{uuid.uuid4()}", json={"amount": "1.00"}
    )
    assert cost.status_code == 404

    item = client.patch(
        f"/api/assets/{asset_id}/maintenance-items/{uuid.uuid4()}", json={"label": "x"}
    )
    assert item.status_code == 404


def test_edit_does_not_touch_sibling_rows(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    target, sibling = created["time_based_costs"][0], created["time_based_costs"][1]

    client.patch(f"/api/assets/{asset_id}/time-based-costs/{target['id']}", json={"amount": "99999.00"})

    rows = {row["id"]: row for row in client.get(f"/api/assets/{asset_id}/time-based-costs").json()}
    assert rows[sibling["id"]]["amount"] == sibling["amount"]
    assert rows[sibling["id"]]["label"] == sibling["label"]


def test_cost_routes_work_for_non_vehicle_asset(client: TestClient) -> None:
    """A bare non-vehicle asset can carry cost rows: the old type-gated 404 is gone."""
    created = client.post("/api/assets", json={"name": "My House", "type": "house"}).json()
    asset_id = created["asset"]["id"]
    assert created["time_based_costs"] == []

    body = {"label": "Roof fund", "amount": "50000.00", "interval_value": 12, "interval_unit": "months"}
    response = client.post(f"/api/assets/{asset_id}/time-based-costs", json=body)

    assert response.status_code == 201
    assert response.json()["asset_id"] == asset_id
    listed = client.get(f"/api/assets/{asset_id}/time-based-costs").json()
    assert [row["label"] for row in listed] == ["Roof fund"]


def _months_before_today(months: int) -> str:
    """Return an ISO date `months` whole months before today, clamped to day 1 for stability."""
    today = date.today()
    index = today.year * 12 + (today.month - 1) - months
    year, month = divmod(index, 12)
    return date(year, month + 1, 1).isoformat()


def test_create_time_based_cost_with_past_anchor_rolls_next_due_forward(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    anchor = _months_before_today(3)

    body = {
        "label": "Inspection",
        "amount": "25000.00",
        "interval_value": 1,
        "interval_unit": "months",
        "first_due_date": anchor,
    }
    response = client.post(f"/api/assets/{asset_id}/time-based-costs", json=body)

    assert response.status_code == 201
    row = response.json()
    assert row["first_due_date"] == anchor
    assert row["next_due_date"] is not None
    assert date.fromisoformat(row["next_due_date"]) >= date.today()


def test_create_without_anchor_derives_next_due_from_creation(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    body = {"label": "Car wash", "amount": "3000.00", "interval_value": 1, "interval_unit": "months"}
    response = client.post(f"/api/assets/{asset_id}/time-based-costs", json=body)

    assert response.status_code == 201
    row = response.json()
    # No explicit anchor: the next-due date is still resolved, derived from the creation date one
    # interval out, rather than being null.
    assert row["first_due_date"] is None
    assert row["next_due_date"] is not None
    assert date.fromisoformat(row["next_due_date"]) >= date.today()

    # Seeded vehicle template rows likewise get a creation-derived next_due_date, still with no anchor.
    listed = client.get(f"/api/assets/{asset_id}/time-based-costs")
    assert listed.status_code == 200
    template_rows = [r for r in listed.json() if r["technical_key"] is not None]
    assert template_rows
    assert all(r["first_due_date"] is None for r in template_rows)
    assert all(
        r["next_due_date"] is not None and date.fromisoformat(r["next_due_date"]) >= date.today()
        for r in template_rows
    )


def test_patch_sets_then_clears_anchor(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    cost_id = created["time_based_costs"][0]["id"]
    anchor = _months_before_today(2)

    set_response = client.patch(
        f"/api/assets/{asset_id}/time-based-costs/{cost_id}", json={"first_due_date": anchor}
    )
    assert set_response.status_code == 200
    set_row = set_response.json()
    assert set_row["first_due_date"] == anchor
    assert set_row["next_due_date"] is not None
    assert date.fromisoformat(set_row["next_due_date"]) >= date.today()

    clear_response = client.patch(
        f"/api/assets/{asset_id}/time-based-costs/{cost_id}", json={"first_due_date": None}
    )
    assert clear_response.status_code == 200
    clear_row = clear_response.json()
    # Clearing the explicit anchor falls back to the creation-derived next-due date, not null.
    assert clear_row["first_due_date"] is None
    assert clear_row["next_due_date"] is not None
    assert date.fromisoformat(clear_row["next_due_date"]) >= date.today()


def test_next_due_roll_forward_correct_through_api(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    # Anchor two whole 6-month intervals (12 months) before today, on day 1.
    anchor_iso = _months_before_today(12)
    anchor = date.fromisoformat(anchor_iso)

    body = {
        "label": "Semi-annual service",
        "amount": "40000.00",
        "interval_value": 6,
        "interval_unit": "months",
        "first_due_date": anchor_iso,
    }
    response = client.post(f"/api/assets/{asset_id}/time-based-costs", json=body)
    assert response.status_code == 201

    # Expected: roll forward by 6-month steps to the first occurrence on or after today.
    step = 0
    while True:
        index = anchor.year * 12 + (anchor.month - 1) + step * 6
        year, month = divmod(index, 12)
        occurrence = date(year, month + 1, anchor.day)
        if occurrence >= date.today():
            break
        step += 1
    assert response.json()["next_due_date"] == occurrence.isoformat()


def test_next_due_anchors_on_latest_linked_payment(client: TestClient, db_session: Session) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    cost = next(c for c in created["time_based_costs"] if c["technical_key"] == "comprehensive_insurance")

    # Two recorded occurrences of the cost; the later is the most recent occurrence (the anchor).
    latest_payment = date(2026, 2, 1)
    _seed_linked_payment(db_session, asset_id, cost["id"], latest_payment)
    _seed_linked_payment(db_session, asset_id, cost["id"], date(2025, 6, 25))

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs").json()
    row = next(r for r in listed if r["id"] == cost["id"])

    expected = calculator.next_due_date(latest_payment, cost["interval_value"], cost["interval_unit"], date.today())
    assert row["first_due_date"] is None
    assert row["next_due_date"] == expected.isoformat()
    # Anchored on the payment month rather than the creation date: the due day matches the payment.
    assert date.fromisoformat(row["next_due_date"]).day == latest_payment.day


def test_explicit_anchor_beats_linked_payment(client: TestClient, db_session: Session) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    cost = created["time_based_costs"][0]
    _seed_linked_payment(db_session, asset_id, cost["id"], date(2024, 1, 15))

    anchor = _months_before_today(1)
    client.patch(f"/api/assets/{asset_id}/time-based-costs/{cost['id']}", json={"first_due_date": anchor})

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs").json()
    row = next(r for r in listed if r["id"] == cost["id"])
    expected = calculator.next_due_date(date.fromisoformat(anchor), cost["interval_value"], cost["interval_unit"], date.today())
    assert row["first_due_date"] == anchor
    assert row["next_due_date"] == expected.isoformat()
