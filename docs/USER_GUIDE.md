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

The landing page — every number is **live OpenWeatherMap data** for 12
Pakistani cities.

- **☁ Sync live weather** — pulls real conditions + 5-day forecasts now
  (a first sync also starts automatically on a fresh install; then the
  backend re-syncs every 10 minutes). The header chip shows when data was
  last synced.
- **KPI cards** — average temperature, humidity, wind, PM2.5, total live
  readings and the missing-value count.
- **Trend chart** — pick Temperature / Humidity / Wind / PM2.5 / Rainfall;
  the subtitle tells you the aggregation (5-minute buckets on brand-new
  history, then hourly, daily, monthly as the warehouse grows).
- **Current conditions across cities** — weather emoji, region tag and the
  freshest reading per city; PM2.5 above 150 µg/m³ is highlighted red.

## 🌦️ Live Weather

The real-time heart of the platform (refreshes every 30 s; backend re-syncs
every 10 min).

- **☁ Sync now** — fetch fresh data immediately (a friendly 30-second
  cooldown protects the free API quota).
- **City cards** — emoji, temperature, feels-like, humidity, wind, PM2.5 and
  an AQI badge (Good → Very poor).
- **By-city bar chart** — compare the selected metric across all 12 cities.
- **Latest readings table** — station, observation time, pressure and
  condition for every city.

## 🗄️ Data Explorer

Browse the live warehouse: `openweather_current` (one row per city per sync)
and `openweather_forecast` (40 three-hour slots per city) — switch datasets
with the dropdown.

- Dataset cards show rows, partitions, size and a “Live · OpenWeather” tag.
- Filter by **station**, **start date**, **end date** — server-side
  pagination (50 rows/page).
- Missing measurements display as `—` (never zero-filled — zeros would skew
  the analytics; e.g. OpenWeather has no CO₂ sensor, so CO₂ stays honest).

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
  (Analytics) → 3) Sync live weather (Live Weather) → 4) Watch alerts appear.
- Session lasts 8 hours; you'll be redirected to login when it expires.
- All numbers in tables show `—` when the underlying measurement was
  missing — this is intentional (graceful handling of incomplete data).
