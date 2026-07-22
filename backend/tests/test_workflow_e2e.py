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

from datetime import date, timedelta

from fastapi.testclient import TestClient

# The browser sends these exact payloads. Keep them mirrored with the frontend client.
VEHICLE_BODY = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"year": 2018, "make": "Toyota", "model": "Corolla", "starting_odometer": 120000},
    "selected_cost_keys": ["mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"],
}
STARTING_ODOMETER = 120000
FUTURE_END = str(date.today() + timedelta(days=30))


def test_create_bucket_and_check_in_workflow(client: TestClient) -> None:
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

    # 3. Submit the wizard: create the asset from the template with the picked cost rows.
    created = client.post("/api/assets", json=VEHICLE_BODY)
    assert created.status_code == 201
    asset_id = created.json()["asset"]["id"]
    assert created.headers["Location"] == f"/api/assets/{asset_id}"

    # 4. The frontend navigates to the new bucket's detail — the step most likely to 404 if the
    #    read route or id contract is broken (the reported "not found" symptom lands here).
    detail = client.get(f"/api/assets/{asset_id}")
    assert detail.status_code == 200, f"post-create detail fetch failed: {detail.status_code} {detail.text}"
    assert detail.json()["id"] == asset_id

    # 5. Detail screen lists the seeded cost rows; the picked time-based row is present.
    time_based = client.get(f"/api/assets/{asset_id}/time-based-costs")
    assert time_based.status_code == 200
    assert any(row["technical_key"] == "mandatory_liability_insurance" for row in time_based.json())

    # 6. Add a custom cost, exactly as the wizard posts extra draft rows after creation.
    custom_cost = client.post(
        f"/api/assets/{asset_id}/time-based-costs",
        json={"label": "Car wash", "amount": "3000.00", "interval_value": 1, "interval_unit": "months"},
    )
    assert custom_cost.status_code == 201

    # 7. Check-in preview (deterministic, writes nothing) then commit — the Check-In screen flow.
    check_in_body = {"period_end": FUTURE_END, "usage_end": STARTING_ODOMETER + 900, "expenses": []}
    preview = client.post(f"/api/assets/{asset_id}/check-ins/preview", json=check_in_body)
    assert preview.status_code == 200
    assert preview.json()["usage_amount"] == 900

    commit = client.post(f"/api/assets/{asset_id}/check-ins", json={**check_in_body, "notes": "first month"})
    assert commit.status_code == 201

    # 8. The new bucket now shows up in the workspace overview.
    final_overview = client.get("/api/assets")
    assert final_overview.status_code == 200
    assert any(asset["id"] == asset_id for asset in final_overview.json()["assets"])
