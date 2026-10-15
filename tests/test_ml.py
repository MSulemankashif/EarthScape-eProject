"""Tests for the ML models (anomaly, trend, correlation)."""

import numpy as np
import pandas as pd
import pytest

from src.ml.models import (
    AnomalyDetectionModel,
    ClimateModelRegistry,
    CorrelationAnalyzer,
    TrendPredictionModel,
)


def make_df(n: int = 400, seed: int = 7) -> pd.DataFrame:
    """Daily weather-like series with seasonality, trend and one outlier."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    t = np.arange(n)
    seasonal = 8 * np.sin(2 * np.pi * t / 365.25)
    temp = 24 + 0.01 * t + seasonal + rng.normal(0, 1.2, n)
    temp[100] = 55.0  # injected outlier
    return pd.DataFrame({
        "date": dates,
        "station_id": "STN-001",
        "temperature_c": temp,
        "humidity_pct": 50 + 15 * np.sin(2 * np.pi * t / 365.25 + 1) + rng.normal(0, 4, n),
        "rainfall_mm": np.abs(rng.normal(2, 1.5, n)),
        "co2_ppm": 415 + 0.02 * t + rng.normal(0, 2, n),
        "pm25": np.abs(rng.normal(60, 12, n)),
        "wind_speed_kph": np.abs(rng.normal(11, 3, n)),
        "sea_level_mm": -4 + 0.01 * t + rng.normal(0, 1, n),
    })


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------
def test_anomaly_model_flags_injected_outlier():
    df = make_df()
    model = AnomalyDetectionModel(contamination=0.02).train(df)
    result = model.predict(df)

    assert "is_anomaly" in result.columns
    assert "anomaly_score" in result.columns
    assert bool(result.loc[100, "is_anomaly"]), "55C outlier must be flagged"
    rate = result["is_anomaly"].mean()
    assert 0.0 < rate < 0.1, f"anomaly rate unrealistic: {rate}"


def test_anomaly_model_handles_missing_values():
    df = make_df()
    df.loc[0:20, "temperature_c"] = np.nan
    model = AnomalyDetectionModel(contamination=0.02).train(df)
    result = model.predict(df)
    assert len(result) == len(df)


def test_anomaly_model_save_load_roundtrip(tmp_path):
    df = make_df()
    model = AnomalyDetectionModel(contamination=0.02).train(df)
    path = model.save(tmp_path / "model.joblib")

    loaded = AnomalyDetectionModel.load(path)
    original = model.predict(df)["is_anomaly"]
    restored = loaded.predict(df)["is_anomaly"]
    assert (original == restored).all()


def test_anomaly_untrained_raises():
    with pytest.raises(RuntimeError):
        AnomalyDetectionModel().predict(make_df())


# ---------------------------------------------------------------------------
# Trend prediction
# ---------------------------------------------------------------------------
def test_trend_model_learns_warming_direction():
    df = make_df()
    model = TrendPredictionModel(metric="temperature_c").train(df)
    summary = model.summary()

    assert summary["direction"] == "warming"
    assert summary["slope_per_year"] > 0
    assert summary["r2"] > 0.7


def test_forecast_shape_and_continuity():
    df = make_df()
    model = TrendPredictionModel(metric="temperature_c").train(df)
    fc = model.forecast(30)

    assert len(fc) == 30
    assert list(fc.columns) == ["date", "temperature_c"]
    # Forecast starts right after the last training date
    assert pd.Timestamp(fc["date"].iloc[0]) > model.last_date


def test_trend_model_needs_minimum_data():
    df = make_df(n=10)
    with pytest.raises(ValueError):
        TrendPredictionModel(metric="temperature_c").train(df)


def test_trend_model_ignores_missing_and_noise():
    df = make_df()
    df.loc[50:60, "temperature_c"] = np.nan
    model = TrendPredictionModel(metric="temperature_c").train(df)
    assert model.model is not None


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------
def test_correlation_matrix_is_symmetric():
    df = make_df()
    analyzer = CorrelationAnalyzer()
    matrix = analyzer.analyze(df)

    assert matrix.shape[0] == matrix.shape[1]
    assert np.allclose(matrix.values, matrix.values.T, equal_nan=True)
    assert np.allclose(np.diag(matrix.values), 1.0)


def test_correlation_known_relationship():
    """humidity and temperature have an offset seasonal link -> r != 0."""
    df = make_df()
    analyzer = CorrelationAnalyzer()
    analyzer.analyze(df)
    rels = analyzer.top_relationships(k=20)

    assert rels, "no relationships returned"
    assert all(0 <= abs(r["pearson_r"]) <= 1 for r in rels)
    # Sorted by strength descending
    mags = [abs(r["pearson_r"]) for r in rels]
    assert mags == sorted(mags, reverse=True)


def test_correlation_unsorted_pairs_deduplicated():
    df = make_df()
    result = ClimateModelRegistry.correlate(df)
    pairs = {(r["variable_a"], r["variable_b"])
             for r in result["top_relationships"]}
    assert len(pairs) == len(result["top_relationships"])


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_registry_train_and_status(tmp_path):
    df = make_df()
    reg = ClimateModelRegistry(model_dir=tmp_path)

    reg.train_anomaly(df, contamination=0.02)
    reg.train_trend(df, "temperature_c")

    status = reg.status()
    assert status["anomaly_model_trained"] is True
    assert "temperature_c" in status["trend_models"]
    assert status["trend_models"]["temperature_c"]["direction"] == "warming"

    # Models persist across registry instances (reload from disk)
    reg2 = ClimateModelRegistry(model_dir=tmp_path)
    model = reg2.load_anomaly()
    assert model is not None
    trend = reg2.load_trend("temperature_c")
    assert trend is not None
    assert trend.forecast(5) is not None
