"""
EarthScape Climate Agency - Flask REST API
==========================================
Backend for the React dashboard. Blueprints:

  /api/auth      login / register / me / users        (roles: admin, analyst)
  /api/live      LIVE OpenWeather sync/status/forecast (primary data source)
  /api/data      datasets, readings, ingestion control
  /api/analytics MapReduce jobs, ML models, correlations
  /api/alerts    rules CRUD + alert history
  /api/stream    offline simulator (test fixture only)
  /api/feedback  support tickets & feedback
  /api/system    health / performance monitoring stats

Run:  python -m src.api.app            (then start the React frontend)
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

from src.alerts import AlertEngine, AlertRule
from src.auth import (
    authenticate,
    admin_required,
    create_user,
    current_user,
    issue_token,
    list_users,
    lockout_status,
    login_required,
    role_required,
    seed_default_users,
)
from src.config import (
    APP_HOST,
    APP_PORT,
    DEBUG,
    MODE,
    OPENWEATHER_API_KEY,
    OW_SYNC_INTERVAL_MIN,
    PROCESSED_DATA_DIR,
)
from src.db import get_db
from src.hadoop.storage import get_storage
from src.hadoop.mapreduce.job_runner import list_jobs, run_job
from src.ingestion.pipeline import list_datasets, run_full_ingestion
from src.live import openweather as ow
from src.ml.models import METRICS, ClimateModelRegistry
from src.streaming import (
    get_latest_readings,
    get_live_series,
    start_stream,
    stop_stream,
)
from src.utils.backup import create_backup, latest_backup, list_backups, verify_backup
from src.utils.logger import get_logger

log = get_logger("earthscape.api")

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"],
     supports_credentials=True)

# Performance monitoring: in-memory ring of recent data-processing runs
_job_history: list[dict] = []


@app.after_request
def security_headers(response):
    """
    Data-security hardening (non-functional requirement).

    Production deployments terminate TLS at Apache/nginx; these headers
    complement transport encryption by locking down browser behaviour.
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'self'; img-src 'self' data:;")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response

# ---------------------------------------------------------------------------
# Singletons shared across requests
# ---------------------------------------------------------------------------
registry = ClimateModelRegistry()

def _persist_alert(alert) -> None:
    """Dispatcher: log every alert AND store it in the database."""
    AlertEngine.log_dispatcher(alert)
    try:
        _db.insert("alerts", alert.to_dict())
    except Exception as exc:  # pragma: no cover - never break alerting
        log.error("Failed to persist alert %s: %s", alert.alert_id, exc)


alert_engine = AlertEngine(dispatcher=_persist_alert)
_db = get_db()
_start_time = time.time()


def _weather_df(limit: int | None = None) -> pd.DataFrame:
    """
    Load LIVE OpenWeather observations from HDFS-partitioned storage.

    This is the project's primary dataset: every sync appends one real
    reading per city under /climate/openweather_current. The synthetic test
    archives (weather_stations.csv & friends) are intentionally NOT served
    to the UI — they exist only for offline tests and the MapReduce CLI.
    """
    storage = get_storage()
    df = storage.read_dataset("/climate/openweather_current/**/*.csv")
    if df.empty:
        return df
    if "date" not in df.columns:
        # Defensive: rebuild the date column from the year=/month= folders.
        parts = storage.glob("/climate/openweather_current/**/*.csv")
        frames = []
        for part in parts:
            chunk = pd.read_csv(storage.root / part)
            year = part.split("year=")[1].split("/")[0]
            month = part.split("month=")[1].split("/")[0]
            chunk["date"] = f"{year}-{month}-01"
            frames.append(chunk)
        df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    return df.tail(limit) if limit else df


# ---------------------------------------------------------------------------
# Health / system
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "EarthScape Climate Agency API",
        "storage_backend": get_storage().name,
        "database_backend": get_db().name,
        "mode": MODE,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })


