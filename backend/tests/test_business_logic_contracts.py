"""Regression coverage for backend-owned calculations and asset capabilities (issue #99)."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_monthly_cost_annualizes_exactly_and_latest_modeled_expense_rolls_reference(
    client: TestClient, db_session: Session
) -> None:
    asset_id = client.post("/api/assets", json={"name": "Home", "type": "house"}).json()["asset"]["id"]
    created = client.post(
        f"/api/assets/{asset_id}/time-based-costs",
        json={"label": "Monthly", "amount": "100.00", "interval_value": 1, "interval_unit": "months"},
    )
    assert created.status_code == 201
    row = created.json()
    assert Decimal(row["reference_amount"]) == Decimal("100.00")
    assert Decimal(row["annualized_amount"]) == Decimal("1200.00")
    assert Decimal(row["daily_rate"]) == Decimal("3")

    bucket = db_session.scalars(select(Bucket).where(Bucket.asset_id == uuid.UUID(asset_id))).one()
    db_session.add(
        ExpenseEvent(
            bucket_id=bucket.id,
            event_date=date.today(),
            kind="modeled",
            amount=Decimal("150.00"),
            paid_out_of_pocket=Decimal(0),
            source_type="time_based_cost",
            source_id=uuid.UUID(row["id"]),
        )
    )
    db_session.flush()

    listed = client.get(f"/api/assets/{asset_id}/time-based-costs").json()[0]
    assert Decimal(listed["reference_amount"]) == Decimal("150.00")
    assert Decimal(listed["annualized_amount"]) == Decimal("1800.00")
    assert Decimal(listed["daily_rate"]) == Decimal("5")

    updated = client.patch(
        f"/api/assets/{asset_id}/time-based-costs/{row['id']}",
        json={"amount": "200.00"},
    ).json()
    assert Decimal(updated["amount"]) == Decimal("200.00")
    assert Decimal(updated["reference_amount"]) == Decimal("150.00")
    assert Decimal(updated["annualized_amount"]) == Decimal("1800.00")


def test_tracks_usage_follows_profile_not_freeform_type(client: TestClient) -> None:
    vehicle_id = client.post(
        "/api/assets",
        json={"name": "Vehicle", "template": "vehicle", "vehicle": {"starting_odometer": 42}},
    ).json()["asset"]["id"]
    misleading_bare_id = client.post(
        "/api/assets", json={"name": "Display-only car", "type": "car"}
    ).json()["asset"]["id"]

    assert client.get(f"/api/assets/{vehicle_id}").json()["tracks_usage"] is True
    bare = client.get(f"/api/assets/{misleading_bare_id}").json()
    assert bare["type"] == "car"
    assert bare["tracks_usage"] is False
    assert bare["current_usage"] is None

    preview = client.post(
        f"/api/assets/{misleading_bare_id}/check-ins/preview",
        json={"period_end": date.today().isoformat()},
    )
    assert preview.status_code == 200
    assert preview.json()["usage_start"] is None
    assert preview.json()["usage_end"] is None
    assert preview.json()["usage_amount"] is None

    missing_vehicle_usage = client.post(
        f"/api/assets/{vehicle_id}/check-ins/preview",
        json={"period_end": date.today().isoformat()},
    )
    assert missing_vehicle_usage.status_code == 422


def test_allocation_estimate_combines_template_override_and_custom_row_without_persistence(
    client: TestClient, db_session: Session
) -> None:
    models = (Asset, Bucket, TimeBasedCost, UsageBasedCost, MaintenanceItem, CheckIn, AllocationEvent, ExpenseEvent)
    before = {model: _count(db_session, model) for model in models}
    response = client.post(
        "/api/allocation-estimates",
        json={
            "template": "vehicle",
            "selected_cost_keys": ["mandatory_liability_insurance", "usage_based_reserve"],
            "cost_overrides": [
                {
                    "technical_key": "mandatory_liability_insurance",
                    "amount": "100.00",
                    "interval_value": 1,
                    "interval_unit": "months",
                },
                {"technical_key": "usage_based_reserve", "amount": "12.00"},
            ],
            "custom_time_based_costs": [
                {
                    "client_key": "draft-1",
                    "label": "Annual custom",
                    "amount": "1200.00",
                    "interval_value": 1,
                    "interval_unit": "years",
                }
            ],
        },
    )

    assert response.status_code == 200
    estimate = response.json()
    assert [line["key"] for line in estimate["lines"]] == [
        "mandatory_liability_insurance",
        "draft-1",
    ]
    assert Decimal(estimate["yearly_total"]) == Decimal("2400.00")
    assert Decimal(estimate["monthly_total"]) == Decimal("200.00")
    assert Decimal(estimate["daily_total"]) == Decimal("7")
    assert {model: _count(db_session, model) for model in models} == before


def test_allocation_estimate_empty_and_invalid_inputs(client: TestClient) -> None:
    empty = client.post("/api/allocation-estimates", json={})
    assert empty.status_code == 200
    assert empty.json()["lines"] == []
    assert Decimal(empty.json()["yearly_total"]) == 0

    template_default = client.post(
        "/api/allocation-estimates",
        json={
            "template": "vehicle",
            "selected_cost_keys": ["mandatory_liability_insurance"],
        },
    )
    assert template_default.status_code == 200
    assert Decimal(template_default.json()["lines"][0]["reference_amount"]) == Decimal("50119.00")
    assert Decimal(template_default.json()["yearly_total"]) == Decimal("50119.00")

    unknown = client.post(
        "/api/allocation-estimates",
        json={"template": "vehicle", "selected_cost_keys": ["flux_capacitor"]},
    )
    assert unknown.status_code == 422

    invalid_interval = client.post(
        "/api/allocation-estimates",
        json={
            "custom_time_based_costs": [
                {
                    "client_key": "bad",
                    "label": "Bad",
                    "amount": "10.00",
                    "interval_value": 0,
                    "interval_unit": "months",
                }
            ]
        },
    )
    assert invalid_interval.status_code == 422


def test_house_allocation_estimate_defaults_overrides_and_template_isolation_are_persistence_free(
    client: TestClient, db_session: Session
) -> None:
    models = (
        Asset,
        Bucket,
        TimeBasedCost,
        UsageBasedCost,
        MaintenanceItem,
        CheckIn,
        AllocationEvent,
        ExpenseEvent,
    )
    before = {model: _count(db_session, model) for model in models}
    house_keys = [
        "building_tax",
        "home_insurance",
        "boiler_cleaning",
        "air_conditioner_cleaning",
    ]

    untouched = client.post(
        "/api/allocation-estimates",
        json={"template": "house", "selected_cost_keys": house_keys},
    )
    assert untouched.status_code == 200
    payload = untouched.json()
    assert [line["key"] for line in payload["lines"]] == [*house_keys, "manual_extra"]
    assert Decimal(payload["yearly_total"]) == Decimal("414000.00")
    assert Decimal(payload["monthly_total"]) == Decimal("34500.00")
    assert Decimal(payload["daily_total"]) == Decimal("1134")
    assert {model: _count(db_session, model) for model in models} == before

    without_buffer = client.post(
        "/api/allocation-estimates",
        json={
            "template": "house",
            "selected_cost_keys": house_keys,
            "manual_extra_monthly": "0",
        },
    )
    assert without_buffer.status_code == 200
    assert [line["key"] for line in without_buffer.json()["lines"]] == house_keys
    assert Decimal(without_buffer.json()["yearly_total"]) == Decimal("198000.00")
    assert Decimal(without_buffer.json()["monthly_total"]) == Decimal("16500.00")
    assert {model: _count(db_session, model) for model in models} == before

    overridden_buffer = client.post(
        "/api/allocation-estimates",
        json={
            "template": "house",
            "selected_cost_keys": house_keys,
            "manual_extra_monthly": "1000",
        },
    )
    assert overridden_buffer.status_code == 200
    assert overridden_buffer.json()["lines"][-1]["key"] == "manual_extra"
    assert Decimal(overridden_buffer.json()["lines"][-1]["monthly_amount"]) == Decimal("1000.00")
    assert Decimal(overridden_buffer.json()["yearly_total"]) == Decimal("210000.00")
    assert {model: _count(db_session, model) for model in models} == before

    for body in (
        {"template": "house", "selected_cost_keys": ["vehicle_tax"]},
        {"template": "vehicle", "selected_cost_keys": ["building_tax"]},
        {"template": "house", "manual_extra_monthly": "-1"},
    ):
        response = client.post("/api/allocation-estimates", json=body)
        assert response.status_code == 422
        assert {model: _count(db_session, model) for model in models} == before


def test_pet_allocation_estimate_defaults_overrides_and_template_isolation_are_persistence_free(
    client: TestClient, db_session: Session
) -> None:
    models = (
        Asset,
        Bucket,
        TimeBasedCost,
        UsageBasedCost,
        MaintenanceItem,
        CheckIn,
        AllocationEvent,
        ExpenseEvent,
    )
    before = {model: _count(db_session, model) for model in models}
    pet_keys = ["pet_insurance", "annual_vaccinations"]

    for body in (
        {"template": "pet", "selected_cost_keys": pet_keys},
        {
            "template": "pet",
            "selected_cost_keys": pet_keys,
            "manual_extra_monthly": "0",
        },
    ):
        response = client.post("/api/allocation-estimates", json=body)
        assert response.status_code == 200
        payload = response.json()
        assert [line["key"] for line in payload["lines"]] == pet_keys
        assert Decimal(payload["yearly_total"]) == Decimal("50000.00")
        assert Decimal(payload["monthly_total"]) == Decimal("4167")
        assert Decimal(payload["daily_total"]) == Decimal("137")
        assert {model: _count(db_session, model) for model in models} == before

    overridden = client.post(
        "/api/allocation-estimates",
        json={
            "template": "pet",
            "selected_cost_keys": ["annual_vaccinations"],
            "cost_overrides": [
                {
                    "technical_key": "annual_vaccinations",
                    "amount": "24000",
                    "interval_value": 6,
                    "interval_unit": "months",
                }
            ],
        },
    )
    assert overridden.status_code == 200
    payload = overridden.json()
    assert [line["key"] for line in payload["lines"]] == ["annual_vaccinations"]
    assert Decimal(payload["lines"][0]["reference_amount"]) == Decimal("24000.00")
    assert Decimal(payload["yearly_total"]) == Decimal("48000.00")
    assert Decimal(payload["monthly_total"]) == Decimal("4000.00")
    assert Decimal(payload["daily_total"]) == Decimal("132")
    assert {model: _count(db_session, model) for model in models} == before

    for body in (
        {"template": "pet", "selected_cost_keys": ["vehicle_tax"]},
        {"template": "pet", "selected_cost_keys": ["building_tax"]},
    ):
        response = client.post("/api/allocation-estimates", json=body)
        assert response.status_code == 422
        assert {model: _count(db_session, model) for model in models} == before
