"""
Real-time climate data streaming simulator
==========================================
Satisfies the "Real-time Data Processing" functional requirement.

A background thread continuously generates live readings (as an environmental
sensor network would), pushes them through the ingestion pipeline and stores
them in the HDFS live partition. Consumers (dashboard + alert engine) read the
latest readings from `get_latest_readings()`.

The simulator is deliberately pluggable: replace `generate_reading()` with a
Kafka/MQTT consumer to attach a real event source without touching the rest of
the system.
"""

import random
import threading
import time
from collections import deque
from datetime import datetime

from src.config import (
    RAW_DATA_DIR,
    STREAM_BATCH_PER_TICK,
    STREAM_INTERVAL_SECONDS,
)
from src.ingestion.pipeline import ingest_reading
from src.utils.logger import get_logger

log = get_logger("earthscape.stream")

# In-memory ring buffer of the newest readings (consumed by the dashboard API)
_LATEST: deque[dict] = deque(maxlen=500)
_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None

# Baselines per region, mirroring the test-data generator
_BASELINES = {
    "coastal": {"temperature_c": 27.5, "humidity_pct": 68, "co2_ppm": 415.0,
                "pm25": 55.0, "wind_speed_kph": 12.0, "rainfall_mm": 3.0,
                "sea_level_mm": 0.0},
    "inland": {"temperature_c": 24.0, "humidity_pct": 48, "co2_ppm": 422.0,
               "pm25": 78.0, "wind_speed_kph": 10.0, "rainfall_mm": 1.8,
               "sea_level_mm": -6.0},
    "highland": {"temperature_c": 12.5, "humidity_pct": 42, "co2_ppm": 405.0,
                 "pm25": 22.0, "wind_speed_kph": 14.0, "rainfall_mm": 1.2,
                 "sea_level_mm": 14.0},
}

_STATIONS = [
    ("STN-001", "Karachi", "coastal"),
    ("STN-002", "Lahore", "inland"),
    ("STN-003", "Islamabad", "inland"),
    ("STN-004", "Quetta", "highland"),
    ("STN-005", "Peshawar", "inland"),
    ("STN-006", "Hyderabad", "coastal"),
    ("STN-007", "Multan", "inland"),
    ("STN-008", "Gilgit", "highland"),
    ("STN-009", "Skardu", "highland"),
    ("STN-010", "Sukkur", "inland"),
    ("STN-011", "Bahawalpur", "inland"),
    ("STN-012", "Gwadar", "coastal"),
]


def generate_reading(rng: random.Random | None = None) -> dict:
    """
    Produce one simulated live reading.

    ~5% of readings intentionally carry an extreme spike so the alerting and
    anomaly-detection features always have something to show.
    """
    rng = rng or random
    stn_id, city, region = rng.choice(_STATIONS)
    base = _BASELINES[region]

    reading = {
        "station_id": stn_id,
        "city": city,
        "region": region,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "temperature_c": round(base["temperature_c"] + rng.gauss(0, 2.0), 2),
        "humidity_pct": round(min(100, max(0, base["humidity_pct"] + rng.gauss(0, 6))), 2),
        "co2_ppm": round(base["co2_ppm"] + rng.gauss(0, 3), 2),
        "pm25": round(max(1.0, base["pm25"] + rng.gauss(0, 12)), 2),
        "wind_speed_kph": round(max(0.0, base["wind_speed_kph"] + rng.gauss(0, 3)), 2),
        "rainfall_mm": round(max(0.0, base["rainfall_mm"] + rng.gauss(0, 1.2)), 2),
        "sea_level_mm": round(base["sea_level_mm"] + rng.gauss(0, 1.5), 2),
    }

    if rng.random() < 0.05:  # spike for the demo
        spike_metric = rng.choice(["temperature_c", "pm25", "wind_speed_kph",
                                   "co2_ppm"])
        reading[spike_metric] = round(reading[spike_metric] * rng.uniform(1.8, 2.6), 2)
        reading["simulated_event"] = spike_metric
    return reading


def get_latest_readings(limit: int = 100) -> list[dict]:
    """Newest-first snapshot of the live stream (thread-safe)."""
    with _LOCK:
        items = list(_LATEST)
    return list(reversed(items))[:limit]


def get_live_series(station_id: str | None = None,
                    metric: str = "temperature_c",
                    limit: int = 200) -> dict:
    """Time series of one metric for charting, optionally filtered by station."""
    with _LOCK:
        items = list(_LATEST)
    if station_id:
        items = [r for r in items if r.get("station_id") == station_id]
    items = items[-limit:]
    return {
        "timestamps": [r["timestamp"] for r in items],
        "values": [r.get(metric) for r in items],
        "stations": [r.get("station_id") for r in items],
        "metric": metric,
    }


def _stream_loop(interval: float = STREAM_INTERVAL_SECONDS,
                 batch: int = STREAM_BATCH_PER_TICK) -> None:
    """Continuously generate + ingest readings until stopped."""
    rng = random.Random()
    log.info("Live stream started (interval=%ss, batch=%d)", interval, batch)
    while not _STOP.is_set():
        for _ in range(batch):
            reading = generate_reading(rng)
            try:
                stored = ingest_reading(reading)
            except Exception as exc:  # pragma: no cover - defensive
                log.error("Failed to ingest live reading: %s", exc)
                stored = reading
            with _LOCK:
                _LATEST.append(stored)
        _STOP.wait(interval)
    log.info("Live stream stopped.")


def start_stream(interval: float = STREAM_INTERVAL_SECONDS,
                 batch: int = STREAM_BATCH_PER_TICK,
                 persist: bool = True) -> threading.Thread:
    """Start the background stream thread (idempotent)."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return _THREAD
    _STOP.clear()
    target = _stream_loop if persist else \
        lambda: _stream_loop(interval, batch)
    _THREAD = threading.Thread(target=target, args=(), daemon=True,
                               name="earthscape-stream")
    _THREAD.start()
    return _THREAD


def stop_stream(timeout: float = 5.0) -> None:
    """Signal the stream thread to stop and wait for it."""
    _STOP.set()
    if _THREAD and _THREAD.is_alive():
        _THREAD.join(timeout=timeout)


def stream_once() -> list[dict]:
    """Generate a single batch without starting a thread (used by tests)."""
    rng = random.Random()
    batch = [ingest_reading(generate_reading(rng))
             for _ in range(STREAM_BATCH_PER_TICK)]
    with _LOCK:
        _LATEST.extend(batch)
    return batch
