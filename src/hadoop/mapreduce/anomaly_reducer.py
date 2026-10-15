#!/usr/bin/env python
"""
Reducer: climate anomaly detector
=================================
Aggregates the mapper's moment counters, derives mean & stddev per
(station, metric), then re-scans every emitted value and prints anomalies.

Output CSV:
    station_id,metric,mean,stddev,zscore,value

The z-score threshold comes from EARTHSCAPE_ANOMALY_ZSCORE (default 3.0).
"""

import math
import os
import sys
from collections import defaultdict

ZSCORE_THRESHOLD = float(os.environ.get("EARTHSCAPE_ANOMALY_ZSCORE", "3.0"))


def main() -> None:
    counts = defaultdict(int)
    sums = defaultdict(float)
    sq_sums = defaultdict(float)
    values = defaultdict(list)          # key -> [individual values]

    for line in sys.stdin:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 4:
            continue
        key, n, val, val_sq = parts
        try:
            counts[key] += int(n)
            sums[key] += float(val)
            sq_sums[key] += float(val_sq)
            values[key].append(float(val))
        except ValueError:
            continue  # malformed line tolerated

    header_printed = False
    for key in sorted(values):
        station, metric = key.split("|", 1)
        n = counts[key]
        if n < 2:
            continue  # cannot compute a meaningful stddev
        mean = sums[key] / n
        variance = max(0.0, sq_sums[key] / n - mean * mean)
        stddev = math.sqrt(variance)
        if stddev == 0:
            continue

        for value in values[key]:
            zscore = (value - mean) / stddev
            if abs(zscore) >= ZSCORE_THRESHOLD:
                if not header_printed:
                    sys.stdout.write("station_id,metric,mean,stddev,zscore,value\n")
                    header_printed = True
                sys.stdout.write(
                    f"{station},{metric},{mean:.4f},{stddev:.4f},"
                    f"{zscore:.4f},{value:.4f}\n"
                )


if __name__ == "__main__":
    main()
