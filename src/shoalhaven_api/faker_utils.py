import random
from datetime import datetime, timedelta
from typing import List, Dict

import numpy as np
import pandas as pd
from faker import Faker

from shoalhaven_api.data.shoalhaven_locations import SHOALHAVEN_LOCATIONS
from shoalhaven_api.location import Location


def make_fake_location(fake: Faker) -> Location:
    loc = random.choice(SHOALHAVEN_LOCATIONS)
    suburb = loc["suburb"]
    postcode = loc["postcode"]
    street = random.choice(loc["streets"])
    number = random.randint(1, 200)
    full_address = f"{number} {street}, {suburb} NSW {postcode}"
    # Add small jitter to coordinates
    lat = loc["lat"] + random.uniform(-0.01, 0.01)
    lon = loc["lon"] + random.uniform(-0.01, 0.01)
    return Location(full_address, street, postcode, suburb, "NSW", "Australia", (lon, lat))


def generate_meters_csv(path: str, count: int = 10, seed: int = 12345) -> List[str]:
    fake = Faker("en_AU")
    Faker.seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    meter_ids = []
    rows = []
    for i in range(count):
        meter_id = f"METER-{fake.unique.random_number(digits=6):06d}"
        meter_ids.append(meter_id)
        loc = make_fake_location(fake)
        # common demo types/units
        mtype = random.choice(["electricity", "solar", "electricity"])
        unit = "kWh"
        # meters.csv format expected by loadSites: [id, address, type, unit]
        # we pass the full address string; loadSites will call geocodeLocationString
        # but for fake demo we want to avoid API calls - we'll handle via custom path
        rows.append((meter_id, loc.fullAddress, mtype, unit))

    # Write in format compatible with loadSites (address string as second col)
    with open(path, "w") as f:
        for r in rows:
            f.write(f"{r[0]},{r[1]},{r[2]},{r[3]}\n")

    return meter_ids


def generate_meters_direct(meter_ids: List[str] = None, count: int = 10, seed: int = 12345):
    """Generate Meter objects directly with pre-built Location objects (bypass geocoding)."""
    from shoalhaven_api.meter import Meter

    fake = Faker("en_AU")
    Faker.seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    meters = []
    if meter_ids is None:
        meter_ids = [f"METER-{fake.unique.random_number(digits=6):06d}" for _ in range(count)]
    for mid in meter_ids:
        loc = make_fake_location(fake)
        mtype = random.choice(["electricity", "solar"])
        meters.append(Meter(mid, loc, mtype, "kWh"))
    return meters


def _diurnal_pattern(hour: int) -> float:
    # Simple diurnal pattern for residential/commercial-ish load
    if 0 <= hour < 6:
        return 0.4
    if 6 <= hour < 9:
        return 0.8
    if 9 <= hour < 17:
        return 1.0
    if 17 <= hour < 21:
        return 1.3
    return 0.7


def generate_readings_dataframe(
    meter_ids: List[str],
    start_date: datetime,
    end_date: datetime,
    granularity_minutes: int = 30,
    seed: int = 12345,
) -> pd.DataFrame:
    Faker.seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    # Create time range at granularity
    freq = f"{granularity_minutes}min"
    dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    df = pd.DataFrame({"Date": dates})

    for mid in meter_ids:
        # base load varies per meter
        base = random.uniform(0.1, 0.5)
        scale = random.uniform(0.8, 1.4)
        values = []
        for dt in dates:
            hour = dt.hour
            dow = dt.dayofweek  # 0 Mon
            month = dt.month
            # seasonal factor (simple)
            seasonal = 1.0 + 0.2 * np.sin(2 * np.pi * (month - 1) / 12.0)
            # weekend reduction
            weekend = 0.85 if dow >= 5 else 1.0
            # diurnal
            diurnal = _diurnal_pattern(hour)
            noise = random.gauss(1.0, 0.05)
            val = base * scale * diurnal * seasonal * weekend * noise
            # ensure positive
            if val < 0:
                val = abs(val)
            values.append(round(val, 6))
        # column name format expected by loadReadingsDataframe: {meterId}_...
        df[f"{mid}_kWh_Import"] = values

    return df


def write_readings_csv(df: pd.DataFrame, path: str):
    # Format Date as DD/MM/YYYY HH:MM to match existing parser
    df_out = df.copy()
    df_out["Date"] = df_out["Date"].dt.strftime("%d/%m/%Y %H:%M")
    df_out.to_csv(path, index=False)
