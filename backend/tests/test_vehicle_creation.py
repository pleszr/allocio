import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket, VehicleProfile
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost
from tests.conftest import TEST_USER_ID

VALID_BODY = {"name": "My Car", "year": 2018, "make": "Toyota", "model": "Corolla", "starting_odometer": 120000}


def test_create_vehicle_happy_path(client: TestClient) -> None:
    response = client.post("/api/vehicles", json=VALID_BODY)

    assert response.status_code == 201
    assert response.headers["Location"].startswith("/api/vehicles/")

    payload = response.json()
    assert payload["asset"]["id"] in response.headers["Location"]
    assert len(payload["time_based_costs"]) == 6
    assert len(payload["usage_based_costs"]) == 1
    assert len(payload["maintenance_items"]) == 14

    all_rows = [*payload["time_based_costs"], *payload["usage_based_costs"], *payload["maintenance_items"]]
    assert all(row["label"] for row in all_rows)

    time_keys = {row["technical_key"] for row in payload["time_based_costs"]}
    assert "mandatory_liability_insurance" in time_keys
    assert payload["usage_based_costs"][0]["technical_key"] == "usage_based_reserve"
    maintenance_keys = {row["technical_key"] for row in payload["maintenance_items"]}
    assert "all_season_tires" in maintenance_keys


def test_create_vehicle_persists_full_record_set(client: TestClient, db_session: Session) -> None:
    client.post("/api/vehicles", json=VALID_BODY)

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
    assert (len(time_based), len(usage_based), len(maintenance)) == (6, 1, 14)


def test_create_vehicle_rolls_back_on_failure(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced failure mid-transaction")

    monkeypatch.setattr("app.services.vehicle_service.insert_vehicle_dependents", boom)

    response = client.post("/api/vehicles", json=VALID_BODY)

    assert response.status_code == 500
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []
    assert db_session.scalars(select(Bucket)).all() == []
    assert db_session.scalars(select(TimeBasedCost)).all() == []


def test_create_vehicle_missing_name_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/vehicles", json={"year": 2018})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []


def test_create_vehicle_negative_odometer_is_422(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/vehicles", json={"name": "My Car", "starting_odometer": -1})

    assert response.status_code == 422
    assert db_session.scalars(select(Asset).where(Asset.user_id == TEST_USER_ID)).all() == []
