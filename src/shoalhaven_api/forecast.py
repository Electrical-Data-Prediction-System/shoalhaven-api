from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

import numpy as np
import pandas as pd

import shoalhaven_api.db as db

GRANULARITY = Literal["hour", "day"]

# horizon/season are in buckets, context is how much history the model sees
GRANULARITY_CONFIG = {
    "hour": {"freq": "h", "horizon": 168, "season": 168, "context": timedelta(weeks=8)},
    "day": {"freq": "D", "horizon": 30, "season": 7, "context": timedelta(days=730)},
}

TIMEZONE = "Australia/Sydney"


# p10, p50, p90 arrays shaped (series, horizon)
Forecast = dict[str, np.ndarray]


class Forecaster(Protocol):
    name: str

    def predict(self, history: np.ndarray, horizon: int) -> Forecast: ...


# Models

class SeasonalNaiveForecaster:
    """Repeats the last season. The band comes from the spread of season-on-season changes."""

    def __init__(self, season: int) -> None:
        self.season = season
        self.name = f"seasonal-naive-{season}"

    def predict(self, history: np.ndarray, horizon: int) -> Forecast:
        history = np.asarray(history, dtype=float)
        season = min(self.season, history.shape[1])

        # Fill gaps in the last season with the mean of that phase across all history
        phases = np.arange(history.shape[1]) % season
        phase_means = np.stack(
            [_nanmean(history[:, phases == p], axis=1) for p in range(season)],
            axis=1,
        )
        last = history[:, -season:]
        last_phases = phases[-season:]
        last = np.where(np.isnan(last), phase_means[:, last_phases], last)
        last = np.nan_to_num(last)

        reps = int(np.ceil(horizon / season))
        p50 = np.tile(last, reps)[:, :horizon]

        if history.shape[1] > season:
            residuals = history[:, season:] - history[:, :-season]
        else:
            residuals = np.zeros_like(history)
        low = _nanquantile(residuals, 0.1)
        high = _nanquantile(residuals, 0.9)

        return Forecast(
            p10=np.clip(p50 + low[:, None], 0, None),
            p50=p50,
            p90=np.clip(p50 + high[:, None], 0, None),
        )


class TimestralForecaster:
    """Mistral's Timestral time-series model. Needs `uv sync --group forecast`."""

    def __init__(self, size: str = "5M") -> None:
        # Imported here so the API never loads torch
        from timestral import TimestralForecaster as Model

        self.name = f"timestral-{size}"
        self.model = Model.from_pretrained(f"mistralai/Timestral-{size}")

    def predict(self, history: np.ndarray, horizon: int) -> Forecast:
        context = np.asarray(history, dtype=np.float32)[:, None, :]
        out = self.model.forecast(context, prediction_length=horizon)

        return Forecast(
            p10=np.clip(np.asarray(out.quantile(0.1))[:, 0, :], 0, None),
            p50=np.clip(np.asarray(out.median)[:, 0, :], 0, None),
            p90=np.clip(np.asarray(out.quantile(0.9))[:, 0, :], 0, None),
        )


# History

def build_history(
    granularity: GRANULARITY,
    meter_ids: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Timestamp] | None:
    """Return a regular grid of bucketed kWh (rows: buckets, cols: meters) and the anchor.

    The anchor is the start of the bucket after the last complete one, which is where
    the forecast begins. The bucket holding the latest reading is dropped as it may be partial.
    """
    config = GRANULARITY_CONFIG[granularity]

    latest = _latest_timestamp(meter_ids)
    if latest is None:
        return None

    end = _as_utc(latest)
    start = end - config["context"] - timedelta(days=1)

    rows = db.aggregateMeterPowerRows(meter_ids, granularity, start, end)
    if not rows:
        return None

    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert(TIMEZONE)
    frame = frame.set_index("date").sort_index()

    # Drop the possibly partial last bucket, then reindex so gaps become NaN
    anchor = frame.index.max()
    frame = frame[frame.index < anchor]
    if frame.empty:
        return None

    grid = pd.date_range(frame.index.min(), frame.index.max(), freq=config["freq"])
    frame = frame.reindex(grid)

    return frame, anchor


