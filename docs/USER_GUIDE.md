# 📖 User Guide — EarthScape Climate Agency Dashboard

## Getting started

1. Start the backend (`python -m src.api.app`) and frontend (`npm run dev`).
2. Open <http://localhost:5173>.
3. Sign in with **admin / admin@123** (full access) or **analyst / analyst@123**
   (analytics only).

The left sidebar navigates between pages. Your username and role badge are at
the bottom of the sidebar.

---

## 📊 Dashboard

The landing page with national climate KPIs.

- **Run Ingestion Pipeline** — loads the raw CSV datasets into partitioned
  HDFS-style storage. Click this once on a fresh install; the stat cards,
  trend chart and station table appear afterwards.
- **KPI cards** — average temperature, CO₂, PM2.5, rainfall, missing-value
  count and active storage backend.
- **Monthly temperature chart** — national average, last 36 months.
- **Latest Reading per Station** — one row per station; PM2.5 values above
  150 µg/m³ are highlighted red (hazardous air quality).

## 📡 Live Stream

Real-time sensor feed (polls every 3 seconds).

- **Start/Stop simulator** (admin only) — the generator pushes 3 readings
  every 2 seconds, including occasional spikes (~5%) so the alert system has
  events to show.
- **Metric selector** — watch temperature, CO₂, PM2.5, wind, humidity or
  rainfall live.
- **Latest readings table** — rows tagged `spike` are simulated extreme
  events.

## 🗄️ Data Explorer

Browse the historical dataset (13,140 daily readings × 12 stations,
2022-01-01 → 2024-12-31).

- Dataset cards show rows, partitions and size per ingested dataset.
- Filter by **station**, **start date**, **end date** — server-side
  pagination (50 rows/page).
- Missing measurements display as `—` (never zero-filled — zeros would skew
  the analytics).

## 🧠 Analytics & Machine Learning

**MapReduce Jobs** (big-data processing layer):

| Job | What it does |
|---|---|
| `monthly_aggregation` | Per station-month: count/mean/min/max/stddev of every metric |
| `anomaly_detection` | Z-score anomalies per station & metric (threshold 3σ) |

Click **Run** — the result preview appears below the job list.

**ML Models**:

- **Train ML Models** button trains:
  - *Isolation Forest* anomaly detector (multivariate, ~2% expected rate)
  - *Trend models* for temperature, CO₂ and rainfall (linear trend +
    annual seasonality)
- After training you see the anomaly count/rate, the 50 most recent
  anomalies with their scores, and each trend's direction, slope and R².

**Correlations** — strongest Pearson relationships between climate variables
as a bar chart + table (e.g. CO₂ vs sea level: r = −0.81, very strong).

## 🔮 Forecasts

Pick a **metric** (temperature / CO₂ / rainfall) and a **horizon**
(30–365 days). The chart shows the projected values; the cards show:

- **Direction** — warming / cooling
- **Slope per year** — e.g. −1.42 °C/yr on the demo dataset
- **R²** — model fit quality
- **Trained until** — last date of training data

> Train the models first on the Analytics page if forecasts are empty.

## 🚨 Alerts

- **Alert history** — every threshold breach with severity
  (`info` / `warning` / `critical`), station and timestamp. Filter by
  minimum severity. Auto-refreshes every 8 seconds.
- **Threshold rules** — 14 default rules (temperature high/low, CO₂, PM2.5,
  wind, rain, humidity, sea level). Analysts can view; **admins** can add
  custom rules, enable/disable or delete them.

Example custom rule: `co2_watch — co2_ppm exceeds 450 → critical`.

## 💬 Feedback & Support

- Submit a ticket: category (bug / data issue / feature request / other),
  subject and message.
- Users see their own tickets; **admins see all** and can mark them
  `in progress` or `resolved`.

## ⚙️ Admin (admin role only)

- **Users** — change anyone's role between `analyst` and `admin` via the
  dropdown; see status and last login.
- **System health** — uptime, storage/database backends, CPU cores, storage
  used, live-stream state, alert totals, model status and log files.

---

## Tips

- **First-time checklist**: 1) Run ingestion (Dashboard) → 2) Train models
  (Analytics) → 3) Start stream (Live Stream) → 4) Watch alerts appear.
- Session lasts 8 hours; you'll be redirected to login when it expires.
- All numbers in tables show `—` when the underlying measurement was
  missing — this is intentional (graceful handling of incomplete data).
