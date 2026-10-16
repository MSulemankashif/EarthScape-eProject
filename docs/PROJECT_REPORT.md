# 📑 Project Report — EarthScape Climate Agency
### Big Data eProject — Problem Definition, Design & Documentation

---

## 1. Problem Definition

Climate change is a global challenge driven by greenhouse-gas emissions,
deforestation and land-use changes, producing unprecedented shifts in climate
patterns and more frequent severe weather events. The **EarthScape Climate
Agency** collects vast climate data from satellites, weather stations and
environmental sensors. The agency needs a robust solution to **process,
analyze and visualize** this data for informed, proactive decision-making.

### Objectives

1. Ingest diverse climate datasets (historical + real-time).
2. Store them scalably on HDFS with partitioning for fast retrieval.
3. Process them in parallel with Hadoop MapReduce.
4. Detect climate patterns, anomalies and correlations with machine learning.
5. Deliver interactive dashboards and real-time alerts to stakeholders.
6. Secure the system with role-based authentication.

---

## 2. Design Specifications

### 2.1 Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + Recharts, Axios |
| Backend | Python 3 / Flask REST API |
| Storage | HDFS (real) or LocalHDFS simulation — Hive-style partitions |
| Processing | Hadoop Streaming-compatible MapReduce (Python mapper/reducer) |
| ML | scikit-learn (IsolationForest, LinearRegression), NumPy, pandas |
| Database | MongoDB (optional) / JSON document store fallback |
| Auth | Werkzeug PBKDF2-SHA256 + itsdangerous signed tokens |
| Streaming | Background thread simulator + ring buffer (Kafka/MQTT-ready hook) |

### 2.2 Data model

**weather_stations.csv** (13,140 rows — 12 stations × 3 years daily)
`station_id, city, latitude, longitude, region, date, temperature_c,
humidity_pct, rainfall_mm, co2_ppm, pm25, wind_speed_kph, sea_level_mm`

**sensor_network.csv** (20,000 rows) — air quality / soil moisture / water pH
/ noise sensors with battery status.

**satellite_imagery.csv** (468 rows) — weekly NDVI, land-surface temperature,
aerosol index, chlorophyll-a, ice cover per region.

HDFS layout: `/climate/<dataset>/year=YYYY/month=MM/part-00000.csv`
(live readings also carry `day=DD`).

### 2.3 Roles & access control

| Capability | Analyst | Admin |
|---|---|---|
| View dashboards, data, forecasts, alerts | ✅ | ✅ |
| Run ingestion, MapReduce jobs, train models | ✅ | ✅ |
| Submit feedback tickets | ✅ | ✅ |
| Manage users & roles | ❌ | ✅ |
| Add/disable/delete alert rules | ❌ | ✅ |
| Start/stop live stream | ❌ | ✅ |
| Update ticket status | ❌ | ✅ |

---

## 3. Diagrams

### 3.1 System architecture (Context + level-1 flow)

```
                                ┌─────────────────────────────┐
   Weather Stations ──CSV──►    │                             │
   Sensor Network  ──CSV──►     │   INGESTION PIPELINE        │
   Satellites      ──CSV──►     │   validate → clean →        │
   Live Simulator ──thread──►   │   range-check → partition   │
                                └──────────────┬──────────────┘
                                               │ write
                                               ▼
                                ┌─────────────────────────────┐
                                │  HDFS STORAGE (partitioned) │
                                │  /climate/weather|sensors|  │
                                │  satellite|live/…           │
                                └───────┬─────────────┬───────┘
                       read             │             │ read
              ┌─────────────────────────┘             └──────────────────┐
              ▼                                                          ▼
┌──────────────────────────┐                            ┌──────────────────────────┐
│  MAPREDUCE PROCESSING    │                            │  ML ANALYTICS            │
│  • monthly_aggregation   │                            │  • IsolationForest       │
│  • anomaly_detection (σ) │                            │  • Trend forecasting     │
└────────────┬─────────────┘                            │  • Pearson correlation   │
             │ results                                  └────────────┬─────────────┘
             ▼                                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                        FLASK REST API  (/api/*)                                │
│  auth · data · analytics · alerts · stream · feedback · system                 │
└───────────────┬────────────────────────────────────────┬───────────────────────┘
                │ JSON (JWT)                             │ evaluates
                ▼                                        ▼
┌──────────────────────────────┐          ┌──────────────────────────────┐
│  REACT DASHBOARD             │          │  ALERT ENGINE                │
│  Dashboard · Live · Data ·   │          │  14 threshold rules +        │
│  Analytics · Forecasts ·     │◄─alerts──│  custom rules → log + DB +   │
│  Alerts · Feedback · Admin   │          │  (email/webhook ready)       │
└──────────────────────────────┘          └──────────────────────────────┘
```

