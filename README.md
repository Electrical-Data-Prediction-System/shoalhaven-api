# Shoalhaven API
A `fastapi` implementation that parses CSV data, making it query-able and performing predictions.

- **Backend**: FastAPI + Uvicorn
- **Database**: MongoDB (`hydrochart`, collections `meter` and `reading`)
- **Parsing**: `pandas` for fast, batched CSV ingestion
- **Geocoding**: MapBox Geocoding API to enrich meter locations
- **CLI**: `typer` + `rich`

## Setup
1. Install dependencies and sync the environment: `uv sync`
2. Copy `.env` configuration with your `MONGODB_CONNECTION_STRING` and `MAPBOX_API` keys
3. Use `shoalhaven --help` to get started!

## Using the CLI
`shoalhaven serve` runs the FastAPI server.

| Command | Description |
| --- | --- |
| `shoalhaven pushMeters [file]` | Upserts all meters from CSV (default `./csv/meters.csv`) into MongoDB |
| `shoalhaven allMeters` | Lists every meter in MongoDB |
| `shoalhaven queryMeters` | Filters meters by `--type`, `--unit`, or a partial `--location` search |
| `shoalhaven pushReadings [file] [granularity]` | Drops and repopulates readings from CSV. `granularity` in minutes: `60` hourly, `240` 4-hourly, `1440` daily (default `60`) |
| `shoalhaven ping` | Tests connectivity to the MongoDB instance |
| `shoalhaven serve` | Starts the FastAPI dev server |

## API Routes
Dates are formatted in ISO, e.g. `2026-08-03 05:34:37.967019`.

| Route | Description |
| --- | --- |
| `GET /` | Health check |
| `GET /getMeterObject/{meter_id}` | Returns a single meter object by ID |
| `GET /aggregateMeterPowerBetween/{meter_id}?start=&end=` | Sums KWH per meter between dates |
| `GET /aggregateAllMeterPowerBetween/?start=&end=` | Sums KWH for all meters between dates |
| `GET /formatLocation/{query}` | Geocodes a location string into structured data |
| `GET /getReadingsBetween/?start=&end=&meter_id=` | Raw readings between two dates, optionally filtered by meter |
| `GET /aggregateReadingsBetween/?start=&end=` | Monthly KWH aggregates between two dates |

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
├── geocoding.py  # MapBox geocoding integration
└── dashboard.py  # Graph formatting helpers
```
