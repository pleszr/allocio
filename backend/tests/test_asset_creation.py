from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket, VehicleProfile
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost
from tests.conftest import TEST_USER_ID

VEHICLE_BODY = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"starting_odometer": 120000},
}
SELECTED_KEYS = ["mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"]
VEHICLE_BODY_WITH_SELECTION = {**VEHICLE_BODY, "selected_cost_keys": SELECTED_KEYS}
HOUSE_BODY = {"name": "My House", "type": "house"}


def test_create_vehicle_no_selection_creates_profile_and_bucket_but_no_rows(client: TestClient) -> None:
    response = client.post("/api/assets", json=VEHICLE_BODY)

    assert response.status_code == 201
    assert response.headers["Location"].startswith("/api/assets/")

    payload = response.json()
    assert payload["asset"]["id"] in response.headers["Location"]
    assert payload["asset"]["type"] == "vehicle"
    assert payload["profile"] is not None
    assert set(payload["profile"]) == {"asset_id", "starting_odometer"}
    assert payload["profile"]["starting_odometer"] == 120000
    assert payload["time_based_costs"] == []
    assert payload["usage_based_costs"] == []
    assert payload["maintenance_items"] == []


def test_create_vehicle_no_selection_persists_profile_bucket_and_zero_rows(
    client: TestClient, db_session: Session
) -> None:
    client.post("/api/assets", json=VEHICLE_BODY)

    assets = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all()
    assert len(assets) == 1
    asset = assets[0]
    assert asset.type == "vehicle"

    profiles = db_session.scalars(select(VehicleProfile).where(VehicleProfile.asset_id == asset.id)).all()
    assert len(profiles) == 1

    buckets = db_session.scalars(select(Bucket).where(Bucket.asset_id == asset.id)).all()
    assert len(buckets) == 1
    assert buckets[0].currency == "HUF"

    time_based = db_session.scalars(select(TimeBasedCost).where(TimeBasedCost.asset_id == asset.id)).all()
    usage_based = db_session.scalars(select(UsageBasedCost).where(UsageBasedCost.asset_id == asset.id)).all()
    maintenance = db_session.scalars(select(MaintenanceItem).where(MaintenanceItem.asset_id == asset.id)).all()
    assert (len(time_based), len(usage_based), len(maintenance)) == (0, 0, 0)


def test_create_vehicle_with_selection_clones_only_selected_rows(client: TestClient) -> None:
    response = client.post("/api/assets", json=VEHICLE_BODY_WITH_SELECTION)

    assert response.status_code == 201
    payload = response.json()
    assert payload["profile"] is not None
    assert [row["technical_key"] for row in payload["time_based_costs"]] == ["mandatory_liability_insurance"]
    assert [row["technical_key"] for row in payload["usage_based_costs"]] == ["usage_based_reserve"]
    assert [row["technical_key"] for row in payload["maintenance_items"]] == ["all_season_tires"]


def test_create_vehicle_with_selection_persists_only_selected_rows(
    client: TestClient, db_session: Session
) -> None:
    client.post("/api/assets", json=VEHICLE_BODY_WITH_SELECTION)

    asset = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).one()
    assert db_session.scalars(select(VehicleProfile).where(VehicleProfile.asset_id == asset.id)).all() != []
    assert db_session.scalars(select(Bucket).where(Bucket.asset_id == asset.id)).all() != []

    time_based = db_session.scalars(select(TimeBasedCost).where(TimeBasedCost.asset_id == asset.id)).all()
    usage_based = db_session.scalars(select(UsageBasedCost).where(UsageBasedCost.asset_id == asset.id)).all()
    maintenance = db_session.scalars(select(MaintenanceItem).where(MaintenanceItem.asset_id == asset.id)).all()
    assert (len(time_based), len(usage_based), len(maintenance)) == (1, 1, 1)
    assert time_based[0].technical_key == "mandatory_liability_insurance"
    assert usage_based[0].technical_key == "usage_based_reserve"
    assert maintenance[0].technical_key == "all_season_tires"


