# 🌍 EarthScape Climate Agency — Big Data Analytics Platform

**eProject submission** as per *Big Data - EarthScape Climate Agency* documentation.

A full-stack climate-data platform: **Python (Flask) REST API + Hadoop-style
MapReduce + Machine Learning + React dashboard**, with real-time streaming,
alerting and role-based access control.

---

## ✨ Features (mapped to the eProject requirements)

| Requirement | Implementation |
|---|---|
| User Authentication & Authorization | Signed expiring tokens, roles: `admin`, `analyst`, **brute-force lockout** (5 fails → 5 min) (`src/auth/`) |
| Data Ingestion | Weather stations, sensor network, satellite CSVs + live readings (`src/ingestion/`) |
| Data Storage (HDFS) | Partitioned `year=/month=/day=` layout; LocalHDFS simulation + real `hdfs` CLI backend (`src/hadoop/storage.py`) |
| Data Processing (MapReduce) | Hadoop Streaming-compatible mapper/reducer pairs: monthly aggregation + z-score anomaly detection, **every run timed** (`src/hadoop/mapreduce/`) |
| Real-time Processing | Background stream simulator feeding the pipeline + alert engine (`src/streaming/`) |
| Machine Learning | Isolation Forest anomalies, linear+seasonal trend forecasts, Pearson correlation, **freshness metadata** (`src/ml/models.py`) |
| Data Visualization | Humanized React dashboard: greeting shell, toasts, metric-selectable charts, friendly empty states, mobile drawer (`frontend/`) |
| Notifications & Alerts | Configurable threshold rules, severity levels, persisted history, live sidebar bell badge, log/email/webhook dispatchers (`src/alerts/`) |
| Feedback & Support | Ticket system with statuses, admin queue (`/feedback` page) |
| Performance Monitoring | `/api/system/stats`: uptime, storage, logs, model status + **processing-time history & averages** |
| **Data Backup** | Automated zips of users/alerts/models/results/logs → `backups/`, auto-prune (14), integrity **Verify**, REST + CLI (`src/utils/backup.py`) |
| Security | PBKDF2-SHA256 hashing, login lockout, security headers (CSP/nosniff/frame-deny), role guards, path-traversal-safe storage, CORS lockdown |
| Documentation | Guides + **in-app Help/FAQ**, **FAQ.md**, **demo video script**, `ReadMe.docx` |

---

## 🚀 Quick Start (local mode — no Hadoop/MongoDB needed)

### 1. Backend (Python 3.11+)

```powershell
pip install -r requirements.txt

# Generate synthetic test data (33k+ rows across 3 datasets)
python -m src.ingestion.generate_test_data

# Load data into HDFS-partitioned storage
python -m src.ingestion.pipeline

# Start the REST API on http://127.0.0.1:5000
python -m src.api.app
```

### 2. Frontend (React + Vite, Node 18+)

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api to :5000)
```

Production build: `npm run build` → static files in `frontend/dist/`.

### 3. Log in

| Role | Username | Password | Can do |
|---|---|---|---|
| Admin | `admin` | `admin@123` | Everything: users, rules, stream control |
| Analyst | `analyst` | `analyst@123` | Analytics, dashboards, feedback |

---

## 🧪 Run the MapReduce jobs

```powershell
python -m src.hadoop.mapreduce.job_runner monthly_aggregation data/raw/weather_stations.csv
python -m src.hadoop.mapreduce.job_runner anomaly_detection  data/raw/weather_stations.csv
```

Or from the **Analytics** page in the UI. On a real cluster set
`EARTHSCAPE_MODE=hadoop` (uses the `hdfs` CLI + Hadoop Streaming jar).

---

## 🧬 Train the ML models

From the **Analytics** page click *Train ML Models*, or via API:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/analytics/ml/train -Headers @{Authorization="Bearer $token"}
```

Forecasts appear on the **Forecasts** page.

---

## ▶️ One-shot startup scripts

```powershell
.\scripts\start_backend.ps1      # API on :5000
.\scripts\start_frontend.ps1     # React dev server on :5173
```

