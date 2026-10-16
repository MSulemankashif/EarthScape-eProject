"""Tests for the Hadoop Streaming mapper/reducer pair."""

import subprocess
import sys
from pathlib import Path

MR = Path(__file__).resolve().parent.parent / "src" / "hadoop" / "mapreduce"

SAMPLE = """station_id,city,date,temperature_c,humidity_pct,rainfall_mm,co2_ppm,pm25,wind_speed_kph,sea_level_mm
STN-001,Karachi,2024-01-01,20.5,70,0.0,415.2,55,10,-4
STN-001,Karachi,2024-01-02,21.0,72,1.5,416.0,60,12,-4
STN-001,Karachi,2024-01-03,,75,0.5,417.1,58,11,-3
STN-002,Lahore,2024-01-01,15.0,50,0.0,422.0,80,8,-6
STN-002,Lahore,2024-01-02,16.0,52,0.0,421.0,82,9,-6
STN-002,Lahore,2024-01-03,14.5,49,0.0,423.0,79,8,-6
STN-002,Lahore,2024-01-04,15.5,51,0.1,422.5,81,7,-6
STN-002,Lahore,2024-01-05,15.2,50,0.0,421.8,80,9,-6
STN-002,Lahore,2024-01-06,51.0,48,0.0,423.0,82,9,-6
"""


def run(mapper: Path, reducer: Path, data: str, env=None) -> str:
    import os
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if env:
        environment.update(env)
    mapped = subprocess.run([sys.executable, str(mapper)],
                            input=data, capture_output=True, text=True,
                            env=environment, check=True)
    sorted_out = "\n".join(sorted(mapped.stdout.splitlines())) + "\n"
    reduced = subprocess.run([sys.executable, str(reducer)],
                             input=sorted_out, capture_output=True, text=True,
                             env=environment, check=True)
    return reduced.stdout


def test_monthly_aggregation_basic_stats():
    out = run(MR / "mapper.py", MR / "reducer.py", SAMPLE)
    lines = [l for l in out.splitlines() if l]
    assert lines, "reducer produced no output"

    header = lines[0]
    assert header.startswith("station_id,month,metric")

    # STN-001 temperature: 20.5 and 21.0 present, blank skipped -> n=2
    temp_rows = [l for l in lines
                 if l.startswith("STN-001,2024-01,temperature_c,")]
    assert temp_rows, "STN-001 temperature aggregate missing"
    n = int(temp_rows[0].split(",")[3])
    assert n == 2, f"missing value not skipped: count was {n}"

    # STN-002 has an injected 51.0 outlier -> max must reflect it
    temp2 = [l for l in lines
             if l.startswith("STN-002,2024-01,temperature_c,")]
    assert temp2 and "51.0000" in temp2[0], "outlier lost by the reducer"


def test_anomaly_detection_flags_outlier():
    out = run(MR / "anomaly_mapper.py", MR / "anomaly_reducer.py", SAMPLE,
              env={"EARTHSCAPE_ANOMALY_ZSCORE": "1.5"})
    lines = [l for l in out.splitlines() if l and not l.startswith("station_id")]
    flagged = {l.split(",")[0] + "|" + l.split(",")[1] for l in lines}
    assert "STN-002|temperature_c" in flagged, "51.0C outlier not flagged"
    # The near-identical readings must NOT be flagged
    assert "STN-002|sea_level_mm" not in flagged


def test_malformed_lines_do_not_crash():
    broken = SAMPLE + "garbage,line,here\nSTN-003,city,2024-02-01,abc,1,2,3,4,5,6\n"
    out = run(MR / "mapper.py", MR / "reducer.py", broken)
    assert "STN-001" in out  # good data still processed


def test_empty_input_is_tolerated():
    out = run(MR / "mapper.py", MR / "reducer.py",
              "station_id,city,date,temperature_c\n")
    # Only the CSV header line, no data rows
    assert out.strip().splitlines() == ["station_id,month,metric,count,mean,min,max,stddev,sum"]


def test_job_runner_api():
    """job_runner.run_job returns a DataFrame and persists the output."""
    import tempfile

    import pandas as pd

    from src.hadoop.mapreduce.job_runner import list_jobs, run_job

    jobs = list_jobs()
    assert {j["name"] for j in jobs} == {"monthly_aggregation", "anomaly_detection"}

    with tempfile.TemporaryDirectory() as tmp:
        csv = Path(tmp) / "in.csv"
        csv.write_text(SAMPLE, encoding="utf-8")
        out = Path(tmp) / "out.csv"
        df = run_job("monthly_aggregation", csv, out)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert out.exists()
