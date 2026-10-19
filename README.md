# Shoalhaven API
A `fastapi` implementation that parses CSV data, making it query-able and performing predictions.

- **Backend**: FastAPI + Uvicorn
- **Database**: MongoDB (`hydrochart`, collections `meter` and `reading`)
- **Parsing**: `pandas` for fast, batched CSV ingestion
- **Geocoding**: MapBox Geocoding API to enrich meter locations
- **CLI**: `typer` + `rich`

## Prerequisites
- `uv` installed.
- Python >=3.13 installed.

## Setup
1. Install dependencies and sync the environment: `uv sync`
2. Copy `.env` configuration with your `MONGODB_CONNECTION_STRING` and `MAPBOX_API` keys, see `.env.example`
3. Use `shoalhaven --help` to get started!

## Using the CLI
`shoalhaven serve` runs the FastAPI server.

| Command | Description |
| --- | --- |
| `shoalhaven pushMeters [file=./csv/meters.csv] [granularity=60]` | Upserts all meters from CSV (default `./csv/meters.csv`) into MongoDB, granularity filters only uploads rows whose `hour * 60 + minute` is divisible by it |
| `shoalhaven allMeters` | Lists every meter in MongoDB |
| `shoalhaven queryMeters` | Filters meters by `--type`, `--unit`, or a partial `--location` search |
| `shoalhaven pushReadings [file] [granularity]` | Drops and repopulates readings from CSV. `granularity` in minutes: `60` hourly, `240` 4-hourly, `1440` daily (default `60`) |
| `shoalhaven ping` | Tests connectivity to the MongoDB instance |
| `shoalhaven serve [host=0.0.0.0] [port=8000]` | Starts the FastAPI dev server |

### Warning
`pushReadings` is currently destructive, it drops the collection before adding from the specified CSV.

## API Routes
Dates are formatted in ISO when querying, e.g. `2026-08-03 05:35:00`.

| Route | Description |
| --- | --- |
| `GET /` | Health check |
| `GET /meters?location=` | Searches meters by address, street, postcode, suburb, region, or country |
| `GET /meters/{meter_id}` | Returns a single meter object by ID |
| `GET /meters/{meter_id}/aggregate-power?start=&end=&interval=` | Sums KWH per meter, optionally grouped by `5m`, `week`, `month`, or `year` buckets |
| `GET /meters/power/aggregate-power?start=&end=` | Sums KWH for all meters between dates |
| `GET /locations/geocode/{query}` | Geocodes a location string into structured data |
| `GET /meters/{meter_id}/readings?start=&end=` | Raw readings between two dates, optionally filtered by meter |
| `GET /meters/{meter_id}/readings/latest` | Timestamp of the latest reading for a meter |
| `GET /readings/aggregate?start=&end=` | Monthly KWH aggregates between two dates |


## Data Model
- **Meter**: `_id`, `location`, `type`, `unit`
- **Location**: `fullAddress`, `street`, `postcode`, `place`, `region`, `country`, `coordinates` (longitude, latitude)
- **Reading**: `_meterId`, `kwh`, `timestamp`

## Project Structure
```
src/shoalhaven_api/
├── api.py        # FastAPI routes
├── cli.py        # Typer CLI commands
├── db.py         # MongoDB client + query/aggregation helpers
├── meter.py      # Meter model + CSV ingestion
├── reading.py    # Reading model + fast pandas CSV ingestion
├── location.py   # Location model
└── geocoding.py  # MapBox geocoding integration
```
