"""
OpenWeather live integration tests
==================================
Every test mocks `src.live.openweather._http_get` — no real network calls.
Storage, catalog registration and CSV export are isolated to tmp paths so
the repository's data/ folder is never touched.
"""

import json
from datetime import datetime

import pandas as pd
import pytest

from src.live import openweather as ow


# ---------------------------------------------------------------------------
# Fake OpenWeather payloads
# ---------------------------------------------------------------------------
def _weather_payload(city="Karachi", temp=33.4):
    return {
        "dt": 1760000000,
        "timezone": 18000,                     # UTC+5 (Pakistan)
        "name": city,
        "main": {"temp": temp, "feels_like": 36.1, "humidity": 61,
                 "pressure": 1008},
        "wind": {"speed": 4.2},                # m/s -> 15.12 kph
        "rain": {"3h": 1.6},
        "clouds": {"all": 40},
        "visibility": 9000,
        "sys": {"sunrise": 1759977600, "sunset": 1760019000},
        "weather": [{"main": "Clear", "description": "clear sky",
                     "icon": "01d"}],
    }


def _air_payload():
    return {"list": [{"main": {"aqi": 3},
                      "components": {"pm2_5": 32.68, "pm10": 58.0,
                                     "co": 230.1, "no2": 8.4, "o3": 41.2,
                                     "so2": 4.7}}]}


def _forecast_payload(tz=18000):
    items = []
    for i in range(40):
        items.append({
            "dt": 1760000000 + i * 3 * 3600,
            "main": {"temp": 30 + i * 0.1, "feels_like": 33.0,
                     "humidity": 55, "pressure": 1007},
            "wind": {"speed": 3.0},
            "rain": {"3h": 0.4} if i % 5 == 0 else {},
            "pop": 0.42 if i % 5 == 0 else 0.0,
            "weather": [{"main": "Rain", "description": "light rain",
                         "icon": "10d"}],
        })
    return {"city": {"timezone": tz}, "list": items}


def make_fake_http(fail_air=False, calls=None):
    """Return a fake `_http_get` that serves canned responses by URL."""

    def fake(url, tries=2):
        if calls is not None:
            calls.append(url)
        if "air_pollution" in url:
            if fail_air:
                raise ow.OpenWeatherError("Air quality unavailable.")
            return _air_payload()
        if "forecast?" in url:
            return _forecast_payload()
        if "weather?" in url:
            return _weather_payload()
        raise ow.OpenWeatherError(f"Unexpected URL: {url}")

    return fake


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def live_env(tmp_path, monkeypatch, client):
    """Client + isolated OpenWeather module state (mocked HTTP everywhere)."""
    from src.hadoop.storage import LocalHDFS

    registered = []
    exported = []

    monkeypatch.setattr(ow, "get_storage", lambda: LocalHDFS(tmp_path / "hdfs"))
    monkeypatch.setattr(ow, "PROCESSED_DATA_DIR", tmp_path / "processed")

    def fake_register(name, rows, partitions, columns, source):
        registered.append({"name": name, "rows": rows, "source": source,
                           "partitions": partitions, "columns": columns})

    monkeypatch.setattr(ow, "register_dataset", fake_register)
    monkeypatch.setattr(
        ow, "export_dataset_csv",
        lambda dataset: exported.append(dataset) or "ok")
    monkeypatch.setattr(ow, "_http_get", make_fake_http())
    ow.reset_state()
    yield {"client": client, "registered": registered,
           "exported": exported, "tmp": tmp_path}
    ow.reset_state()


@pytest.fixture()
def live_headers(live_env):
    res = live_env["client"].post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin@123"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.get_json()['token']}"}


