# EarthScape Climate Agency — Demo Video Script

> The eProject requires a recorded demo video. This is a ready-to-follow
> **5–7 minute script**: start both servers first
> (`scripts/start_backend.ps1` + `scripts/start_frontend.ps1`),
> open `http://localhost:5173`, then narrate along.
> Record with Win+G (Xbox Game Bar), OBS, or any screen recorder.

---

## 0:00–0:30 — Title & problem
> "This is **EarthScape Climate Agency**, a big-data platform that ingests
> satellite, weather-station and sensor data, stores it in HDFS-partitioned
> storage, processes it with Hadoop MapReduce, finds anomalies with machine
> learning, and alerts analysts in real time — all through a React dashboard."

**Show:** the login screen (hover the two demo-account chips).

## 0:30–1:00 — Authentication & roles
1. Click the **Analyst** chip → **Sign in**.
2. Point out: greeting header, grouped sidebar, role badge.
3. Log out, sign in as **Admin** (`admin / admin@123`) — the
   **Admin Console** link appears only for admins.
4. *(Optional security beat)* mention: "Passwords are PBKDF2-hashed, tokens are
   signed, and five wrong passwords lock the account for five minutes."

## 1:00–1:45 — Data ingestion (batch)
1. Dashboard shows the empty-state **3-step guide** → click **“⚙ Load climate data”**.
2. Narrate: *"raw CSVs are cleaned — duplicates dropped, ranges validated, ~1.5%
   missing values tracked — then written as `year=/month=/day=` HDFS partitions."*
3. Toast shows rows + duration; KPI cards, station table and trend chart fill in.
4. Mention the **metric selector**: switch Temperature → CO₂ → PM2.5.

## 1:45–2:30 — Storage & Data Explorer
1. Open **Data Explorer**: dataset cards (weather 13,140 · sensors 20,000 ·
   satellite 468 rows, partition counts, size).
2. Apply a station + date filter, page through results.
3. *"Same interface drives a real HDFS cluster when `EARTHSCAPE_MODE=hadoop`."*

## 2:30–3:30 — MapReduce & ML
1. **Analytics & ML** → run **anomaly_detection** job → show preview table +
   ⏱ duration chip.
2. Click **“🧠 Train ML Models”** → toast: anomalies found + training seconds +
   freshness chip *"trained just now on 13,140 rows"*.
3. Scroll to **correlations** — e.g. *CO₂ vs sea-level r ≈ −0.81*.
4. **Forecasts**: pick CO₂, 90 days → stat cards (direction, slope, R²) + projection chart.

## 3:30–4:30 — Real-time streaming & alerts
1. **Live Stream** → **“▶ Start simulator”** — readings stream in, chart moves.
2. Watch an injected spike (e.g. 51 °C heatwave) appear in the table with a
   `heatwave spike` tag.
3. Sidebar **Alerts bell** gets a badge → open **Alerts** → show the live history
   (`critical` rows) and the 14 default rules.
4. As admin: add a custom rule (`pm25 > 200`) and show it toggling on/off —
   *"thresholds are configuration, not code."*
5. Stop the simulator.

## 4:30–5:15 — Monitoring, backups & support
1. **Admin Console**: users table (change a role), **system health** chips,
   **⏱ data-processing times** (rows + duration per job), **model freshness**.
2. Click **“📦 Back up now”** → confirm → toast shows files + size; hit **Verify**
   on the new archive.
3. **Support**: submit a ticket (`bug`, subject, message) → it appears with status.
4. **Help & FAQ**: open the accordion — *"in-app user documentation with FAQs."*

## 5:15–5:45 — Tests & closing
1. Switch to the terminal, run:
   ```powershell
   python -m pytest tests/ -q     # → 109 passed
   ```
2. Closing line:
   > *"Delivered: source code, test data, installation instructions, README with
   > assumptions, diagrams, and this demo — 109 automated tests passing."*

---

### 🎬 Recording checklist
- [ ] Both servers running; browser at `http://localhost:5173`, 100 % zoom
- [ ] Close personal tabs/notifications (Do Not Disturb)
- [ ] Say **localhost:5173**, not `127.0.0.1`
- [ ] Reset demo data first if needed: `python -m src.ingestion.generate_test_data`
      then `python -m src.ingestion.pipeline`
- [ ] Keep the video between 5–8 minutes, one continuous take if possible
