"""
OpenWeatherMap live client & sync engine
========================================
The dashboard's PRIMARY data source: real, live climate data pulled from the
OpenWeatherMap free-tier API (no synthetic readings anywhere in the UI).

Endpoints used (free plan, 60 calls/minute):
    GET /data/2.5/weather?q=City,CC    current conditions per city
    GET /data/2.5/air_pollution        AQI + PM2.5 / PM10 / O3 / NO2 / CO
    GET /data/2.5/forecast?q=City,CC   real 5-day / 3-hour forecast

Flow of one sync:
    12 cities x (weather + air) [+ optional 12 forecast calls]
        -> normalized rows (project schema, missing metrics stay NaN)
        -> cleaning + range validation (pipeline helpers)
        -> appended to HDFS-partitioned storage
        -> dataset catalog + flat CSV export (MapReduce/Tableau/Jupyter)
        -> alert rules evaluated per reading
        -> in-memory cache for fast dashboard reads

Every request is plain ``urllib`` (no extra dependency) with friendly,
human-readable errors mapped from HTTP status codes.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.config import (
    OPENWEATHER_API_KEY,
    OPENWEATHER_BASE,
    OPENWEATHER_UNITS,
    OW_HTTP_TIMEOUT,
    OW_MIN_SYNC_GAP_SECONDS,
    OW_SYNC_FORECAST,
    OW_SYNC_INTERVAL_MIN,
    PROCESSED_DATA_DIR,
)
from src.hadoop.storage import get_storage
from src.ingestion.pipeline import (
    apply_range_validation,
    coerce_numeric,
    register_dataset,
)
from src.utils.logger import get_logger

log = get_logger("earthscape.live")

# ---------------------------------------------------------------------------
# Station network — 12 real Pakistani cities with coordinates
# ---------------------------------------------------------------------------
CITIES: list[dict] = [
    {"code": "OW-KHI", "name": "Karachi",     "country": "PK", "lat": 24.8608, "lon": 67.0011, "region": "coastal"},
    {"code": "OW-GWD", "name": "Gwadar",      "country": "PK", "lat": 25.1268, "lon": 62.3205, "region": "coastal"},
    {"code": "OW-HYD", "name": "Hyderabad",   "country": "PK", "lat": 25.3960, "lon": 68.3578, "region": "inland"},
    {"code": "OW-LHE", "name": "Lahore",      "country": "PK", "lat": 31.5204, "lon": 74.3587, "region": "inland"},
    {"code": "OW-FSD", "name": "Faisalabad",  "country": "PK", "lat": 31.4504, "lon": 73.1350, "region": "inland"},
    {"code": "OW-MUX", "name": "Multan",      "country": "PK", "lat": 30.1575, "lon": 71.5249, "region": "inland"},
    {"code": "OW-ISB", "name": "Islamabad",   "country": "PK", "lat": 33.6844, "lon": 73.0479, "region": "inland"},
    {"code": "OW-RWP", "name": "Rawalpindi",  "country": "PK", "lat": 33.5651, "lon": 73.0169, "region": "inland"},
    {"code": "OW-PEW", "name": "Peshawar",    "country": "PK", "lat": 34.0151, "lon": 71.5249, "region": "inland"},
    {"code": "OW-UET", "name": "Quetta",      "country": "PK", "lat": 30.1798, "lon": 66.9750, "region": "highland"},
    {"code": "OW-GIL", "name": "Gilgit",      "country": "PK", "lat": 35.9208, "lon": 74.3144, "region": "highland"},
    {"code": "OW-MUR", "name": "Murree",      "country": "PK", "lat": 33.9070, "lon": 73.3943, "region": "highland"},
]

# Every storage row carries the full project schema. OpenWeather has no
# outdoor CO2 or sea-level sensor, so those columns stay null — a genuine
# demonstration of "handle missing or incomplete data gracefully".
SCHEMA_METRICS = ["temperature_c", "humidity_pct", "rainfall_mm",
                  "co2_ppm", "pm25", "wind_speed_kph", "sea_level_mm"]

CURRENT_DATASET = "openweather_current"
FORECAST_DATASET = "openweather_forecast"

FORECAST_CACHE_TTL = 300          # seconds: reuse /forecast responses

# ---------------------------------------------------------------------------
# Module state (in-memory cache + sync bookkeeping)
# ---------------------------------------------------------------------------
_state: dict = {
    "last_sync_ts": 0.0,
    "last_sync_at": None,
    "rows": [],                    # latest normalized reading per city
    "duration_seconds": None,
    "sync_count": 0,
    "last_error": None,
    "last_partial_errors": [],
}
_forecast_cache: dict[str, tuple[float, list[dict]]] = {}


class OpenWeatherError(RuntimeError):
    """Friendly, human-readable API/network failure."""


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _http_get(url: str, tries: int = 2) -> dict:
    """GET JSON from OpenWeather, mapping failures to friendly errors."""
    last_exc: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=OW_HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("message", "")
            except Exception:                                  # pragma: no cover
                detail = ""
            if exc.code == 401:
                raise OpenWeatherError(
                    "OpenWeather rejected the API key (401). "
                    "Check OPENWEATHER_API_KEY in src/config.py.") from exc
            if exc.code == 429:
                raise OpenWeatherError(
                    "OpenWeather rate limit reached (429) — wait a minute "
                    "and try again.") from exc
            if exc.code == 404:
                raise OpenWeatherError(
                    f"City not found on OpenWeather (404). {detail}") from exc
            last_exc = OpenWeatherError(
                f"OpenWeather HTTP {exc.code}: {detail or exc.reason}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = OpenWeatherError(
                f"Network unavailable while calling OpenWeather ({exc}). "
                "Check your internet connection.")
        if attempt < tries - 1:
            time.sleep(1.2)        # brief back-off before the retry
    raise last_exc if last_exc else OpenWeatherError("OpenWeather call failed.")


def _local_dt(unix: int | float, tz_offset: int) -> datetime:
    """Unix timestamp -> naive city-local datetime (what users expect)."""
    return datetime.fromtimestamp(int(unix), tz=timezone.utc) + timedelta(
        seconds=tz_offset)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------
def fetch_current(city: dict) -> dict:
    """Current conditions + air quality for ONE city -> normalized row."""
    params = urllib.parse.urlencode({
        "q": f"{city['name']},{city['country']}",
        "units": OPENWEATHER_UNITS,
        "appid": OPENWEATHER_API_KEY,
    })
    weather = _http_get(f"{OPENWEATHER_BASE}/weather?{params}")
    tz_offset = int(weather.get("timezone", 0))

    # Air quality is enrichment — a hiccup here must not fail the sync.
    components: dict = {}
    aqi = None
    try:
        air = _http_get(
            f"{OPENWEATHER_BASE}/air_pollution?lat={city['lat']}"
            f"&lon={city['lon']}&appid={OPENWEATHER_API_KEY}")
        first = air.get("list", [{}])[0]
        components = first.get("components", {})
        aqi = first.get("main", {}).get("aqi")
    except OpenWeatherError as exc:
        log.warning("Air quality unavailable for %s: %s", city["name"], exc)

    main = weather.get("main", {})
    wind = weather.get("wind", {})
    rain = weather.get("rain", {})
    sys_info = weather.get("sys", {})
    condition = (weather.get("weather") or [{}])[0]

    obs = _local_dt(weather.get("dt", time.time()), tz_offset)
    wind_ms = wind.get("speed")
    row = {
        "station_id": city["code"],
        "city": city["name"],
        "country": city["country"],
        "region": city["region"],
        "latitude": city["lat"],
        "longitude": city["lon"],
        "date": obs.isoformat(timespec="seconds"),
        # --- core schema (metrics used by charts / alerts / MapReduce) ---
        "temperature_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity_pct": main.get("humidity"),
        "rainfall_mm": rain.get("3h", 0.0),   # no field = no rain reported
        "co2_ppm": None,                       # no outdoor CO2 sensor (missing)
        "pm25": components.get("pm2_5"),
        "wind_speed_kph": round(wind_ms * 3.6, 2) if wind_ms is not None else None,
        "sea_level_mm": None,                  # no live source (missing)
        # --- extras that make the live view richer ---
        "pressure_hpa": main.get("pressure"),
        "cloud_pct": weather.get("clouds", {}).get("all"),
        "visibility_m": weather.get("visibility"),
        "aqi": aqi,
        "co_ugm3": components.get("co"),
        "no2_ugm3": components.get("no2"),
        "o3_ugm3": components.get("o3"),
        "so2_ugm3": components.get("so2"),
        "pm10_ugm3": components.get("pm10"),
        "weather_main": condition.get("main"),
        "weather_desc": condition.get("description"),
        "weather_icon": condition.get("icon"),
        "sunrise": datetime.fromtimestamp(
            sys_info["sunrise"], tz=timezone.utc
        ).astimezone(timezone(timedelta(seconds=tz_offset))).strftime("%H:%M") \
            if sys_info.get("sunrise") else None,
        "sunset": datetime.fromtimestamp(
            sys_info["sunset"], tz=timezone.utc
        ).astimezone(timezone(timedelta(seconds=tz_offset))).strftime("%H:%M") \
            if sys_info.get("sunset") else None,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
    }
    return row


def fetch_forecast(city: dict) -> list[dict]:
    """Real 5-day / 3-hour forecast for ONE city -> list of normalized rows."""
    cached = _forecast_cache.get(city["name"])
    if cached and time.time() - cached[0] < FORECAST_CACHE_TTL:
        return cached[1]

    params = urllib.parse.urlencode({
        "q": f"{city['name']},{city['country']}",
        "units": OPENWEATHER_UNITS,
        "appid": OPENWEATHER_API_KEY,
    })
    payload = _http_get(f"{OPENWEATHER_BASE}/forecast?{params}")
    tz_offset = int(payload.get("city", {}).get("timezone", 0))

    rows: list[dict] = []
    for item in payload.get("list", []):
        main = item.get("main", {})
        wind = item.get("wind", {})
        rain = item.get("rain", {})
        wind_ms = wind.get("speed")
        condition = (item.get("weather") or [{}])[0]
        rows.append({
            "station_id": city["code"],
            "city": city["name"],
            "country": city["country"],
            "region": city["region"],
            "date": _local_dt(item.get("dt", 0), tz_offset)
                        .isoformat(timespec="seconds"),
            "temperature_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "humidity_pct": main.get("humidity"),
            "rainfall_mm": rain.get("3h", 0.0),
            "co2_ppm": None,
            "pm25": None,                    # air forecast is a paid add-on
            "wind_speed_kph": round(wind_ms * 3.6, 2) if wind_ms is not None else None,
            "sea_level_mm": None,
            "precipitation_prob": item.get("pop"),
            "weather_main": condition.get("main"),
            "weather_desc": condition.get("description"),
            "weather_icon": condition.get("icon"),
            "is_forecast": True,
            "synced_at": datetime.now().isoformat(timespec="seconds"),
        })
    _forecast_cache[city["name"]] = (time.time(), rows)
    return rows


# ---------------------------------------------------------------------------
# Storage helpers (append-friendly, unlike partition_and_store which overwrites)
# ---------------------------------------------------------------------------
def _store_append(df: pd.DataFrame, dataset: str,
                  date_col: str = "date") -> list[str]:
    """Append rows to /climate/<dataset>/year=/month=/ part-files."""
    storage = get_storage()
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    written: list[str] = []
    for (year, month), group in work.groupby([work[date_col].dt.year,
                                              work[date_col].dt.month]):
        path = (f"/climate/{dataset}/year={int(year)}/"
                f"month={int(month):02d}/part-00000.csv")
        if storage.exists(path):
            existing = storage.read_dataframe(path)
            group = pd.concat([existing, group], ignore_index=True)
        storage.put_dataframe(group, path)
        written.append(path)
    return written


def export_dataset_csv(dataset: str) -> str | None:
    """Flat CSV copy for MapReduce jobs, Tableau, Jupyter and RStudio."""
    storage = get_storage()
    df = storage.read_dataset(f"/climate/{dataset}/**/*.csv")
    if df.empty:
        return None
    target = PROCESSED_DATA_DIR / f"{dataset}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)
    return str(target)


def _clean(rows: list[dict]) -> pd.DataFrame:
    """Numeric coercion + physical range validation (pipeline rules)."""
    df = pd.DataFrame(rows)
    df = coerce_numeric(df, SCHEMA_METRICS + [
        "latitude", "longitude", "pressure_hpa", "cloud_pct",
        "visibility_m", "aqi", "precipitation_prob",
    ])
    df = apply_range_validation(df)
    return df


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------
def sync(include_forecast: bool | None = None,
         on_reading=None, force: bool = False) -> dict:
    """
    Pull live data for every city, store it, register it and raise alerts.

    Returns a summary dict; raises OpenWeatherError when nothing could be
    fetched. A second call inside the cooldown window is skipped (unless
    force=True) so the free API quota is protected.
    """
    now = time.time()
    gap = now - _state["last_sync_ts"]
    if not force and _state["last_sync_ts"] and gap < OW_MIN_SYNC_GAP_SECONDS:
        return {
            "skipped": True,
            "message": (f"Synced {int(gap)}s ago — cooldown of "
                        f"{OW_MIN_SYNC_GAP_SECONDS}s protects the free API quota."),
            "status": status(),
        }
    if not OPENWEATHER_API_KEY:
        raise OpenWeatherError(
            "No OpenWeather API key configured — set OPENWEATHER_API_KEY.")

    started = time.perf_counter()
    include_forecast = OW_SYNC_FORECAST if include_forecast is None \
        else include_forecast
    errors: list[str] = []
    rows: list[dict] = []

    # 1) current conditions + air quality (2 calls per city)
    for city in CITIES:
        try:
            rows.append(fetch_current(city))
        except OpenWeatherError as exc:
            errors.append(f"{city['name']}: {exc}")
            log.warning("Live fetch failed for %s: %s", city["name"], exc)

    if not rows:
        _state["last_error"] = errors[0] if errors else "no data"
        raise OpenWeatherError(
            "Every city failed: " + (errors[0] if errors else "unknown error"))

    # 2) optional real 5-day forecast (1 call per city)
    fc_rows: list[dict] = []
    if include_forecast:
        for city in CITIES:
            try:
                fc_rows.extend(fetch_forecast(city))
            except OpenWeatherError as exc:
                errors.append(f"{city['name']} forecast: {exc}")

    # 3) clean + store (append so repeated syncs build live history)
    current_df = _clean(rows)
    partitions = _store_append(current_df, CURRENT_DATASET)
    if fc_rows:
        _store_append(_clean(fc_rows), FORECAST_DATASET)

    # 4) catalog + flat CSVs for MapReduce / external tools
    storage = get_storage()
    for dataset in (CURRENT_DATASET, FORECAST_DATASET) if fc_rows \
            else (CURRENT_DATASET,):
        full = storage.read_dataset(f"/climate/{dataset}/**/*.csv")
        register_dataset(
            name=dataset,
            rows=len(full),
            partitions=sorted(storage.glob(f"/climate/{dataset}/**/*.csv")),
            columns=list(full.columns),
            source="openweather",
        )
        export_dataset_csv(dataset)

    # 5) alert rules evaluate every live reading
    fired = 0
    if on_reading:
        for row in rows:
            try:
                fired += len(on_reading(row) or [])
            except Exception as exc:                # pragma: no cover
                log.error("Alert evaluation failed: %s", exc)

    duration = round(time.perf_counter() - started, 3)
    _state.update({
        "last_sync_ts": time.time(),
        "last_sync_at": datetime.now().isoformat(timespec="seconds"),
        "rows": rows,
        "duration_seconds": duration,
        "sync_count": _state["sync_count"] + 1,
        "last_error": None,
        "last_partial_errors": errors,
    })
    log.info("Live sync complete: %d cities in %.2fs (%d forecast rows, "
             "%d alert(s)%s)", len(rows), duration, len(fc_rows), fired,
             f", {len(errors)} partial error(s)" if errors else "")

    return {
        "skipped": False,
        "message": f"Fetched live conditions for {len(rows)} cities in {duration}s.",
        "readings": len(rows),
        "forecast_rows": len(fc_rows),
        "alerts_fired": fired,
        "duration_seconds": duration,
        "errors": errors,
        "status": status(),
    }


# ---------------------------------------------------------------------------
# Read views
# ---------------------------------------------------------------------------
def latest() -> dict:
    """
    Latest reading per city — from the in-process cache, or (after a server
    restart) rebuilt from HDFS-partitioned storage so the UI stays alive.
    """
    if _state["rows"]:
        return {"synced_at": _state["last_sync_at"],
                "count": len(_state["rows"]), "readings": _state["rows"]}

    df = get_storage().read_dataset(f"/climate/{CURRENT_DATASET}/**/*.csv")
    if df.empty:
        return {"synced_at": None, "count": 0, "readings": []}
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    tail = (df.dropna(subset=["date"]).sort_values("date")
              .groupby("station_id").tail(1))
    records = []
    for rec in tail.to_dict(orient="records"):
        clean = {}
        for key, val in rec.items():
            if val is None or (isinstance(val, float) and pd.isna(val)):
                clean[key] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                clean[key] = val.isoformat()
            elif hasattr(val, "item"):
                clean[key] = val.item()
            else:
                clean[key] = val
        records.append(clean)
    return {"synced_at": str(df["date"].max()), "count": len(records),
            "readings": records}


def status() -> dict:
    """Live-source health for the Admin console and the UI chips."""
    key = OPENWEATHER_API_KEY or ""
    gap = time.time() - _state["last_sync_ts"] if _state["last_sync_ts"] else None
    next_in = None
    if OW_SYNC_INTERVAL_MIN > 0 and _state["last_sync_ts"]:
        elapsed_min = (time.time() - _state["last_sync_ts"]) / 60
        next_in = max(0, round(OW_SYNC_INTERVAL_MIN - elapsed_min, 1))
    return {
        "configured": bool(key),
        "key_masked": (key[:6] + "…" + key[-4:]) if len(key) > 12 else None,
        "base_url": OPENWEATHER_BASE,
        "units": OPENWEATHER_UNITS,
        "cities": len(CITIES),
        "auto_sync": OW_SYNC_INTERVAL_MIN > 0,
        "interval_minutes": OW_SYNC_INTERVAL_MIN,
        "forecast_enabled": OW_SYNC_FORECAST,
        "cooldown_seconds": OW_MIN_SYNC_GAP_SECONDS,
        "seconds_since_sync": round(gap, 1) if gap is not None else None,
        "next_auto_sync_in_min": next_in,
        "last_sync_at": _state["last_sync_at"],
        "last_sync_rows": len(_state["rows"]),
        "last_duration_seconds": _state["duration_seconds"],
        "sync_count": _state["sync_count"],
        "last_error": _state["last_error"],
        "partial_errors": _state["last_partial_errors"],
        "calls_per_sync": len(CITIES) * (3 if OW_SYNC_FORECAST else 2),
    }


def reset_state() -> None:
    """Testing helper: clear caches and cooldown."""
    _state.update({k: v for k, v in {
        "last_sync_ts": 0.0, "last_sync_at": None, "rows": [],
        "duration_seconds": None, "sync_count": 0, "last_error": None,
        "last_partial_errors": [],
    }.items()})
    _forecast_cache.clear()