# ---------------------------------------------------------------------------
# Fetcher unit tests
# ---------------------------------------------------------------------------
def test_fetch_current_normalizes_project_schema(monkeypatch):
    monkeypatch.setattr(ow, "_http_get", make_fake_http())
    row = ow.fetch_current(ow.CITIES[0])

    # Full schema present; live CO2 + sea-level are honest nulls (missing).
    for col in ("temperature_c", "humidity_pct", "rainfall_mm", "co2_ppm",
                "pm25", "wind_speed_kph", "sea_level_mm"):
        assert col in row
    assert row["station_id"] == "OW-KHI"
    assert row["city"] == "Karachi"
    assert row["region"] == "coastal"
    assert row["temperature_c"] == 33.4
    assert row["humidity_pct"] == 61
    assert row["wind_speed_kph"] == pytest.approx(15.12)   # 4.2 m/s * 3.6
    assert row["rainfall_mm"] == 1.6
    assert row["pm25"] == 32.68
    assert row["aqi"] == 3
    assert row["co2_ppm"] is None and row["sea_level_mm"] is None
    assert row["weather_main"] == "Clear"
    assert row["sunrise"] and row["sunset"]
    # date parses as a city-local timestamp
    parsed = datetime.fromisoformat(row["date"])
    assert parsed.year >= 2025


def test_fetch_current_survives_air_quality_failure(monkeypatch):
    monkeypatch.setattr(ow, "_http_get", make_fake_http(fail_air=True))
    row = ow.fetch_current(ow.CITIES[0])
    assert row["temperature_c"] == 33.4        # weather still delivered
    assert row["pm25"] is None                 # graceful missing value
    assert row["aqi"] is None


def test_fetch_forecast_shape_and_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(ow, "_http_get", make_fake_http(calls=calls))
    ow.reset_state()
    try:
        rows = ow.fetch_forecast(ow.CITIES[0])
        assert len(rows) == 40
        assert rows[0]["is_forecast"] is True
        assert rows[0]["precipitation_prob"] in (0.0, 0.42)
        assert rows[0]["city"] == "Karachi"
        first_calls = len(calls)

        # Second call inside the TTL must be served from cache.
        again = ow.fetch_forecast(ow.CITIES[0])
        assert len(again) == 40
        assert len(calls) == first_calls
    finally:
        ow.reset_state()


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------
def test_sync_writes_partitions_catalog_and_csv(live_env):
    fired = []
    result = ow.sync(on_reading=lambda r: fired.append(r) or [], force=True)

    assert result["skipped"] is False
    assert result["readings"] == len(ow.CITIES) == 12
    assert result["forecast_rows"] == 40 * 12
    assert result["errors"] == []
    assert "12 cities" in result["message"]
    assert len(fired) == 12                       # alerts saw every reading

    # HDFS-partitioned storage written under year=/month= folders
    storage = ow.get_storage()
    parts = storage.glob("/climate/openweather_current/**/*.csv")
    assert parts and all("year=" in p and "month=" in p for p in parts)
    stored = storage.read_dataset("/climate/openweather_current/**/*.csv")
    assert len(stored) == 12
    assert set(ow.SCHEMA_METRICS).issubset(stored.columns)
    assert stored["co2_ppm"].isna().all()         # missing metric preserved

    # Forecast dataset + catalog + flat CSV exports
    fc_parts = storage.glob("/climate/openweather_forecast/**/*.csv")
    assert fc_parts
    sources = {c["name"]: c["source"] for c in live_env["registered"]}
    assert sources[ow.CURRENT_DATASET] == "openweather"
    assert sources[ow.FORECAST_DATASET] == "openweather"
    assert ow.CURRENT_DATASET in live_env["exported"]

    # In-memory cache feeds /api/live/latest
    latest = ow.latest()
    assert latest["count"] == 12
    assert {r["city"] for r in latest["readings"]} == {
        c["name"] for c in ow.CITIES}


def test_sync_appends_across_runs(live_env):
    ow.sync(force=True)
    ow.sync(force=True, include_forecast=False)

    storage = ow.get_storage()
    stored = storage.read_dataset("/climate/openweather_current/**/*.csv")
    assert len(stored) == 24                      # append, never overwrite
    # newest sync recorded latest
    assert ow.status()["last_sync_rows"] == 12


