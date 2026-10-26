
import logging
from datetime import UTC, date, datetime, time, timedelta
from os import getenv
from typing import Any, Literal

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError
from pymongo.server_api import ServerApi

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.DEBUG)

load_dotenv()

# Constants
INTERVAL = Literal["5m", "hour", "day", "week", "month", "year"]

INTERVAL_CONFIG = {
    "5m": {"unit": "minute", "binSize": 5},
    "hour": {"unit": "hour", "binSize": 1},
    "day": {"unit": "day", "binSize": 1},
    "week": {"unit": "week", "binSize": 1},
    "month": {"unit": "month", "binSize": 1},
    "year": {"unit": "year", "binSize": 1},
}


# MongoDB client setup
uri = getenv("MONGODB_CONNECTION_STRING")
environment = getenv("APP_ENV")
client = MongoClient(uri, server_api=ServerApi("1"))

db = client.get_database("demo") if environment == "dev" else client.get_database("hydrochart")
meters = db.get_collection("meter")
readings = db.get_collection("reading")
forecasts = db.get_collection("forecast")
market = db.get_collection("market")

# The NEM runs on Australian Eastern Standard Time all year, with no daylight saving
NEM_TIMEZONE = "+10:00"

# Testing

def testPing() -> None:
    try:
        client.admin.command("ping")
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)



# Meters

def meterFindOne(query: dict) -> dict | None:
    result = meters.find_one(query)
    return result


def meterFindAll(query: dict) -> list[dict]:
    results = meters.find(query)
    return list(results)


def meterUpsert(query: dict, data: dict) -> None:
    meters.replace_one(query, data, upsert=True)



# Power

def aggregateMeterPowerRows(
    meter_ids: list[str] | str | None = None,
    interval: INTERVAL | None = None,
    startDate: datetime | date | None = None,
    endDate: datetime | date | None = None,
    raw: bool = False
) -> list[dict[str, Any]]:
    """Return one row per timestamp, with one column per meter."""

    start, end = _date_range(startDate, endDate)

    query: dict[str, Any] = {
        "timestamp": {"$gte": start, "$lte": end}
    }

    if isinstance(meter_ids, str):
        meter_ids = [meter_ids]

    if meter_ids is not None:
        query["_meterId"] = {"$in": meter_ids}

    date_expression: Any = "$timestamp"

    if not raw and interval is not None:
        bucket = INTERVAL_CONFIG[interval]
        date_expression = {
            "$dateTrunc": {
                "date": "$timestamp",
                **bucket,
                "timezone": "Australia/Sydney",
            }
        }

    value_expression = (
        {"$first": "$kwh"} if raw
        else {"$sum": {"$round": ["$kwh", 5]}}
    )

    pipeline = [
        {"$match": query},

        # Combine readings for each meter and timestamp.
        {
            "$group": {
                "_id": {
                    "meterId": "$_meterId",
                    "date": date_expression,
                },
                "kwh": value_expression,
            } 
        },

        # Collect all meter readings for each timestamp.
        {
            "$group": {
                "_id": "$_id.date",
                "readings": {
                    "$push": {
                        "k": "$_id.meterId",
                        "v": "$kwh",
                    }
                },
            }
        },

        # Sort by timestamp
        {"$sort": {"_id": 1}},

        # Convert readings array into dictionary
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "kwh": {"$round": ["$kwh", 2]},
                "readings": {"$arrayToObject": "$readings"},
            }
        },

        # Return one flat row containing date and meter-ID fields.
        {
            "$replaceRoot": {
                "newRoot": {
                    "$mergeObjects": [
                        {"date": "$date"},
                        "$readings",
                    ]
                }
            }
        },

    ]

    return list(readings.aggregate(pipeline, allowDiskUse=True))



def aggregateMeterTotals(
    meter_ids: list[str] | None = None,
    startDate: datetime | date | None = None,
    endDate: datetime | date | None = None,
) -> list[dict[str, Any]]:
    """Return one kWh total per meter between two dates."""

    start, end = _date_range(startDate, endDate)

    query: dict[str, Any] = {"timestamp": {"$gte": start, "$lte": end}}
    if meter_ids is not None:
        query["_meterId"] = {"$in": meter_ids}

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$_meterId", "KWH": {"$sum": "$kwh"}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "name": "$_id", "KWH": {"$round": ["$KWH", 2]}}},
    ]

    return list(readings.aggregate(pipeline))



# Readings

def aggregateReadingsBetween(
    startDate: datetime | date | None = None,
    endDate: datetime | date | None = None,
) -> dict[str, list[dict[str, Any]]]:
    # -> list[dict[str | datetime, float]]: Optional
    start, end = _date_range(startDate, endDate)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start, "$lte": end}}},
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

    points = list(readings.aggregate(pipeline))
    return {"series": [{"name": "KWH", "data": points}]}

    # optional: flattend return points  


def readingsGetBetween(
    startDate: date | None = None,
    endDate: datetime | date | None = None,
    meter_id: str | None = None,
) -> list[dict]:
    query = {}

    if endDate is None:
        endDate = datetime.now(UTC)

    if startDate is None:
        startDate = endDate - timedelta(days=30)

    query["timestamp"] = {"$gte": startDate, "$lte": endDate}
    
    if meter_id:
        query["_meterId"] = meter_id

    results = readings.find(query, {"_id": 0})

    return list(results)


