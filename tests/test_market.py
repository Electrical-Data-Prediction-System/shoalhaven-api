from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

import shoalhaven_api.api as api_module
import shoalhaven_api.market as market

client = TestClient(api_module.app)


def payload(points):
    """OpenElectricity's response shape, trimmed to the parts we read"""
    return {"success": True, "data": [{"metric": "price", "results": [{"name": "price_NSW1", "data": points}]}]}


def test_parse_response_flattens_points_and_skips_gaps():
    docs = market.parse_response("price", payload([
        ["2025-06-01T00:00:00+10:00", 144.4],
        ["2025-06-01T00:30:00+10:00", None],
    ]))

    assert docs == [{
        "series": "price",
        "timestamp": datetime(2025, 5, 31, 14, 0, tzinfo=UTC),
        "value": 144.4,
        "unit": "$/MWh",
    }]


def test_fetch_series_requests_in_back_to_back_chunks():
    requests = []

    def handler(request: httpx.Request):
        requests.append(dict(request.url.params))
        return httpx.Response(200, json=payload([[request.url.params["date_start"] + "+10:00", 1.0]]))

    fake = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))

    docs = market.fetch_series("price", datetime(2025, 1, 1), datetime(2025, 2, 1), fake, pause=0)

    # 31 days in 15 day chunks
    assert [r["date_start"] for r in requests] == [
        "2025-01-01T00:00:00", "2025-01-16T00:00:00", "2025-01-31T00:00:00",
    ]
    # date_end is exclusive, so each chunk ends where the next starts
    assert requests[0]["date_end"] == "2025-01-16T00:00:00"
    assert requests[-1]["date_end"] == "2025-02-01T00:00:00"
    assert requests[0]["network_region"] == "NSW1" and requests[0]["interval"] == "30m"
    assert len(docs) == 3


def test_fetch_series_treats_404_as_no_data():
    fake = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(lambda r: httpx.Response(404)))

    assert market.fetch_series("gullen_solar", datetime(2025, 1, 1), datetime(2025, 1, 2), fake, pause=0) == []


def test_price_stats_splits_midday_and_evening():
    # Naive UTC, as Mongo returns it: 02:00 UTC is midday NEM, 08:00 UTC is 6pm NEM
    rows = [
        {"timestamp": datetime(2025, 6, 1, 2), "value": -20.0},
        {"timestamp": datetime(2025, 6, 1, 3), "value": 0.0},
        {"timestamp": datetime(2025, 6, 1, 8), "value": 300.0},
        {"timestamp": datetime(2025, 6, 1, 15), "value": 80.0},
    ]

    stats = market.price_stats(rows)

    assert stats["negativeShare"] == 25.0
    assert stats["middayAverage"] == -10.0
    assert stats["eveningAverage"] == 300.0
    assert stats["max"] == 300.0 and stats["min"] == -20.0


def test_market_routes_default_to_cached_range(monkeypatch):
    start, end = datetime(2025, 1, 1), datetime(2025, 12, 31, 23, 30)
    captured = {}

    def series_rows(series, s, e, interval, months):
        captured.update(series=series, start=s, end=e, interval=interval, months=months)
        return [{"date": s, "price": 101.5}]

    monkeypatch.setattr(api_module.db, "marketRange", lambda series="price": (start, end))
    monkeypatch.setattr(api_module.db, "marketSeriesRows", series_rows)

    response = client.get("/market/series", params={"series": ["price", "solar_rooftop"], "months": [12, 1, 2]})

    assert response.status_code == 200
    assert response.json()[0]["price"] == 101.5
    assert captured == {
        "series": ["price", "solar_rooftop"], "start": start, "end": end, "interval": "day", "months": [12, 1, 2],
    }


def test_market_routes_explain_when_nothing_is_cached(monkeypatch):
    monkeypatch.setattr(api_module.db, "marketRange", lambda series="price": None)

    response = client.get("/market/stats")

    assert response.status_code == 404
    assert "pushMarket" in response.json()["detail"]


def test_market_routes_reject_unknown_series():
    response = client.get("/market/series", params={"series": "coal"})

    assert response.status_code == 422