def test_sync_cooldown_skips_unless_forced(live_env):
    ow.sync(force=True)
    second = ow.sync()                            # inside the 30s cooldown
    assert second["skipped"] is True
    assert "quota" in second["message"]

    forced = ow.sync(force=True)
    assert forced["skipped"] is False


def test_sync_raises_when_every_city_fails(monkeypatch):
    def broken(url, tries=2):
        raise ow.OpenWeatherError("Network unavailable while calling "
                                  "OpenWeather.")
    monkeypatch.setattr(ow, "_http_get", broken)
    ow.reset_state()
    with pytest.raises(ow.OpenWeatherError):
        ow.sync(force=True)
    assert "Network unavailable" in ow.status()["last_error"]


def test_status_reports_configuration():
    ow.reset_state()
    st = ow.status()
    assert st["configured"] is True
    assert st["key_masked"].startswith("e4594")
    assert st["cities"] == 12
    assert st["units"] == "metric"
    assert st["auto_sync"] is (ow.OW_SYNC_INTERVAL_MIN > 0)
    assert st["calls_per_sync"] in (24, 36)
    assert st["last_sync_at"] is None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
def test_live_endpoints_require_authentication(live_env):
    client = live_env["client"]
    assert client.get("/api/live/status").status_code == 401
    assert client.get("/api/live/latest").status_code == 401
    assert client.get("/api/live/cities").status_code == 401
    assert client.post("/api/live/sync").status_code == 401
    assert client.get("/api/live/forecast").status_code == 401


