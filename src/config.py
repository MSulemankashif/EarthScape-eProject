"""
EarthScape Climate Agency - Central Configuration
=================================================
All paths, thresholds and runtime flags used across the project live here.

The project can run in two storage modes:
  * "local"  -> a local folder simulates HDFS (no Hadoop needed, default)
  * "hadoop" -> real HDFS + Hadoop Streaming (set EARTHSCAPE_MODE=hadoop)

MongoDB is optional. If EARTHSCAPE_MONGO_URI is not reachable the app
transparently falls back to a JSON-file datastore so the project always runs.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
DOCS_DIR = BASE_DIR / "docs"

# Mini-HDFS root used when Hadoop is not installed
HDFS_SIM_ROOT = DATA_DIR / "hdfs_sim"
HDFS_REMOTE_BASE = "/user/earthscape"  # real HDFS base path

# ---------------------------------------------------------------------------
# Runtime mode
# ---------------------------------------------------------------------------
# EARTHSCAPE_MODE = "local" | "hadoop"
MODE = os.environ.get("EARTHSCAPE_MODE", "local").lower()

# Optional real MongoDB (e.g. mongodb://localhost:27017). Empty => JSON store.
MONGO_URI = os.environ.get("EARTHSCAPE_MONGO_URI", "")

# ---------------------------------------------------------------------------
# Data generation defaults (test data)
# ---------------------------------------------------------------------------
STATION_COUNT = 12
YEARS_OF_HISTORY = 3          # daily records per station
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Climate thresholds used by the alerting engine
# ---------------------------------------------------------------------------
ALERT_THRESHOLDS = {
    "temperature_c": {"high": 42.0, "low": -25.0},
    "humidity_pct": {"high": 98.0, "low": 5.0},
    "co2_ppm": {"high": 450.0, "low": 250.0},
    "pm25": {"high": 150.0, "low": 0.0},          # AQI hazardous
    "sea_level_mm": {"high": 120.0, "low": -80.0},
    "rainfall_mm": {"high": 250.0, "low": 0.0},   # cloudburst level
    "wind_speed_kph": {"high": 90.0, "low": 0.0},
}

# Z-score used by the anomaly detector
ANOMALY_ZSCORE = 3.0

# ---------------------------------------------------------------------------
# Web application
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("EARTHSCAPE_SECRET_KEY", "earthscape-dev-secret-change-in-prod")
SESSION_LIFETIME_HOURS = 8
APP_HOST = os.environ.get("EARTHSCAPE_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("EARTHSCAPE_PORT", "5000"))
DEBUG = os.environ.get("EARTHSCAPE_DEBUG", "1") == "1"

# ---------------------------------------------------------------------------
# Real-time stream simulator
# ---------------------------------------------------------------------------
STREAM_INTERVAL_SECONDS = 2     # delay between simulated live readings
STREAM_BATCH_PER_TICK = 3        # readings pushed per interval

# Ensure every directory exists at import time
for _d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, MODELS_DIR, LOGS_DIR, HDFS_SIM_ROOT):
    _d.mkdir(parents=True, exist_ok=True)