@app.get("/api/system/stats")
@login_required
def system_stats():
    """Performance monitoring data for the dashboard."""
    import os
    from src.config import LOGS_DIR

    log_files = []
    if LOGS_DIR.exists():
        for f in LOGS_DIR.glob("*.log*"):
            log_files.append({"name": f.name,
                              "size_kb": round(f.stat().st_size / 1024, 1)})

    storage = get_storage()
    return jsonify({
        "uptime_seconds": round(time.time() - _start_time, 1),
        "storage": {
            "backend": storage.name,
            "total_bytes": storage.du("/climate") if storage.exists("/climate") else 0,
        },
        "database": {"backend": get_db().name},
        "alerts": alert_engine.stats(),
        "models": registry.status(),
        "log_files": log_files,
        "cpu_count": os.cpu_count(),
        "stream_active": _stream_state["active"],
        # Performance monitoring: recent data-processing times
        "processing": {
            "recent_jobs": _job_history[-8:],
            "job_count": len(_job_history),
            "avg_seconds": (round(sum(j["duration_seconds"]
                                      for j in _job_history) / len(_job_history), 3)
                            if _job_history else 0),
        },
        "backups": {
            "count": len(list_backups()),
            "latest": latest_backup(),
        },
    })


@app.post("/api/system/backup")
@admin_required
def api_create_backup():
    """Admin-only: create an on-demand automated data backup (zip archive)."""
    body = request.get_json(silent=True) or {}
    try:
        result = create_backup(label=body.get("label", "manual"))
    except OSError as exc:
        log.error("Backup failed: %s", exc)
        return jsonify({"error": f"Backup failed: {exc}"}), 500
    log.info("Backup created via API by %s: %s",
             current_user()["username"], result["file"])
    return jsonify({"message": f"Backup created ({result['files']} files).",
                    "backup": result}), 201


@app.get("/api/system/backups")
@admin_required
def api_list_backups():
    items = list_backups()
    return jsonify({"backups": items, "count": len(items)})


@app.get("/api/system/backups/<name>/verify")
@admin_required
def api_verify_backup(name: str):
    """Integrity-check an archive (all members readable, nothing corrupt)."""
    try:
        return jsonify(verify_backup(name))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except IOError as exc:
        return jsonify({"error": str(exc), "valid": False}), 422


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@app.post("/api/auth/login")
def api_login():
    body = request.get_json(silent=True) or {}
    username = body.get("username", "")
    user = authenticate(username, body.get("password", ""))
    if not user:
        # Surface lockout state so the UI can warn the user kindly
        status = lockout_status(username)
        if status["locked"]:
            mins = max(1, status["locked_for_seconds"] // 60)
            return jsonify({
                "error": (f"Too many failed attempts — this account is locked "
                          f"for {mins} minute(s). Try again later."),
                "lockout": status,
            }), 423
        return jsonify({
            "error": "Invalid username or password.",
            "lockout": status,
        }), 401
    return jsonify({
        "token": issue_token(user),
        "user": {"username": user["username"], "email": user["email"],
                 "role": user["role"]},
    })


@app.post("/api/auth/register")
def api_register():
    body = request.get_json(silent=True) or {}
    try:
        # Only admins may create admin accounts
        role = body.get("role", "analyst")
        caller = current_user()
        if role == "admin" and (not caller or caller.get("role") != "admin"):
            role = "analyst"
        user = create_user(body.get("username", ""), body.get("email", ""),
                           body.get("password", ""), role)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"message": "User registered.", "user": user}), 201


@app.get("/api/auth/me")
@login_required
def api_me():
    return jsonify({"user": current_user()})


@app.get("/api/auth/users")
@admin_required
def api_users():
    return jsonify({"users": list_users()})


@app.patch("/api/auth/users/<username>/role")
@admin_required
def api_change_role(username: str):
    """Admin-only: promote/demote a user between analyst and admin."""
    body = request.get_json(silent=True) or {}
    role = body.get("role", "")
    if role not in ("admin", "analyst"):
        return jsonify({"error": "Role must be 'admin' or 'analyst'."}), 400
    from src.auth import change_role
    if not change_role(username, role):
        return jsonify({"error": f"User '{username}' not found."}), 404
    log.info("Role change: %s -> %s (by %s)", username, role,
             current_user()["username"])
    return jsonify({"message": f"{username} is now {role}."})


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------
@app.get("/api/data/datasets")
@login_required
def api_datasets():
    """Live OpenWeather datasets only — synthetic test archives stay hidden."""
    storage = get_storage()
    catalog = {name: meta for name, meta in list_datasets().items()
               if str(meta.get("source", "")).startswith("openweather")}
    summary = []
    for name, meta in catalog.items():
        size = storage.du(f"/climate/{name}") if storage.exists(f"/climate/{name}") else 0
        summary.append({**meta, "name": name, "size_bytes": size})
    return jsonify({"datasets": summary,
                    "storage_backend": storage.name})


