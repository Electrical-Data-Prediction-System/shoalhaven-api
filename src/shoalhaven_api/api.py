from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import shoalhaven_api.db as db
from shoalhaven_api.geocoding import geocodeLocationString
from shoalhaven_api.openelec import test
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
    meter_id: str, start: datetime | None = None, end: datetime | None = None
) -> ChartResponse:
    results = db.aggregateMeterPowerBetween(meter_id, start, end)

    return ChartResponse.model_validate(results)


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


@app.get("/openelec/test", response_model=ChartResponse)
def openelecTest() -> ChartResponse:
    return ChartResponse.model_validate(test())
