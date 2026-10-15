#!/usr/bin/env python
"""
Mapper: monthly climate aggregation (Hadoop Streaming compatible)
==================================================================
Reads CSV records from STDIN (or a file argument) and emits one intermediate
key per station-month for every metric.

Input record (weather stations CSV):
    station_id,city,latitude,longitude,region,date,temperature_c,...

Output (tab separated, fed to the reducer):
    STN-001|2024-05\ttemperature_c\t38.5
    STN-001|2024-05\trainfall_mm\t12.3
    ...

This mapper is intentionally tolerant: rows with missing/NaN measurements
are skipped rather than crashing the job (requirement: "handle missing or
incomplete data gracefully").

Run standalone:  python mapper.py ../../data/raw/weather_stations.csv
Run on Hadoop:   hadoop jar $STREAMING_JAR -mapper mapper.py -file mapper.py ...
"""

import csv
import math
import sys

MEASUREMENTS = [
    "temperature_c", "humidity_pct", "rainfall_mm",
    "co2_ppm", "pm25", "wind_speed_kph", "sea_level_mm",
]


def is_number(value) -> bool:
    """True when value parses to a finite float (rejects '', None, NaN)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def map_record(row: dict):
    """Yield (key, metric, value) tuples for one input row."""
    station = (row.get("station_id") or "UNKNOWN").strip()
    date = (row.get("date") or "").strip()
    month = date[:7] if len(date) >= 7 else "0000-00"
    key = f"{station}|{month}"

    for metric in MEASUREMENTS:
        raw = row.get(metric, "")
        if is_number(raw):
            yield key, metric, float(raw)
        # else: incomplete datum -> skipped, counted by the reducer via logs


def main() -> None:
    stream = open(sys.argv[1], newline="", encoding="utf-8") if len(sys.argv) > 1 \
        else sys.stdin
    reader = csv.DictReader(stream)
    for row in reader:
        for key, metric, value in map_record(row):
            sys.stdout.write(f"{key}\t{metric}\t{value}\n")


if __name__ == "__main__":
    main()
