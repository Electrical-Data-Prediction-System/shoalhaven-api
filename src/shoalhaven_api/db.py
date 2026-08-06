import datetime
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from os import getenv
from dotenv import load_dotenv
from pymongo.errors import BulkWriteError
from shoalhaven_api.meter import Meter

load_dotenv()


# MongoDB client setup
uri = getenv("MONGODB_CONNECTION_STRING")
client = MongoClient(uri, server_api=ServerApi("1"))

db = client.get_database("hydrochart")
meters = db.get_collection("meter")
readings = db.get_collection("reading")


def testPing() -> None:
    try:
        client.admin.command("ping")
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)


def formatISOAsMonth(iso: str) -> str:
    dt = datetime.datetime.fromisoformat(iso)
    month = dt.strftime("%B")

    return month

def meterFindOne(query: dict) -> dict | None:
    result = meters.find_one(query)
    return result


def meterFindAll(query: dict) -> list[dict]:
    results = meters.find(query)
    return list(results)


def meterFindAllAsClass(query: dict) -> list[Meter]:
    # Fetch dict meter objects
    results = meterFindAll(query)
    meters = []

    # Parse into python Meter class
    for meter in results:
        newMeter = Meter(meter["_id"], meter["location"], meter["type"], meter["unit"])
        meters.append(newMeter)

    return meters


def meterUpsert(query: dict, data: dict) -> None:
    meters.replace_one(query, data, upsert=True)


def aggregateReadingsBetween(
    startDate: datetime.date | None = None,
    endDate: datetime.date = datetime.datetime.now(),
) -> list[dict]:
    query = {}

    if startDate is None:
        startDate = endDate - datetime.timedelta(days=365)

    start = (
        startDate
        if isinstance(startDate, datetime.datetime)
        else datetime.datetime.combine(startDate, datetime.time.min)
    )
    end = (
        endDate
        if isinstance(endDate, datetime.datetime)
        else datetime.datetime.combine(endDate, datetime.time.max)
    )

    query["timestamp"] = {"$gte": start, "$lte": end}

    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": {"$dateTrunc": {"date": "$timestamp", "unit": "month"}},
                "KWH": {"$sum": "$kwh"},
            }
        },
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "x": "$_id", "y": "$KWH"}},
    ]
    results = list(readings.aggregate(pipeline))

    formatted = []
    formatted.append({"id": "power"})
    formatted.append({"data": results})

    return formatted


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


def aggregateMeterPowerBetween(
    meterId: str | None = None,
    startDate: datetime.date | None = None,
    endDate: datetime.date | None = None,
) -> list[dict]:
    query = {}

    if meterId:
        query["_meterId"] = meterId
    if endDate is None:
        endDate = datetime.date.today()
    if startDate is None:
        startDate = endDate - datetime.timedelta(days=365)

    start = (
        startDate
        if isinstance(startDate, datetime.datetime)
        else datetime.datetime.combine(startDate, datetime.time.min)
    )
    end = (
        endDate
        if isinstance(endDate, datetime.datetime)
        else datetime.datetime.combine(endDate, datetime.time.max)
    )

    query["timestamp"] = {"$gte": start, "$lte": end}

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$_meterId", "KWH": {"$sum": "$kwh"}}},
        {
            "$project": {
                "_id": 0,
                "name": "$_id",
                "KWH": 1,
                "KPI": "4,554",
                "bounceRate": "45%",
            }
        },
    ]

    results = readings.aggregate(pipeline)

    return list(results)


def aggregateAllMeterPowerBetween(
    startDate: datetime.date | None = None,
    endDate: datetime.date | None = None,
) -> list[dict]:
    query = {}

    if endDate is None:
        endDate = datetime.date.today()
    if startDate is None:
        startDate = endDate - datetime.timedelta(days=365)

    start = (
        startDate
        if isinstance(startDate, datetime.datetime)
        else datetime.datetime.combine(startDate, datetime.time.min)
    )
    end = (
        endDate
        if isinstance(endDate, datetime.datetime)
        else datetime.datetime.combine(endDate, datetime.time.max)
    )

    query["timestamp"] = {"$gte": start, "$lte": end}

    results = readings.aggregate(
        [
            {"$match": query},
            {"$group": {"_id": "$_meterId", "KWH": {"$sum": "$kwh"}}},
            {
                "$project": {
                    "_id": 0,
                    "name": "$_id",
                    "KWH": 1,
                    "KPI": "4,554",
                    "bounceRate": "45%",
                }
            },
        ]
    )

    return list(results)


def readingInsertMany(data: list[dict]) -> tuple[int, int]:
    try:
        res = readings.insert_many(data, ordered=False)
        return len(res.inserted_ids), 0
    except BulkWriteError as e:
        return e.details["nInserted"], len(data) - e.details["nInserted"]
