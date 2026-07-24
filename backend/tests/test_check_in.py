import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi.testclient import TestClient

from app.domain.vehicle_defaults import vehicle_catalog_keys

# These scenarios exercise check-in accrual over the full seeded cost set, so select every
# catalog row at creation (the picker itself is covered by the asset-creation/catalog tests).
VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
    "selected_cost_keys": sorted(vehicle_catalog_keys()),
}
STARTING_ODOMETER = 120000
# Assets are backdated 90 days (see `_create_vehicle`) so a first check-in period can end in the
# past (or today) while still landing after the derived `period_start`.
PERIOD_END = str(date.today() - timedelta(days=60))
LATER_END = str(date.today() - timedelta(days=30))


def _create_vehicle(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> dict[str, object]:
    """Create a vehicle, backdate it, and return its full created record set, including seeded cost rows."""
    response = client.post("/api/assets", json=VALID_VEHICLE)
    assert response.status_code == 201
    created = response.json()
    backdate_asset_creation(created["asset"]["id"])
    return created


def _preview_body(
    period_end: str, usage_end: int, expenses: list | None = None, active_tire_type: str | None = None
) -> dict[str, object]:
    body: dict[str, object] = {"period_end": period_end, "usage_end": usage_end, "expenses": expenses or []}
    if active_tire_type is not None:
        body["active_tire_type"] = active_tire_type
    return body


def _dec(value: object) -> Decimal:
    """Parse a JSON-serialized amount (number or string) as an exact Decimal."""
    return Decimal(str(value))


def _maintenance_item(created: dict[str, object], technical_key: str) -> dict[str, object]:
    """Find a seeded maintenance item by its stable technical key."""
    return next(item for item in created["maintenance_items"] if item["technical_key"] == technical_key)


def test_first_check_in_derives_period_from_asset(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    body = _preview_body(PERIOD_END, STARTING_ODOMETER + 900)
    result = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body)

    assert result.status_code == 200
    preview = result.json()
    assert preview["usage_start"] == STARTING_ODOMETER
    assert preview["usage_amount"] == 900
    assert preview["period_end"] == PERIOD_END
    # First check-in starts at the asset's (backdated) creation date, so the period is a positive span.
    assert preview["elapsed_days"] > 0
    assert date.fromisoformat(preview["period_start"]) < date.fromisoformat(PERIOD_END)


def test_preview_is_deterministic_and_writes_nothing(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    body = _preview_body(PERIOD_END, STARTING_ODOMETER + 500)

    first = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()
    second = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()

    assert first == second
    # No allocation/expense rows should have been created by previewing.
    assert client.get(f"/api/assets/{asset_id}/expenses").json() == []


def test_preview_covers_every_active_cost(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    time_based_count = len(created["time_based_costs"])

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
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


def test_preview_balance_totals_reflect_expense(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    expenses = [{"kind": "other", "amount": "5000.00", "comment": "car wash"}]

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900, expenses),
    ).json()

    assert len(preview["expense_lines"]) == 1
    assert _dec(preview["total_expense"]) == Decimal("5000.00")
    assert _dec(preview["balance_before"]) == Decimal("0")
    assert _dec(preview["net_bucket_change"]) == _dec(preview["total_allocation"]) - Decimal("5000.00")
    assert _dec(preview["balance_after"]) == _dec(preview["balance_before"]) + _dec(preview["net_bucket_change"])


def test_post_creates_check_in_and_events(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    time_based_count = len(created["time_based_costs"])
    expenses = [{"kind": "other", "amount": "5000.00", "comment": "car wash"}]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json={**_preview_body(PERIOD_END, STARTING_ODOMETER + 900, expenses), "notes": "first month"},
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


def test_post_amounts_match_preceding_preview(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    body = _preview_body(PERIOD_END, STARTING_ODOMETER + 900)

    preview = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()
    posted = client.post(f"/api/assets/{asset_id}/check-ins", json=body).json()

    preview_alloc = sorted((line["source_id"], _dec(line["amount"])) for line in preview["allocation_lines"])
    posted_alloc = sorted((event["source_id"], _dec(event["amount"])) for event in posted["allocation_events"])
    assert preview_alloc == posted_alloc


def test_subsequent_check_in_starts_where_previous_ended(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    first_usage_end = STARTING_ODOMETER + 900

    client.post(f"/api/assets/{asset_id}/check-ins", json=_preview_body(PERIOD_END, first_usage_end))
    next_preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(LATER_END, first_usage_end + 300),
    ).json()

    assert next_preview["period_start"] == PERIOD_END
    assert next_preview["usage_start"] == first_usage_end
    assert next_preview["usage_amount"] == 300


def test_balance_before_reflects_prior_posting(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    posted = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
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


def test_period_end_not_after_start_is_422(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body("2000-01-01", STARTING_ODOMETER + 100),
    )

    assert result.status_code == 422


def test_period_end_in_future_is_422(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    future_end = str(date.today() + timedelta(days=1))

    result = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(future_end, STARTING_ODOMETER + 100),
    )

    assert result.status_code == 422


def test_period_end_today_is_accepted(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(str(date.today()), STARTING_ODOMETER + 100),
    )

    assert result.status_code == 200


def test_usage_end_below_start_is_422(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER - 1),
    )

    assert result.status_code == 422


def test_post_modeled_expense_with_foreign_source_is_422(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
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
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 100, expenses),
    )

    assert result.status_code == 422


def test_unknown_asset_is_404(client: TestClient) -> None:
    result = client.post(
        f"/api/assets/{uuid.uuid4()}/check-ins/preview",
        json=_preview_body(PERIOD_END, 100),
    )

    assert result.status_code == 404


def _add_usage_row(client: TestClient, asset_id: str, label: str, rate: str) -> str:
    """Create an extra active usage-based cost row and return its id."""
    response = client.post(
        f"/api/assets/{asset_id}/usage-based-costs", json={"label": label, "amount_per_unit": rate}
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_preview_multi_row_usage_accrual(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    # Seeded row is 10 HUF/km; add two more active rows so there are three usage components.
    _add_usage_row(client, asset_id, "Fuel", "45.0000")
    _add_usage_row(client, asset_id, "Tire wear", "4.0000")

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
    ).json()

    usage_lines = [line for line in preview["allocation_lines"] if line["source_type"] == "usage_based_cost"]
    assert len(usage_lines) == 3
    # Each active row emits its own line with a distinct source_id.
    assert len({line["source_id"] for line in usage_lines}) == 3
    amounts = {_dec(line["amount"]) for line in usage_lines}
    # usage_amount is 900; each line is quantize(900 * rate).
    assert amounts == {Decimal("9000.00"), Decimal("40500.00"), Decimal("3600.00")}
    time_based_total = sum(
        (_dec(line["amount"]) for line in preview["allocation_lines"] if line["source_type"] == "time_based_cost"),
        Decimal(0),
    )
    assert _dec(preview["total_allocation"]) == time_based_total + Decimal("9000.00") + Decimal("40500.00") + Decimal(
        "3600.00"
    )


def test_post_creates_one_event_per_usage_row(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    _add_usage_row(client, asset_id, "Fuel", "45.0000")
    _add_usage_row(client, asset_id, "Tire wear", "4.0000")

    posted = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
    ).json()

    usage_events = [e for e in posted["allocation_events"] if e["source_type"] == "usage_based_cost"]
    assert len(usage_events) == 3
    assert len({e["source_id"] for e in usage_events}) == 3
    assert {e["metadata_json"]["label"] for e in usage_events} == {"Usage-based reserve", "Fuel", "Tire wear"}
    assert {_dec(e["amount"]) for e in usage_events} == {
        Decimal("9000.00"),
        Decimal("40500.00"),
        Decimal("3600.00"),
    }


def test_multi_row_preview_equals_post(client: TestClient, backdate_asset_creation: Callable[[str], None]) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    _add_usage_row(client, asset_id, "Fuel", "45.0000")
    _add_usage_row(client, asset_id, "Tire wear", "4.0000")
    body = _preview_body(PERIOD_END, STARTING_ODOMETER + 900)

    preview = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=body).json()
    posted = client.post(f"/api/assets/{asset_id}/check-ins", json=body).json()

    preview_usage = sorted(
        (line["source_id"], _dec(line["amount"]))
        for line in preview["allocation_lines"]
        if line["source_type"] == "usage_based_cost"
    )
    posted_usage = sorted(
        (e["source_id"], _dec(e["amount"]))
        for e in posted["allocation_events"]
        if e["source_type"] == "usage_based_cost"
    )
    assert preview_usage == posted_usage
    assert _dec(preview["total_allocation"]) == sum(
        (_dec(e["amount"]) for e in posted["allocation_events"]), Decimal(0)
    )


def test_deactivated_usage_row_excluded_from_preview(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    _add_usage_row(client, asset_id, "Fuel", "45.0000")
    tire_id = _add_usage_row(client, asset_id, "Tire wear", "4.0000")

    deactivate = client.patch(
        f"/api/assets/{asset_id}/usage-based-costs/{tire_id}", json={"is_active": False}
    )
    assert deactivate.status_code == 200

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
    ).json()

    usage_lines = [line for line in preview["allocation_lines"] if line["source_type"] == "usage_based_cost"]
    assert len(usage_lines) == 2
    amounts = {_dec(line["amount"]) for line in usage_lines}
    # The deactivated 4 HUF/km row (900*4 = 3600) is absent.
    assert Decimal("3600.00") not in amounts
    assert amounts == {Decimal("9000.00"), Decimal("40500.00")}


def test_single_usage_row_reconciles_byte_for_byte(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    """Regression guard: with the one seeded usage row, per-row quantize equals the old single-line amount."""
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
    ).json()

    usage_lines = [line for line in preview["allocation_lines"] if line["source_type"] == "usage_based_cost"]
    assert len(usage_lines) == 1
    # Seeded reserve is 10 HUF/km * 900 km, unchanged from the single-reserve behavior.
    assert _dec(usage_lines[0]["amount"]) == Decimal("9000.00")


def test_maintenance_expense_resets_non_tire_item_date_and_odometer(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    item = _maintenance_item(created, "annual_service")
    expenses = [
        {
            "kind": "modeled",
            "amount": "25000.00",
            "source_type": "maintenance_item",
            "source_id": item["id"],
        }
    ]
    usage_end = STARTING_ODOMETER + 900

    result = client.post(
        f"/api/assets/{asset_id}/check-ins", json=_preview_body(PERIOD_END, usage_end, expenses)
    )
    assert result.status_code == 201

    refreshed = _maintenance_item(client.get(f"/api/assets/{asset_id}").json(), "annual_service")
    assert refreshed["last_serviced_at_date"] == PERIOD_END
    assert refreshed["last_serviced_at_odometer"] == usage_end


def test_maintenance_expense_resets_tire_item_date_only(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    item = _maintenance_item(created, "all_season_tires")
    original_odometer = item["last_serviced_at_odometer"]
    expenses = [
        {
            "kind": "modeled",
            "amount": "140000.00",
            "source_type": "maintenance_item",
            "source_id": item["id"],
        }
    ]
    usage_end = STARTING_ODOMETER + 900

    result = client.post(
        f"/api/assets/{asset_id}/check-ins", json=_preview_body(PERIOD_END, usage_end, expenses)
    )
    assert result.status_code == 201

    refreshed = _maintenance_item(client.get(f"/api/assets/{asset_id}").json(), "all_season_tires")
    assert refreshed["last_serviced_at_date"] == PERIOD_END
    # Tire items reset by date only; the odometer field is left untouched.
    assert refreshed["last_serviced_at_odometer"] == original_odometer


def test_failed_post_does_not_reset_maintenance_baseline(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    item = _maintenance_item(created, "annual_service")
    before_date = item["last_serviced_at_date"]
    before_odometer = item["last_serviced_at_odometer"]
    expenses = [
        {"kind": "modeled", "amount": "25000.00", "source_type": "maintenance_item", "source_id": item["id"]},
        {
            "kind": "modeled",
            "amount": "40000.00",
            "source_type": "time_based_cost",
            "source_id": str(uuid.uuid4()),  # foreign source -> whole post rejected
        },
    ]

    result = client.post(
        f"/api/assets/{asset_id}/check-ins", json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900, expenses)
    )
    assert result.status_code == 422

    refreshed = _maintenance_item(client.get(f"/api/assets/{asset_id}").json(), "annual_service")
    assert refreshed["last_serviced_at_date"] == before_date
    assert refreshed["last_serviced_at_odometer"] == before_odometer


def test_active_tire_type_defaults_to_previous_check_in(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    first_usage_end = STARTING_ODOMETER + 900

    posted = client.post(
        f"/api/assets/{asset_id}/check-ins",
        json=_preview_body(PERIOD_END, first_usage_end, active_tire_type="winter"),
    )
    assert posted.status_code == 201
    assert posted.json()["check_in"]["active_tire_type"] == "winter"

    next_preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(LATER_END, first_usage_end + 300),
    ).json()
    assert next_preview["active_tire_type"] == "winter"


def test_active_tire_type_explicit_value_overrides_default(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]
    first_usage_end = STARTING_ODOMETER + 900

    client.post(
        f"/api/assets/{asset_id}/check-ins",
        json=_preview_body(PERIOD_END, first_usage_end, active_tire_type="winter"),
    )

    next_preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(LATER_END, first_usage_end + 300, active_tire_type="summer"),
    ).json()
    assert next_preview["active_tire_type"] == "summer"


def test_active_tire_type_is_null_without_prior_check_in(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    created = _create_vehicle(client, backdate_asset_creation)
    asset_id = created["asset"]["id"]

    preview = client.post(
        f"/api/assets/{asset_id}/check-ins/preview",
        json=_preview_body(PERIOD_END, STARTING_ODOMETER + 900),
    ).json()

    assert preview["active_tire_type"] is None
