"""End-to-end API workflow test — the fast pre-commit safety net.

This test replays the exact request sequence the React frontend fires when a user creates a
bucket and runs a check-in (see `frontend/src/api/client.ts` and `NewBucketScreen.tsx`). It is
deliberately a single ordered walk rather than isolated unit tests: its job is to catch a broken
frontend/backend contract (a moved route, a renamed field, a bad status code) before commit, which
per-endpoint tests do not, since each asserts its own slice in isolation.

It runs in-process via `TestClient` against real Postgres using the transactional-rollback fixture
in `conftest.py`, so it stays fast and leaves no residue. The browser Playwright suite in
`frontend/e2e/` covers the same journey through a real browser and full stack.
"""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi.testclient import TestClient

# The browser sends these exact payloads. Keep them mirrored with the frontend client.
# `cost_overrides` mirrors what the New Bucket wizard now always sends for a selected time-based
# or usage-based row (its current value, edited or not) — maintenance-item keys never get one.
VEHICLE_BODY = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000, "manufacture_year": 2020},
    "selected_cost_keys": ["mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"],
    "cost_overrides": [
        {"technical_key": "mandatory_liability_insurance", "amount": 50119, "interval_value": 12, "interval_unit": "months"},
        {"technical_key": "usage_based_reserve", "amount": 10},
    ],
}
HOUSE_KEYS = [
    "building_tax",
    "home_insurance",
    "boiler_cleaning",
    "air_conditioner_cleaning",
]
HOUSE_OVERRIDES = [
    {
        "technical_key": "building_tax",
        "amount": 38000,
        "interval_value": 12,
        "interval_unit": "months",
    },
    {
        "technical_key": "home_insurance",
        "amount": 80000,
        "interval_value": 12,
        "interval_unit": "months",
    },
    {
        "technical_key": "boiler_cleaning",
        "amount": 35000,
        "interval_value": 12,
        "interval_unit": "months",
    },
    {
        "technical_key": "air_conditioner_cleaning",
        "amount": 45000,
        "interval_value": 12,
        "interval_unit": "months",
    },
]
PET_KEYS = ["pet_insurance", "annual_vaccinations"]
PET_OVERRIDES = [
    {
        "technical_key": "pet_insurance",
        "amount": 30000,
        "interval_value": 12,
        "interval_unit": "months",
    },
    {
        "technical_key": "annual_vaccinations",
        "amount": 20000,
        "interval_value": 12,
        "interval_unit": "months",
    },
]
STARTING_ODOMETER = 120000
# The asset is backdated 90 days below so this period can end in the past (the browser also lets
# the user pick a past period_end; see docs/vehicle-rules.md).
PERIOD_END = str(date.today() - timedelta(days=60))


