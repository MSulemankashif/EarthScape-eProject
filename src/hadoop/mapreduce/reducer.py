#!/usr/bin/env python
"""
Reducer: monthly climate aggregation (Hadoop Streaming compatible)
===================================================================
Consumes the mapper output sorted by key and computes, per station-month:
    count, sum, mean, min, max, stddev  for each measurement.

Output CSV (with header) written to STDOUT:
    station_id,month,metric,count,mean,min,max,stddev,sum

Local run (after sorting):
    python mapper.py data.csv | sort | python reducer.py > result.csv

Because Hadoop Streaming delivers values in arbitrary order, the reducer
buffers everything for one key before aggregating - standard practice.
"""

import math
import sys
from collections import defaultdict

HEADER = "station_id,month,metric,count,mean,min,max,stddev,sum"


def main() -> None:
    # Header is emitted first so the CSV is self-describing (pandas, Impala)
    sys.stdout.write(HEADER + "\n")

    current_key = None
    buckets = defaultdict(list)  # metric -> [values]

    def flush(key: str) -> None:
        if key is None:
            return
        station, month = key.split("|", 1)
        for metric, values in sorted(buckets.items()):
            n = len(values)
            total = math.fsum(values)
            mean = total / n
            var = math.fsum((v - mean) ** 2 for v in values) / n
            sys.stdout.write(
                f"{station},{month},{metric},{n},{mean:.4f},"
                f"{min(values):.4f},{max(values):.4f},{math.sqrt(var):.4f},{total:.4f}\n"
            )
        buckets.clear()

    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue  # malformed record -> skipped, job keeps going
        key, metric, raw = parts
        try:
            value = float(raw)
        except ValueError:
            continue
        if key != current_key:
            flush(current_key)
            current_key = key
        buckets[metric].append(value)

    flush(current_key)


if __name__ == "__main__":
    main()
