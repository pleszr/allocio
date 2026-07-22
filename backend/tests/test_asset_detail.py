"""GET /api/assets/{asset_id} composes one asset's dashboard payload (issue #23)."""
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi.testclient import TestClient

from app.domain.vehicle_defaults import vehicle_catalog_keys

# The detail payload asserts over the full seeded maintenance/cost set, so select every key.
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"year": 2018, "make": "Toyota", "model": "Corolla", "starting_odometer": 120000},
    "selected_cost_keys": sorted(vehicle_catalog_keys()),
}
STARTING_ODOMETER = 120000
FUTURE_END = str(date.today() + timedelta(days=30))


def _create_vehicle(client: TestClient) -> str:
    return client.post("/api/assets", json=VALID_VEHICLE).json()["asset"]["id"]


def _post_check_in(client: TestClient, asset_id: str, usage_end: int, expenses: list | None = None) -> dict:
    body = {"period_end": FUTURE_END, "usage_end": usage_end, "expenses": expenses or []}
    response = client.post(f"/api/assets/{asset_id}/check-ins", json=body)
    assert response.status_code == 201
    return response.json()


def test_detail_composes_derived_figures_and_usage(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
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
    assert body["last_check_in_date"] == FUTURE_END
    assert body["health"] in {"underfunded", "healthy", "overflowing"}

    # daily_accrual = recommended_monthly_allocation * 12 / 365, quantized to cents.
    monthly = Decimal(body["recommended_monthly_allocation"])
    expected_daily = (monthly * 12 / 365).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert Decimal(body["daily_accrual"]) == expected_daily

    # balance = sum(posted allocations) - the 100 expense.
    allocated = sum(Decimal(a["amount"]) for a in posted["allocation_events"])
    assert Decimal(body["balance"]) == allocated - Decimal("100")


def test_detail_maintenance_items_carry_status(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
    body = client.get(f"/api/assets/{asset_id}").json()
    assert len(body["maintenance_items"]) > 0  # vehicle template seeds maintenance rows
    assert all(item["status"] in {"ok", "soon", "due", "overdue"} for item in body["maintenance_items"])


def test_detail_recent_activity_merges_inflows_and_outflows(client: TestClient) -> None:
    asset_id = _create_vehicle(client)
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
    assert expense["label"] == "Brake job"
    # newest first.
    dates = [item["event_date"] for item in activity]
    assert dates == sorted(dates, reverse=True)


def test_detail_non_vehicle_has_null_usage_and_echoes_profile(client: TestClient) -> None:
    body = {
        "name": "Cedar St.",
        "type": "house",
        "subtitle": "2-bed · Built 1978",
        "attributes": {"built": "1978"},
    }
    asset_id = client.post("/api/assets", json=body).json()["asset"]["id"]

    detail = client.get(f"/api/assets/{asset_id}").json()
    assert detail["subtitle"] == "2-bed · Built 1978"
    assert detail["attributes"] == {"built": "1978"}
    assert detail["current_usage"] is None
    assert detail["usage_since_last_check_in"] is None
    assert detail["last_check_in_date"] is None
    assert detail["maintenance_items"] == []
    assert detail["recent_activity"] == []


def test_detail_unknown_asset_is_404(client: TestClient) -> None:
    assert client.get(f"/api/assets/{uuid.uuid4()}").status_code == 404