def test_create_bucket_and_check_in_workflow(
    client: TestClient, backdate_asset_creation: Callable[[str], None]
) -> None:
    """Walk the full create-bucket -> add-cost -> check-in journey the browser performs."""
    # 1. Workspace overview loads (the app's first fetch on Home/Dashboard).
    overview = client.get("/api/assets")
    assert overview.status_code == 200
    assert isinstance(overview.json()["assets"], list)

    # 2. The New Bucket wizard loads the vehicle template catalog for the cost picker.
    catalog = client.get("/api/asset-templates/vehicle/catalog")
    assert catalog.status_code == 200
    catalog_body = catalog.json()
    assert catalog_body["template_key"] == "vehicle"
    catalog_keys = {
        row["technical_key"]
        for group in ("time_based_costs", "usage_based_costs", "maintenance_items")
        for row in catalog_body[group]
    }
    for key in VEHICLE_BODY["selected_cost_keys"]:
        assert key in catalog_keys, f"selected key {key!r} is not in the catalog"

    # 3. The wizard asks the backend for its non-persisting review estimate.
    estimate = client.post(
        "/api/allocation-estimates",
        json={
            "template": VEHICLE_BODY["template"],
            "selected_cost_keys": VEHICLE_BODY["selected_cost_keys"],
            "cost_overrides": VEHICLE_BODY["cost_overrides"],
            "custom_time_based_costs": [],
        },
    )
    assert estimate.status_code == 200
    assert Decimal(estimate.json()["yearly_total"]) > 0

    # 4. Submit the wizard: create the asset from the template with the picked cost rows.
    created = client.post("/api/assets", json=VEHICLE_BODY)
    assert created.status_code == 201
    asset_id = created.json()["asset"]["id"]
    assert created.headers["Location"] == f"/api/assets/{asset_id}"
    assert created.json()["profile"]["manufacture_year"] == 2020
    backdate_asset_creation(asset_id)

    # 5. The frontend navigates to the new bucket's detail — the step most likely to 404 if the
    #    read route or id contract is broken (the reported "not found" symptom lands here).
    detail = client.get(f"/api/assets/{asset_id}")
    assert detail.status_code == 200, f"post-create detail fetch failed: {detail.status_code} {detail.text}"
    assert detail.json()["id"] == asset_id
    assert detail.json()["tracks_usage"] is True

    # 6. Detail screen lists the seeded cost rows; the picked time-based row is present.
    time_based = client.get(f"/api/assets/{asset_id}/time-based-costs")
    assert time_based.status_code == 200
    insurance = next(
        row for row in time_based.json() if row["technical_key"] == "mandatory_liability_insurance"
    )
    assert Decimal(insurance["annualized_amount"]) == Decimal(insurance["amount"])
    assert Decimal(insurance["daily_rate"]) > 0

    # 7. Add a custom cost, exactly as the wizard posts extra draft rows after creation.
    custom_cost = client.post(
        f"/api/assets/{asset_id}/time-based-costs",
        json={"label": "Car wash", "amount": "3000.00", "interval_value": 1, "interval_unit": "months"},
    )
    assert custom_cost.status_code == 201

    # 8. Configure the recurring monthly buffer the Costs screen exposes.
    manual_extra = client.put(f"/api/assets/{asset_id}/manual-extra", json={"amount": "1000.00"})
    assert manual_extra.status_code == 200

    # 9. Check-in preview (deterministic, writes nothing) then commit — the Check-In screen flow.
    check_in_body = {"period_end": PERIOD_END, "usage_end": STARTING_ODOMETER + 900, "expenses": []}
    allocation_preview = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=check_in_body)
    assert allocation_preview.status_code == 200
    assert any(line["source_type"] == "manual_extra" for line in allocation_preview.json()["allocation_lines"])
    allocation = Decimal(allocation_preview.json()["total_allocation"])
    check_in_body["expenses"] = [
        {"kind": "other", "amount": str(allocation + Decimal("100.00")), "comment": "Large repair"}
    ]
    preview = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=check_in_body)
    assert preview.status_code == 200
    assert preview.json()["usage_amount"] == 900
    assert Decimal(preview.json()["paid_out_of_pocket"]) == Decimal("100.00")
    assert Decimal(preview.json()["balance_after"]) == Decimal("0.00")
    expected_balance_after = preview.json()["balance_after"]

    commit = client.post(f"/api/assets/{asset_id}/check-ins", json={**check_in_body, "notes": "first month"})
    assert commit.status_code == 201
    allocation_events = commit.json()["allocation_events"]
    assert any(line["source_type"] == "manual_extra" for line in allocation_events)
    expected_allocated = sum((Decimal(line["amount"]) for line in allocation_events), start=Decimal("0"))

    # 10. The new bucket now shows up in the workspace overview.
    final_overview = client.get("/api/assets")
    assert final_overview.status_code == 200
    assert any(asset["id"] == asset_id for asset in final_overview.json()["assets"])

    # 11. The Dashboard reads the backend-owned adaptive allocation signal from asset detail.
    dashboard_detail = client.get(f"/api/assets/{asset_id}")
    assert dashboard_detail.status_code == 200
    dashboard_body = dashboard_detail.json()
    average_allocation = dashboard_body["average_allocation"]
    assert average_allocation["months"] == 3
    assert Decimal(average_allocation["amount"]) == expected_allocated
    assert dashboard_body["vehicle_age_years"] == date.today().year - 2020
    assert dashboard_body["tracked_in_app_months"] >= 2
    expected_average_cost = ((expected_allocated + Decimal("100.00")) / 12).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert Decimal(dashboard_body["average_monthly_cost"]) == expected_average_cost
    assert dashboard_body["next_maintenance"] is None

    # 12. The History tab lists the posted check-in with the same balance the preview promised —
    #    guards the exact frontend/backend contract HistoryScreen.tsx depends on.
    history = client.get(f"/api/assets/{asset_id}/check-in-history")
    assert history.status_code == 200
    rows = history.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["period_end"] == PERIOD_END
    assert Decimal(rows[0]["allocated"]) == expected_allocated
    assert rows[0]["usage_since_last"] == 900
    assert Decimal(rows[0]["paid_out_of_pocket"]) == Decimal("100.00")
    assert Decimal(str(rows[0]["balance"])) == Decimal(str(expected_balance_after))


