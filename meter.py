import csv


class Meter:
    def __init__(self, _id, _location, _type, _unit) -> None:
        self.id = _id
        self.location = _location
        self.type = _type
        self.unit = _unit

    def __str__(self) -> str:
        return f"{self.id}: @ {self.location}, {self.type} / {self.unit}"


# Mappings for meter ID to meter object
def loadSites(file) -> dict[str, Meter]:
    meterMap = {}

    with open(file, "r", newline="") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=",")
        for row in csvreader:
            rowObject = Meter(row[0], row[1], row[2], row[3])
            meterMap[row[0]] = rowObject

    return meterMap


# Pull site details from csv, load into objects
mappings = loadSites("flow-site-details.csv")
# for meterID in mappings:
#     print(mappings[meterID])
