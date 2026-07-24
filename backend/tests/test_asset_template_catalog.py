from decimal import Decimal

from fastapi.testclient import TestClient


def test_get_vehicle_catalog_returns_all_groups(client: TestClient) -> None:
    response = client.get("/api/asset-templates/vehicle/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["template_key"] == "vehicle"
    assert len(payload["time_based_costs"]) == 6
    assert len(payload["usage_based_costs"]) == 1
    assert len(payload["maintenance_items"]) == 14


def test_get_vehicle_catalog_spot_checks_known_keys_and_field_shapes(client: TestClient) -> None:
    payload = client.get("/api/asset-templates/vehicle/catalog").json()

    time_by_key = {row["technical_key"]: row for row in payload["time_based_costs"]}
    assert "comprehensive_insurance" in time_by_key
    comprehensive = time_by_key["comprehensive_insurance"]
    assert Decimal(str(comprehensive["amounts"]["HUF"])) == Decimal("11650")
    assert Decimal(str(comprehensive["amounts"]["EUR"])) == Decimal("29")
    assert Decimal(str(comprehensive["amounts"]["USD"])) == Decimal("32")
    assert isinstance(comprehensive["interval_value"], int)
    assert comprehensive["interval_unit"] == "months"

    reserve = payload["usage_based_costs"][0]
    assert reserve["technical_key"] == "usage_based_reserve"
    assert Decimal(str(reserve["amounts_per_unit"]["HUF"])) == Decimal("10")
    assert reserve["usage_unit"] == "km"
    assert set(reserve["amounts_per_unit"].keys()) == {"HUF", "EUR", "USD"}

    maint_by_key = {row["technical_key"]: row for row in payload["maintenance_items"]}
    assert "all_season_tires" in maint_by_key
    all_season = maint_by_key["all_season_tires"]
    assert all_season["interval_km"] == 50000
    assert all_season["interval_months"] == 36
    assert all_season["tire_type"] == "all_season"

    other = maint_by_key["other"]
    assert other["interval_km"] is None
    assert other["interval_months"] is None
    assert other["estimated_costs"] is None


def test_get_catalog_unknown_template_is_404(client: TestClient) -> None:
    response = client.get("/api/asset-templates/spaceship/catalog")

    assert response.status_code == 404
    assert "detail" in response.json()
