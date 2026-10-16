# 👨‍💻 Developer Guide — EarthScape Climate Agency

## Architecture overview

```
┌────────────┐   HTTP/JSON    ┌──────────────────────┐
│  React SPA │ ─────────────► │  Flask REST API      │
│  (Vite)    │  /api/*        │  src/api/app.py      │
└────────────┘                └──────┬───────────────┘
                                     │ calls
        ┌───────────────┬────────────┼───────────────┬────────────────┐
        ▼               ▼            ▼               ▼                ▼
  src/auth/       src/hadoop/   src/ml/models   src/alerts/     src/streaming/
  tokens+roles    storage.py    anomaly/trend   rule engine     live OpenWeather sync
                  mapreduce/    correlation     dispatchers     (background
                  job_runner                                  thread)
        │               │            │               │                │
        ▼               ▼            ▼               ▼                ▼
   src/db/         data/hdfs_sim  data/models    data/db/alerts  data/hdfs_sim
  (Mongo|JSON)     (or real HDFS)  (*.joblib)      (JSON file)   /climate/live/
```

## Key design decisions

1. **Storage abstraction** (`src/hadoop/storage.py`) — `get_storage()` returns
   `LocalHDFS` (default) or `RemoteHDFS` (real `hdfs` CLI). Both implement the
   same interface: `mkdirs/put/put_dataframe/get/read_dataframe/ls/glob/
   read_dataset/rm/du/exists`. Partitions follow Hive-style
   `year=YYYY/month=MM/day=DD` folder naming; returned paths are always POSIX
   (`/`), even on Windows.
2. **Database abstraction** (`src/db/`) — `MongoBackend` and `JsonBackend`
   share one contract (`insert/find/find_one/update/delete/count`). Selection
   happens once at startup via `get_db()`; JSON files live in `data/db/`.
3. **Alert dispatch** — `AlertEngine(dispatcher=fn)`; the API passes
   `_persist_alert` which logs + writes to the `alerts` collection. Email and
   webhook dispatchers ship as static factories (`email_dispatcher`,
   `webhook_dispatcher`).
4. **Streaming hook** — `start_stream(on_reading=callable)` lets the API
   evaluate every live reading against the alert rules without coupling the
   modules.

## Module reference

| Module | Exports | Notes |
|---|---|---|
| `src.config` | paths, thresholds, `MODE`, env knobs | All tunables in one file |
| `src.utils.logger` | `get_logger(name)` | console + rotating file in `logs/` |
| `src.hadoop.storage` | `get_storage`, `partition_and_store`, `LocalHDFS`, `RemoteHDFS` | |
| `src.hadoop.mapreduce.job_runner` | `run_job`, `list_jobs` | local pipe mode = map→sort→reduce |
| `src.ingestion.generate_test_data` | `main()` | CLI: `python -m src.ingestion.generate_test_data` |
| `src.ingestion.pipeline` | `run_full_ingestion`, `ingest_reading`, catalog fns | cleaning + validation + registration |
| `src.streaming` | `start_stream`, `stop_stream`, `stream_once`, `get_latest_readings`, `get_live_series` | ring buffer (500) + thread |
| `src.ml.models` | `AnomalyDetectionModel`, `TrendPredictionModel`, `CorrelationAnalyzer`, `ClimateModelRegistry` | joblib persistence in `data/models/` |
| `src.alerts` | `AlertEngine`, `AlertRule`, `Alert` | 14 default rules from config |
| `src.auth` | `authenticate`, `issue_token`, `login_required`, `role_required`, `admin_required` | itsdangerous signed tokens |
| `src.db` | `get_db`, `JsonBackend`, `MongoBackend` | |

## REST API surface

