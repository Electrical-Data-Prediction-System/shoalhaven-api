from pymongo import MongoClient
from pymongo.server_api import ServerApi
from os import getenv
from dotenv import load_dotenv

load_dotenv()
testing = True


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
    results = meters.find(query, {"_id": 0})
    return list(results)


def meterUpsert(query: dict, data: dict) -> None:
    meters.replace_one(query, data, upsert=True)


def readingInsertMany(data: list[dict]) -> None:
    readings.insert_many(data, ordered=False)
