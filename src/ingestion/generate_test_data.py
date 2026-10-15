"""
Synthetic climate test-data generator
=====================================
Produces three realistic datasets for the EarthScape Climate Agency:

  1. weather_stations.csv  - daily readings from ground weather stations
  2. sensor_network.csv    - environmental sensor network (hourly, recent)
  3. satellite_imagery.csv - satellite derived climate indices (weekly)

The data contains:
  * seasonal + long-term warming trend
  * regional differences per station
  * intentional missing values (blank cells) so the pipeline can demonstrate
    "graceful handling of incomplete data"
  * a handful of injected extreme anomalies for the alerting / ML demo

Usage:
    python -m src.ingestion.generate_test_data
"""

import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    RAW_DATA_DIR,
    RANDOM_SEED,
    STATION_COUNT,
    YEARS_OF_HISTORY,
)
from src.utils.logger import get_logger

log = get_logger("earthscape.generate")

# Pakistani / regional style cities keep the eProject grounded in its context.
CITIES = [
    ("STN-001", "Karachi", 24.86, 67.01, "coastal"),
    ("STN-002", "Lahore", 31.55, 74.34, "inland"),
    ("STN-003", "Islamabad", 33.68, 73.05, "inland"),
    ("STN-004", "Quetta", 30.18, 66.98, "highland"),
    ("STN-005", "Peshawar", 34.01, 71.58, "inland"),
    ("STN-006", "Hyderabad", 25.39, 68.37, "coastal"),
    ("STN-007", "Multan", 30.20, 71.47, "inland"),
    ("STN-008", "Gilgit", 35.92, 74.31, "highland"),
    ("STN-009", "Skardu", 35.33, 75.53, "highland"),
    ("STN-010", "Sukkur", 27.71, 68.85, "inland"),
    ("STN-011", "Bahawalpur", 29.40, 71.68, "inland"),
    ("STN-012", "Gwadar", 25.12, 62.33, "coastal"),
]

REGION_BASE = {
    "coastal": {"temp": 27.5, "hum": 68, "rain": 3.0, "co2": 415.0, "pm25": 55.0, "sea": 0.0},
    "inland": {"temp": 24.0, "hum": 48, "rain": 1.8, "co2": 422.0, "pm25": 78.0, "sea": -6.0},
    "highland": {"temp": 12.5, "hum": 42, "rain": 1.2, "co2": 405.0, "pm25": 22.0, "sea": 14.0},
}


def _seasonal(day_of_year: int) -> float:
    """Simple sinusoidal seasonal component peaking mid-July."""
    return math.sin((day_of_year - 100) / 365.0 * 2 * math.pi)


def generate_weather_stations(start: str = "2022-01-01") -> pd.DataFrame:
    """Daily weather-station records for the last N years."""
    rng = random.Random(RANDOM_SEED)
    np_rng = np.random.default_rng(RANDOM_SEED)
    dates = pd.date_range(start=start, periods=YEARS_OF_HISTORY * 365, freq="D")

    rows = []
    for stn_id, city, lat, lon, region in CITIES:
        base = REGION_BASE[region]
        for i, date in enumerate(dates):
            seas = _seasonal(date.timetuple().tm_yday)
            trend = 0.012 * (i / 365.0)  # slow warming trend ~0.012 C/year
            temp = base["temp"] + 7.5 * seas + trend + rng.gauss(0, 1.8)
            hum = min(100, max(2, base["hum"] - 18 * seas + rng.gauss(0, 6)))
            # Monsoon months (Jul-Sep) get most rain
            monsoon = 1.6 if 6 <= date.month <= 9 else 0.35
            rain = max(0.0, base["rain"] * monsoon + rng.gauss(0, 1.4))
            co2 = base["co2"] + 2.4 * (i / 365.0) + rng.gauss(0, 3.0)
            pm25 = max(1.0, base["pm25"] + (12 if 10 <= date.month <= 1 else 0)
                       + rng.gauss(0, 12))
            wind = max(0.0, 9.0 + 5 * abs(seas) + rng.gauss(0, 4))
            sea = base["sea"] + 0.09 * (i / 365.0) + 4.5 * seas + rng.gauss(0, 1.2)

            rows.append({
                "station_id": stn_id,
                "city": city,
                "latitude": round(lat + rng.uniform(-0.02, 0.02), 4),
                "longitude": round(lon + rng.uniform(-0.02, 0.02), 4),
                "region": region,
                "date": date.strftime("%Y-%m-%d"),
                "temperature_c": round(temp, 2),
                "humidity_pct": round(hum, 2),
                "rainfall_mm": round(rain, 2),
                "co2_ppm": round(co2, 2),
                "pm25": round(pm25, 2),
                "wind_speed_kph": round(wind, 2),
                "sea_level_mm": round(sea, 2),
            })

    df = pd.DataFrame(rows)

    # --- Inject realistic data-quality issues -------------------------------
    # 1) ~1.5% random missing values across measurement columns
    measure_cols = ["temperature_c", "humidity_pct", "rainfall_mm",
                    "co2_ppm", "pm25", "wind_speed_kph", "sea_level_mm"]
    mask = np_rng.random(df.shape[0]) < 0.015
    df.loc[mask, measure_cols] = df.loc[mask, measure_cols].mask(
        np_rng.random((int(mask.sum()), len(measure_cols))) < 0.5
    )

    # 2) A few injected extreme anomalies (heatwaves / cyclone / pollution spike)
    anomaly_specs = [
        ("STN-001", "2024-05-20", "temperature_c", 51.0),   # Karachi heatwave
        ("STN-002", "2024-06-15", "pm25", 480.0),           # Lahore smog spike
        ("STN-006", "2024-09-01", "rainfall_mm", 320.0),    # cloudburst
        ("STN-005", "2023-04-12", "wind_speed_kph", 118.0), # storm
        ("STN-009", "2024-01-05", "temperature_c", -31.0),  # cold wave
    ]
    for stn, day, col, val in anomaly_specs:
        idx = df.index[(df["station_id"] == stn) & (df["date"] == day)]
        if len(idx):
            df.loc[idx[0], col] = val
            log.info("Injected anomaly: %s %s %s=%s", stn, day, col, val)

    log.info("Weather stations dataset: %d rows x %d cols", *df.shape)
    return df


