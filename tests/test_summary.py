from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

import shoalhaven_api.api as api_module
import shoalhaven_api.summary as summary

client = TestClient(api_module.app)


def test_latest_full_month_skips_a_month_that_has_only_started():
    # Data ending at midnight on 1 Jan means December is the last complete month
    assert summary.latest_full_month(datetime(2026, 1, 1, 0, 0)) == datetime(2025, 12, 1)
    # Data stopping mid-December means November is the last complete month
    assert summary.latest_full_month(datetime(2025, 12, 15, 9, 30)) == datetime(2025, 11, 1)
    # The final half hour of December counts as complete
    assert summary.latest_full_month(datetime(2025, 12, 31, 23, 30)) == datetime(2025, 12, 1)


def test_wall_time_to_utc_follows_daylight_saving():
    # January is daylight time (UTC+11), June is standard time (UTC+10)
    assert summary.wall_time_to_utc(datetime(2025, 1, 15, 12, 0)) == datetime(2025, 1, 15, 1, 0)
    assert summary.wall_time_to_utc(datetime(2025, 6, 15, 12, 0)) == datetime(2025, 6, 15, 2, 0)


def test_month_summary_totals_busiest_day_and_wholesale_cost():
    rows = [
        {"timestamp": datetime(2025, 6, 1, 12, 0), "kwh": 100.0},
        {"timestamp": datetime(2025, 6, 2, 12, 0), "kwh": 300.0},
        {"timestamp": datetime(2025, 6, 2, 12, 30), "kwh": 100.0},
        # July, so it's left out
        {"timestamp": datetime(2025, 7, 1, 12, 0), "kwh": 999.0},
    ]
    # Prices keyed by real UTC: midday in June is 02:00 UTC
    prices = {
        datetime(2025, 6, 1, 2, 0): 50.0,
        datetime(2025, 6, 2, 2, 0): 100.0,
        datetime(2025, 6, 2, 2, 30): -20.0,
    }

    result = summary.month_summary(rows, prices, datetime(2025, 6, 1))

    assert result["totalKwh"] == 500.0
    assert result["busiestDay"] == {"date": date(2025, 6, 2), "kwh": 400.0}
    # 100 x 50 + 300 x 100 + 100 x -20, all / 1000
    assert result["wholesaleCost"] == 33.0
    assert result["pricedShare"] == 1.0


def test_month_summary_has_no_cost_without_market_data():
    rows = [{"timestamp": datetime(2025, 6, 1, 12, 0), "kwh": 100.0}]

    result = summary.month_summary(rows, {}, datetime(2025, 6, 1))

    assert result["wholesaleCost"] is None
    assert result["pricedShare"] == 0


def test_power_summary_compares_latest_full_month_with_the_one_before(monkeypatch):
    captured = {}

    def totals(start, end):
        captured.update(start=start, end=end)
        return [
            {"timestamp": datetime(2025, 11, 10, 12, 0), "kwh": 80.0},
            {"timestamp": datetime(2025, 12, 10, 12, 0), "kwh": 100.0},
        ]

    monkeypatch.setattr(api_module.db, "readingLatestTimestamp", lambda meter_id=None: datetime(2026, 1, 1))
    monkeypatch.setattr(api_module.db, "readingTotalsByTimestamp", totals)
    monkeypatch.setattr(api_module.db, "marketFind", lambda *args: [])

    response = client.get("/meters/power/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["current"]["month"].startswith("2025-12-01") and body["current"]["totalKwh"] == 100.0
    assert body["previous"]["month"].startswith("2025-11-01") and body["previous"]["totalKwh"] == 80.0
    assert body["current"]["wholesaleCost"] is None
    assert captured == {"start": datetime(2025, 11, 1), "end": datetime(2026, 1, 1)}
