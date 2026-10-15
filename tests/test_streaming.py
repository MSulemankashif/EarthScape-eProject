"""Tests for the real-time streaming simulator."""

import time

import pytest

from src import streaming
from src.streaming import (
    generate_reading,
    get_latest_readings,
    get_live_series,
    stream_once,
)


@pytest.fixture(autouse=True)
def clean_buffer():
    """Empty the shared ring buffer before/after each test."""
    with streaming._LOCK:
        streaming._LATEST.clear()
    yield
    with streaming._LOCK:
        streaming._LATEST.clear()


def test_generate_reading_schema():
    r = generate_reading()
    for key in ("station_id", "city", "region", "timestamp",
                "temperature_c", "co2_ppm", "pm25"):
        assert key in r, f"missing key {key}"
    assert r["region"] in ("coastal", "inland", "highland")
    assert -60 < r["temperature_c"] < 70


def test_generate_reading_is_seeded_reproducible():
    import random
    a = generate_reading(random.Random(5))
    b = generate_reading(random.Random(5))
    assert a == b


def test_stream_once_appends_to_buffer():
    batch = stream_once()
    assert len(batch) >= 1
    latest = get_latest_readings(limit=10)
    assert len(latest) == len(batch)
    # Newest first
    assert latest[0]["timestamp"] >= latest[-1]["timestamp"]


def test_live_series_filtering():
    stream_once()
    stream_once()

    everything = get_live_series(metric="temperature_c")
    assert len(everything["values"]) >= 1
    assert everything["metric"] == "temperature_c"

    one_station = get_live_series(station_id="STN-001")
    assert all(s == "STN-001" for s in one_station["stations"])


def test_start_and_stop_stream():
    t = streaming.start_stream(interval=0.05, batch=1, persist=False)
    assert t.is_alive()
    deadline = time.time() + 3
    while time.time() < deadline and not get_latest_readings(1):
        time.sleep(0.05)
    streaming.stop_stream(timeout=3)
    assert not t.is_alive()
    assert get_latest_readings(1), "no readings produced before stop"


def test_spike_probability_generates_events():
    import random
    rng = random.Random(3)
    events = sum(1 for _ in range(200)
                 if "simulated_event" in generate_reading(rng))
    # ~5% expected -> between 0 and 25 out of 200 is a sane band
    assert 0 < events < 30
