import csv
from shoalhaven_api.location import Location
from shoalhaven_api.geocoding import geocodeLocationString
from rich.progress import track


class Meter:
    def __init__(self, _id: str, _location: Location, _type: str, _unit: str) -> None:
        self.id = _id
        self.location = _location
        self.type = _type
        self.unit = _unit

    def __str__(self) -> str:
        return f"{self.id}: @ {self.location}, {self.type} / {self.unit}"

    def to_dict(self) -> dict:
        return {
            "_id": self.id,
            "location": self.location.to_dict(),
            "type": self.type,
            "unit": self.unit,
        }


# Mappings for meter ID to meter object
def loadSites(file) -> dict[str, Meter]:
    meterMap = {}

    with open(file, "r", newline="") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=",")
        for row in csvreader:
            # Format location
            location = geocodeLocationString(row[1])

            rowObject = Meter(row[0], location, row[2], row[3])
            meterMap[row[0]] = rowObject

    return meterMap


# Update meters in db with local file, or create if id does not exist
def pushSites(file):
    import shoalhaven_api.db as db

    mappings = loadSites(file)
    for id in track(mappings, description=f"Pushing sites from '{file}'"):
        db.meterUpsert({"_id": id}, mappings[id].to_dict())
