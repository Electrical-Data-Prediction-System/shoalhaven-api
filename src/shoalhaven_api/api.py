from datetime import UTC, datetime, timedelta
import re
from typing import Literal, Any, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import shoalhaven_api.db as db
from shoalhaven_api import market
from shoalhaven_api.geocoding import geocodeLocationString
from shoalhaven_api.schemas import (
    ChartPoint,
    ChartResponse,
    ChartSeries, 
    ForecastResponse,
    MarketProfileRow,
    MarketRow,
    MarketStats,
    Meter,
    MeterPowerRow,
    MeterResponse, 
    MeterTotal,
    Reading,
)

app = FastAPI()

# How far back a single meter's chart looks by default, per bucket size
DEFAULT_RANGE_DAYS = {"5m": 1, "hour": 7, "day": 90, "week": 365, "month": 365, "year": 365}

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
    start, end = validate_date_range(start, end, 365)

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

@app.get("/meters/power/raw-power", response_model=list[MeterPowerRow])
def getRawMeterPower(
    meterIds: list[str] | None = Query(default=None),
    start: datetime | None = None,
    end: datetime | None = None
) -> list[dict[str, Any]]:

    validate_meter_ids(meterIds)
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

def validate_meter_ids(meter_ids: str | list[str] | None = Query(default=None)):
    if meter_ids is not None and not meter_ids:
        raise HTTPException(
            status_code=400, 
            detail="meterIds cannot be an empty list",
        )
        