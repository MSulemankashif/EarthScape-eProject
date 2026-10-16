# EarthScape Climate Agency — Demo Video Script

> The eProject requires a recorded demo video. This is a ready-to-follow
> **5–7 minute script**: start both servers first
> (`scripts/start_backend.ps1` + `scripts/start_frontend.ps1`),
> open `http://localhost:5173`, then narrate along.
> Record with Win+G (Xbox Game Bar), OBS, or any screen recorder.
>
> **Needs internet** — the platform shows *real, live* OpenWeatherMap data
> (auto-syncs 4 seconds after the backend boots, then every 10 minutes).

---

## 0:00–0:30 — Title & problem
> "This is **EarthScape Climate Agency**, a big-data platform that pulls
> **live weather for 12 Pakistani cities from the OpenWeatherMap API**,
> stores it in HDFS-partitioned storage, processes it with Hadoop MapReduce,
> finds anomalies with machine learning, and alerts analysts in real time —
> all through a React dashboard."

**Show:** the login screen (hover the two demo-account chips).

## 0:30–1:00 — Authentication & roles
1. Click the **Analyst** chip → **Sign in**.
2. Point out: greeting header, grouped sidebar, role badge.
3. Log out, sign in as **Admin** (`admin / admin@123`) — the
   **Admin Console** link appears only for admins.
4. *(Optional security beat)* mention: "Passwords are PBKDF2-hashed, tokens are
   signed, and five wrong passwords lock the account for five minutes."

## 1:00–1:45 — Live data ingestion
1. Dashboard (first visit shows the empty-state **3-step guide**) → the
   **first sync starts automatically**, or click **“☁ Sync live weather”**.
2. Narrate: *"real conditions — temperature, humidity, wind, PM2.5, AQI —
   are fetched from OpenWeather for 12 cities, cleaned (ranges validated,
   missing values kept honest), and written as `year=/month=` HDFS partitions.
   Each city's real 5-day forecast is stored too."*
3. Toast shows cities + duration + forecast rows; KPI cards, city table
   (weather emoji, AQI tags) and the trend chart fill in.
4. Mention the **metric selector**: Temperature → Humidity → Wind → PM2.5,
   and the subtitle that says *hourly average · live since the first sync*.
5. Point at the header chip: **“Live · synced 12s ago”**.

## 1:45–2:30 — Storage & Data Explorer
1. Open **Data Explorer**: dataset cards for `openweather_current` and
   `openweather_forecast` (rows, partition counts, size, “Live · OpenWeather” tag).
2. Switch the dataset dropdown to the 5-day forecast; apply a station + date
   filter, page through results.
3. *"Same interface drives a real HDFS cluster when `EARTHSCAPE_MODE=hadoop`."*

## 2:30–3:30 — MapReduce & ML
1. **Analytics & ML** → set **anomaly sensitivity (z-score)** to *1.5 ·
   sensitive* → run **anomaly_detection** job → show preview table +
   ⏱ duration chip (it reads the live export `openweather_current.csv`).
   Narrate: *"the reducer z-scores each station's own history — at 3σ a young
   warehouse legitimately reports 'no anomalies', so the threshold is
   configurable."*
2. Click **“🧠 Train ML Models”** → toast: anomalies found + training seconds +
   freshness chip *"trained just now on N live rows"*.
   If the info toast appears, narrate it proudly: *"trend models honestly
   wait for ≥ 30 days of live history instead of fitting garbage — the real
   5-day OpenWeather forecast covers near-term needs meanwhile."*
3. Scroll to **correlations** — e.g. temperature × humidity on the real
   readings; note honestly: *"metrics without live values, like outdoor CO₂,
   are skipped rather than faked."*
4. **Forecasts**: the **real OpenWeather 5-day chart** renders first
   (city dropdown, temp + humidity lines, High/Low, rain slots) — then the
   **model projection** card below (direction, slope, R²).

## 3:30–4:30 — Live Weather & alerts
1. **Live Weather** → city cards with weather emoji + AQI badges, the
   by-city comparison bar chart, and the detailed readings table.
2. Hit **“☁ Sync now”** → success toast (or the friendly 30-second cooldown
   message — *"protects the free API quota"*).
3. Sidebar **Alerts bell** gets a badge → open **Alerts** → show the history
   and the 14 default rules.
4. As admin: add a custom rule (e.g. `pm25 > 100`) and show it toggling on/off —
   *"thresholds are configuration, not code."*

## 4:30–5:15 — Monitoring, backups & support
1. **Admin Console**: users table (change a role), the **🌍 OpenWeather live
   source** card (masked key, auto-sync every 10 min, last sync + duration,
   calls/sync), **system health** chips, **⏱ data-processing times**,
   **model freshness**.
2. Click **“📦 Back up now”** → confirm → toast shows files + size; hit **Verify**
   on the new archive.
3. **Support**: submit a ticket (`bug`, subject, message) → it appears with status.
4. **Help & FAQ**: open the accordion — *"in-app user documentation with FAQs"*
   (including "Where does the live data come from?").

## 5:15–5:45 — Tests & closing
1. Switch to the terminal, run:
   ```powershell
   python -m pytest tests/ -q     # → 128 passed
   ```
2. Closing line:
   > *"Delivered: source code, test data, installation instructions, README with
   > assumptions, diagrams, and this demo — 128 automated tests passing,
   > with live OpenWeather data flowing end to end."*

---

### 🎬 Recording checklist
- [ ] Both servers running; browser at `http://localhost:5173`, 100 % zoom
- [ ] **Internet connected** — data is live (first sync happens ~4 s after boot)
- [ ] Close personal tabs/notifications (Do Not Disturb)
- [ ] Say **localhost:5173**, not `127.0.0.1`
- [ ] Optional: press **“☁ Sync now”** once right before recording so the
      "synced Xs ago" chip looks fresh
- [ ] Keep the video between 5–8 minutes, one continuous take if possible
