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

## Environment variables
Create a .env file that specifies
```
MONGODB_CONNECTION_STRING=              # connection string to mongodb database
MAPBOX_API=                             # connection string to mapbox, only needed if converting location string into subcomponents
APP_ENV="dev"                           # specifies which database should be selected, 
                                        # dev for demo database, prod for hydrochart database,
                                        # need account that can access the respective database in the mongoDB connection string
```


## Setup
1. Install dependencies and sync the environment: `uv sync`
2. Copy `.env` configuration with your `MONGODB_CONNECTION_STRING` and `MAPBOX_API` keys, see `.env.example`
3. Use `uv run shoalhaven --help` to get started!

## Using the CLI
`uv run shoalhaven serve` runs the FastAPI server.

| Command | Description |
| --- | --- |
| `uv run shoalhaven pushMeters [file=./csv/meters.csv] [granularity=60]` | Upserts all meters from CSV (default `./csv/meters.csv`) into MongoDB, granularity filters only uploads rows whose `hour * 60 + minute` is divisible by it |
| `uv run shoalhaven allMeters` | Lists every meter in MongoDB |
| `uv run shoalhaven queryMeters` | Filters meters by `--type`, `--unit`, or a partial `--location` search |
| `uv run shoalhaven pushReadings [file] [granularity]` | Drops and repopulates readings from CSV. `granularity` in minutes: `60` hourly, `240` 4-hourly, `1440` daily (default `60`) |
| `uv run shoalhaven ping` | Tests connectivity to the MongoDB instance |
| `uv run shoalhaven serve [host=0.0.0.0] [port=8000]` | Starts the FastAPI dev server |
| `uv run shoalhaven pushMarket [--start 2025-01-01] [--end 2026-01-01] [--series price]` | Fetches NSW price, demand, rooftop/utility solar and Gullen Range solar (30 min) from OpenElectricity into the `market` collection. Needs `OPENELECTRICITY_API_KEY` |
| `uv run --group forecast shoalhaven forecast [--granularity both] [--size 5M] [--meter-id ID]` | Forecasts usage with Timestral and saves it to MongoDB (see Forecasting) |

### Warning
`pushReadings` is currently destructive, it drops the collection before adding from the specified CSV.

## Forecasting
Forecasts are made ahead of time from the CLI and saved to the `forecast` collection, so the API never has to load the model.

- **Model:** [Timestral](https://github.com/mistralai/timestral), Mistral's pretrained time-series model (modified MIT licence). It isn't an LLM: it takes past kWh values and returns future ones with a p10-p90 range. It runs on CPU, and `5M` is a 21 MB download cached on first use.
- **Install:** the model needs PyTorch, so it lives in an optional group. Run `uv sync --group forecast`. A normal `uv sync` (Docker, Vercel) doesn't install it.
- **Products:** `hour` is the next 7 days, hourly, from 8 weeks of history. `day` is the next 30 days, daily, from 2 years of history. Both start where the latest readings end.
- **Backtest:** each run holds back the final horizon of real data and scores the model against a seasonal-naive baseline (repeat the last week). Both scores are printed and saved with the forecast.

Re-run the command whenever new readings are loaded.

## Market data
NSW electricity market data comes from [OpenElectricity](https://openelectricity.org.au) (free key, data licensed CC BY-NC 4.0, attribute it wherever it's shown). It's fetched once with `pushMarket` and cached, so the dashboard never calls OpenElectricity directly. The free tier only reaches back 2 years, so keep the cache.

Times are grouped in NEM time (UTC+10 all year, no daylight saving), which is how the market itself runs.

## API Routes
Dates are formatted in ISO when querying, e.g. `2026-08-03 05:35:00`.

| Route | Description |
| --- | --- |
| `GET /` | Health check |
| `GET /meters?location=` | Searches meters by address, street, postcode, suburb, region, or country |
| `GET /meters/power/summary` | All meters for the latest full month and the month before: total kWh, busiest day, and wholesale cost (each half hour's kWh x NSW spot price from the `market` cache) |
| `GET /meters/map?start=&end=` | Every meter with its address, coordinates, total kWh (default: the year before the latest reading, `null` if no readings) and `inShoalhaven` (false when geocoded outside the Shoalhaven) |
| `GET /meters/{meter_id}` | Returns a single meter object by ID |
| `GET /meters/{meter_id}/aggregate-power?start=&end=&interval=` | Sums KWH per meter, optionally grouped by `5m`, `hour`, `day`, `week`, `month`, or `year` buckets |
| `GET /meters/{meter_id}/forecast?granularity=` | Saved `hour` or `day` forecast (p10/p50/p90 points and backtest scores), 404 if none has been generated |
| `GET /meters/power/aggregate-power?start=&end=` | Sums KWH for all meters between dates |
| `GET /market/series?series=&interval=&months=` | Cached market series averaged per `30m`, `day` or `month` (series: `price`, `demand`, `solar_rooftop`, `solar_utility`, `gullen_solar`) |
| `GET /market/daily-profile?series=&months=` | Average of each series for every half hour of the day (the "duck curve") |
| `GET /market/stats?months=` | Spot price summary: average, max, min, % negative, midday vs evening averages |
| `GET /locations/geocode/{query}` | Geocodes a location string into structured data |
| `GET /meters/{meter_id}/readings?start=&end=` | Raw readings between two dates, optionally filtered by meter |
| `GET /meters/{meter_id}/readings/latest` | Timestamp of the latest reading for a meter |
| `GET /readings/aggregate?start=&end=` | Monthly KWH aggregates between two dates |

## Testing
Run the API route tests with `uv run pytest` from this directory. Tests use mocked database calls and do not require a MongoDB connection.

## Data Model
- **Meter**: `_id`, `location`, `type`, `unit`
- **Location**: `fullAddress`, `street`, `postcode`, `place`, `region`, `country`, `coordinates` (longitude, latitude)
- **Reading**: `_meterId`, `kwh`, `timestamp`
- **Forecast**: `_id` (`meterId:granularity`), `meterId`, `granularity`, `model`, `generatedAt`, `anchor`, `points` (`x`, `p10`, `p50`, `p90`), `backtest`

## Project Structure
```
src/shoalhaven_api/
├── api.py        # FastAPI routes
├── cli.py        # Typer CLI commands
├── db.py         # MongoDB client + query/aggregation helpers
├── meter.py      # Meter model + CSV ingestion
├── reading.py    # Reading model + fast pandas CSV ingestion
├── forecast.py   # Timestral + baseline forecasting and backtests
├── summary.py    # Monthly totals, busiest day and wholesale cost for the stat cards
├── market.py     # OpenElectricity fetching + price summary
├── location.py   # Location model
└── geocoding.py  # MapBox geocoding integration
```
