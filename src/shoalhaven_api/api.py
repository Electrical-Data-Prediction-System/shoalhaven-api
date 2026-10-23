from datetime import UTC, datetime, timedelta
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import shoalhaven_api.db as db
from shoalhaven_api.geocoding import geocodeLocationString
from shoalhaven_api.schemas import ChartResponse, Meter, MeterResponse, Reading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
)


@app.get("/")
async def root():
    return {"message": "Hello World"}


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


@app.get("/meters/power/aggregate-power", response_model=ChartResponse)
def getAllAggregatedMeterPower(
    start: datetime | None = None, end: datetime | None = None
) -> ChartResponse:
    results = db.aggregateAllMeterPowerBetween(start, end)

    return ChartResponse.model_validate(results)


@app.get("/meters/{meter_id}/aggregate-power", response_model=ChartResponse)
def getAggregatedMeterPower(
    meter_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: Literal["5m", "week", "month", "year"] | None = None,
) -> ChartResponse:
    if interval is not None:
        results = db.aggregateMeterPowerByInterval(meter_id, interval, start, end)
    else:
        results = db.aggregateMeterPowerBetween(meter_id, start, end)

    return ChartResponse.model_validate(results)


@app.get("/meters/{meter_id}/readings/latest")
def getLatestMeterReading(meter_id: str) -> dict[str, datetime | None]:
    return {"timestamp": db.readingLatestTimestamp(meter_id)}


@app.get("/locations/geocode/{query}")
def formatLocation(query: str) -> dict:
    location = geocodeLocationString(query)

    return location.to_dict()


# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/meters/{meter_id}/readings", response_model=list[Reading])
def getReadingsBetween(
    meter_id: str,
    start: datetime,
    end: datetime | None = None,
) -> list[Reading]:
    if not end:
        end = datetime.now(UTC)
    if end <= start:
        raise HTTPException(
            status_code=400, detail="Start date cannot be ahead of end date"
        )

    results = db.readingsGetBetween(start, end, meter_id)

    return [Reading.model_validate(r) for r in results]


# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/readings/aggregate", response_model=ChartResponse)
def sumReadingsBetween(
    start: datetime | None = None, end: datetime | None = None
) -> ChartResponse:
    if not end:
        end = datetime.now(UTC)
    if start is None:
        start = end - timedelta(days=365)

    if end <= start:
        raise HTTPException(
            status_code=400, detail="Start date cannot be ahead of end date"
        )

    results = db.aggregateReadingsBetween(start, end)

    return ChartResponse.model_validate(results)
