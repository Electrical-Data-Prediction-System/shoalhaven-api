# Generating Fake Demo Data

This project includes Faker-based utilities to generate geographically plausible demo data for the Shoalhaven region.

## Requirements met
- Uses Faker for realistic synthetic data
- Locations are geographically plausible within Shoalhaven (Nowra, Bomaderry, Ulladulla, Milton, Sussex Inlet, Berry, Shoalhaven Heads) with jittered coordinates
- Data spans over 2 years by default
- Granular to every 30 minutes by default (configurable)
- Uses the built-in CLI and the same granular logic as CSV uploading (`pushReadings` with granularity filtering)

## Usage

### Generate and push to DB in one go (recommended for demos)
```bash
shoalhaven seed-fake --meter-count 15 --years 2.0 --granularity-minutes 30
```

### Generate CSVs only
```bash
shoalhaven generate-fake-csv --meter-count 10 --years 2.0 --granularity-minutes 30 --csv-dir ./csv/fake
```

You can then use the existing CLI commands:
```bash
shoalhaven pushMeters ./csv/fake/meters.csv
shoalhaven pushReadings ./csv/fake/readings.csv 30
```

## Notes
- `seed-fake` pushes meters directly to DB (bypassing geocoding API calls) for reliability in demos. Locations are still Shoalhaven-plausible.
- Readings are generated with diurnal/seasonal/weekend patterns for realism.
- CSV format matches the existing parsers exactly.
- Granularity is enforced the same way as `loadReadingsDataframe` (filtering by `(hour*60 + minute) % granularity_minutes == 0`).
