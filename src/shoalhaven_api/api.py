from datetime import datetime, timedelta, UTC
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shoalhaven_api.db as db
from shoalhaven_api.geocoding import geocodeLocationString

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/meters/{meter_id}")
def get_meter(meter_id: str) -> dict:
    meterObject = db.meterFindOne({"_id": meter_id})

    if meterObject:
        return {"meterObject": meterObject}
    else:
        raise HTTPException(status_code=404, detail="No meters found")


@app.get("/meters/power/aggregate-power")
def getAllAggregatedMeterPower(
    start: datetime | None = None, end: datetime | None = None
) -> list[dict]:
    results = db.aggregateAllMeterPowerBetween(start, end)

    return results


@app.get("/meters/{meter_id}/aggregate-power")
def getAggregatedMeterPower(
    meter_id: str, start: datetime | None = None, end: datetime | None = None
) -> list[dict]:
    results = db.aggregateMeterPowerBetween(meter_id, start, end)

    return results


@app.get("/locations/geocode/{query}")
def formatLocation(query: str) -> dict:
    location = geocodeLocationString(query)

    return location.to_dict()


# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/meters/{meter_id}/readings")
def getReadingsBetween(
    meter_id: str,
    start: datetime,
    end: datetime | None = None,
) -> list[dict]:
    if not end:
        end = datetime.now(UTC)
    if end <= start:
        raise HTTPException(
            status_code=400, detail="Start date cannot be ahead of end date"
        )

    results = db.readingsGetBetween(start, end, meter_id)

    return list(results)


# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/readings/aggregate")
def sumReadingsBetween(
    start: datetime | None = None, end: datetime | None = None
) -> list[dict]:
    if not end:
        end = datetime.now(UTC)
    if start is None:
        start = end - timedelta(days=365)

    if end <= start:
        raise HTTPException(
            status_code=400, detail="Start date cannot be ahead of end date"
        )

    results = db.aggregateReadingsBetween(start, end)

    return list(results)
