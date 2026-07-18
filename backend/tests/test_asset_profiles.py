"""Non-vehicle assets round-trip an opaque subtitle + attributes and surface subtitle on reads (issue #56)."""
from fastapi.testclient import TestClient

VALID_VEHICLE = {
    "name": "My Car",
    "template": "vehicle",
    "vehicle": {"year": 2018, "make": "Toyota", "model": "Corolla", "starting_odometer": 120000},
}


def test_house_asset_stores_subtitle_and_attributes(client: TestClient) -> None:
    body = {
        "name": "Cedar St.",
        "type": "house",
        "subtitle": "2-bed · Built 1978",
        "attributes": {"built": "1978", "size": "85"},
    }
    created = client.post("/api/assets", json=body)
    assert created.status_code == 201
    asset = created.json()["asset"]
    assert asset["subtitle"] == "2-bed · Built 1978"
    assert asset["attributes"] == {"built": "1978", "size": "85"}

    # The subtitle surfaces on the workspace overview summary for that asset.
    overview = client.get("/api/assets").json()
    summary = next(item for item in overview["assets"] if item["id"] == asset["id"])
    assert summary["subtitle"] == "2-bed · Built 1978"


def test_pet_asset_with_attributes_only_has_null_subtitle(client: TestClient) -> None:
    body = {"name": "Maya", "type": "pet", "attributes": {"breed": "Border Collie", "age": 4}}
    asset = client.post("/api/assets", json=body).json()["asset"]
    assert asset["subtitle"] is None
    assert asset["attributes"] == {"breed": "Border Collie", "age": 4}


def test_vehicle_create_unchanged_and_can_carry_subtitle(client: TestClient) -> None:
    payload = {**VALID_VEHICLE, "subtitle": "2018 · Sedan"}
    created = client.post("/api/assets", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["asset"]["type"] == "vehicle"
    assert body["asset"]["subtitle"] == "2018 · Sedan"
    assert body["profile"]["starting_odometer"] == 120000  # vehicle profile still attached


def test_omitting_subtitle_and_attributes_yields_null(client: TestClient) -> None:
    asset = client.post("/api/assets", json={"name": "Bare", "type": "boat"}).json()["asset"]
    assert asset["subtitle"] is None
    assert asset["attributes"] is None


def test_oversized_attributes_are_rejected(client: TestClient) -> None:
    too_many = {"name": "Big", "type": "house", "attributes": {str(i): i for i in range(31)}}
    assert client.post("/api/assets", json=too_many).status_code == 422

    non_scalar = {"name": "Nested", "type": "house", "attributes": {"nested": {"a": 1}}}
    assert client.post("/api/assets", json=non_scalar).status_code == 422
