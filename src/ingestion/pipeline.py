"""
Climate data ingestion pipeline
===============================
Implements the "Data Ingestion" functional requirement of the eProject:

  * supports diverse sources  -> weather stations CSV, sensor network CSV,
    satellite imagery CSV
  * handles historical AND real-time data  -> `ingest_historical()` for the
    backfill, `ingest_reading()` for the live stream
  * cleans the data           -> numeric coercion, NaN handling, range checks
  * stores it in HDFS         -> partitioned by year/month (see storage.py)
  * registers datasets        -> a JSON catalog so the rest of the app can
    discover what has been ingested

Missing / incomplete values are preserved as NaN in storage and dropped only
at aggregation time, satisfying "handle missing or incomplete data gracefully".
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.hadoop.storage import get_storage, partition_and_store
from src.utils.logger import get_logger

log = get_logger("earthscape.ingest")

CATALOG_PATH = PROCESSED_DATA_DIR / "dataset_catalog.json"

# Accepted ranges per measurement – values outside are treated as sensor
# faults and replaced with NaN instead of corrupting the analytics.
VALID_RANGES = {
    "temperature_c": (-90.0, 60.0),
    "humidity_pct": (0.0, 100.0),
    "rainfall_mm": (0.0, 2000.0),
    "co2_ppm": (150.0, 1000.0),
    "pm25": (0.0, 2000.0),
    "wind_speed_kph": (0.0, 400.0),
    "sea_level_mm": (-500.0, 500.0),
}


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------
def coerce_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Convert columns to float; anything unparseable becomes NaN."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def apply_range_validation(df: pd.DataFrame) -> pd.DataFrame:
    """Blank out physically impossible readings (sensor faults)."""
    out = df.copy()
    flagged = 0
    for col, (lo, hi) in VALID_RANGES.items():
        if col not in out.columns:
            continue
        bad = out[col].notna() & ((out[col] < lo) | (out[col] > hi))
        flagged += int(bad.sum())
        out.loc[bad, col] = np.nan
    if flagged:
        log.info("Range validation blanked %d out-of-range value(s)", flagged)
    return out


def clean_weather_stations(df: pd.DataFrame) -> pd.DataFrame:
    """Full cleaning pass for the weather-station dataset."""
    out = coerce_numeric(
        df, ["temperature_c", "humidity_pct", "rainfall_mm", "co2_ppm",
             "pm25", "wind_speed_kph", "sea_level_mm", "latitude", "longitude"]
    )
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date", "station_id"])
    out = apply_range_validation(out)

    missing = int(out[["temperature_c", "humidity_pct", "rainfall_mm"]].isna().sum().sum())
    log.info("Cleaned weather stations: %d rows, %d missing measurements retained as NaN",
             len(out), missing)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Dataset catalog (so the app can discover stored data)
# ---------------------------------------------------------------------------
def _load_catalog() -> dict:
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {"datasets": {}}


def _save_catalog(catalog: dict) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")


def register_dataset(name: str, rows: int, partitions: list[str],
                     columns: list[str], source: str) -> None:
    catalog = _load_catalog()
    catalog["datasets"][name] = {
        "rows": rows,
        "columns": columns,
        "source": source,
        "partitions": partitions,
        "partition_count": len(partitions),
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_catalog(catalog)
    log.info("Registered dataset '%s' (%d rows, %d partitions)",
             name, rows, len(partitions))


def list_datasets() -> dict:
    return _load_catalog()["datasets"]


# ---------------------------------------------------------------------------
# Historical ingestion
# ---------------------------------------------------------------------------
def ingest_historical(csv_name: str = "weather_stations.csv",
                      dataset: str = "weather") -> dict:
    """
    Load a raw CSV, clean it, store it partitioned in HDFS and register it.

    Returns a summary dict used by the dashboard.
    """
    src = RAW_DATA_DIR / csv_name
    if not src.exists():
        raise FileNotFoundError(
            f"{src} not found. Run `python -m src.ingestion.generate_test_data` first."
        )

    log.info("Ingesting historical file %s", src.name)
    raw = pd.read_csv(src)
    cleaned = clean_weather_stations(raw)

    storage = get_storage()
    partitions = partition_and_store(cleaned, dataset, "date", storage)

    register_dataset(
        name=dataset,
        rows=len(cleaned),
        partitions=partitions,
        columns=list(cleaned.columns),
        source=csv_name,
    )
    return {
        "dataset": dataset,
        "rows_ingested": len(cleaned),
        "partitions": len(partitions),
        "missing_values": int(cleaned.isna().sum().sum()),
    }


def ingest_sensor_csv(csv_name: str = "sensor_network.csv",
                      dataset: str = "sensors") -> dict:
    """Ingest the environmental sensor network feed."""
    src = RAW_DATA_DIR / csv_name
    if not src.exists():
        raise FileNotFoundError(f"{src} not found.")

    raw = pd.read_csv(src)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce")
    raw = raw.dropna(subset=["timestamp", "sensor_id"])
    raw["value"] = pd.to_numeric(raw["value"], errors="coerce")

    storage = get_storage()
    partitions = partition_and_store(raw, dataset, "timestamp", storage)

    register_dataset(dataset, len(raw), partitions, list(raw.columns), csv_name)
    return {"dataset": dataset, "rows_ingested": len(raw),
            "partitions": len(partitions)}


def ingest_satellite_csv(csv_name: str = "satellite_imagery.csv",
                         dataset: str = "satellite") -> dict:
    """Ingest the satellite-derived climate indices."""
    src = RAW_DATA_DIR / csv_name
    if not src.exists():
        raise FileNotFoundError(f"{src} not found.")

    raw = pd.read_csv(src)
    raw["week_ending"] = pd.to_datetime(raw["week_ending"], errors="coerce")
    raw = raw.dropna(subset=["week_ending"])

    storage = get_storage()
    partitions = partition_and_store(raw, dataset, "week_ending", storage)

    register_dataset(dataset, len(raw), partitions, list(raw.columns), csv_name)
    return {"dataset": dataset, "rows_ingested": len(raw),
            "partitions": len(partitions)}


# ---------------------------------------------------------------------------
# Real-time ingestion (called by the stream simulator)
# ---------------------------------------------------------------------------
def ingest_reading(reading: dict) -> dict:
    """
    Validate and persist ONE live reading.

    Used by the real-time streaming module. Bad values are nulled out, and the
    reading is appended to today's live partition in HDFS.
    """
    record = dict(reading)
    record["timestamp"] = record.get("timestamp") or datetime.now().isoformat(
        timespec="seconds")

    for col, (lo, hi) in VALID_RANGES.items():
        if col in record and record[col] is not None:
            try:
                value = float(record[col])
                record[col] = value if lo <= value <= hi else None
            except (TypeError, ValueError):
                record[col] = None

    ts = pd.Timestamp(record["timestamp"])
    path = (f"/climate/live/readings/year={ts.year}/month={ts.month:02d}/"
            f"day={ts.day:02d}/part-live.csv")

    storage = get_storage()
    df = pd.DataFrame([record])
    if storage.exists(path):
        existing = storage.read_dataframe(path)
        df = pd.concat([existing, df], ignore_index=True)
    storage.put_dataframe(df, path)
    return record


def run_full_ingestion() -> list[dict]:
    """Backfill every historical source. Used by the CLI and the dashboard."""
    results = []
    for fn in (ingest_historical, ingest_sensor_csv, ingest_satellite_csv):
        try:
            results.append(fn())
        except FileNotFoundError as exc:
            log.warning("Skipping %s: %s", fn.__name__, exc)
    return results


if __name__ == "__main__":
    for summary in run_full_ingestion():
        print(summary)