def test_live_status_endpoint(live_env, live_headers):
    res = live_env["client"].get("/api/live/status", headers=live_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["configured"] is True
    assert body["base_url"].endswith("/data/2.5")


def test_live_cities_endpoint(live_env, live_headers):
    res = live_env["client"].get("/api/live/cities", headers=live_headers)
    assert res.status_code == 200
    cities = res.get_json()["cities"]
    assert len(cities) == 12
    assert {"code", "name", "lat", "lon", "region"} <= set(cities[0])


def test_live_sync_and_latest_endpoints(live_env, live_headers):
    client = live_env["client"]

    res = client.post("/api/live/sync", json={}, headers=live_headers)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["readings"] == 12
    assert body["skipped"] is False

    res = client.get("/api/live/latest", headers=live_headers)
    assert res.status_code == 200
    latest = res.get_json()
    assert latest["count"] == 12
    row = latest["readings"][0]
    assert row["temperature_c"] is not None
    assert "weather_main" in row

    # Cooldown: an immediate second sync reports itself as skipped.
    res = client.post("/api/live/sync", json={}, headers=live_headers)
    assert res.status_code == 200
    assert res.get_json()["skipped"] is True


def test_live_forecast_endpoint(live_env, live_headers):
    client = live_env["client"]
    res = client.get("/api/live/forecast?city=Lahore", headers=live_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["city"]["name"] == "Lahore"
    assert body["count"] == 40
    assert body["points"][0]["temperature_c"] is not None

    res = client.get("/api/live/forecast?city=Gotham", headers=live_headers)
    assert res.status_code == 404
    assert "Unknown city" in res.get_json()["error"]


def test_datasets_endpoint_hides_synthetic_archives(live_env, live_headers,
                                                    monkeypatch):
    catalog = {
        "weather": {"source": "weather_stations.csv", "rows": 13140},
        "sensors": {"source": "sensor_network.csv", "rows": 20000},
        "openweather_current": {"source": "openweather", "rows": 12},
    }
    monkeypatch.setattr("src.api.app.list_datasets", lambda: catalog)
    res = live_env["client"].get("/api/data/datasets", headers=live_headers)
    assert res.status_code == 200
    names = [d["name"] for d in res.get_json()["datasets"]]
    assert names == ["openweather_current"]        # dummy data never shown


def test_readings_empty_hint_points_to_live_sync(live_env, live_headers):
    res = live_env["client"].get("/api/data/readings", headers=live_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["readings"] == []
    assert "Sync live weather" in body["hint"]


# ---------------------------------------------------------------------------
# Analytics guards for live data with missing metrics
# ---------------------------------------------------------------------------
def _live_like_df(days=3):
    """Synthetic *shape* of accumulated live rows (values arbitrary)."""
    n = days * 4
    dates = pd.date_range("2026-10-13", periods=n, freq="6h")
    return pd.DataFrame({
        "station_id": ["OW-LHE"] * n,
        "city": ["Lahore"] * n,
        "date": dates,
        "temperature_c": [30 + (i % 7) for i in range(n)],
        "humidity_pct": [50 + (i % 5) for i in range(n)],
        "rainfall_mm": [0.0] * n,
        "co2_ppm": [float("nan")] * n,           # no live CO2 sensor
        "pm25": [20 + (i % 9) for i in range(n)],
        "wind_speed_kph": [8 + (i % 4) for i in range(n)],
        "sea_level_mm": [float("nan")] * n,      # no live source
        "region": ["inland"] * n,
        "aqi": [3] * n,
        "weather_main": ["Clear"] * n,
    })


def test_correlation_skips_metrics_without_live_values(live_env, live_headers,
                                                       monkeypatch):
    monkeypatch.setattr("src.api.app._weather_df", _live_like_df)
    res = live_env["client"].get("/api/analytics/correlation",
                                 headers=live_headers)
    assert res.status_code == 200, res.get_json()
    matrix = res.get_json()["matrix"]
    assert "co2_ppm" not in matrix               # all-null columns excluded
    assert "sea_level_mm" not in matrix
    assert "temperature_c" in matrix


def test_timeseries_adapts_to_short_live_spans(live_env, live_headers,
                                               monkeypatch):
    monkeypatch.setattr("src.api.app._weather_df", _live_like_df)
    res = live_env["client"].get("/api/analytics/timeseries?metric=temperature_c",
                                 headers=live_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["frequency"] == "h"              # 3-day span -> hourly buckets
    assert len(body["points"]) >= 3
    assert "00:00" in body["points"][0]["date"] or ":" in body["points"][0]["date"]

    # A metric with no live values gives a friendly error, not a crash.
    res = live_env["client"].get("/api/analytics/timeseries?metric=co2_ppm",
                                 headers=live_headers)
    assert res.status_code == 400


def test_summary_ignores_absent_metrics(live_env, live_headers, monkeypatch):
    monkeypatch.setattr("src.api.app._weather_df", _live_like_df)
    res = live_env["client"].get("/api/analytics/summary", headers=live_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["available"] is True
    assert body["source"] == "openweather"
    assert body["averages"]["co2_ppm"] is None
    assert body["averages"]["temperature_c"] is not None
    assert body["missing_values"] > 0            # missing data is reported
    # live extras surfaced for the dashboard table
    assert "humidity_pct" in body["latest_by_station"][0]
    assert "weather_main" in body["latest_by_station"][0]


def test_run_job_defaults_to_live_csv(live_env, live_headers, monkeypatch):
    # Fake the live export existing in a tmp PROCESSED_DATA_DIR
    monkeypatch.setattr("src.api.app.PROCESSED_DATA_DIR", live_env["tmp"])
    target = live_env["tmp"] / f"{ow.CURRENT_DATASET}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("station_id,temperature_c\nOW-LHE,30\n", encoding="utf-8")

    captured = {}

    def fake_run_job(name, input_csv, zscore=3.0):
        captured["input"] = input_csv
        return pd.DataFrame({"job": [name]})

    monkeypatch.setattr("src.api.app.run_job", fake_run_job)
    res = live_env["client"].post("/api/analytics/jobs/run",
                                  json={"job": "anomaly_detection"},
                                  headers=live_headers)
    assert res.status_code == 200, res.get_json()
    assert captured["input"] == f"data/processed/{ow.CURRENT_DATASET}.csv"
