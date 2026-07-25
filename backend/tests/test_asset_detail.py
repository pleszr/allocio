"""GET /api/assets/{asset_id} composes one asset's dashboard payload (issue #23)."""
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi.testclient import TestClient

from app.domain.vehicle_defaults import vehicle_catalog_keys

# The detail payload asserts over the full seeded maintenance/cost set, so select every key.
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
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
    assert body["health"] in {"underfunded", "healthy", "overflowing"}

    # daily_accrual = recommended_monthly_allocation * 12 / 365, quantized to cents.
    monthly = Decimal(body["recommended_monthly_allocation"])
    expected_daily = (monthly * 12 / 365).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert Decimal(body["daily_accrual"]) == expected_daily

    # balance = sum(posted allocations) - the 100 expense.
    allocated = sum(Decimal(a["amount"]) for a in posted["allocation_events"])
    assert Decimal(body["balance"]) == allocated - Decimal("100")


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
    assert expense["label"] == "Brake job"
    # newest first.
    dates = [item["event_date"] for item in activity]
    assert dates == sorted(dates, reverse=True)


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
