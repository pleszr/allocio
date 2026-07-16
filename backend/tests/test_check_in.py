import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi.testclient import TestClient

VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"year": 2018, "make": "Toyota", "model": "Corolla", "starting_odometer": 120000},
}
STARTING_ODOMETER = 120000
FUTURE_END = str(date.today() + timedelta(days=30))
LATER_END = str(date.today() + timedelta(days=60))


def _create_vehicle(client: TestClient) -> dict[str, object]:
    """Create a vehicle and return its full created record set, including seeded cost rows."""
    response = client.post("/api/assets", json=VALID_VEHICLE)
    assert response.status_code == 201
    return response.json()


def _preview_body(period_end: str, usage_end: int, expenses: list | None = None) -> dict[str, object]:
    return {"period_end": period_end, "usage_end": usage_end, "expenses": expenses or []}


def _dec(value: object) -> Decimal:
    """Parse a JSON-serialized amount (number or string) as an exact Decimal."""
    return Decimal(str(value))


def test_first_check_in_derives_period_from_asset(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    body = _preview_body(FUTURE_END, STARTING_ODOMETER + 900)
    result = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body)

    assert result.status_code == 200
    preview = result.json()
    assert preview["usage_start"] == STARTING_ODOMETER
    assert preview["usage_amount"] == 900
    assert preview["period_end"] == FUTURE_END
    # First check-in starts at the asset's creation date, so the period is a positive span.
    assert preview["elapsed_days"] > 0
    assert date.fromisoformat(preview["period_start"]) < date.fromisoformat(FUTURE_END)


def test_preview_is_deterministic_and_writes_nothing(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    body = _preview_body(FUTURE_END, STARTING_ODOMETER + 500)

    first = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()
    second = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()

    assert first == second
    # No allocation/expense rows should have been created by previewing.
    assert client.get(f"/api/assets/{asset_id}/expenses").json() == []


def test_preview_covers_every_active_cost(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    time_based_count = len(created["time_based_costs"])

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(FUTURE_END, STARTING_ODOMETER + 900),
    ).json()

    lines = preview["allocation_lines"]
    time_based_lines = [line for line in lines if line["source_type"] == "time_based_cost"]
    usage_lines = [line for line in lines if line["source_type"] == "usage_based_cost"]
    assert len(time_based_lines) == time_based_count
    assert len(usage_lines) == 1
    # Usage-based reserve is 10 HUF/km * 900 km.
    assert _dec(usage_lines[0]["amount"]) == Decimal("9000.00")
    # Seasonal tire change: 14000 every 6 months annualized over elapsed days (vehicle-rules Example 2).
    tire = next(line for line in time_based_lines if line["label"] == "Seasonal tire change")
    expected_tire = (Decimal("28000") / Decimal(365) * Decimal(preview["elapsed_days"])).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert _dec(tire["amount"]) == expected_tire
    # total_allocation is exactly the sum of the line amounts.
    assert _dec(preview["total_allocation"]) == sum((_dec(line["amount"]) for line in lines), Decimal(0))


def test_preview_balance_totals_reflect_expense(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    expenses = [{"kind": "other", "amount": "5000.00", "comment": "car wash"}]

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(FUTURE_END, STARTING_ODOMETER + 900, expenses),
    ).json()

    assert len(preview["expense_lines"]) == 1
    assert _dec(preview["total_expense"]) == Decimal("5000.00")
    assert _dec(preview["balance_before"]) == Decimal("0")
    assert _dec(preview["net_bucket_change"]) == _dec(preview["total_allocation"]) - Decimal("5000.00")
    assert _dec(preview["balance_after"]) == _dec(preview["balance_before"]) + _dec(preview["net_bucket_change"])


def test_post_creates_check_in_and_events(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    time_based_count = len(created["time_based_costs"])
    expenses = [{"kind": "other", "amount": "5000.00", "comment": "car wash"}]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json={**_preview_body(FUTURE_END, STARTING_ODOMETER + 900, expenses), "notes": "first month"},
    )

    assert result.status_code == 201
    body = result.json()
    assert body["check_in"]["status"] == "posted"
    assert body["check_in"]["notes"] == "first month"
    assert body["check_in"]["usage_amount"] == 900
    assert len(body["allocation_events"]) == time_based_count + 1
    assert len(body["expense_events"]) == 1
    check_in_id = body["check_in"]["id"]
    assert result.headers["Location"] == f"/api/assets/{asset_id}/check-ins/{check_in_id}"
    assert all(event["check_in_id"] == check_in_id for event in body["allocation_events"])
    # The posted expense is now visible on the expense listing.
    assert any(row["comment"] == "car wash" for row in client.get(f"/api/assets/{asset_id}/expenses").json())


def test_post_amounts_match_preceding_preview(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    body = _preview_body(FUTURE_END, STARTING_ODOMETER + 900)

    preview = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()
    posted = client.post(f"/api/assets/{asset_id}/check-ins", json=body).json()

    preview_alloc = sorted((line["source_id"], _dec(line["amount"])) for line in preview["allocation_lines"])
    posted_alloc = sorted((event["source_id"], _dec(event["amount"])) for event in posted["allocation_events"])
    assert preview_alloc == posted_alloc


def test_subsequent_check_in_starts_where_previous_ended(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    first_usage_end = STARTING_ODOMETER + 900

    client.post(f"/api/assets/{asset_id}/check-ins", json=_preview_body(FUTURE_END, first_usage_end))
    next_preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(LATER_END, first_usage_end + 300),
    ).json()

    assert next_preview["period_start"] == FUTURE_END
    assert next_preview["usage_start"] == first_usage_end
    assert next_preview["usage_amount"] == 300


def test_balance_before_reflects_prior_posting(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    posted = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json=_preview_body(FUTURE_END, STARTING_ODOMETER + 900),
    ).json()

    next_preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(LATER_END, STARTING_ODOMETER + 900),
    ).json()

    # After one posting with no expenses, the next preview opens at the prior total allocation.
    expected_balance_before = sum(
        (_dec(event["amount"]) for event in posted["allocation_events"]), Decimal(0)
    )
    assert _dec(next_preview["balance_before"]) == expected_balance_before


def test_period_end_not_after_start_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body("2000-01-01", STARTING_ODOMETER + 100),
    )

    assert result.status_code == 422


def test_usage_end_below_start_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(FUTURE_END, STARTING_ODOMETER - 1),
    )

    assert result.status_code == 422


def test_post_modeled_expense_with_foreign_source_is_422(client: TestClient) -> None:
    created = _create_vehicle(client)
    asset_id = created["asset"]["id"]
    expenses = [
        {
            "kind": "modeled",
            "amount": "40000.00",
            "source_type": "time_based_cost",
            "source_id": str(uuid.uuid4()),
        }
    ]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json=_preview_body(FUTURE_END, STARTING_ODOMETER + 100, expenses),
    )

    assert result.status_code == 422


def test_unknown_asset_is_404(client: TestClient) -> None:
    result = client.post(
        f"/api/assets/{uuid.uuid4()}/check-ins/preview",
        json=_preview_body(FUTURE_END, 100),
    )

    assert result.status_code == 404
