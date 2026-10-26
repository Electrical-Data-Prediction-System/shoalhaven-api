from datetime import UTC, datetime, timedelta
import re
from typing import Literal, Any, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import shoalhaven_api.db as db
from shoalhaven_api import market, summary
from shoalhaven_api.geocoding import geocodeLocationString
from shoalhaven_api.schemas import (
    ChartPoint,
    ChartResponse,
    ChartSeries, 
    DailyUsage,
    ForecastResponse,
    MarketProfileRow,
    MarketRow,
    MarketStats,
    Meter,
    MeterPowerRow,
    MeterMapPoint,
    MeterResponse, 
    MeterTotal,
    PowerSummary,
    Reading,
)

app = FastAPI()

# How far back a single meter's chart looks by default, per bucket size
DEFAULT_RANGE_DAYS = {"5m": 1, "hour": 7, "day": 90, "week": 365, "month": 365, "year": 365}

# Rough box around the Shoalhaven LGA. Meters outside it were geocoded to the wrong town
SHOALHAVEN_BOUNDS = {"west": 150.2, "east": 151.0, "south": -35.8, "north": -34.6}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
)


@app.get("/")
async def root():
    return {"message": "Hello World"}


# Meters

@app.get("/meters", response_model=list[Meter])
def search_meters(location: str = Query(min_length=2, max_length=100)) -> list[Meter]:
    search_term = location.strip()
    if len(search_term) < 2:
        return []

    pattern = re.escape(search_term)
    query = {
        "$or": [
            {f"location.{field}": {"$regex": pattern, "$options": "i"}}
            for field in ("fullAddress", "street", "postcode", "place", "region", "country")
        ]
    }
    meters = db.meterFindAll(query)

    return [
        Meter.model_validate({
            **meter,
            "_id": str(meter["_id"])
        })
        for meter in meters
    ]