def generate_sensor_network(rows: int = 20000) -> pd.DataFrame:
    """Environmental sensor network feed (hourly-ish, most recent period)."""
    rng = random.Random(RANDOM_SEED + 7)
    end = datetime.now()
    sensors = [f"SNS-{i:03d}" for i in range(1, 41)]
    types = ["air_quality", "soil_moisture", "water_ph", "noise_level"]

    records = []
    for _ in range(rows):
        stn_id, city, _, _, region = rng.choice(CITIES)
        base = REGION_BASE[region]
        ts = end - timedelta(hours=rng.randint(1, 24 * 90))
        stype = rng.choice(types)
        if stype == "air_quality":
            value = max(1.0, base["pm25"] + rng.gauss(0, 15))
            unit = "pm25_ug_m3"
        elif stype == "soil_moisture":
            value = min(100.0, max(0.0, 38 + rng.gauss(0, 9)))
            unit = "percent"
        elif stype == "water_ph":
            value = min(9.0, max(5.5, 7.4 + rng.gauss(0, 0.4)))
            unit = "ph"
        else:
            value = max(30.0, 62 + rng.gauss(0, 8))
            unit = "db"
        records.append({
            "sensor_id": rng.choice(sensors),
            "sensor_type": stype,
            "station_id": stn_id,
            "city": city,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "value": round(value, 3),
            "unit": unit,
            "battery_pct": round(min(100, max(5, rng.gauss(78, 14))), 1),
        })
    df = pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)
    log.info("Sensor network dataset: %d rows x %d cols", *df.shape)
    return df


def generate_satellite_imagery() -> pd.DataFrame:
    """Weekly satellite-derived climate indices per region."""
    rng = random.Random(RANDOM_SEED + 13)
    np_rng = np.random.default_rng(RANDOM_SEED + 13)
    weeks = pd.date_range(end=datetime.now().normalize(), periods=YEARS_OF_HISTORY * 52, freq="W")

    rows = []
    sat_ids = ["SAT-A", "SAT-B", "SAT-C"]
    for week in weeks:
        for region in REGION_BASE:
            seas = _seasonal(week.timetuple().tm_yday)
            idx = weeks.get_loc(week)
            rows.append({
                "satellite_id": rng.choice(sat_ids),
                "region": region,
                "week_ending": week.strftime("%Y-%m-%d"),
                "ndvi": round(min(0.95, max(0.02, 0.45 + 0.25 * seas + rng.gauss(0, 0.05))), 4),
                "lst_c": round(REGION_BASE[region]["temp"] + 6.0 * seas + rng.gauss(0, 1.5), 2),
                "aerosol_index": round(max(0.01, 0.28 + (0.18 if region == "inland" else 0.05)
                                           + 0.1 * (idx / len(weeks)) + rng.gauss(0, 0.04)), 4),
                "chla_mg_m3": round(max(0.1, 1.1 - 0.4 * seas + rng.gauss(0, 0.15)), 3),
                "ice_cover_pct": round(min(100, max(0, 34 - 6 * seas - 0.9 * (idx / len(weeks) * 10)
                                                    + rng.gauss(0, 3))), 2),
            })
    df = pd.DataFrame(rows)
    log.info("Satellite imagery dataset: %d rows x %d cols", *df.shape)
    return df


def main() -> None:
    """Generate all test datasets and persist them into data/raw/."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    ws = generate_weather_stations()
    ws.to_csv(RAW_DATA_DIR / "weather_stations.csv", index=False)

    sn = generate_sensor_network()
    sn.to_csv(RAW_DATA_DIR / "sensor_network.csv", index=False)

    sat = generate_satellite_imagery()
    sat.to_csv(RAW_DATA_DIR / "satellite_imagery.csv", index=False)

    log.info("Test data written to %s", RAW_DATA_DIR)
    for f in ("weather_stations.csv", "sensor_network.csv", "satellite_imagery.csv"):
        p = RAW_DATA_DIR / f
        log.info("  %-24s %8.1f KB", f, p.stat().st_size / 1024)


if __name__ == "__main__":
    main()