### 3.2 Data Flow Diagram (DFD — Level 1)

```
 ┌────────┐ raw CSVs   ┌──────────────────┐ cleaned    ┌───────────────┐
 │Sources │───────────►│ 1.0 Ingestion    │───────────►│ D1 HDFS       │
 │(sats,  │            │ validate/clean/  │ partitions │  /climate/…   │
 │stations│            │ partition        │            └───────┬───────┘
 │sensors)│            └──────────────────┘                    │
 └────────┘                          ▲                ┌────────┴────────┐
      ▲ live readings                │ catalog        │                 │
      │                    ┌─────────┴────────┐       ▼                 ▼
 ┌────┴───────────┐        │ D2 Dataset       │ ┌───────────┐   ┌───────────────┐
 │ 2.0 Stream     │───────►│ Catalog (JSON)   │ │ 3.0       │   │ 4.0           │
 │ Simulator      │        └──────────────────┘ │ MapReduce │   │ ML Analytics  │
 └────┬───────────┘                              │ jobs      │   │ anomaly/trend │
      │ readings                                └─────┬─────┘   │ correlation   │
      │                                               │ stats   └──────┬────────┘
      ▼                                               ▼                ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ 5.0 FLASK API — serves JSON to the dashboard, enforces auth & roles       │
 └───────────┬───────────────────────────────────────────────┬───────────────┘
             │ readings/metrics                              │ alert events
             ▼                                               ▼
 ┌───────────────────────────┐                  ┌───────────────────────────┐
 │ 6.0 React Dashboard       │                  │ 7.0 Alert Engine          │
 │ (visualization + control) │◄──── alerts ─────│ rules → log/DB/(email)    │
 └───────────────────────────┘                  └───────────────────────────┘
             │ user actions (tickets)
             ▼
 ┌───────────────────────────┐
 │ D3 Users DB (Mongo/JSON)  │◄── 8.0 Auth (login, roles, tokens)
 │ D4 Feedback tickets       │
 └───────────────────────────┘
```

### 3.3 Ingestion flowchart

```
            [Start]
               │
               ▼
      ┌────────────────┐   no   ┌────────────────────┐
      │ Raw CSV exists?├────────►│ Skip with warning  │
      └───────┬────────┘        └─────────┬──────────┘
              │ yes                        │
              ▼                            │
      ┌────────────────┐                   │
      │ Read CSV       │                   │
      └───────┬────────┘                   │
              ▼                            │
      ┌────────────────┐                   │
      │ Coerce numeric │  garbage ──► NaN  │
      │ (bad → NaN)    │                   │
      └───────┬────────┘                   │
              ▼                            │
      ┌────────────────┐                   │
      │ Parse dates    │  invalid ─► DROP  │
      │ drop bad rows  │                   │
      └───────┬────────┘                   │
              ▼                            │
      ┌────────────────┐                   │
      │ Range check    │  impossible ─►NaN │  (e.g. 999°C, 150% humidity)
      └───────┬────────┘                   │
              ▼                            │
      ┌────────────────┐                   │
      │ Partition by   │                   │
      │ year=/month=   │                   │
      └───────┬────────┘                   │
              ▼                            │
      ┌────────────────┐                   │
      │ PUT to HDFS    │                   │
      │ + register in  │                   │
      │ catalog        │                   │
      └───────┬────────┘                   │
              ▼                            ▼
           [End] ◄─────────────────────────┘
```

### 3.4 MapReduce flow (monthly aggregation)

```
  input CSV ──► [ MAPPER: emits  key=STN|YYYY-MM  value=metric\tvalue ]
                              │  (missing values skipped)
                              ▼
                    [ SHUFFLE & SORT by key ]
                              │
                              ▼
                 [ REDUCER: per key buffers values,
                   emits count, mean, min, max, stddev, sum ]
                              │
                              ▼
                data/processed/monthly_aggregation.csv
```

### 3.5 Alert evaluation flowchart

