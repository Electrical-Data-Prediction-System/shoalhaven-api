from fastapi.testclient import TestClient

import shoalhaven_api.api as api_module

client = TestClient(api_module.app)


def test_health_check():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_search_meters_escapes_search_input(monkeypatch):
    captured = {}
    meter = {
        "_id": "meter-1",
        "location": {
            "fullAddress": "10 Main Street, Nowra NSW 2541",
            "street": "10 Main Street",
            "postcode": "2541",
            "place": "Nowra",
            "region": "NSW",
            "country": "Australia",
            "coordinates": [150.6, -34.9],
        },
        "type": "electricity",
        "unit": "kWh",
    }

    def find_all(query):
        captured["query"] = query
        return [meter]

    monkeypatch.setattr(api_module.db, "meterFindAll", find_all)

    response = client.get("/meters", params={"location": "Nowra.*"})

    assert response.status_code == 200
    assert response.json()[0]["_id"] == "meter-1"
    assert captured["query"]["$or"][0]["location.fullAddress"]["$regex"] == r"Nowra\.\*"


def test_get_unknown_meter_returns_404(monkeypatch):
    monkeypatch.setattr(api_module.db, "meterFindOne", lambda query: None)

    response = client.get("/meters/missing-meter")

    assert response.status_code == 404
    assert response.json()["detail"] == "No meters found"


def test_meter_aggregate_returns_chart_response(monkeypatch):
    expected = {"series": [{"name": "KWH", "data": [{"x": "2026-01-01", "y": 12.5}]}]}
    monkeypatch.setattr(api_module.db, "aggregateMeterPowerByInterval", lambda *args: expected)

    response = client.get(
        "/meters/meter-1/aggregate-power",
        params={"interval": "month", "start": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_meter_aggregate_rejects_unknown_interval():
    response = client.get("/meters/meter-1/aggregate-power", params={"interval": "quarter"})

    assert response.status_code == 422


def test_readings_rejects_end_before_start():
    response = client.get(
        "/meters/meter-1/readings",
        params={"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Start date cannot be ahead of end date"
