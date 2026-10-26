from datetime import UTC, datetime, timedelta

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


def test_all_meter_aggregate_defaults_to_year_before_latest_reading(monkeypatch):
    captured = {}
    latest = datetime(2026, 1, 1, tzinfo=UTC)

    def aggregate_meter_power_rows(meter_ids, interval, start, end):
        captured.update(meter_ids=meter_ids, interval=interval, start=start, end=end)
        return []

    monkeypatch.setattr(api_module.db, "aggregateMeterPowerRows", aggregate_meter_power_rows)
    monkeypatch.setattr(api_module.db, "readingLatestTimestamp", lambda meter_id=None: latest)

    response = client.get(
        "/meters/power/aggregate-power",
        params={"interval": "month", "meterIds": "meter-1"},
    )

    assert response.status_code == 200
    assert captured["interval"] == "month"
    assert captured["meter_ids"] == ["meter-1"]
    assert captured["end"] == latest
    assert captured["end"] - captured["start"] == timedelta(days=365)


def test_readings_rejects_end_before_start():
    response = client.get(
        "/meters/meter-1/readings",
        params={"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Start date cannot be ahead of end date"


def test_meter_forecast_returns_saved_forecast(monkeypatch):
    saved = {
        "_id": "meter-1:day",
        "meterId": "meter-1",
        "granularity": "day",
        "model": "timestral-5M",
        "generatedAt": datetime(2026, 10, 1, tzinfo=UTC),
        "anchor": datetime(2026, 9, 30, tzinfo=UTC),
        "points": [{"x": datetime(2026, 9, 30, tzinfo=UTC), "p10": 1.0, "p50": 2.0, "p90": 3.0}],
        "backtest": None,
    }
    captured = {}

    def find_one(meter_id, granularity):
        captured.update(meter_id=meter_id, granularity=granularity)
        return saved

    monkeypatch.setattr(api_module.db, "forecastFindOne", find_one)

    response = client.get("/meters/meter-1/forecast", params={"granularity": "day"})

    assert response.status_code == 200
    assert captured == {"meter_id": "meter-1", "granularity": "day"}
    assert response.json()["points"][0]["p50"] == 2.0


def test_meter_forecast_missing_returns_404(monkeypatch):
    monkeypatch.setattr(api_module.db, "forecastFindOne", lambda *args: None)

    response = client.get("/meters/meter-1/forecast", params={"granularity": "hour"})

    assert response.status_code == 404


def test_meter_totals_default_to_year_before_latest_reading(monkeypatch):
    latest = datetime(2026, 3, 1, tzinfo=UTC)
    captured = {}

    def aggregate_meter_totals(meter_ids, start, end):
        captured.update(meter_ids=meter_ids, start=start, end=end)
        return [{"name": "meter-1", "KWH": 42.5}]

    monkeypatch.setattr(api_module.db, "readingLatestTimestamp", lambda meter_id=None: latest)
    monkeypatch.setattr(api_module.db, "aggregateMeterTotals", aggregate_meter_totals)

    response = client.get("/meters/power/totals")

    assert response.status_code == 200
    assert response.json() == [{"name": "meter-1", "KWH": 42.5}]
    assert captured["end"] == latest
    assert captured["start"] == latest - timedelta(days=365)


def test_meter_map_joins_totals_and_flags_meters_outside_shoalhaven(monkeypatch):
    def meter(meter_id, coordinates):
        return {
            "_id": meter_id,
            "type": "Water Pump Station",
            "location": {"fullAddress": f"{meter_id} Street", "place": "Nowra", "coordinates": coordinates},
            "unit": "kWh",
        }

    monkeypatch.setattr(api_module.db, "readingLatestTimestamp", lambda meter_id=None: datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(api_module.db, "aggregateMeterTotals", lambda *args: [{"name": "nowra", "KWH": 1200.5}])
    monkeypatch.setattr(api_module.db, "meterFindAll", lambda query: [
        meter("nowra", [150.6, -34.87]),
        meter("forbes", [148.0, -33.37]),
    ])

    response = client.get("/meters/map")

    assert response.status_code == 200
    nowra, forbes = response.json()
    assert nowra["totalKwh"] == 1200.5 and nowra["inShoalhaven"] is True
    assert forbes["totalKwh"] is None and forbes["inShoalhaven"] is False
