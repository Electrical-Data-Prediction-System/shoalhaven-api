import csv
from datetime import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import shoalhaven_api.db as db
from rich.progress import Progress
from rich.console import Console


class Reading:
    def __init__(self, _meterId: str, _kwh: float, _timestamp: datetime) -> None:
        self.meterId = _meterId
        self.kwh = _kwh
        self.timestamp = _timestamp

    def __str__(self) -> str:
        return f"{self.meterId}: @ {self.timestamp}, {self.kwh} kwh"

    def to_dict(self) -> dict:
        return {
            "_id": f"{self.meterId}|{self.timestamp.isoformat()}",
            "_meterId": self.meterId,
            "kwh": self.kwh,
            "timestamp": self.timestamp,
        }


# Mappings for meter ID to meter object
def loadReadings(file) -> list[Reading]:
    console = Console()

    readingsMap = []

    with open(file, "r", newline="") as csvfile:
        buffer = []
        csvreader = csv.reader(csvfile, delimiter=",")

        # Pull all rows into buffer, first row of buffer is header row
        for row in csvreader:
            buffer.append(row)

        # Pull meter IDs from first row (header row)
        meterColumns = []
        for header in buffer[0]:
            # Only pull ID, header is formatted as 'ID_kWh_ImportToSite...'
            meterColumns.append(header.split("_")[0])

        # Pop first item as its the datetime column
        meterColumns.pop(0)

        # Pop header row from buffer, all that logic is done!
        buffer.pop(0)

        # Read in all other objects with respect to its column ID and datetime
        for row in buffer:
            # First column is always the datetime for the kwh data, formatted as '31/12/2026 23:55'
            time = datetime.strptime(row[0], "%d/%m/%Y %H:%M")
            data = row[1:]
            for i, kwh in enumerate(data):
                # Map index to meter ID column
                meterId = meterColumns[i]

                # Some readings get expoerted as none, default to 0.0
                if kwh == "":
                    kwh = 0.0

                # Make reader object and add to mapping!
                reading = Reading(meterId, float(kwh), time)
                readingsMap.append(reading)

    console.out(f"Loaded {len(readingsMap)} readings!")
    return readingsMap


# A quicker way to parse CSV files via pandas
def loadReadingsDataframe(file) -> list[dict]:
    df = pd.read_csv(file)

    # Parse the Date column once, vectorised
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y %H:%M")

    # Wide into long, one row per (Date, meterColumn)
    long = df.melt(id_vars=["Date"], var_name="header", value_name="kwh")

    #'NEEE002335_kWh_Import to Site' into 'NEEE002335'
    long["_meterId"] = long["header"].str.split("_").str[0]

    # Empty cells arrive as NaN to default to 0.0
    long["kwh"] = long["kwh"].fillna(0.0)

    # Composite _id
    long["timestamp"] = long["Date"].dt.to_pydatetime()
    long["_id"] = long["_meterId"] + "|" + long["Date"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    return long[["_id", "_meterId", "kwh", "timestamp"]].to_dict(orient="records")


# Update readings in db with local file, or create if id does not exist
def pushReadings(file):
    console = Console()
    # Check for file before doing anything
    console.out(f"Loading readings from {file}...")
    records = loadReadingsDataframe(file)
    if not records:
        return

    # Once we have a file, we can safely drop the readings table, backup CSV exists also
    console.out(f"Loaded {len(records)} readings, dropping readings table")
    db.readings.drop()

    # Then populate the db with the CSV data
    BATCH_SIZE = 50000
    batches = [records[i : i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    total_inserted = total_skipped = 0

    # Multithread it, otherwise it takes forever
    with Progress() as progress:
        task = progress.add_task(f"Pushing readings from '{file}'", total=len(records))

        futures = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            for b in batches:
                fut = ex.submit(db.readingInsertMany, b)
                fut.add_done_callback(
                    lambda f, size=len(b): progress.advance(task, size)
                )
                futures.append(fut)

            for fut in as_completed(futures):
                inserted, skipped = fut.result()
                total_inserted += inserted
                total_skipped += skipped

    console.out(f"Inserted {total_inserted:,}, skipped {total_skipped:,}")