```
  live reading ──► for each enabled rule ──► condition met? ──no──► next rule
                        │                                              │
                       yes                                            done
                        ▼
              create Alert (id, severity, message)
                        │
                        ▼
              dispatch(): log ──► persist to DB ──► (email/webhook optional)
                        │
                        ▼
              dashboard polls /api/alerts/history
```

---

## 4. Functional requirement coverage

| # | Requirement | Where implemented | Verified by |
|---|---|---|---|
| 1 | Auth & role-based access | `src/auth/`, guards on every endpoint | `test_auth_db.py`, `test_api.py` |
| 2 | Data ingestion (3 sources, historical + real-time) | `src/ingestion/pipeline.py`, `src/streaming/` | `test_ingestion.py`, `test_streaming.py` |
| 3 | HDFS storage + partitioning | `src/hadoop/storage.py` | `test_storage.py` |
| 4 | MapReduce parallel processing | `src/hadoop/mapreduce/*` | `test_mapreduce.py` |
| 5 | Missing/incomplete data handling | cleaning pipeline + mapper/reducer skips | `test_ingestion.py`, `test_mapreduce.py` |
| 6 | Real-time processing + batch integration | stream simulator → same pipeline + HDFS live partitions | `test_streaming.py` |
| 7 | ML: anomaly, trend, correlation | `src/ml/models.py` | `test_ml.py` |
| 8 | Interactive dashboards | React pages (`frontend/src/pages/`) | manual + build |
| 9 | Notifications & alerts (configurable) | `src/alerts/` + Alerts page | `test_alerts.py`, live smoke test |
| 10 | Feedback & support | `/api/feedback` + Support page | `test_api.py` |
| 11 | Performance monitoring | `/api/system/stats` + Admin page | `test_api.py` |
| 12 | Data security | hashing, tokens, role guards, CORS, path-traversal safety | `test_auth_db.py`, `test_storage.py` |

## 5. Non-functional coverage

- **Reliability** — atomic JSON writes (tmp+replace), rotating logs, alert
  dispatcher wrapped in try/except, missing-file tolerant ingestion.
- **Scalability** — partitioned storage enables date pruning; MapReduce jobs
  scale to a real cluster via `EARTHSCAPE_MODE=hadoop`; horizontal API
  scaling possible behind a load balancer (stateless tokens).
- **Performance monitoring** — uptime, storage bytes, log sizes, alert/model
  stats exposed at `/api/system/stats`.
- **Compliance** — CSV exports compatible with Impala/Tableau/Jupyter; strict
  JSON (NaN→null); documented assumptions.

## 6. Test data used

Generated by `src/ingestion/generate_test_data.py` (seeded, reproducible):

- 12 stations across coastal/inland/highland regions, 2022-01-01 → 2024-12-31
- Seasonal sinusoid + 0.012 °C/yr warming trend + Gaussian noise
- Monsoon-aware rainfall, winter PM2.5, rising CO₂
- **Injected quality issues:** ~1.5% missing values (287 in temperature etc.)
- **Injected extreme events:** Karachi heatwave 51 °C (2024-05-20), Lahore
  smog 480 µg/m³ (2024-06-15), Hyderabad cloudburst 320 mm (2024-09-01),
  Peshawar storm 118 kph (2023-04-12), Skardu cold wave −31 °C (2024-01-05)

The MapReduce anomaly job and Isolation Forest both flag these events.

## 7. How to run

See [INSTALLATION.md](INSTALLATION.md). Short version:

```powershell
pip install -r requirements.txt
python -m src.ingestion.generate_test_data
python -m src.ingestion.pipeline
python -m src.api.app              # backend :5000
cd frontend; npm install; npm run dev   # frontend :5173
```

Login: `admin/admin@123` or `analyst/analyst@123`.

## 8. Assumptions

1. Lab machines have no Hadoop cluster → LocalHDFS simulation (same
   interface; real HDFS activates via `EARTHSCAPE_MODE=hadoop`).
2. MongoDB optional → JSON document store fallback (same API).
3. Climate datasets are synthetic but statistically realistic (documented in
   §6).
4. Email/webhook alert channels implemented but not enabled (no SMTP in lab).
5. Tableau/Impala/RStudio consume exported CSVs offline (per software list).

---

*End of report. Source code: project root. Tests: `python -m pytest tests/ -q`
→ 93 passed.*
