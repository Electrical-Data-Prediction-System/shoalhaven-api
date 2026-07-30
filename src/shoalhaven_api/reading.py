import csv
from datetime import datetime

from rich import console
import shoalhaven_api.db as db
from rich.progress import track
from rich.console import Console


class Reading:
    def __init__(self, _meterId: str, _kwh: float, _timestamp: datetime) -> None:
        self.meterId = _meterId
        self.kwh = _kwh
        self.timestamp = _timestamp

    def __str__(self) -> str:
        return f"{self.meterId}: @ {self.timestamp}, {self.kwh} kwh"

    def to_dict(self) -> dict:
        return {"_meterId": self.meterId, "kwh": self.kwh, "timestamp": self.timestamp}


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


# Update readings in db with local file, or create if id does not exist
def pushReadings(file):
    mappings = loadReadings(file)

    for reading in track(mappings, description=f"Pushing readings from '{file}'"):
        # A reading is identified by both its meterId and timestamp, as 2 records cannot overlap at the same time or place
        db.readingInsertMany([reading.to_dict()])
