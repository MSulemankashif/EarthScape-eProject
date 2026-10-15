"""Tests for the data ingestion pipeline and test-data generator."""

import numpy as np
import pandas as pd
import pytest

from src.hadoop.storage import LocalHDFS
from src.ingestion import pipeline
from src.ingestion.generate_test_data import (
    generate_satellite_imagery,
    generate_sensor_network,
    generate_weather_stations,
)
from src.ingestion.pipeline import (
    apply_range_validation,
    clean_weather_stations,
    coerce_numeric,
    ingest_reading,
    register_dataset,
    list_datasets,
)


# ---------------------------------------------------------------------------
# Test data generator
# ---------------------------------------------------------------------------
def test_weather_stations_shape():
    df = generate_weather_stations()
    assert len(df) > 1000
    assert {"station_id", "date", "temperature_c", "co2_ppm"} <= set(df.columns)


def test_weather_stations_contain_missing_and_anomalies():
    df = generate_weather_stations()
    assert df["temperature_c"].isna().any(), "expected injected missing values"
    assert df["temperature_c"].max() > 48, "expected injected heatwave"
    assert df["pm25"].max() > 400, "expected injected smog spike"


def test_sensor_network_shape():
    df = generate_sensor_network(rows=500)
    assert len(df) == 500
    assert {"sensor_id", "sensor_type", "value", "unit"} <= set(df.columns)
    assert df["sensor_type"].nunique() == 4


def test_satellite_shape():
    df = generate_satellite_imagery()
    assert len(df) > 100
    assert {"ndvi", "lst_c", "aerosol_index"} <= set(df.columns)


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def test_coerce_numeric_blanks_garbage():
    df = pd.DataFrame({"temperature_c": ["20.5", "abc", "", "30"]})
    out = coerce_numeric(df, ["temperature_c"])
    assert out["temperature_c"].tolist()[0] == 20.5
    assert np.isnan(out["temperature_c"].tolist()[1])
    assert np.isnan(out["temperature_c"].tolist()[2])


def test_range_validation_blanks_impossible_values():
    df = pd.DataFrame({
        "temperature_c": [25.0, 999.0, -200.0],
        "humidity_pct": [50.0, 150.0, -10.0],
    })
    out = apply_range_validation(df)
    assert out["temperature_c"][0] == 25.0
    assert np.isnan(out["temperature_c"][1])
    assert np.isnan(out["temperature_c"][2])
    assert np.isnan(out["humidity_pct"][1])
    assert np.isnan(out["humidity_pct"][2])


def test_clean_weather_stations_full_pass():
    raw = pd.DataFrame({
        "station_id": ["S1", "S1", "S2"],
        "city": ["A", "A", "B"],
        "region": ["inland"] * 3,
        "date": ["2024-01-01", "not-a-date", "2024-01-02"],
        "temperature_c": ["20.5", "21.0", "999"],
        "humidity_pct": ["50", "55", "60"],
        "rainfall_mm": ["0", "1", "2"],
        "co2_ppm": ["415", "416", "417"],
        "pm25": ["50", "55", "60"],
        "wind_speed_kph": ["10", "11", "12"],
        "sea_level_mm": ["0", "1", "2"],
        "latitude": ["24.8", "24.8", "31.5"],
        "longitude": ["67.0", "67.0", "74.3"],
    })
    out = clean_weather_stations(raw)

    assert len(out) == 2, "invalid date row must be dropped"
    assert out["date"].dtype.kind == "M"
    assert np.isnan(out["temperature_c"].iloc[1]), "999C must be blanked"


# ---------------------------------------------------------------------------
# Ingestion with a temp storage backend
# ---------------------------------------------------------------------------
@pytest.fixture()
def local_store(tmp_path, monkeypatch):
    store = LocalHDFS(tmp_path / "hdfs")
    monkeypatch.setattr(pipeline, "get_storage", lambda: store)
    monkeypatch.setattr(pipeline, "CATALOG_PATH",
                        tmp_path / "catalog.json")
    return store


def test_ingest_reading_persists_to_daily_partition(local_store):
    record = ingest_reading({
        "station_id": "STN-001",
        "city": "Karachi",
        "temperature_c": 33.5,
        "timestamp": "2024-06-15T10:30:00",
    })
    assert record["station_id"] == "STN-001"

    files = local_store.glob("/climate/live/readings/year=2024/month=06/day=15/*.csv")
    assert files, "reading not stored in the expected daily partition"
    stored = local_store.read_dataframe(files[0])
    assert "STN-001" in stored["station_id"].values


def test_ingest_reading_blanks_impossible_values(local_store):
    record = ingest_reading({
        "station_id": "STN-002",
        "temperature_c": 999.0,   # impossible -> None
        "humidity_pct": "oops",   # garbage   -> None
        "timestamp": "2024-06-15T11:00:00",
    })
    assert record["temperature_c"] is None
    assert record["humidity_pct"] is None


def test_dataset_catalog_registration(local_store):
    register_dataset("weather", 10, ["/a.csv", "/b.csv"], ["x", "y"], "test.csv")
    catalog = list_datasets()
    assert "weather" in catalog
    assert catalog["weather"]["rows"] == 10
    assert catalog["weather"]["partition_count"] == 2


def test_full_ingestion_skips_missing_files(tmp_path, monkeypatch):
    store = LocalHDFS(tmp_path / "hdfs")
    monkeypatch.setattr(pipeline, "get_storage", lambda: store)
    monkeypatch.setattr(pipeline, "CATALOG_PATH", tmp_path / "catalog.json")
    monkeypatch.setattr(pipeline, "RAW_DATA_DIR", tmp_path)  # empty dir

    results = pipeline.run_full_ingestion()
    assert results == [], "missing raw files should be skipped, not crash"