@app.get("/meters/map", response_model=list[MeterMapPoint])
def getMeterMap(
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    # Same default as the totals route: the year before the latest reading
    if end is None:
        end = db.readingLatestTimestamp()
    start, end = validate_date_range(start, end, 365)

    totals = {row["name"]: row["KWH"] for row in db.aggregateMeterTotals(None, start, end)}

    points = []
    for meter in db.meterFindAll({}):
        location = meter["location"]
        lon, lat = location["coordinates"]
        points.append({
            "id": str(meter["_id"]),
            "type": meter["type"],
            "fullAddress": location["fullAddress"],
            "place": location["place"],
            "coordinates": (lon, lat),
            "totalKwh": totals.get(meter["_id"]),
            "inShoalhaven": SHOALHAVEN_BOUNDS["west"] <= lon <= SHOALHAVEN_BOUNDS["east"]
                and SHOALHAVEN_BOUNDS["south"] <= lat <= SHOALHAVEN_BOUNDS["north"],
        })
    return points


# Declared before /meters/{meter_id}, otherwise "daily-usage" would be read as a meter id
@app.get("/meters/daily-usage", response_model=list[DailyUsage])
def getDailyUsage(
    meterIds: list[str] = Query(min_length=1, max_length=100),
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    """Each meter's kWh per local day, for alert limits. Defaults to the year before the latest reading"""
    if end is None:
        # Stop at the start of the latest reading's day, unless that day's last half hour is in,
        # so a partly-read final day doesn't look like a sudden drop in usage
        latest = latest_reading_end(meterIds)
        end = latest.replace(hour=0, minute=0, second=0, microsecond=0)
        if (latest.hour, latest.minute) >= (23, 30):
            end += timedelta(days=1)
    start, end = validate_date_range(start, end, 365)

    return db.meterDailyTotals(meterIds, start, end)


@app.get("/meters/{meter_id}", response_model=MeterResponse)
def get_meter(meter_id: str) -> MeterResponse:
    meterObject = db.meterFindOne({"_id": meter_id})

    if meterObject:
        return MeterResponse(meterObject=Meter.model_validate(meterObject))
    else:
        raise HTTPException(status_code=404, detail="No meters found")


# Power

@app.get("/meters/power/aggregate-power", response_model=list[MeterPowerRow])
def getAllAggregatedMeterPower(
    meterIds: list[str] | None = Query(default=None),
    start: datetime | None = None, 
    end: datetime | None = None,
    interval: db.INTERVAL | None = None,
) -> list[dict[str, Any]]:
    
    validate_meter_ids(meterIds)
    if end is None:
        end = latest_reading_end(meterIds)
    start, end = validate_date_range(start, end, DEFAULT_RANGE_DAYS.get(interval, 365))

    return db.aggregateMeterPowerRows(meterIds, interval, start, end)

@app.get("/meters/power/totals", response_model=list[MeterTotal])
def getMeterTotals(
    meterIds: list[str] | None = Query(default=None),
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:

    validate_meter_ids(meterIds)
    # Data is historical, so default to the year before the latest reading rather than today
    if end is None:
        end = db.readingLatestTimestamp()
    start, end = validate_date_range(start, end, 365)

    return db.aggregateMeterTotals(meterIds, start, end)

@app.get("/meters/power/summary", response_model=PowerSummary)
def getPowerSummary() -> dict[str, Any]:
    """All meters for the latest full month and the month before, for the dashboard's stat cards"""
    latest = db.readingLatestTimestamp()
    if latest is None:
        raise HTTPException(status_code=404, detail="No readings found")

    month = summary.latest_full_month(latest)
    previous = summary.previous_month(month)
    end = summary.next_month(month)

    rows = db.readingTotalsByTimestamp(previous, end)
    # A day either side covers the shift between Sydney time and UTC
    price_rows = db.marketFind(["price"], previous - timedelta(days=1), end + timedelta(days=1))
    prices = {row["timestamp"]: row["value"] for row in price_rows}

    return {
        "current": summary.month_summary(rows, prices, month),
        "previous": summary.month_summary(rows, prices, previous),
    }

@app.get("/meters/power/raw-power", response_model=list[MeterPowerRow])
def getRawMeterPower(
    meterIds: list[str] | None = Query(default=None),
    start: datetime | None = None,
    end: datetime | None = None
) -> list[dict[str, Any]]:

    validate_meter_ids(meterIds)
    if end is None:
        end = latest_reading_end(meterIds)
    start, end = validate_date_range(start, end, 1)

    return db.aggregateMeterPowerRows(meterIds, startDate=start, endDate=end, raw=True)
    

# for compatability reasons
@app.get("/meters/{meter_id}/aggregate-power", response_model=ChartResponse)
def getAggregatedMeterPower(
    meter_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: db.INTERVAL | None = None,
) -> ChartResponse:

    # Data is historical, so count back from the meter's latest reading rather than today
    if end is None:
        end = db.readingLatestTimestamp(meter_id)
    start, end = validate_date_range(start, end, DEFAULT_RANGE_DAYS.get(interval, 30))

    rows = db.aggregateMeterPowerRows(meter_id, interval, start, end)
    
    points = [
        ChartPoint(x=row["date"], y=row[meter_id])
        for row in rows
    ]

    return ChartResponse(
        series=[ChartSeries(name="KWH", data=points)]
    )


# Forecasts

@app.get("/meters/{meter_id}/forecast", response_model=ForecastResponse)
def getMeterForecast(
    meter_id: str,
    granularity: Literal["hour", "day"] = "day",
) -> ForecastResponse:
    forecast = db.forecastFindOne(meter_id, granularity)

    if not forecast:
        raise HTTPException(status_code=404, detail="No forecast found")

    return ForecastResponse.model_validate(forecast)


# Readings

@app.get("/meters/{meter_id}/readings/latest")
def getLatestMeterReading(meter_id: str) -> dict[str, datetime | None]:
    return {"timestamp": db.readingLatestTimestamp(meter_id)}

# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/meters/{meter_id}/readings", response_model=list[Reading])
def getReadingsBetween(
    meter_id: str,
    start: datetime,
    end: datetime | None = None,
) -> list[Reading]:
    start, end = validate_date_range(start, end)

    results = db.readingsGetBetween(start, end, meter_id)
    return [Reading.model_validate(r) for r in results]


# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/readings/aggregate", response_model=ChartResponse)
def sumReadingsBetween(
    start: datetime | None = None, 
    end: datetime | None = None
) -> ChartResponse:
    if end is None:
        end = latest_reading_end()
    start, end = validate_date_range(start, end)
    

    results = db.aggregateReadingsBetween(start, end)
    return ChartResponse.model_validate(results)

    # this is what i would do but we are too far down the rabbit hole now
    # return [ChartPoint.model_validate(point) for point in results]


# Market (cached OpenElectricity data, NSW region)

@app.get("/market/series", response_model=list[MarketRow])
def getMarketSeries(
    series: list[market.SERIES] = Query(default=["price"]),
    start: datetime | None = None,
    end: datetime | None = None,
    interval: Literal["30m", "day", "month"] = "day",
    months: list[int] | None = Query(default=None),
) -> list[dict[str, Any]]:
    start, end = market_date_range(start, end)
    return db.marketSeriesRows(series, start, end, interval, months)


@app.get("/market/daily-profile", response_model=list[MarketProfileRow])
def getMarketDailyProfile(
    series: list[market.SERIES] = Query(default=["price", "solar_rooftop", "solar_utility"]),
    start: datetime | None = None,
    end: datetime | None = None,
    months: list[int] | None = Query(default=None),
) -> list[dict[str, Any]]:
    start, end = market_date_range(start, end)
    return db.marketDailyProfile(series, start, end, months)


@app.get("/market/stats", response_model=MarketStats)
def getMarketStats(
    start: datetime | None = None,
    end: datetime | None = None,
    months: list[int] | None = Query(default=None),
) -> dict[str, Any]:
    start, end = market_date_range(start, end)
    rows = db.marketFind(["price"], start, end, months)
    return {"start": start, "end": end, **market.price_stats(rows)}


# locations

@app.get("/locations/geocode/{query}")
def formatLocation(query: str) -> dict:
    location = geocodeLocationString(query)

    return location.to_dict()


# Helper Functions

def validate_date_range(
        start: datetime | None, 
        end: datetime | None, 
        days: int = 365
) -> tuple[datetime, datetime]:
    if start is not None and end is not None and end <= start:
        raise HTTPException(
            status_code=400,
            detail="Start date must be before end date",
        )

    if end is None:
            end = datetime.now(UTC)

    if start is None:
            start = end - timedelta(days=days)

    return start, end

def market_date_range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    """Default to everything cached, since market data is fetched once from the CLI"""
    if start is None or end is None:
        cached = db.marketRange()
        if cached is None:
            raise HTTPException(status_code=404, detail="No market data cached, run: shoalhaven pushMarket")
        start = start or cached[0]
        end = end or cached[1]

    if end <= start:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    return start, end

def latest_reading_end(meter_ids: list[str] | None = None) -> datetime:
    """Default end for charts: data is historical, so use the latest reading (now if there are none)"""
    if meter_ids:
        timestamps = [t for t in (db.readingLatestTimestamp(m) for m in meter_ids) if t is not None]
        latest = max(timestamps, default=None)
    else:
        latest = db.readingLatestTimestamp()
    return latest or datetime.now(UTC)

def validate_meter_ids(meter_ids: str | list[str] | None = Query(default=None)):
    if meter_ids is not None and not meter_ids:
        raise HTTPException(
            status_code=400, 
            detail="meterIds cannot be an empty list",
        )
        