def test_create_vehicle_with_unknown_selected_key_is_422(client: TestClient, db_session: Session) -> None:
    body = {**VEHICLE_BODY, "selected_cost_keys": ["mandatory_liability_insurance", "flux_capacitor"]}
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_create_selected_keys_without_template_is_422(client: TestClient, db_session: Session) -> None:
    body = {"name": "My House", "type": "house", "selected_cost_keys": ["mandatory_liability_insurance"]}
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_create_bare_asset_has_bucket_but_no_profile_or_rows(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json=HOUSE_BODY)

    assert response.status_code == 201
    payload = response.json()
    assert payload["asset"]["type"] == "house"
    assert payload["profile"] is None
    assert payload["time_based_costs"] == []
    assert payload["usage_based_costs"] == []
    assert payload["maintenance_items"] == []

    asset = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).one()
    assert asset.type == "house"
    assert db_session.scalars(select(VehicleProfile).where(VehicleProfile.asset_id == asset.id)).all() == []
    buckets = db_session.scalars(select(Bucket).where(Bucket.asset_id == asset.id)).all()
    assert len(buckets) == 1
    assert db_session.scalars(select(TimeBasedCost).where(TimeBasedCost.asset_id == asset.id)).all() == []


def test_new_bucket_adopts_owner_default_currency_after_settings_change(
    client: TestClient, db_session: Session
) -> None:
    # Existing bucket created before the settings change keeps its currency.
    client.post("/api/assets", json=VEHICLE_BODY_WITH_SELECTION)
    first_asset = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).one()
    first_bucket = db_session.scalars(select(Bucket).where(Bucket.asset_id == first_asset.id)).one()
    assert first_bucket.currency == "HUF"

    # Change the owner's default currency, then create a second vehicle asset.
    assert client.put("/api/users/me/settings", json={"default_currency": "EUR", "language": "en"}).status_code == 200
    client.post("/api/assets", json=VEHICLE_BODY_WITH_SELECTION)

    assets = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all()
    assert len(assets) == 2
    second_asset = next(a for a in assets if a.id != first_asset.id)

    second_bucket = db_session.scalars(select(Bucket).where(Bucket.asset_id == second_asset.id)).one()
    assert second_bucket.currency == "EUR"
    second_reserve = db_session.scalars(
        select(UsageBasedCost).where(UsageBasedCost.asset_id == second_asset.id)
    ).one()
    assert second_reserve.currency == "EUR"

    # The pre-existing bucket is untouched by the settings change.
    db_session.refresh(first_bucket)
    assert first_bucket.currency == "HUF"


