"""
MapReduce job runner
====================
Executes the mapper/reducer pairs defined in this package.

Two execution modes:

  * local   - pipes data through Python mappers/reducers in-process
              (equivalent to `hadoop jar hadoop-streaming.jar` but on one
              machine). This is what the eProject uses by default.

  * hadoop  - builds and runs a real Hadoop Streaming command when a cluster
              is available (EARTHSCAPE_MODE=hadoop).

Jobs provided:
  * monthly_aggregation  - per station-month count/mean/min/max/stddev
  * anomaly_detection    - z-score anomalies per station & metric
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import MODE, PROCESSED_DATA_DIR
from src.utils.logger import get_logger

log = get_logger("earthscape.mapreduce")

MR_DIR = Path(__file__).resolve().parent

JOBS = {
    "monthly_aggregation": {
        "mapper": MR_DIR / "mapper.py",
        "reducer": MR_DIR / "reducer.py",
        "output": PROCESSED_DATA_DIR / "monthly_aggregation.csv",
        "description": "Monthly statistics per weather station",
    },
    "anomaly_detection": {
        "mapper": MR_DIR / "anomaly_mapper.py",
        "reducer": MR_DIR / "anomaly_reducer.py",
        "output": PROCESSED_DATA_DIR / "anomalies.csv",
        "description": "Z-score based climate anomaly detection",
    },
}

HADOOP_STREAMING_JAR = os.environ.get(
    "EARTHSCAPE_STREAMING_JAR",
    "/opt/hadoop/share/hadoop/tools/lib/hadoop-streaming-3.3.6.jar",
)


def run_local_pipeline(mapper: Path, reducer: Path, input_csv: Path,
                       zscore: float = 3.0) -> subprocess.CompletedProcess:
    """
    Simulate Hadoop Streaming on a single machine:
        map  -> sort  -> reduce
    Environment knobs (e.g. anomaly threshold) are forwarded to the reducer.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "EARTHSCAPE_ANOMALY_ZSCORE": str(zscore)}

    map_proc = subprocess.run(
        [sys.executable, str(mapper), str(input_csv)],
        capture_output=True, text=True, env=env,
    )
    if map_proc.returncode != 0:
        raise RuntimeError(f"Mapper failed:\n{map_proc.stderr}")

    # Hadoop shuffles & sorts by key between the two phases
    sorted_lines = "\n".join(sorted(map_proc.stdout.splitlines())) + "\n"

    reduce_proc = subprocess.run(
        [sys.executable, str(reducer)],
        input=sorted_lines, capture_output=True, text=True, env=env,
    )
    if reduce_proc.returncode != 0:
        raise RuntimeError(f"Reducer failed:\n{reduce_proc.stderr}")

    return reduce_proc


def run_hadoop_streaming(mapper: Path, reducer: Path, hdfs_input: str,
                         hdfs_output: str) -> str:
    """Launch a real Hadoop Streaming job (requires a live cluster)."""
    cmd = [
        "hadoop", "jar", HADOOP_STREAMING_JAR,
        "-files", f"{mapper},{reducer}",
        "-mapper", mapper.name,
        "-reducer", reducer.name,
        "-input", hdfs_input,
        "-output", hdfs_output,
    ]
    log.info("Launching: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Hadoop job failed:\n{proc.stderr}")
    return proc.stdout


def run_job(job_name: str, input_csv: str | Path,
            output_path: Optional[str | Path] = None,
            zscore: float = 3.0) -> pd.DataFrame:
    """
    Run a named MapReduce job over `input_csv`.

    Returns the result as a DataFrame and (by default) persists it inside
    data/processed/. Works in both local and hadoop modes.
    """
    if job_name not in JOBS:
        raise KeyError(f"Unknown job '{job_name}'. Available: {list(JOBS)}")

    job = JOBS[job_name]
    input_csv = Path(input_csv)
    out = Path(output_path) if output_path else job["output"]
    out.parent.mkdir(parents=True, exist_ok=True)

    log.info("Running job '%s' (%s) over %s",
             job_name, job["description"], input_csv.name)

    result = run_local_pipeline(job["mapper"], job["reducer"], input_csv, zscore)

    out.write_text(result.stdout, encoding="utf-8")
    log.info("Job '%s' finished -> %s", job_name, out)

    if not result.stdout.strip():
        return pd.DataFrame()
    return pd.read_csv(out)


def list_jobs() -> list[dict]:
    """Job catalogue used by the web dashboard."""
    return [
        {
            "name": name,
            "description": job["description"],
            "mapper": job["mapper"].name,
            "reducer": job["reducer"].name,
            "output": str(job["output"]),
            "mode": MODE,
        }
        for name, job in JOBS.items()
    ]


if __name__ == "__main__":
    # Convenience CLI: python -m src.hadoop.mapreduce.job_runner anomaly_detection data.csv
    if len(sys.argv) < 3:
        print("Usage: python -m src.hadoop.mapreduce.job_runner <job> <input_csv>")
        print("Jobs :", ", ".join(JOBS))
        sys.exit(1)
    df = run_job(sys.argv[1], sys.argv[2])
    print(df.head(20).to_string(index=False) if not df.empty else "(no output)")