def future_index(anchor: pd.Timestamp, granularity: GRANULARITY, horizon: int) -> pd.DatetimeIndex:
    return pd.date_range(anchor, periods=horizon, freq=GRANULARITY_CONFIG[granularity]["freq"])


# Backtest

def backtest(
    history: np.ndarray,
    horizon: int,
    model: Forecaster,
    baseline: Forecaster,
) -> list[dict | None]:
    """Hold out the final `horizon` buckets and score the model against the baseline per series."""
    if history.shape[1] <= horizon * 2:
        return [None] * history.shape[0]

    train, actual = history[:, :-horizon], history[:, -horizon:]
    model_p50 = model.predict(train, horizon)["p50"]
    baseline_p50 = baseline.predict(train, horizon)["p50"]

    results = []
    for i in range(history.shape[0]):
        model_mae, model_mape = _errors(model_p50[i], actual[i])
        baseline_mae, baseline_mape = _errors(baseline_p50[i], actual[i])
        results.append({
            "horizon": horizon,
            "modelMae": model_mae,
            "baselineMae": baseline_mae,
            "modelMape": model_mape,
            "baselineMape": baseline_mape,
        })
    return results


# Pipeline

def run_forecasts(
    granularity: GRANULARITY,
    meter_ids: list[str] | None = None,
    model: Forecaster | None = None,
    do_backtest: bool = True,
) -> list[dict]:
    """Forecast every meter at one granularity, save the results and return them."""
    config = GRANULARITY_CONFIG[granularity]
    horizon = config["horizon"]

    built = build_history(granularity, meter_ids)
    if built is None:
        return []
    frame, anchor = built

    # Skip meters with no usable history
    frame = frame.loc[:, frame.notna().any()]
    if frame.empty:
        return []

    model = model or TimestralForecaster()
    baseline = SeasonalNaiveForecaster(config["season"])

    history = frame.to_numpy(dtype=float).T
    forecast = model.predict(history, horizon)
    scores = backtest(history, horizon, model, baseline) if do_backtest else [None] * len(frame.columns)

    timestamps = [ts.tz_convert(UTC).to_pydatetime() for ts in future_index(anchor, granularity, horizon)]
    generated_at = datetime.now(UTC)

    docs = []
    for i, meter_id in enumerate(frame.columns):
        doc = {
            "_id": f"{meter_id}:{granularity}",
            "meterId": meter_id,
            "granularity": granularity,
            "model": model.name,
            "generatedAt": generated_at,
            "anchor": anchor.tz_convert(UTC).to_pydatetime(),
            "points": [
                {
                    "x": ts,
                    "p10": round(float(forecast["p10"][i, j]), 5),
                    "p50": round(float(forecast["p50"][i, j]), 5),
                    "p90": round(float(forecast["p90"][i, j]), 5),
                }
                for j, ts in enumerate(timestamps)
            ],
            "backtest": scores[i],
        }
        db.forecastUpsert(doc)
        docs.append(doc)

    return docs


# Helper Functions

def _latest_timestamp(meter_ids: list[str] | None) -> datetime | None:
    if meter_ids is None:
        return db.readingLatestTimestamp()

    timestamps = [t for t in (db.readingLatestTimestamp(m) for m in meter_ids) if t is not None]
    return max(timestamps, default=None)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _errors(predicted: np.ndarray, actual: np.ndarray) -> tuple[float | None, float | None]:
    mask = ~np.isnan(actual)
    if not mask.any():
        return None, None

    error = np.abs(predicted[mask] - actual[mask])
    mae = float(error.mean())

    nonzero = np.abs(actual[mask]) > 1e-9
    mape = float((error[nonzero] / np.abs(actual[mask][nonzero])).mean() * 100) if nonzero.any() else None

    return round(mae, 5), (round(mape, 3) if mape is not None else None)


def _nanmean(values: np.ndarray, axis: int) -> np.ndarray:
    counts = (~np.isnan(values)).sum(axis=axis)
    sums = np.nansum(values, axis=axis)
    return np.divide(sums, counts, out=np.full(sums.shape, np.nan), where=counts > 0)


def _nanquantile(values: np.ndarray, q: float) -> np.ndarray:
    out = np.zeros(values.shape[0])
    for i, row in enumerate(values):
        row = row[~np.isnan(row)]
        if row.size:
            out[i] = np.quantile(row, q)
    return out