def test_create_asset_rolls_back_on_failure(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    bucket_count_before = len(db_session.scalars(select(Bucket)).all())
    time_based_count_before = len(db_session.scalars(select(TimeBasedCost)).all())

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced failure mid-transaction")

    monkeypatch.setattr("app.services.asset_service.insert_asset_dependents", boom)

    response = client.post("/api/assets", json=VEHICLE_BODY)

    assert response.status_code == 500
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []
    assert len(db_session.scalars(select(Bucket)).all()) == bucket_count_before
    assert len(db_session.scalars(select(TimeBasedCost)).all()) == time_based_count_before


def test_create_asset_missing_name_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json={"type": "house"})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_create_asset_missing_type_without_template_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json={"name": "Nameless type"})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_vehicle_block_without_template_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/assets", json={"name": "My Car", "type": "vehicle", "vehicle": {"starting_odometer": 120000}}
    )

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_unknown_template_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json={"name": "Mystery", "template": "spaceship"})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_negative_odometer_is_422(client: TestClient, db_session: Session) -> None:
    body = {"name": "My Car", "template": "vehicle", "vehicle": {"starting_odometer": -1}}
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_removed_asset_metadata_is_absent_from_openapi(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert set(schemas["VehicleDetailsInput"]["properties"]) == {"starting_odometer"}
    assert {"subtitle", "attributes"}.isdisjoint(schemas["CreateAssetRequest"]["properties"])
    assert {"subtitle", "attributes"}.isdisjoint(schemas["AssetResponse"]["properties"])
    assert set(schemas["VehicleProfileResponse"]["properties"]) == {"asset_id", "starting_odometer"}
    assert "subtitle" not in schemas["AssetSummaryResponse"]["properties"]
    assert {"subtitle", "attributes"}.isdisjoint(schemas["AssetDetailResponse"]["properties"])


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Legacy", "type": "house", "subtitle": "Old detail"},
        {"name": "Legacy", "type": "house", "attributes": {"built": 1978}},
        {"name": "Legacy", "template": "vehicle", "vehicle": {"make": "Toyota"}},
        {"name": "Legacy", "template": "vehicle", "vehicle": {"model": "Corolla"}},
        {"name": "Legacy", "template": "vehicle", "vehicle": {"year": 2018}},
    ],
)
def test_removed_asset_metadata_is_rejected(
    client: TestClient, db_session: Session, body: dict[str, object]
) -> None:
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_cost_override_changes_time_based_amount_and_interval(client: TestClient, db_session: Session) -> None:
    body = {
        **VEHICLE_BODY_WITH_SELECTION,
        "cost_overrides": [
            {
                "technical_key": "mandatory_liability_insurance",
                "amount": 60000,
                "interval_value": 6,
                "interval_unit": "months",
            }
        ],
    }
    response = client.post("/api/assets", json=body)

    assert response.status_code == 201
    asset = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).one()
    liability = db_session.scalars(
        select(TimeBasedCost).where(
            TimeBasedCost.asset_id == asset.id, TimeBasedCost.technical_key == "mandatory_liability_insurance"
        )
    ).one()
    assert liability.amount == 60000
    assert liability.interval_value == 6
    assert liability.interval_unit == "months"


def test_cost_override_changes_usage_based_amount(client: TestClient, db_session: Session) -> None:
    body = {
        **VEHICLE_BODY_WITH_SELECTION,
        "cost_overrides": [{"technical_key": "usage_based_reserve", "amount": 15}],
    }
    response = client.post("/api/assets", json=body)

    assert response.status_code == 201
    asset = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).one()
    reserve = db_session.scalars(select(UsageBasedCost).where(UsageBasedCost.asset_id == asset.id)).one()
    assert reserve.amount_per_unit == 15


def test_cost_override_for_unselected_key_is_422(client: TestClient, db_session: Session) -> None:
    body = {
        **VEHICLE_BODY_WITH_SELECTION,
        "cost_overrides": [{"technical_key": "vehicle_tax", "amount": 1000}],
    }
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_cost_override_for_maintenance_key_is_422(client: TestClient, db_session: Session) -> None:
    body = {
        **VEHICLE_BODY_WITH_SELECTION,
        "cost_overrides": [{"technical_key": "all_season_tires", "amount": 1000}],
    }
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_cost_override_with_partial_interval_is_422(client: TestClient, db_session: Session) -> None:
    body = {
        **VEHICLE_BODY_WITH_SELECTION,
        "cost_overrides": [{"technical_key": "mandatory_liability_insurance", "amount": 60000, "interval_value": 6}],
    }
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_cost_overrides_without_template_is_422(client: TestClient, db_session: Session) -> None:
    body = {
        "name": "My House",
        "type": "house",
        "cost_overrides": [{"technical_key": "mandatory_liability_insurance", "amount": 1000}],
    }
    response = client.post("/api/assets", json=body)

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_create_vehicle_with_eur_currency_clones_eur_template_amounts(
    client: TestClient, db_session: Session
) -> None:
    assert client.put("/api/users/me/settings", json={"default_currency": "EUR", "language": "en"}).status_code == 200
    response = client.post("/api/assets", json=VEHICLE_BODY_WITH_SELECTION)

    assert response.status_code == 201
    asset = db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).one()
    liability = db_session.scalars(
        select(TimeBasedCost).where(
            TimeBasedCost.asset_id == asset.id, TimeBasedCost.technical_key == "mandatory_liability_insurance"
        )
    ).one()
    assert liability.amount == 125
    reserve = db_session.scalars(select(UsageBasedCost).where(UsageBasedCost.asset_id == asset.id)).one()
    assert reserve.amount_per_unit == Decimal("0.025")
