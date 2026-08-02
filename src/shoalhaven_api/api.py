from fastapi import FastAPI, HTTPException
import shoalhaven_api.db as db
from shoalhaven_api.geocoding import geocodeLocationString
from shoalhaven_api.location import Location

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
def formatLocation(query: str) -> Location:
    location = geocodeLocationString(query)

    return location
