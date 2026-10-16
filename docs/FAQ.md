# EarthScape Climate Agency — FAQ

> The "user documentation" deliverable requires FAQs and tutorials.
> A friendly in-app version lives at **Help & FAQ** inside the dashboard;
> this file is the printable/knowledge-base copy.

---

## 🚀 Getting started (tutorials)

### Tutorial 1 — Pull your first live weather (≈10 seconds)
1. Sign in (`admin / admin@123` or `analyst / analyst@123`).
2. On the **Dashboard**, press **“☁ Sync live weather”** (a first sync also
   starts on its own when the warehouse is empty).
3. Wait for the success toast — real conditions for **12 Pakistani cities**
   (temperature, humidity, wind, PM2.5, AQI) plus each city's **real 5-day
   forecast** are fetched from OpenWeatherMap, cleaned, and written into
   HDFS-style `year=/month=` partitions.
4. KPI cards, the city table and every chart fill in automatically.

### Tutorial 2 — Watch live weather arrive
1. Open **Live Weather**.
2. City cards show current conditions with AQI badges; a bar chart compares
   the selected metric across all 12 cities.
3. The page polls every 30 seconds while the backend re-syncs every 10 minutes —
   or press **“☁ Sync now”** for fresh data immediately.
4. Keep the **Alerts** bell in the sidebar — every reading is evaluated against
   your rules the moment it lands.

### Tutorial 3 — Train models and forecast
1. Open **Analytics & ML** → **“🧠 Train ML Models”** (needs ≥10 live readings —
   auto-sync collects 12 every 10 minutes).
2. The page reports anomalies found, training duration and model freshness.
3. Open **Forecasts** for the **real 5-day OpenWeather forecast** (default) plus
   the model's long-range projection (30–365 days).

### Tutorial 4 — Create your own alert rule
1. Open **Alerts** (admin) → **“Add your own rule”**.
2. Example: metric `pm25`, exceeds `> 150`, severity `critical`.
3. The next live reading that matches fires an alert immediately.

---

## ❓ Frequently asked questions

**Q: The dashboard looks empty. Is something broken?**
No — the warehouse simply has no live data yet. Click **“☁ Sync live weather”**
on the Dashboard. Everything (charts, models, correlations) appears afterwards.

**Q: Where does the data come from? Is it real?**
Real. The backend calls the **OpenWeatherMap API** (`/weather`, `/air_pollution`,
`/forecast`) for 12 cities — actual temperatures, humidity, wind, PM2.5 and AQI
observations, refreshed every 10 minutes (plus on demand). The free tier allows
60 calls/minute; a 30-second cooldown between manual syncs protects that quota.
The key sits in `src/config.py` and can be overridden with `OPENWEATHER_API_KEY`.

**Q: Why are CO₂ and sea level always “—”?**
OpenWeatherMap offers no outdoor CO₂ or sea-level sensor, so those columns are
honestly stored as *missing* rather than faked — and every chart, average and
correlation skips them gracefully (see “How is missing data handled?” below).
Offline test archives do contain synthetic CO₂ for exercising the ML code.

**Q: Is real Hadoop required?**
No. By default the app runs in **simulation mode**: `data/hdfs_sim/` mirrors real
HDFS partitioning and the MapReduce jobs run through a local pipe that mimics
`hadoop jar`. Set `EARTHSCAPE_MODE=hadoop` to drive a real cluster via its CLI —
the storage interface is identical.

**Q: Does it need MongoDB?**
Same story. The default store is a JSON document backend with MongoDB's API
(`find`, `insert`, `update`). Set `EARTHSCAPE_MONGO_URI=mongodb://…` and the same
code talks to a real MongoDB (Mongo Compass works for browsing it).

**Q: How do alerts work?**
Every live reading is evaluated against all enabled rules the moment it is
synced. Rules are plain data: `metric + comparator + threshold + severity` —
CRUD from the UI, no restart required. 14 sensible defaults ship with the app
(e.g. `temperature_c > 45 °C`, `pm25 > 300 µg/m³`).

**Q: I mistyped my password five times and now I'm locked out.**
That is the brute-force protection: 5 failed attempts lock the account for
5 minutes (15-minute failure window). The login response tells you exactly how
long is left. It is per-username — other users are unaffected.

**Q: Who can do what?**
| Action | Analyst | Admin |
|---|---|---|
| View data, run jobs, train models | ✅ | ✅ |
| Trigger live weather syncs | ✅ | ✅ |
| Manage alert rules, users, backups | ❌ | ✅ |
| Submit support tickets | ✅ | ✅ |

Enforced server-side on **every** endpoint (`@role_required` / `@admin_required`),
not just hidden in the UI.

**Q: How do backups work?**
Admin Console → **“📦 Back up now”**. Users, alerts, tickets, models, processed
results and logs are zipped into `backups/earthscape_YYYYmmdd_HHMMSS.zip`.
The newest 14 archives are kept automatically; **Verify** performs an integrity
check. The HDFS tree is excluded on purpose — it is fully regenerable by
re-running ingestion. CLI: `python -m src.utils.backup [--list|--prune N|--verify F]`.

**Q: Where can I see performance?**
The Admin Console has a **“⏱ Data-processing times”** card: every MapReduce run
and model training is timed (duration, rows, finish time) plus session averages.
Uptime, storage size, log sizes, CPU count and model freshness sit next to it.

**Q: How fresh are the ML models?**
The Analytics page shows a freshness chip (`trained 8 min ago on 48 rows`).
Retrain any time — each sync adds 12 more live readings, and training takes a
couple of seconds and overwrites the old artifacts atomically.

**Q: The frontend won't load — “connection refused”.**
Two servers must run: backend on **:5000** and Vite on **:5173**. Use
`http://localhost:5173` (not `127.0.0.1` — Vite binds the IPv6 localhost).
Start them with `scripts/start_backend.ps1` and `scripts/start_frontend.ps1`.

**Q: Are my credentials safe?**
Passwords are salted PBKDF2-HMAC-SHA256 hashes (never stored plaintext), sessions
are signed expiring tokens, responses carry security headers
(`X-Content-Type-Options`, `X-Frame-Options`, CSP, `Cache-Control: no-store`),
and production deployments terminate TLS at Apache/nginx as documented in
`docs/INSTALLATION.md`.

**Q: How is missing data handled?**
The cleaning step drops exact duplicate rows, coerces types, clips values to
physically plausible ranges (e.g. −90…60 °C), and leaves gaps as `NaN` which are
skipped by MapReduce mappers and treated as missing by the ML imputer. Live data
demonstrates this daily: OpenWeather has no CO₂ sensor, so those cells arrive
empty and are skipped by charts and correlation instead of being invented. The
Dashboard's **Missing Values** card reports how many were found.

**Q: Can I export data for Tableau / RStudio / Impala / Jupyter?**
Yes — every dataset is plain CSV, including the live export
`data/processed/openweather_current.csv` (+ `openweather_forecast.csv`),
refreshed on every sync. Point Tableau at them, load them in RStudio,
`CREATE EXTERNAL TABLE … STORED AS TEXTFILE` in Impala, or open them in
Jupyter (`pandas.read_csv`). See `docs/TOOLS_GUIDE.md`.

---

## 🆘 Still stuck?
Open **Support → ✍️ Open a ticket** inside the app — pick a category, describe the
problem, and it is stored with a trackable status (`open → in_progress → resolved`).
