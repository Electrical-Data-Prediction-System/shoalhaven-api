import datetime
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from os import getenv
from dotenv import load_dotenv
from pymongo.errors import BulkWriteError

load_dotenv()
testing = not bool(getenv("PRODUCTION"))


# MongoDB client setup
uri = getenv("MONGODB_CONNECTION_STRING")
client = MongoClient(uri, server_api=ServerApi("1"))

# DB instance setup, fall to testing if needed.
db = client.get_database("hydrochart_test" if testing else "hydrochart")
meters = db.get_collection("meter")
readings = db.get_collection("reading")


def testPing() -> None:
    try:
        client.admin.command("ping")
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)


def meterFindAll(query: dict) -> list[dict]:
    results = meters.find(query)
    return list(results)


def meterUpsert(query: dict, data: dict) -> None:
    meters.replace_one(query, data, upsert=True)


def readingsGetBetween(
    startDate: datetime.date,
    endDate: datetime.date = datetime.datetime.now(),
    meter_id: str | None = None,
) -> list[dict]:
    query = {}

    query["timestamp"] = {"$gte": startDate, "$lte": endDate}
    if meter_id:
        query["_meterId"] = meter_id

    print(query)

    results = readings.find(query, {"_id": 0})

    return list(results)


def readingInsertMany(data: list[dict]) -> tuple[int, int]:
    try:
        res = readings.insert_many(data, ordered=False)
        return len(res.inserted_ids), 0
    except BulkWriteError as e:
        return e.details["nInserted"], len(data) - e.details["nInserted"]