@app.post("/api/data/ingest")
@role_required("admin", "analyst")
def api_ingest():
    """Trigger the full historical ingestion pipeline."""
    try:
        results = run_full_ingestion()
    except Exception as exc:
        log.error("Ingestion failed: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify({"message": "Ingestion complete.", "results": results})


@app.get("/api/data/readings")
@login_required
def api_readings():
    """Paginated readings (live observations, or the stored real forecast)."""
    station = request.args.get("station")
    start = request.args.get("start")
    end = request.args.get("end")
    page = max(1, int(request.args.get("page", 1)))
    size = min(500, int(request.args.get("size", 100)))
    dataset = request.args.get("dataset", "openweather_current")
    if dataset not in (ow.CURRENT_DATASET, ow.FORECAST_DATASET):
        dataset = ow.CURRENT_DATASET

    try:
        if dataset == ow.CURRENT_DATASET:
            df = _weather_df()          # tests mock this seam
        else:
            df = get_storage().read_dataset(f"/climate/{dataset}/**/*.csv")
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                df = df.dropna(subset=["date"]).sort_values("date")
    except Exception as exc:
        return jsonify({"error": f"Storage unavailable: {exc}"}), 500
    if df.empty:
        return jsonify({"readings": [], "total": 0, "page": page,
                        "hint": "No live data yet — click “Sync live weather” "
                                "on the dashboard to pull OpenWeather data."})

    if station:
        df = df[df["station_id"] == station]
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]

    total = len(df)
    slice_ = df.iloc[(page - 1) * size: page * size].copy()
    # keep the FULL timestamp: live rows arrive ~every 10 minutes and the UI
    # shows "16 Oct - 18:42" - truncating to a date made rows look identical
    slice_["date"] = slice_["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    records = json_safe(slice_.to_dict(orient="records"))
    return jsonify({"readings": records, "total": total, "page": page,
                    "pages": (total + size - 1) // size, "size": size})


@app.get("/api/data/stations")
@login_required
def api_stations():
    df = _weather_df()
    if df.empty:
        return jsonify({"stations": []})
    stations = (df.groupby(["station_id", "city", "region"])
                  .size().reset_index(name="readings")
                  .to_dict(orient="records"))
    return jsonify({"stations": json_safe(stations)})


def json_safe(records: list[dict]) -> list[dict]:
    """Convert NaN/NaT to None so the JSON is strictly valid."""
    out = []
    for rec in records:
        clean = {}
        for key, val in rec.items():
            if val is None or (isinstance(val, float) and pd.isna(val)):
                clean[key] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                clean[key] = str(val)
            elif hasattr(val, "item"):          # numpy scalars
                clean[key] = val.item()
            else:
                clean[key] = val
        out.append(clean)
    return out


# ---------------------------------------------------------------------------
# Analytics endpoints (MapReduce + ML)
# ---------------------------------------------------------------------------
@app.get("/api/analytics/jobs")
@login_required
def api_jobs():
    return jsonify({"jobs": list_jobs()})


@app.post("/api/analytics/jobs/run")
@role_required("admin", "analyst")
def api_run_job():
    body = request.get_json(silent=True) or {}
    job_name = body.get("job")
    # Default input: the LIVE OpenWeather export when it exists, otherwise
    # the bundled test archive so offline jobs still work.
    default_input = "data/raw/weather_stations.csv"
    live_csv = PROCESSED_DATA_DIR / f"{ow.CURRENT_DATASET}.csv"
    if live_csv.exists():
        default_input = f"data/processed/{ow.CURRENT_DATASET}.csv"
    input_csv = body.get("input") or default_input
    zscore = float(body.get("zscore", 3.0))

    started = time.perf_counter()
    try:
        result = run_job(job_name, input_csv, zscore=zscore)
    except (KeyError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        log.error("MapReduce job failed: %s", exc)
        return jsonify({"error": f"Job failed: {exc}"}), 500
    duration = round(time.perf_counter() - started, 3)

    # Record for performance monitoring (data-processing times)
    _job_history.append({
        "name": f"mapreduce:{job_name}",
        "rows": int(len(result)),
        "duration_seconds": duration,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    del _job_history[:-50]          # keep the last 50 runs only

    preview = json_safe(result.head(50).to_dict(orient="records"))
    message = (f"Job '{job_name}' completed on {len(result)} rows "
               f"in {duration}s.")
    if job_name == "anomaly_detection" and len(result) == 0:
        message = (f"No reading crossed the {zscore}σ threshold — that's a "
                   "healthy result. With young live history each station has "
                   "few values, so z-scores stay small; try a lower threshold "
                   "(e.g. zscore 1.5) or let auto-sync grow the history.")
    return jsonify({"job": job_name, "rows": len(result), "zscore": zscore,
                    "duration_seconds": duration,
                    "preview": preview,
                    "message": message})


@app.post("/api/analytics/ml/train")
@role_required("admin", "analyst")
def api_train_models():
    """Train anomaly + trend models on the LIVE OpenWeather history."""
    started = time.perf_counter()
    try:
        df = _weather_df()
        if df.empty:
            return jsonify({"error": "No live data yet — sync OpenWeather "
                                     "readings first."}), 400
        if len(df) < 10:
            return jsonify({"error": (
                f"Only {len(df)} live readings collected so far — at least 10 "
                "are needed. Auto-sync gathers 12 fresh readings every "
                "10 minutes; run “Sync now” to build history faster.")}), 400

        anomaly = registry.train_anomaly(df, contamination=0.02)
        trained = ["anomaly"]
        skipped = []
        for metric in ("temperature_c", "co2_ppm", "rainfall_mm"):
            # Train only on metrics that actually carry live values AND have
            # enough daily history (OpenWeather has no outdoor CO2 sensor,
            # and a trend needs >= 30 daily points to be meaningful).
            reason = None
            if metric not in df.columns or df[metric].notna().sum() < 10:
                reason = "no live values yet"
            else:
                try:
                    registry.train_trend(df, metric)
                    trained.append(f"trend_{metric}")
                    continue
                except Exception as exc:
                    reason = str(exc)
            skipped.append({"metric": metric, "reason": reason})
            # Never let a model trained on older/test data keep serving
            # "live" projections — drop the stale artifact instead.
            if registry.drop_trend(metric):
                log.info("Dropped stale trend model '%s' (%s)", metric, reason)

        anomalies = anomaly.predict(df)
        flagged = anomalies[anomalies["is_anomaly"]]
        sample = json_safe(flagged.tail(50).drop(
            columns=["is_anomaly"], errors="ignore").to_dict(orient="records"))
        duration = round(time.perf_counter() - started, 3)

        # Freshness metadata — "models must be regularly updated" (NFR)
        freshness = {
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "rows_used": int(len(df)),
            "duration_seconds": duration,
            "metrics_without_enough_data": skipped,
        }
        registry.note_freshness(freshness)

        _job_history.append({
            "name": "ml:train",
            "rows": int(len(df)),
            "duration_seconds": duration,
            "finished_at": freshness["trained_at"],
        })
        del _job_history[:-50]

        message = f"Trained: {', '.join(trained)}"
        if skipped:
            message += (f" · {len(skipped)} trend metric(s) skipped — they "
                        "need >= 30 days of live history; the real 5-day "
                        "OpenWeather forecast covers near-term needs meanwhile")
        return jsonify({
            "message": message,
            "metrics_without_enough_data": skipped,
            "anomalies_detected": int(len(flagged)),
            "anomaly_rate": round(len(flagged) / max(1, len(df)), 4),
            "recent_anomalies": sample,
            "trends": registry.status()["trend_models"],
            "freshness": freshness,
        })
    except Exception as exc:
        log.error("Model training failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.get("/api/analytics/ml/status")
@login_required
def api_ml_status():
    return jsonify(registry.status())


@app.get("/api/analytics/ml/forecast")
@login_required
def api_forecast():
    metric = request.args.get("metric", "temperature_c")
    days = min(730, int(request.args.get("days", 90)))
    model = registry.load_trend(metric)
    if model is None or model.model is None:
        return jsonify({"error": f"No trained trend model for '{metric}'. "
                                 "Train models first."}), 404
    forecast = model.forecast(days)
    return jsonify({"metric": metric, "days": days,
                    "summary": model.summary(),
                    "forecast": json_safe(forecast.to_dict(orient="records"))})


@app.get("/api/analytics/correlation")
@login_required
def api_correlation():
    try:
        df = _weather_df()
        if df.empty:
            return jsonify({"error": "No live data yet — sync first."}), 400
        # Live data has no outdoor CO2 / sea-level sensor: only correlate
        # metrics that actually carry values (graceful missing-data handling).
        cols = [m for m in METRICS
                if m in df.columns and df[m].notna().sum() >= 3]
        if len(cols) < 2:
            return jsonify({"error": "Need at least two live metrics — more "
                                     "readings arrive with every sync."}), 400
        result = ClimateModelRegistry.correlate(df[cols])
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/analytics/summary")
@login_required
def api_analytics_summary():
    """Aggregated KPIs powering the dashboard cards."""
    df = _weather_df()
    if df.empty:
        return jsonify({"available": False})

    present = [m for m in METRICS if m in df.columns]
    numeric = df[present].apply(pd.to_numeric, errors="coerce")
    latest = df.sort_values("date").groupby("station_id").tail(1)

    # Include live-view extras when the columns exist.
    latest_cols = ["station_id", "city", "temperature_c", "co2_ppm",
                   "pm25", "date"]
    for extra in ("region", "humidity_pct", "wind_speed_kph", "aqi",
                  "weather_main"):
        if extra in latest.columns:
            latest_cols.append(extra)

    return jsonify({
        "available": True,
        "source": "openweather",
        "total_readings": int(len(df)),
        "stations": int(df["station_id"].nunique()),
        "date_range": {
            "start": str(df["date"].min().date()),
            "end": str(df["date"].max().date()),
        },
        "averages": json_safe([{
            m: round(float(numeric[m].mean()), 2)
            for m in numeric.columns
        }])[0],
        "latest_by_station": json_safe(
            latest[latest_cols].to_dict(orient="records")),
        "missing_values": int(numeric.isna().sum().sum()),
    })


@app.get("/api/analytics/timeseries")
@login_required
def api_timeseries():
    """
    Resampled trend of one metric, optionally per station.

    Frequency adapts to the data span so live data (minutes old) still renders
    a useful chart: 5-minute buckets <=6 hours, hourly <=2 days,
    daily <=120 days, monthly beyond that.
    """
    metric = request.args.get("metric", "temperature_c")
    station = request.args.get("station")
    limit = min(400, int(request.args.get("months", 60)))

    df = _weather_df()
    if df.empty or metric not in df.columns:
        return jsonify({"error": "No data or unknown metric."}), 400
    if station:
        df = df[df["station_id"] == station]
    df = df.copy()
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    if df[metric].notna().sum() == 0:
        return jsonify({"error": f"No values for '{metric}' yet."}), 400

    span = df["date"].max() - df["date"].min()
    if span <= pd.Timedelta(hours=6):
        # Brand-new live history: bucket per sync window so the chart has
        # several points within the first minutes, not one lonely dot.
        freq, label = ("5min", lambda i: i.strftime("%H:%M"))
    elif span <= pd.Timedelta(days=2):
        freq, label = "h", lambda i: i.strftime("%Y-%m-%d %H:00")
    elif span <= pd.Timedelta(days=120):
        freq, label = "D", lambda i: str(i.date())
    else:
        freq, label = "ME", lambda i: str(i.date())

    series = (df.set_index("date")[metric]
                  .resample(freq).mean().dropna().tail(limit))
    return jsonify({
        "metric": metric, "station": station or "all",
        "frequency": freq,
        "points": [{"date": label(i), "value": round(float(v), 2)}
                   for i, v in series.items()],
    })


# ---------------------------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------------------------
@app.get("/api/alerts/history")
@login_required
def api_alert_history():
    limit = min(500, int(request.args.get("limit", 100)))
    severity = request.args.get("severity", "info")
    stored = _db.find("alerts", limit=limit, sort="timestamp")
    live = alert_engine.recent(limit=limit, min_severity=severity)
    seen = {a["alert_id"] for a in live}
    merged = live + [a for a in stored if a.get("alert_id") not in seen]
    return jsonify({"alerts": merged[:limit], "stats": alert_engine.stats()})


@app.get("/api/alerts/rules")
@login_required
def api_alert_rules():
    return jsonify({"rules": alert_engine.list_rules()})


@app.post("/api/alerts/rules")
@admin_required
def api_add_rule():
    body = request.get_json(silent=True) or {}
    try:
        rule = AlertRule(
            name=body["name"], metric=body["metric"],
            comparator=body.get("comparator", "gt"),
            threshold=float(body["threshold"]),
            severity=body.get("severity", "warning"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid rule: {exc}"}), 400
    alert_engine.add_rule(rule)
    return jsonify({"message": "Rule saved.", "rules": alert_engine.list_rules()}), 201


@app.delete("/api/alerts/rules/<name>")
@admin_required
def api_delete_rule(name: str):
    if not alert_engine.remove_rule(name):
        return jsonify({"error": "Rule not found."}), 404
    return jsonify({"message": f"Rule '{name}' removed."})


@app.post("/api/alerts/rules/<name>/<action>")
@admin_required
def api_toggle_rule(name: str, action: str):
    ok = (alert_engine.enable_rule(name) if action == "enable"
          else alert_engine.disable_rule(name) if action == "disable"
          else False)
    if not ok:
        return jsonify({"error": "Rule not found."}), 404
    return jsonify({"message": f"Rule '{name}' {action}d."})


# ---------------------------------------------------------------------------
# LIVE OpenWeather endpoints (primary data source of the whole dashboard)
# ---------------------------------------------------------------------------
@app.get("/api/live/status")
@login_required
def api_live_status():
    """Health of the OpenWeather integration (used by Admin + UI chips)."""
    return jsonify(ow.status())


@app.get("/api/live/cities")
@login_required
def api_live_cities():
    return jsonify({"cities": ow.CITIES,
                    "units": ow.OPENWEATHER_UNITS})


@app.get("/api/live/latest")
@login_required
def api_live_latest():
    """Latest live reading per city (cache-first, storage-backed fallback)."""
    return jsonify(ow.latest())


@app.post("/api/live/sync")
@role_required("admin", "analyst")
def api_live_sync():
    """
    Pull live conditions + air quality for all 12 cities (and optionally the
    real 5-day forecast), store them, and evaluate alert rules per reading.
    """
    body = request.get_json(silent=True) or {}
    include_fc = body.get("forecast")
    try:
        result = ow.sync(
            include_forecast=None if include_fc is None else bool(include_fc),
            on_reading=alert_engine.evaluate_reading,
            force=bool(body.get("force")),
        )
    except ow.OpenWeatherError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:                    # pragma: no cover
        log.error("Live sync failed: %s", exc)
        return jsonify({"error": f"Live sync failed: {exc}"}), 500
    return jsonify(result)


@app.get("/api/live/forecast")
@login_required
def api_live_forecast():
    """Real 5-day / 3-hour OpenWeather forecast for one city (5-min cache)."""
    city_name = request.args.get("city") or ow.CITIES[0]["name"]
    city = next((c for c in ow.CITIES if c["name"].lower()
                 == city_name.lower()), None)
    if city is None:
        return jsonify({"error": f"Unknown city '{city_name}'.",
                        "cities": [c["name"] for c in ow.CITIES]}), 404
    try:
        points = ow.fetch_forecast(city)
    except ow.OpenWeatherError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({
        "city": city, "count": len(points),
        "points": json_safe(points),
        "note": "Live 5-day / 3-hour forecast from OpenWeatherMap free tier.",
    })


# ---------------------------------------------------------------------------
# Live stream endpoints (offline test simulator — superseded by /api/live)
# ---------------------------------------------------------------------------
_stream_state = {"active": False, "started_at": None}


@app.get("/api/stream/latest")
@login_required
def api_stream_latest():
    limit = min(500, int(request.args.get("limit", 100)))
    return jsonify({"readings": get_latest_readings(limit),
                    "active": _stream_state["active"],
                    "count": len(get_latest_readings(limit))})


@app.get("/api/stream/series")
@login_required
def api_stream_series():
    station = request.args.get("station")
    metric = request.args.get("metric", "temperature_c")
    limit = min(500, int(request.args.get("limit", 200)))
    return jsonify(get_live_series(station, metric, limit))


@app.post("/api/stream/start")
@admin_required
def api_stream_start():
    # Every live reading is evaluated against the alert rules before it
    # reaches the dashboard (functional requirement: real-time alerting).
    start_stream(on_reading=alert_engine.evaluate_reading)
    _stream_state.update(active=True,
                         started_at=datetime.now().isoformat(timespec="seconds"))
    return jsonify({"message": "Live stream started."})


@app.post("/api/stream/stop")
@admin_required
def api_stream_stop():
    stop_stream()
    _stream_state["active"] = False
    return jsonify({"message": "Live stream stopped."})


# ---------------------------------------------------------------------------
# Feedback & support endpoints
# ---------------------------------------------------------------------------
@app.post("/api/feedback")
@login_required
def api_feedback():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400
    ticket = {
        "user": current_user()["username"],
        "category": body.get("category", "feedback"),
        "subject": (body.get("subject") or "No subject").strip()[:200],
        "message": message[:2000],
        "status": "open",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _db.insert("feedback", ticket)
    return jsonify({"message": "Ticket submitted. Our support team will "
                               "respond by email.", "ticket": ticket}), 201


@app.get("/api/feedback")
@login_required
def api_feedback_list():
    user = current_user()
    if user["role"] == "admin":
        tickets = _db.find("feedback", limit=200, sort="created_at")
    else:
        tickets = _db.find("feedback", {"user": user["username"]},
                           limit=100, sort="created_at")
    return jsonify({"tickets": tickets})


@app.patch("/api/feedback/<ticket_id>")
@admin_required
def api_feedback_update(ticket_id: str):
    body = request.get_json(silent=True) or {}
    status = body.get("status", "open")
    if status not in ("open", "in_progress", "resolved"):
        return jsonify({"error": "Invalid status."}), 400
    changed = _db.update("feedback", {"_id": ticket_id},
                         {"status": status,
                          "updated_at": datetime.now().isoformat(timespec="seconds")})
    if not changed:
        return jsonify({"error": "Ticket not found."}), 404
    return jsonify({"message": f"Ticket marked {status}."})


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def _initial_live_sync() -> None:
    """First pull shortly after boot so the dashboard opens with live data."""
    time.sleep(4)
    try:
        ow.sync(on_reading=alert_engine.evaluate_reading, force=True)
    except Exception as exc:
        log.warning("Initial OpenWeather sync failed: %s", exc)


def _auto_sync_loop() -> None:
    """Background thread: refresh live data every OW_SYNC_INTERVAL_MIN."""
    interval = OW_SYNC_INTERVAL_MIN * 60
    while True:
        time.sleep(interval)
        try:
            result = ow.sync(on_reading=alert_engine.evaluate_reading)
            log.info("Auto-sync: %s", result.get("message", result))
        except Exception as exc:
            log.warning("Auto-sync failed: %s", exc)


def create_app() -> Flask:
    """App factory used by tests and the dev server."""
    seed_default_users()
    # Pre-warm the trend models if they exist (no-op otherwise)
    return app


create_app()

if __name__ == "__main__":
    log.info("Starting EarthScape API on http://%s:%s", APP_HOST, APP_PORT)
    if OPENWEATHER_API_KEY and OW_SYNC_INTERVAL_MIN > 0:
        log.info("OpenWeather live sync: every %d min (+ immediate first sync)",
                 OW_SYNC_INTERVAL_MIN)
        threading.Thread(target=_auto_sync_loop, daemon=True).start()
        threading.Thread(target=_initial_live_sync, daemon=True).start()
    app.run(host=APP_HOST, port=APP_PORT, debug=DEBUG, threaded=True)