def readingLatestTimestamp(meterId: str | None = None) -> datetime | None:
    result = readings.find_one(
        {"_meterId": meterId} if meterId else {},
        {"_id": 0, "timestamp": 1},
        sort=[("timestamp", -1)],
    )
    return result["timestamp"] if result else None


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
    res = readings.bulk_write(ops, ordered=False)
    return res.upserted_count, len(data) - res.upserted_count



# Forecasts

def forecastUpsert(doc: dict) -> None:
    forecasts.replace_one({"_id": doc["_id"]}, doc, upsert=True)


def forecastFindOne(meterId: str, granularity: str) -> dict | None:
    return forecasts.find_one({"_id": f"{meterId}:{granularity}"})



# Market

def marketUpsertMany(docs: list[dict]) -> None:
    if not docs:
        return

    market.create_index([("series", 1), ("timestamp", 1)], unique=True)
    ops = [
        UpdateOne(
            {"series": d["series"], "timestamp": d["timestamp"]},
            {"$set": d},
            upsert=True,
        )
        for d in docs
    ]
    market.bulk_write(ops, ordered=False)


def marketRange(series: str = "price") -> tuple[datetime, datetime] | None:
    """First and last cached timestamp for a series"""
    first = market.find_one({"series": series}, {"timestamp": 1}, sort=[("timestamp", 1)])
    last = market.find_one({"series": series}, {"timestamp": 1}, sort=[("timestamp", -1)])
    if not first or not last:
        return None
    return first["timestamp"], last["timestamp"]


def marketFind(
    series: list[str],
    start: datetime,
    end: datetime,
    months: list[int] | None = None,
) -> list[dict]:
    """Raw cached rows, oldest first"""
    return list(market.find(_marketMatch(series, start, end, months), {"_id": 0}).sort("timestamp", 1))


def marketSeriesRows(
    series: list[str],
    start: datetime,
    end: datetime,
    interval: Literal["30m", "day", "month"] = "day",
    months: list[int] | None = None,
) -> list[dict[str, Any]]:
    """One row per bucket with one averaged column per series, e.g. {date, price, solar_rooftop}"""
    date_expression: Any = "$timestamp"
    if interval != "30m":
        date_expression = {"$dateTrunc": {"date": "$timestamp", "unit": interval, "timezone": NEM_TIMEZONE}}

    return list(market.aggregate([
        {"$match": _marketMatch(series, start, end, months)},
        {"$group": {"_id": {"date": date_expression, "series": "$series"}, "value": {"$avg": "$value"}}},
        {"$group": {"_id": "$_id.date", "values": {"$push": {"k": "$_id.series", "v": {"$round": ["$value", 3]}}}}},
        {"$sort": {"_id": 1}},
        {"$replaceRoot": {"newRoot": {"$mergeObjects": [{"date": "$_id"}, {"$arrayToObject": "$values"}]}}},
    ]))


def marketDailyProfile(
    series: list[str],
    start: datetime,
    end: datetime,
    months: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Average of each series for every half hour of the day, e.g. {time: "12:30", price, solar_rooftop}"""
    time_of_day = {"$dateToString": {"date": "$timestamp", "format": "%H:%M", "timezone": NEM_TIMEZONE}}

    return list(market.aggregate([
        {"$match": _marketMatch(series, start, end, months)},
        {"$group": {"_id": {"time": time_of_day, "series": "$series"}, "value": {"$avg": "$value"}}},
        {"$group": {"_id": "$_id.time", "values": {"$push": {"k": "$_id.series", "v": {"$round": ["$value", 3]}}}}},
        {"$sort": {"_id": 1}},
        {"$replaceRoot": {"newRoot": {"$mergeObjects": [{"time": "$_id"}, {"$arrayToObject": "$values"}]}}},
    ]))



# Helper Functions

def _marketMatch(series: list[str], start: datetime, end: datetime, months: list[int] | None) -> dict:
    query: dict[str, Any] = {"series": {"$in": series}, "timestamp": {"$gte": start, "$lte": end}}
    if months:
        query["$expr"] = {"$in": [{"$month": {"date": "$timestamp", "timezone": NEM_TIMEZONE}}, months]}
    return query


def _to_datetime(value: datetime | date, *, end_of_day: bool = False) -> datetime:
    """Convert dates and datetimes into timezone-aware UTC datetimes."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    boundary: time = time.max if end_of_day else time.min
    return datetime.combine(value, boundary, tzinfo=UTC)


def _date_range(start: datetime | date | None, end: datetime | date | None) -> tuple[datetime, datetime]:
    """Apply the default one-year range and normalize its boundaries."""

    end_dt = _to_datetime(end) if end is not None else datetime.now(UTC)

    start_dt = (
        _to_datetime(start)
        if start is not None
        else end_dt - timedelta(days=365)
    )

    # A date-only end means the end of that calendar day.
    if end is not None and isinstance(end, date) and not isinstance(end, datetime):
        end_dt = _to_datetime(end, end_of_day=True)

    if end_dt <= start_dt:
        raise ValueError("Start date must be before end date")

    return start_dt, end_dt