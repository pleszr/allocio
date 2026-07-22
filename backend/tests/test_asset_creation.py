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
    "vehicle": {"year": 2018, "make": "Toyota", "model": "Corolla", "starting_odometer": 120000},
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
    assert payload["profile"]["make"] == "Toyota"
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


def test_create_asset_rolls_back_on_failure(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced failure mid-transaction")

    monkeypatch.setattr("app.services.asset_service.insert_asset_dependents", boom)

    response = client.post("/api/assets", json=VEHICLE_BODY)

    assert response.status_code == 500
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []
    assert db_session.scalars(select(Bucket)).all() == []
    assert db_session.scalars(select(TimeBasedCost)).all() == []


def test_create_asset_missing_name_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json={"type": "house"})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_create_asset_missing_type_without_template_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json={"name": "Nameless type"})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_vehicle_block_without_template_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/assets", json={"name": "My Car", "type": "vehicle", "vehicle": {"make": "Toyota"}})

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
