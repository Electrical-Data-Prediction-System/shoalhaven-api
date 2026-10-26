import time
from datetime import UTC, datetime, timedelta
from os import getenv
from typing import Any, Literal

import httpx

import shoalhaven_api.db as db

BASE_URL = "https://api.openelectricity.org.au/v4"

SERIES = Literal["price", "demand", "solar_rooftop", "solar_utility", "gullen_solar"]

# What to request from OpenElectricity for each series we cache
SERIES_CONFIG: dict[str, dict[str, Any]] = {
    "price": {
        "path": "/market/network/NEM",
        "params": {"metrics": "price", "network_region": "NSW1"},
        "unit": "$/MWh",
    },
    "demand": {
        "path": "/market/network/NEM",
        "params": {"metrics": "demand", "network_region": "NSW1"},
        "unit": "MW",
    },
    "solar_rooftop": {
        "path": "/data/network/NEM",
        "params": {"metrics": "power", "network_region": "NSW1", "fueltech": "solar_rooftop"},
        "unit": "MW",
    },
    "solar_utility": {
        "path": "/data/network/NEM",
        "params": {"metrics": "power", "network_region": "NSW1", "fueltech": "solar_utility"},
        "unit": "MW",
    },
    # Gullen Range Solar Farm (10 MW, near Goulburn), used to simulate a council solar array
    "gullen_solar": {
        "path": "/data/facilities/NEM",
        "params": {"metrics": "power", "unit_code": "GULLRSF1"},
        "unit": "MW",
    },
}

INTERVAL = "30m"
# The free tier allows 16 days of 30 minute data per request
CHUNK = timedelta(days=15)


def fetch_series(
    series: str,
    start: datetime,
    end: datetime,
    client: httpx.Client | None = None,
    pause: float = 0.5,
) -> list[dict]:
    """Download one series between two NEM-time dates as [{series, timestamp, value}]"""
    config = SERIES_CONFIG[series]
    client = client or _client()

    docs = []
    chunk_start = start
    while chunk_start < end:
        # The docs say date_end is inclusive, but in practice it's exclusive, so chunks can share a boundary
        chunk_end = min(chunk_start + CHUNK, end)
        response = client.get(config["path"], params={
            **config["params"],
            "interval": INTERVAL,
            "date_start": chunk_start.isoformat(),
            "date_end": chunk_end.isoformat(),
        })
        # 404 means no records in this window, e.g. the facility wasn't reporting
        if response.status_code != 404:
            response.raise_for_status()
            docs.extend(parse_response(series, response.json()))

        chunk_start += CHUNK
        time.sleep(pause)

    return docs


def parse_response(series: str, payload: dict) -> list[dict]:
    docs = []
    for timeseries in payload.get("data") or []:
        for result in timeseries.get("results", []):
            for timestamp, value in result.get("data", []):
                if value is None:
                    continue
                docs.append({
                    "series": series,
                    "timestamp": datetime.fromisoformat(timestamp),
                    "value": float(value),
                    "unit": SERIES_CONFIG[series]["unit"],
                })
    return docs


def push_market(
    start: datetime,
    end: datetime,
    series: list[str] | None = None,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """Fetch each series and upsert it into the market collection. Returns rows saved per series"""
    counts = {}
    for name in series or list(SERIES_CONFIG):
        docs = fetch_series(name, start, end, client)
        db.marketUpsertMany(docs)
        counts[name] = len(docs)
    return counts


def price_stats(rows: list[dict]) -> dict[str, float | int | None]:
    """Summary of cached price rows for the stat cards ($/MWh)"""
    prices = [r["value"] for r in rows]
    if not prices:
        return {"count": 0, "average": None, "max": None, "min": None,
                "negativeShare": None, "middayAverage": None, "eveningAverage": None}

    def average_between(start_hour: int, end_hour: int) -> float | None:
        values = [r["value"] for r in rows if start_hour <= _nem_hour(r["timestamp"]) < end_hour]
        return round(sum(values) / len(values), 2) if values else None

    return {
        "count": len(prices),
        "average": round(sum(prices) / len(prices), 2),
        "max": round(max(prices), 2),
        "min": round(min(prices), 2),
        "negativeShare": round(sum(p < 0 for p in prices) / len(prices) * 100, 1),
        # Solar peak vs the evening demand peak
        "middayAverage": average_between(10, 15),
        "eveningAverage": average_between(17, 21),
    }


def _nem_hour(timestamp: datetime) -> int:
    """Hour of day in NEM time. Mongo returns naive UTC datetimes"""
    utc = timestamp if timestamp.tzinfo is None else timestamp.astimezone(UTC).replace(tzinfo=None)
    return (utc + timedelta(hours=10)).hour


def _client() -> httpx.Client:
    key = getenv("OPENELECTRICITY_API_KEY")
    if not key:
        raise RuntimeError("OPENELECTRICITY_API_KEY is not set in .env")

    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
