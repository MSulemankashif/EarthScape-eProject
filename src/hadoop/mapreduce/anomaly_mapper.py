#!/usr/bin/env python
"""
Mapper: climate anomaly detector (z-score method)
=================================================
Emits per (station, metric) pairs of (value, running moment counters) so the
reducer can compute global mean/stddev in one pass - the classic
"map-side partial aggregation" pattern taught in big-data courses.

Emitted intermediate format:
    station_id|metric\t1\tvalue\tvalue_sq

The reducer accumulates count / sum / sum-of-squares and then flags every
reading whose z-score exceeds the configured threshold.
"""

import csv
import math
import sys

MEASUREMENTS = [
    "temperature_c", "humidity_pct", "rainfall_mm",
    "co2_ppm", "pm25", "wind_speed_kph", "sea_level_mm",
]


def main() -> None:
    stream = open(sys.argv[1], newline="", encoding="utf-8") if len(sys.argv) > 1 \
        else sys.stdin
    reader = csv.DictReader(stream)
    for row in reader:
        station = (row.get("station_id") or "UNKNOWN").strip()
        for metric in MEASUREMENTS:
            raw = row.get(metric, "")
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue  # skip missing data gracefully
            if not math.isfinite(value):
                continue
            sys.stdout.write(
                f"{station}|{metric}\t1\t{value:.6f}\t{value * value:.6f}\n"
            )


if __name__ == "__main__":
    main()
