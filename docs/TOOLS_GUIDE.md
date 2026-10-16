# Tools Guide — plugging EarthScape into the listed software tools

The software-requirement list names Jupyter, RStudio, VS Code, MongoDB Compass,
Hadoop/HDFS/Apache, Tableau and Impala. Here is exactly how each one connects
to this project — no code changes needed.

---

## 🐍 Jupyter (Anaconda Notebook)

Every dataset and MapReduce output is a plain CSV, so analysis starts in one cell:

```python
import pandas as pd

weather = pd.read_csv("data/raw/weather_stations.csv", parse_dates=["date"])
weather.groupby("region")["temperature_c"].describe()

# MapReduce output (anomaly job)
anomalies = pd.read_csv("data/processed/anomaly_detection/part-00000.csv")
```

Launch from the project root (`jupyter notebook`) so relative paths resolve.
`data/hdfs_sim/climate/.../part-*.csv` files are readable the same way — they are
the "HDFS" copies the pipeline wrote.

## 📊 Tableau

1. **File → Open** → connect to *Text/CSV* → pick `data/raw/weather_stations.csv`
   (or any file under `data/processed/`).
2. Set `date` as a Date field; drag `temperature_c` to Rows, `date` to Columns.
3. For the partitioned store, use *Data → Union* and select the whole
   `data/hdfs_sim/climate/weather/readings` folder — Tableau unions all
   `year=/month=/day=` partition CSVs automatically.

Live dashboards: point Tableau at the REST API with a *Web Data Connector*
or simply export the Analytics previews (CSV in the browser).

## 🐘 Impala (Hadoop SQL)

The partitioned tree is already Hive-style, so external tables map 1:1:

```sql
CREATE EXTERNAL TABLE climate_weather (
  date STRING, station_id STRING, city STRING, region STRING,
  temperature_c DOUBLE, humidity_pct DOUBLE, rainfall_mm DOUBLE,
  co2_ppm DOUBLE, pm25 DOUBLE, wind_speed_kph DOUBLE, sea_level_mm DOUBLE
)
PARTITIONED BY (year STRING, month STRING, day STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/climate/weather/readings';

MSCK REPAIR TABLE climate_weather;

SELECT region, AVG(temperature_c)
FROM climate_weather
WHERE year = '2024'
GROUP BY region;
```

On the local simulation, run the same queries in any dataframe tool against
`data/hdfs_sim/climate/weather/readings/year=*/month=*/day=*/`.

## 📈 RStudio

```r
library(readr)
library(dplyr)

weather <- read_csv("data/raw/weather_stations.csv")
weather %>%
  group_by(region) %>%
  summarise(mean_temp = mean(temperature_c, na.rm = TRUE))

# Forecast comparison against the Python model
fc <- read_csv("data/processed/forecast_temperature_c.csv")
```

## 🍃 MongoDB Compass

With `EARTHSCAPE_MONGO_URI` set, collections live in the `earthscape` database:

| Collection | Contents |
|---|---|
| `users` | accounts (password *hashes* only) |
| `alerts` | persisted alert history |
| `feedback` | support tickets |

Connect Compass to your URI and browse/filter them visually. In the default
JSON mode the same data sits in `data/db/*.json` — open them in Compass's
JSON viewer or any editor.

## 🖥️ VS Code

Recommended extensions: **Python**, **ESLint**, **Pylance**, **SQLite/JSON viewers**.
Useful tasks: `Run Python File`, the integrated terminal for
`python -m pytest tests/ -q`, and `Ctrl+Shift+B` for the Vite build.

## 🐘 Hadoop / HDFS (real cluster)

```powershell
$env:EARTHSCAPE_MODE = "hadoop"     # storage now drives the real `hdfs` CLI
$env:EARTHSCAPE_STREAMING_JAR = "...\hadoop-streaming-3.x.x.jar"
python -m src.api.app
```

Set `EARTHSCAPE_NAMENODE=hdfs://master:9000` if the namenode is remote.
Everything else (endpoints, UI, tests) is unchanged.

## 🌐 Apache (production web tier)

Serve the built frontend + proxy the API (full vhost sample in
`docs/INSTALLATION.md`):

```powershell
cd frontend; npm run build          # → frontend/dist/
```

```apache
ProxyPass        /api  http://127.0.0.1:5000/api
ProxyPassReverse /api  http://127.0.0.1:5000/api
```

TLS termination at Apache gives the HTTPS required by the security NFR;
the API already emits hardened response headers to complement it.
