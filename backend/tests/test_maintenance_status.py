"""Maintenance reads expose calculator-derived status and progress (issue #55)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
}
STARTING_ODOMETER = 120000
FUTURE_END = str(date.today() + timedelta(days=30))


def _create_vehicle(client: TestClient) -> str:
    response = client.post("/api/assets", json=VALID_VEHICLE)
    assert response.status_code == 201
    return response.json()["asset"]["id"]


def _post_check_in(client: TestClient, asset_id: str, usage_end: int) -> None:
    body = {"period_end": FUTURE_END, "usage_end": usage_end, "expenses": []}
    assert client.post(f"/api/assets/{asset_id}/check-ins", json=body).status_code == 201


def _add_maintenance(client: TestClient, asset_id: str, **body: object) -> dict[str, object]:
    response = client.post(f"/api/assets/{asset_id}/maintenance-items", json={"label": "Item", **body})
    assert response.status_code == 201
    return response.json()


def _get_by_id(client: TestClient, asset_id: str, item_id: str) -> dict[str, object]:
    listed = client.get(f"/api/assets/{asset_id}/maintenance-items").json()
    return next(item for item in listed if item["id"] == item_id)


def test_km_status_spans_thresholds_from_current_usage(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
    _post_check_in(client, asset_id, usage_end=130000)  # current usage becomes 130000
    # interval 10000 km; last-serviced odometer chosen to land each item in a distinct band.
    ok = _add_maintenance(client, asset_id, interval_km=10000, last_serviced_at_odometer=129000)  # 0.10
    soon = _add_maintenance(client, asset_id, interval_km=10000, last_serviced_at_odometer=121500)  # 0.85
    due = _add_maintenance(client, asset_id, interval_km=10000, last_serviced_at_odometer=120500)  # 0.95
    overdue = _add_maintenance(client, asset_id, interval_km=10000, last_serviced_at_odometer=119000)  # 1.10

    ok_row = _get_by_id(client, asset_id, ok["id"])
    assert ok_row["status"] == "ok"
    assert ok_row["km_since_service"] == 1000
    assert ok_row["km_progress"] == "0.1"
    assert ok_row["remaining_km"] == 9000
    assert ok_row["months_since_service"] is None
    assert ok_row["month_progress"] is None

    assert _get_by_id(client, asset_id, soon["id"])["status"] == "soon"
    assert _get_by_id(client, asset_id, due["id"])["status"] == "due"
    assert _get_by_id(client, asset_id, overdue["id"])["status"] == "overdue"


def test_month_only_item_derives_status_from_date(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
    # ~13 months elapsed vs a 12-month interval is unambiguously overdue regardless of day-of-month.
    long_ago = str(date.today() - timedelta(days=400))
    item = _add_maintenance(client, asset_id, interval_months=12, last_serviced_at_date=long_ago)
    row = _get_by_id(client, asset_id, item["id"])

    assert row["months_since_service"] >= 12
    assert row["month_progress"] is not None
    assert row["status"] == "overdue"  # >=13/12 > 1.05
    assert row["km_since_service"] is None
    assert row["km_progress"] is None
    assert row["remaining_km"] is None
    assert row["remaining_months"] == 0


def test_non_vehicle_asset_has_no_km_progress(client: TestClient) -> None:
    asset_id = client.post("/api/assets", json={"name": "My House", "type": "house"}).json()["asset"]["id"]
    # A km-interval item on an asset with no odometer resolves to no distance progress.
    km_item = _add_maintenance(client, asset_id, interval_km=50000, last_serviced_at_odometer=0)
    km_row = _get_by_id(client, asset_id, km_item["id"])
    assert km_row["km_since_service"] is None
    assert km_row["km_progress"] is None
    assert km_row["status"] == "ok"  # no resolvable ratio

    # A month-interval item still works without any usage counter; ~13 months vs 6 is clearly overdue.
    month_item = _add_maintenance(
        client, asset_id, interval_months=6, last_serviced_at_date=str(date.today() - timedelta(days=400))
    )
    month_row = _get_by_id(client, asset_id, month_item["id"])
    assert month_row["months_since_service"] >= 6
    assert month_row["month_progress"] is not None
    assert month_row["status"] == "overdue"


def test_current_usage_falls_back_to_starting_odometer_then_latest_check_in(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
    item = _add_maintenance(client, asset_id, interval_km=10000, last_serviced_at_odometer=115000)

    # No check-in yet: current usage = starting odometer (120000) -> since 5000 -> 0.50 -> ok.
    before = _get_by_id(client, asset_id, item["id"])
    assert before["km_since_service"] == 5000
    assert before["status"] == "ok"

    # After a posted check-in the latest usage_end drives current usage: since 15000 -> 1.50 -> overdue.
    _post_check_in(client, asset_id, usage_end=130000)
    after = _get_by_id(client, asset_id, item["id"])
    assert after["km_since_service"] == 15000
    assert after["status"] == "overdue"


def test_post_and_patch_responses_include_status(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
    created = _add_maintenance(client, asset_id, interval_km=10000, last_serviced_at_odometer=119000)
    assert created["status"] in {"ok", "soon", "due", "overdue"}
    assert "km_progress" in created

    patched = client.patch(
        f"/api/assets/{asset_id}/maintenance-items/{created['id']}", json={"label": "Renamed"}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["label"] == "Renamed"
    assert body["status"] in {"ok", "soon", "due", "overdue"}
    assert "month_progress" in body