def test_create_house_template_workflow(client: TestClient) -> None:
    """Walk the House catalog, estimate, create, and detail reads used by the browser."""
    catalog = client.get("/api/asset-templates/house/catalog")
    assert catalog.status_code == 200
    catalog_body = catalog.json()
    assert [row["technical_key"] for row in catalog_body["time_based_costs"]] == HOUSE_KEYS
    assert catalog_body["usage_based_costs"] == []
    assert catalog_body["maintenance_items"] == []

    estimate = client.post(
        "/api/allocation-estimates",
        json={
            "template": "house",
            "selected_cost_keys": HOUSE_KEYS,
            "cost_overrides": HOUSE_OVERRIDES,
            "custom_time_based_costs": [],
            "manual_extra_monthly": 18000,
        },
    )
    assert estimate.status_code == 200
    assert Decimal(estimate.json()["monthly_total"]) == Decimal("34500.00")

    created = client.post(
        "/api/assets",
        json={
            "name": "My House",
            "template": "house",
            "selected_cost_keys": HOUSE_KEYS,
            "cost_overrides": HOUSE_OVERRIDES,
            "manual_extra_monthly": 18000,
        },
    )
    assert created.status_code == 201
    asset_id = created.json()["asset"]["id"]
    assert created.json()["profile"] is None

    detail = client.get(f"/api/assets/{asset_id}")
    assert detail.status_code == 200
    assert detail.json()["tracks_usage"] is False
    assert Decimal(detail.json()["manual_extra_monthly"]) == Decimal("18000.00")
    assert Decimal(detail.json()["recommended_monthly_allocation"]) == Decimal("34500.00")

    time_based = client.get(f"/api/assets/{asset_id}/time-based-costs")
    assert time_based.status_code == 200
    assert {row["technical_key"] for row in time_based.json()} == set(HOUSE_KEYS)
    assert len(time_based.json()) == 4


def test_create_pet_template_workflow(client: TestClient) -> None:
    """Walk the Pet catalog, estimate, create, and detail reads used by the browser."""
    catalog = client.get("/api/asset-templates/pet/catalog")
    assert catalog.status_code == 200
    catalog_body = catalog.json()
    assert [row["technical_key"] for row in catalog_body["time_based_costs"]] == PET_KEYS
    assert catalog_body["usage_based_costs"] == []
    assert catalog_body["maintenance_items"] == []

    estimate = client.post(
        "/api/allocation-estimates",
        json={
            "template": "pet",
            "selected_cost_keys": PET_KEYS,
            "cost_overrides": PET_OVERRIDES,
            "custom_time_based_costs": [],
        },
    )
    assert estimate.status_code == 200
    estimate_body = estimate.json()
    assert [line["key"] for line in estimate_body["lines"]] == PET_KEYS
    assert Decimal(estimate_body["yearly_total"]) == Decimal("50000.00")
    assert Decimal(estimate_body["monthly_total"]) == Decimal("4166.67")
    assert Decimal(estimate_body["daily_total"]) == Decimal("136.99")
    assert all(line["key"] != "manual_extra" for line in estimate_body["lines"])

    created = client.post(
        "/api/assets",
        json={
            "name": "Maya",
            "template": "pet",
            "selected_cost_keys": PET_KEYS,
            "cost_overrides": PET_OVERRIDES,
        },
    )
    assert created.status_code == 201
    asset_id = created.json()["asset"]["id"]
    assert created.json()["profile"] is None

    detail = client.get(f"/api/assets/{asset_id}")
    assert detail.status_code == 200
    assert detail.json()["tracks_usage"] is False
    assert Decimal(detail.json()["manual_extra_monthly"]) == Decimal("0.00")

    time_based = client.get(f"/api/assets/{asset_id}/time-based-costs")
    assert time_based.status_code == 200
    assert len(time_based.json()) == 2
    assert {row["technical_key"] for row in time_based.json()} == set(PET_KEYS)
