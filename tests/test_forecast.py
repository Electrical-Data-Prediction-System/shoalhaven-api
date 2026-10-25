from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

import shoalhaven_api.forecast as forecast


class StubForecaster:
    """Always predicts a constant, so errors are easy to work out by hand"""

    def __init__(self, value: float) -> None:
        self.value = value
        self.name = f"stub-{value}"

    def predict(self, history, horizon):
        p50 = np.full((history.shape[0], horizon), self.value)
        return {"p10": p50, "p50": p50, "p90": p50}


def test_seasonal_naive_repeats_last_season():
    history = np.array([[1, 2, 3, 1, 2, 3, 4, 5, 6]], dtype=float)

    result = forecast.SeasonalNaiveForecaster(season=3).predict(history, horizon=5)

    assert result["p50"].shape == (1, 5)
    assert result["p50"].tolist() == [[4, 5, 6, 4, 5]]
    assert (result["p10"] <= result["p50"]).all()
    assert (result["p90"] >= result["p50"]).all()


def test_seasonal_naive_fills_gaps_with_phase_mean():
    history = np.array([[1, 10, 3, 10, np.nan, 10]], dtype=float)

    result = forecast.SeasonalNaiveForecaster(season=2).predict(history, horizon=2)

    # The missing value sits in phase 0, whose other values are 1 and 3
    assert result["p50"].tolist() == [[2, 10]]


def test_backtest_scores_model_against_baseline():
    history = np.array([[10.0] * 6 + [20.0] * 2])

    scores = forecast.backtest(history, 2, StubForecaster(18), StubForecaster(10))

    assert scores == [{
        "horizon": 2,
        "modelMae": 2.0,
        "baselineMae": 10.0,
        "modelMape": 10.0,
        "baselineMape": 50.0,
    }]


def test_backtest_skips_short_history():
    history = np.ones((2, 3))

    assert forecast.backtest(history, 2, StubForecaster(1), StubForecaster(1)) == [None, None]


def test_build_history_drops_partial_bucket_and_fills_gaps(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {"date": start, "m1": 1.0},
        # 01:00 is missing
        {"date": start + timedelta(hours=2), "m1": 3.0},
        {"date": start + timedelta(hours=3), "m1": 4.0},
    ]
    monkeypatch.setattr(forecast.db, "readingLatestTimestamp", lambda meter_id=None: start + timedelta(hours=3))
    monkeypatch.setattr(forecast.db, "aggregateMeterPowerRows", lambda *args: rows)

    frame, anchor = forecast.build_history("hour")

    assert anchor.tz_convert(UTC).to_pydatetime() == start + timedelta(hours=3)
    assert len(frame) == 3
    values = frame["m1"].tolist()
    assert values[0] == 1.0 and np.isnan(values[1]) and values[2] == 3.0


def test_run_forecasts_saves_one_document_per_meter(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [{"date": start + timedelta(days=i), "m1": 5.0, "m2": 1.0} for i in range(100)]
    saved = []
    monkeypatch.setattr(forecast.db, "readingLatestTimestamp", lambda meter_id=None: start + timedelta(days=99))
    monkeypatch.setattr(forecast.db, "aggregateMeterPowerRows", lambda *args: rows)
    monkeypatch.setattr(forecast.db, "forecastUpsert", saved.append)

    docs = forecast.run_forecasts("day", model=StubForecaster(5.0))

    assert [d["_id"] for d in saved] == ["m1:day", "m2:day"]
    assert len(docs[0]["points"]) == forecast.GRANULARITY_CONFIG["day"]["horizon"]
    # The forecast begins at the dropped partial bucket
    assert docs[0]["points"][0]["x"] == start + timedelta(days=99)
    assert docs[0]["backtest"]["modelMae"] == 0.0


def test_timestral_forecaster_shapes():
    pytest.importorskip("timestral")
    history = np.abs(np.sin(np.linspace(0, 40, 24 * 14)))[None, :] + 1

    result = forecast.TimestralForecaster("5M").predict(history, horizon=24)

    assert result["p50"].shape == (1, 24)
    assert (result["p10"] <= result["p90"]).all()