---

## 🗂️ Project structure

```
EarthScape-eProject/
├── src/
│   ├── api/app.py            Flask REST API (all endpoints)
│   ├── auth/                 Authentication + role guards + lockout
│   ├── hadoop/
│   │   ├── storage.py        HDFS abstraction (local sim + real CLI)
│   │   └── mapreduce/        Mapper/reducer pairs + job runner
│   ├── ingestion/            Test-data generator + cleaning pipeline
│   ├── streaming/            Real-time reading simulator
│   ├── ml/models.py          Anomaly / trend / correlation models
│   ├── alerts/               Threshold rule engine + dispatchers
│   ├── db/                   MongoDB backend + JSON fallback
│   ├── utils/backup.py       Automated data backups (zip + prune + verify)
│   └── config.py             All tunables (paths, thresholds, modes)
├── frontend/                 React SPA (Vite + Recharts) — 10 pages
│   └── src/pages/            Login, Dashboard, Live, Data, Analytics,
│                             Forecasts, Alerts, Support, Help, Admin
├── tests/                    109 pytest tests (unit + API integration)
├── docs/                     Guides, report, FAQ, demo video script
├── scripts/                  Start scripts
└── data/                     raw CSVs, HDFS sim, models, JSON db
```

---

## 📄 Assumptions (per eProject submission rules)

1. **No live Hadoop cluster** in the lab environment → a `LocalHDFS` backend
   simulates HDFS semantics (partitioned layout, POSIX-style paths, ls/put/get/glob)
   behind the same interface as the real `hdfs` CLI. Setting
   `EARTHSCAPE_MODE=hadoop` switches to genuine Hadoop Storage + Streaming
   without code changes.
2. **MongoDB optional** → a JSON-file document store with the same API is used
   when `EARTHSCAPE_MONGO_URI` is unset/unreachable (spec lists MongoDB Compass
   in tools, so the Mongo backend is fully implemented and activates automatically).
3. **Climate data is synthetic** — generated by `generate_test_data.py` with
   realistic seasonality, warming trend, regional variation, ~1.5% missing
   values and injected extreme events (heatwave 51°C, smog 480 µg/m³,
   cloudburst 320 mm, storm 118 kph, cold wave −31°C) to demonstrate
   anomaly detection and graceful missing-data handling.
4. **Email/webhook alert channels** are implemented but disabled by default
   (lab machines have no SMTP server); the log channel persists everything.
5. **Tableau/Impala/RStudio** from the software list are optional downstream
   consumers: all processed outputs are plain CSVs under `data/processed/`
   and `data/hdfs_sim/`, directly loadable into those tools.

---

## 📚 Documentation

- [Installation Instructions](docs/INSTALLATION.md)
- [User Guide](docs/USER_GUIDE.md)
- [Developer Guide](docs/DEVELOPER_GUIDE.md)
- [Project Report (problem definition, design, DFDs, flowcharts)](docs/PROJECT_REPORT.md)
- [FAQ — user documentation](docs/FAQ.md) · in-app under **Help & FAQ**
- [Demo Video Script](docs/DEMO_VIDEO_SCRIPT.md) — follow along while recording
- [Tools Guide (Jupyter / Tableau / Impala / RStudio / Compass)](docs/TOOLS_GUIDE.md)
- `ReadMe.docx` — Word copy of this file (generated for submission)

## ✅ Tests

```powershell
python -m pytest tests/ -q      # 109 passed
```

## 🔐 Security notes

- Passwords hashed with PBKDF2-SHA256 (werkzeug), unique salt per user
- Tokens signed (itsdangerous) with 8-hour expiry
- **Brute-force lockout**: 5 failed logins lock the account for 5 minutes (HTTP 423)
- **Security headers** on every response: CSP, `X-Content-Type-Options`,
  `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Cache-Control: no-store`
- Anonymous users cannot self-register as admin
- Storage layer strips `..` — path traversal impossible
- CORS restricted to the Vite dev origin
