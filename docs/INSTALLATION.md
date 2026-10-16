# 🛠️ Installation Instructions — EarthScape Climate Agency

## 1. Hardware (per eProject spec)

- Intel i5 (4 cores) minimum, i7 recommended
- 16 GB RAM
- 500 GB SSD
- 64-bit Windows 10 or higher
- (Optional) Graphics card for Tableau/ML workloads

## 2. Software

| Tool | Required? | Purpose |
|---|---|---|
| Python 3.11+ | ✅ Yes | Backend, MapReduce, ML |
| Node.js 18+ / npm | ✅ Yes | React dashboard |
| VS Code / PyCharm | Recommended | Development |
| Hadoop + HDFS | Optional | Real cluster mode (`EARTHSCAPE_MODE=hadoop`) |
| MongoDB + Compass | Optional | Production datastore (auto-detected) |
| Jupyter Anaconda | Optional | Exploratory analysis of `data/processed/*.csv` |
| Tableau / Impala / RStudio | Optional | Downstream BI on exported CSVs |

## 3. Backend setup (Windows PowerShell)

```powershell
# 3.1 Clone/copy the project, open a terminal in the project root

# 3.2 Create a virtual environment (recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3.3 Install Python dependencies
pip install -r requirements.txt

# 3.4 Start the REST API  →  http://127.0.0.1:5000
#    (~4 s after boot it performs the FIRST LIVE SYNC: current conditions +
#     air quality + 5-day forecasts for 12 cities from OpenWeatherMap,
#     then re-syncs every 10 minutes. Internet required.)
python -m src.api.app

# 3.5 OPTIONAL — offline test archives (pytest suite + MapReduce CLI only;
#     the UI never displays them)
python -m src.ingestion.generate_test_data   # ~1.2 MB weather + 1.4 MB sensors
python -m src.ingestion.pipeline             # partitions into data/hdfs_sim/
```

Verify: open <http://127.0.0.1:5000/api/health> — expect
`{"status": "ok", "storage_backend": "local-hdfs-sim", ...}`.

## 4. Frontend setup (second terminal)

```powershell
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

The Vite dev server proxies `/api/*` to `127.0.0.1:5000`, so no CORS setup
is needed during development.

### Production build

```powershell
npm run build        # static files in frontend/dist/
# serve dist/ with any static server, or point nginx/Apache at it
```

## 5. First login

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin@123` |
| Analyst | `analyst` | `analyst@123` |

> Change these in production via the **Admin** page or by editing
> `seed_default_users()` in `src/auth/__init__.py`.

## 6. Optional: real Hadoop cluster mode

1. Install Hadoop 3.x and ensure `hdfs` and `hadoop` are on `PATH`.
2. Start HDFS (`start-dfs.sh` / `start-dfs.cmd`).
3. Set environment variables **before** starting the API:

```powershell
$env:EARTHSCAPE_MODE = "hadoop"
$env:EARTHSCAPE_STREAMING_JAR = "C:\hadoop\share\hadoop\tools\lib\hadoop-streaming-3.3.6.jar"
python -m src.api.app
```

Data is then written under `/user/earthscape/climate/…` on the cluster and
MapReduce jobs launch via Hadoop Streaming.

## 7. Optional: MongoDB

```powershell
$env:EARTHSCAPE_MONGO_URI = "mongodb://localhost:27017"
python -m src.api.app
```

If the URI is unreachable the app automatically falls back to the JSON store
in `data/db/` — nothing else changes.

## 8. Run the test suite

```powershell
python -m pytest tests/ -q
# expected: 93 passed
```

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: src` | Run commands from the project root (the folder containing `src/`) |
| Port 5000 busy | `$env:EARTHSCAPE_PORT = "5001"; python -m src.api.app` |
| Blank dashboard | Run the ingestion first (Dashboard → **Run Ingestion Pipeline**) |
| "No trained trend model" | Analytics page → **Train ML Models** |
| npm.ps1 execution policy error | Use `cmd /c "npm install"` or `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Live stream idle | Only admins can start it (Admin page or `POST /api/stream/start`) |

## 10. Uninstall / reset

Stop the servers and delete the generated data:

```powershell
Remove-Item -Recurse -Force data\hdfs_sim, data\db, data\models, data\processed, logs
```

Re-run steps 3.4–3.6 to rebuild from scratch.
