from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")
STEP = timedelta(minutes=30)


def month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def previous_month(month: datetime) -> datetime:
    return month_start(month - timedelta(days=1))


def next_month(month: datetime) -> datetime:
    return month_start(month + timedelta(days=32))


def latest_full_month(latest: datetime) -> datetime:
    """Start of the most recent month whose readings are complete"""
    current = month_start(latest)
    # Complete only if the month's final half hour has been read
    if latest + STEP >= next_month(current):
        return current
    return previous_month(current)


def wall_time_to_utc(timestamp: datetime) -> datetime:
    """
    Readings hold Sydney local time but are stored as if they were UTC.
    Returns the real moment as naive UTC, which is how Mongo returns market timestamps.
    """
    local = timestamp.replace(tzinfo=SYDNEY)
    return local.astimezone(UTC).replace(tzinfo=None)


def month_summary(rows: list[dict], prices: dict[datetime, float], month: datetime) -> dict:
    """
    Totals for one month from [{timestamp, kwh}] rows (all meters added together).
    `prices` maps real UTC half hours to NSW spot price in $/MWh.
    """
    end = next_month(month)
    in_month = [r for r in rows if month <= r["timestamp"] < end]

    daily: dict = defaultdict(float)
    cost = 0.0
    priced_kwh = 0.0
    for row in in_month:
        daily[row["timestamp"].date()] += row["kwh"]
        price = prices.get(wall_time_to_utc(row["timestamp"]))
        if price is not None:
            # kWh x $/MWh / 1000 = $. Negative prices make this negative: the grid pays you to use power
            cost += row["kwh"] * price / 1000
            priced_kwh += row["kwh"]

    total = sum(r["kwh"] for r in in_month)
    busiest = max(daily.items(), key=lambda item: item[1], default=None)

    return {
        "month": month,
        "totalKwh": round(total, 1),
        "busiestDay": {"date": busiest[0], "kwh": round(busiest[1], 1)} if busiest else None,
        # Only report a cost when market data covers the month
        "wholesaleCost": round(cost, 2) if priced_kwh else None,
        "pricedShare": round(priced_kwh / total, 3) if total else 0,
    }
