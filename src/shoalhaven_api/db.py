import datetime
import logging
from datetime import UTC
from os import getenv

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError
from pymongo.server_api import ServerApi

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.DEBUG)

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


def meterFindOne(query: dict) -> dict | None:
    result = meters.find_one(query)
    return result


def meterFindAll(query: dict) -> list[dict]:
    results = meters.find(query)
    return list(results)


def meterUpsert(query: dict, data: dict) -> None:
    meters.replace_one(query, data, upsert=True)


def aggregateReadingsBetween(
    startDate: datetime.datetime | datetime.date | None = None,
    endDate: datetime.datetime | datetime.date | None = None,
) -> dict:
    query = {}

    if endDate is None:
        endDate = datetime.datetime.now(UTC)

    if startDate is None:
        startDate = endDate - datetime.timedelta(days=365)

    start = (
        startDate
        if isinstance(startDate, datetime.datetime)
        else datetime.datetime.combine(startDate, datetime.time.min, UTC)
    )
    end = (
        endDate
        if isinstance(endDate, datetime.datetime)
        else datetime.datetime.combine(endDate, datetime.time.max, UTC)
    )

    query["timestamp"] = {"$gte": start, "$lte": end}

    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": {
                    "$dateTrunc": {
                        "date": "$timestamp",
                        "unit": "month",
                        "timezone": "Australia/Sydney",
                    }
                },
                "KWH": {"$sum": "$kwh"},
            }
        },
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "x": "$_id", "y": "$KWH"}},
    ]
    # results = list(readings.aggregate(pipeline))
    #
    # formatted = []
    # formatted.append({"id": "power"})
    # formatted.append({"data": results})
    # return formatted

    points = list(readings.aggregate(pipeline))

    return {"series": [{"name": "KWH", "data": points}]}


def readingsGetBetween(
    startDate: datetime.date,
    endDate: datetime.datetime | datetime.date | None = None,
    meter_id: str | None = None,
) -> list[dict]:
    query = {}

    if endDate is None:
        endDate = datetime.datetime.now(UTC)

    query["timestamp"] = {"$gte": startDate, "$lte": endDate}
    if meter_id:
        query["_meterId"] = meter_id

    results = readings.find(query, {"_id": 0})

    return list(results)


def readingLatestTimestamp(meterId: str) -> datetime.datetime | None:
    result = readings.find_one(
        {"_meterId": meterId},
        {"_id": 0, "timestamp": 1},
        sort=[("timestamp", -1)],
    )
    return result["timestamp"] if result else None


def aggregateMeterPowerBetween(
    meterId: str | None = None,
    startDate: datetime.date | None = None,
    endDate: datetime.date | None = None,
) -> dict:
    query = {}

    if meterId:
        query["_meterId"] = meterId
    if endDate is None:
        endDate = datetime.datetime.now(UTC).date()
    if startDate is None:
        startDate = endDate - datetime.timedelta(days=365)

    start = (
        startDate
        if isinstance(startDate, datetime.datetime)
        else datetime.datetime.combine(startDate, datetime.time.min, UTC)
    )
    end = (
        endDate
        if isinstance(endDate, datetime.datetime)
        else datetime.datetime.combine(endDate, datetime.time.max, UTC)
    )

    query["timestamp"] = {"$gte": start, "$lte": end}

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$_meterId", "KWH": {"$sum": "$kwh"}}},
        {"$project": {"_id": 0, "x": "$_id", "y": "$KWH"}},
        {"$sort": {"x": 1}},
    ]

    # results = readings.aggregate(pipeline)
    # return list(results)

    points = list(readings.aggregate(pipeline))

    return {"series": [{"name": "KWH", "data": points}]}


def aggregateMeterPowerByInterval(
    meterId: str,
    interval: str,
    startDate: datetime.datetime | None = None,
    endDate: datetime.datetime | None = None,
) -> dict:
    interval_config = {
        "5m": {"unit": "minute", "binSize": 5},
        "week": {"unit": "week", "binSize": 1},
        "month": {"unit": "month", "binSize": 1},
        "year": {"unit": "year", "binSize": 1},
    }
    bucket = interval_config[interval]
    query: dict = {"_meterId": meterId}

    timestamp_filter = {}
    if startDate is not None:
        timestamp_filter["$gte"] = startDate
    if endDate is not None:
        timestamp_filter["$lte"] = endDate
    if timestamp_filter:
        query["timestamp"] = timestamp_filter

    points = list(
        readings.aggregate(
            [
                {"$match": query},
                {
                    "$group": {
                        "_id": {
                            "$dateTrunc": {
                                "date": "$timestamp",
                                **bucket,
                                "timezone": "Australia/Sydney",
                            }
                        },
                        "KWH": {"$sum": "$kwh"},
                    }
                },
                {"$sort": {"_id": 1}},
                {"$project": {"_id": 0, "x": "$_id", "y": "$KWH"}},
            ]
        )
    )

    return {"series": [{"name": "KWH", "data": points}]}


def aggregateAllMeterPowerBetween(
    startDate: datetime.date | None = None,
    endDate: datetime.date | None = None,
) -> dict:
    query = {}

    if endDate is None:
        endDate = datetime.datetime.now(UTC).date()
    if startDate is None:
        startDate = endDate - datetime.timedelta(days=365)

    start = (
        startDate
        if isinstance(startDate, datetime.datetime)
        else datetime.datetime.combine(startDate, datetime.time.min, UTC)
    )
    end = (
        endDate
        if isinstance(endDate, datetime.datetime)
        else datetime.datetime.combine(endDate, datetime.time.max, UTC)
    )

    logger.debug(str(startDate) + " : " + str(endDate))

    query["timestamp"] = {"$gte": start, "$lte": end}

    results = readings.aggregate(
        [
            {"$match": query},
            {"$group": {"_id": "$_meterId", "KWH": {"$sum": "$kwh"}}},
            {
                "$project": {
                    "_id": 0,
                    "x": "$_id",
                    "y": "$KWH",
                }
            },
            {"$sort": {"x": 1}},
        ]
    )

    points = list(results)

    return {"series": [{"name": "KWH", "data": points}]}


def readingInsertMany(data: list[dict]) -> tuple[int, int]:
    try:
        res = readings.insert_many(data, ordered=False)
        return len(res.inserted_ids), 0
    except BulkWriteError as e:
        return e.details["nInserted"], len(data) - e.details["nInserted"]


def readingUpsertMany(data: list[dict]) -> tuple[int, int]:
    ops = [
        UpdateOne(
            {"_meterId": r["_meterId"], "timestamp": r["timestamp"]},
            {"$setOnInsert": r},
            upsert=True,
        )
        for r in data
    ]
    res = db.readings.bulk_write(ops, ordered=False)
    return res.upserted_count, len(data) - res.upserted_count
