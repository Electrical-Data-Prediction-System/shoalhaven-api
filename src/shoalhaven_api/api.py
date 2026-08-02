from fastapi import FastAPI
import shoalhaven_api.db as db
from shoalhaven_api.geocoding import geocodeLocationString

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/getMeterObject/{meter_id}")
def getMeterObject(meter_id: str):
    meterObject = db.meterFindAll({"_id": meter_id})
    return {"meterObject": meterObject}


@app.get("/formatLocation/{query}")
def formatLocation(query: str):
    location = geocodeLocationString(query)

    return location