| Method & path | Guard | Purpose |
|---|---|---|
| `GET /api/health` | — | liveness + backend info |
| `POST /api/auth/login` | — | returns token + user |
| `POST /api/auth/register` | — (role clamped to analyst) | signup |
| `GET /api/auth/me` | login | current user |
| `GET /api/auth/users` | admin | list users |
| `PATCH /api/auth/users/<u>/role` | admin | change role |
| `GET /api/live/status` | login | OpenWeather integration health |
| `GET /api/live/cities` | login | the 12 tracked cities (code/name/lat/lon/region) |
| `GET /api/live/latest` | login | latest live reading per city (cache → storage) |
| `POST /api/live/sync` | admin/analyst | pull live weather now `{forecast?, force?}` |
| `GET /api/live/forecast` | login | real 5-day / 3-hour forecast `?city=` |
| `GET /api/data/datasets` | login | live catalog + sizes (synthetic archives hidden) |
| `POST /api/data/ingest` | admin/analyst | run full ingestion (test archives) |
| `GET /api/data/readings` | login | paginated, filter by station/start/end/dataset |
| `GET /api/data/stations` | login | station list |
| `GET /api/analytics/jobs` | login | job catalogue |
| `POST /api/analytics/jobs/run` | admin/analyst | run MapReduce job `{job, input, zscore}` |
| `POST /api/analytics/ml/train` | admin/analyst | train anomaly + trend models |
| `GET /api/analytics/ml/status` | login | model status |
| `GET /api/analytics/ml/forecast` | login | `?metric=&days=` |
| `GET /api/analytics/correlation` | login | matrix + top pairs |
| `GET /api/analytics/summary` | login | dashboard KPIs |
| `GET /api/analytics/timeseries` | login | monthly resampled metric |
| `GET /api/alerts/history` | login | merged live + stored alerts |
| `GET/POST /api/alerts/rules` | login / admin | list / create rule |
| `DELETE /api/alerts/rules/<n>` | admin | remove rule |
| `POST /api/alerts/rules/<n>/<enable\|disable>` | admin | toggle rule |
| `GET /api/stream/latest` | login | newest readings (offline simulator fixture) |
| `GET /api/stream/series` | login | chart series (offline fixture) |
| `POST /api/stream/start\|stop` | admin | offline simulator control (test fixture) |
| `GET/POST /api/feedback` | login | list (own/all) / create ticket |
| `PATCH /api/feedback/<id>` | admin | update status |
| `GET /api/system/stats` | login | uptime, storage, alerts, models, logs |

## Adding a new MapReduce job

1. Create `src/hadoop/mapreduce/my_mapper.py` and `my_reducer.py`
   (stdin→stdout, `\t`-separated intermediate keys — Hadoop Streaming
   compatible).
2. Register in `JOBS` inside `job_runner.py`:

```python
"my_job": {
    "mapper": MR_DIR / "my_mapper.py",
    "reducer": MR_DIR / "my_reducer.py",
    "output": PROCESSED_DATA_DIR / "my_job.csv",
    "description": "…",
},
```

3. It appears automatically in `GET /api/analytics/jobs` and the UI.

## Adding a new alert rule

```python
from src.alerts import AlertRule
engine.add_rule(AlertRule("ozone_watch", "o3_ppb", "gt", 120.0, "critical"))
```

Or at runtime through `POST /api/alerts/rules` (admin). Rules are evaluated
on every live reading; each breach produces an `Alert` that is logged and
persisted.

## Adding a new ML model

Subclass the pattern used in `src/ml/models.py` (dataclass with `train`,
`predict`/`forecast`, `save`/`load`) and register it on
`ClimateModelRegistry`. Persist with `joblib` into `data/models/`, then add
an endpoint in `src/api/app.py` guarded by `@login_required`.

## Testing

```powershell
python -m pytest tests/ -q                     # all
python -m pytest tests/test_ml.py -q           # one module
python -m pytest tests/test_api.py -v          # API integration
```

Conventions:

- Tests never touch real `data/` — fixtures monkeypatch storage/db/registry
  into `tmp_path`.
- Stream tests use `stream_once()` (synchronous batch) instead of threads.
- API tests use Flask's in-process `test_client()` — no server needed.

## Configuration cheat-sheet (env vars)

| Variable | Default | Effect |
|---|---|---|
| `EARTHSCAPE_MODE` | `local` | `hadoop` → real HDFS + Streaming |
| `EARTHSCAPE_MONGO_URI` | *(empty)* | enable MongoDB backend |
| `EARTHSCAPE_SECRET_KEY` | dev key | token signing secret (**change in prod**) |
| `EARTHSCAPE_HOST` / `EARTHSCAPE_PORT` | 127.0.0.1 / 5000 | API bind |
| `EARTHSCAPE_DEBUG` | `1` | Flask debug/reloader |
| `EARTHSCAPE_STREAMING_JAR` | /opt/hadoop/… | Hadoop Streaming jar path |
| `EARTHSCAPE_ANOMALY_ZSCORE` | `3.0` | reducer z-score threshold |

## Logging

All modules use `get_logger(__name__)` → console + `logs/earthscape.log`
(1 MB × 3 rotations). Keep log lines in the `LEVEL | logger | message` format.

## Code style

- Python: type hints on public functions, docstrings on modules/classes,
  `snake_case`, 100-col lines.
- React: function components + hooks; API calls through `src/api/client.js`
  only (single place for auth header + 401 handling).
