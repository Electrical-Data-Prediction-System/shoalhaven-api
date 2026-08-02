from datetime import datetime
from fastapi import FastAPI, HTTPException
import shoalhaven_api.db as db
from shoalhaven_api.geocoding import geocodeLocationString

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/getMeterObject/{meter_id}")
def getMeterObject(meter_id: str) -> dict:
    meterObject = db.meterFindAll({"_id": meter_id})

    if meterObject:
        return {"meterObject": meterObject}
    else:
        raise HTTPException(status_code=404, detail="No meters found")


@app.get("/formatLocation/{query}")
def formatLocation(query: str) -> dict:
    location = geocodeLocationString(query)

    return location.to_dict()


# Dates are formated in ISO: 2026-08-03 05:34:37.967019
@app.get("/getReadingsBetween/")
def getReadingsBetween(
    start: datetime, end: datetime | None = None, meter_id: str | None = None
) -> list[dict]:
    if not end:
        end = datetime.now()
    if end <= start:
        raise HTTPException(
            status_code=400, detail="Start date cannot be ahead of end date"
        )

    results = db.readingsGetBetween(start, end, meter_id)

    return list(results)
