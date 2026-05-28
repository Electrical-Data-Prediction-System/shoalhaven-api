from fastapi import FastAPI, HTTPException
import meter

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/getMeterObject/{meter_id}")
def getMeterObject(meter_id: str):
    meterObject = {}
    try:
        meterObject = meter.mappings[meter_id]
        return {"meterObject": meterObject}
    except KeyError:
        raise HTTPException(status_code=404, detail="Meter ID not found!")
