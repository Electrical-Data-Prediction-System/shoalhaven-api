# Shoalhaven API
A `fastapi` implementation that parses CSV data, making it query-able and performing predictions.

## Getting started
  - `uv sync`, `shoalhaven serve`, open http://localhost:8000/docs

## Base URI
  http://localhost:8000

## Endpoints
  | Method | Endpoint                       | Purpose        |
  |--------|--------------------------------|----------------|
  | GET    | /getMeterObject/{meter_id}     | Meter by ID    |
  | GET    | /formatLocation/{query}        | Geocode query  |
  | GET    | /getReadingsBetween/           | Readings range |

## Reference

### Get meter object
GET /getMeterObject/{meter_id}
  URI parameters table: meter_id (path, string, required)
  Status codes: 200 / 404
  Example response (meterObject JSON)

### Format location
GET /formatLocation/{query}
  URI parameters: query (path, string, required)
  Status codes: 200
  Example response (Location JSON)

### Get readings between
GET /getReadingsBetween/
  Query parameters table:
    start (string, required, ISO datetime)
    end   (string, optional, defaults to now)
    meter_id (string, optional)
  Status codes: 200 / 400
  Example request/response (Reading JSON)

## Data models
  Location, Meter, Reading — property tables + JSON samples

## API reference
  Full interactive docs: /docs (Swagger), /redoc
Data-model notes to capture (from source)
- Location: fullAddress, street, postcode, place, region, country, coordinates where coordinates = [longitude, latitude] (location.py:20)
- Meter: _id, location, type, unit (meter.py:18)
- Reading: _meterId, kwh, timestamp (reading.py:19)
- GET / returns {"message": "Hello World"} — documented as a health/heartbeat check
