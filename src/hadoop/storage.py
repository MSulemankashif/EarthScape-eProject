"""
Storage abstraction over HDFS
=============================
The eProject requires HDFS as the scalable storage layer. Most student
machines do not have a Hadoop cluster, so this module provides ONE interface
with two interchangeable backends:

  * LocalHDFS  - simulates HDFS layout inside data/hdfs_sim/ (default)
  * RemoteHDFS - shells out to the real `hdfs` CLI when MODE == "hadoop"

All climate datasets are stored *partitioned by year/month* under
    /user/earthscape/climate/<dataset>/year=YYYY/month=MM/part-00000.csv
which mirrors real Hadoop partitioning best-practice and speeds up
date-range retrieval (pruning).

Usage:
    from src.hadoop.storage import get_storage
    st = get_storage()
    st.put(local_path, "/climate/weather/year=2024/month=06/part-00000.csv")
    files = st.glob("/climate/weather/year=2024/*")
"""

import shutil
import subprocess
from pathlib import Path
from typing import List

import pandas as pd

from src.config import HDFS_REMOTE_BASE, HDFS_SIM_ROOT, MODE
from src.utils.logger import get_logger

log = get_logger("earthscape.storage")


class StorageError(RuntimeError):
    """Raised when the underlying storage layer cannot complete an operation."""


class LocalHDFS:
    """Local filesystem that mimics the HDFS directory layout."""

    name = "local-hdfs-sim"

    def __init__(self, root: Path = HDFS_SIM_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- helpers ------------------------------------------------------------
    def _full(self, hdfs_path: str) -> Path:
        rel = hdfs_path.lstrip("/").replace("..", "")
        return self.root / rel

    # -- public API (mirrors the real CLI) ----------------------------------
    def mkdirs(self, hdfs_path: str) -> None:
        self._full(hdfs_path).mkdir(parents=True, exist_ok=True)

    def put(self, local_path: str | Path, hdfs_path: str) -> str:
        src, dst = Path(local_path), self._full(hdfs_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        log.info("PUT %s -> %s", src, dst)
        return str(dst)

    def put_dataframe(self, df: pd.DataFrame, hdfs_path: str) -> str:
        """Write an in-memory DataFrame directly into simulated HDFS."""
        dst = self._full(hdfs_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(dst, index=False)
        log.info("PUT dataframe (%d rows) -> %s", len(df), dst)
        return str(dst)

    def get(self, hdfs_path: str, local_path: str | Path) -> Path:
        src = self._full(hdfs_path)
        if not src.exists():
            raise StorageError(f"No such file in HDFS: {hdfs_path}")
        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return dst

    def read_dataframe(self, hdfs_path: str) -> pd.DataFrame:
        src = self._full(hdfs_path)
        if not src.exists():
            raise StorageError(f"No such file in HDFS: {hdfs_path}")
        return pd.read_csv(src)

    def ls(self, hdfs_path: str) -> List[str]:
        target = self._full(hdfs_path)
        if not target.exists():
            return []
        if target.is_file():
            return [self._rel(target, self.root)]
        return sorted(self._rel(p, self.root)
                      for p in target.rglob("*") if p.is_file())

    def glob(self, pattern: str) -> List[str]:
        """Glob relative to the simulated HDFS root, e.g. /climate/**/part-*.csv"""
        rel = pattern.lstrip("/").replace("..", "")
        return sorted(self._rel(p, self.root)
                      for p in self.root.glob(rel) if p.is_file())

    @staticmethod
    def _rel(path: Path, root: Path) -> str:
        """HDFS-style POSIX path (always forward slashes, even on Windows)."""
        return path.relative_to(root).as_posix()

    def read_dataset(self, dataset_glob: str) -> pd.DataFrame:
        """Read and concatenate every partitioned part file of a dataset."""
        files = self.glob(dataset_glob)
        if not files:
            return pd.DataFrame()
        frames = [pd.read_csv(self.root / f) for f in files]
        return pd.concat(frames, ignore_index=True)

    def rm(self, hdfs_path: str) -> None:
        target = self._full(hdfs_path)
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    def du(self, hdfs_path: str) -> int:
        """Total size in bytes of everything under a path."""
        target = self._full(hdfs_path)
        if target.is_file():
            return target.stat().st_size
        return sum(p.stat().st_size for p in target.rglob("*") if p.is_file())

    def exists(self, hdfs_path: str) -> bool:
        return self._full(hdfs_path).exists()


class RemoteHDFS:
    """Thin wrapper around the real `hdfs` / `hadoop` CLI for a live cluster."""

    name = "remote-hdfs"

    def __init__(self, base: str = HDFS_REMOTE_BASE):
        self.base = base.rstrip("/")
        if shutil.which("hdfs") is None:
            raise StorageError(
                "hdfs CLI not found on PATH. Install Hadoop and set "
                "EARTHSCAPE_MODE=hadoop, or keep the default local mode."
            )

    def _run(self, *args: str) -> str:
        proc = subprocess.run(["hdfs", *args], capture_output=True, text=True)
        if proc.returncode != 0:
            raise StorageError(f"hdfs {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc.stdout

    def mkdirs(self, hdfs_path: str) -> None:
        self._run("dfs", "-mkdir", "-p", f"{self.base}{hdfs_path}")

    def put(self, local_path: str | Path, hdfs_path: str) -> str:
        self.mkdirs(hdfs_path.rsplit("/", 1)[0])
        self._run("dfs", "-put", "-f", str(local_path), f"{self.base}{hdfs_path}")
        return f"{self.base}{hdfs_path}"

    def ls(self, hdfs_path: str) -> List[str]:
        out = self._run("dfs", "-ls", f"{self.base}{hdfs_path}")
        return [line.split()[-1] for line in out.splitlines() if line.strip()]

    def read_dataframe(self, hdfs_path: str) -> pd.DataFrame:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            local = Path(tmp.name)
        try:
            self._run("dfs", "-get", "-f", f"{self.base}{hdfs_path}", str(local))
            return pd.read_csv(local)
        finally:
            local.unlink(missing_ok=True)

    def rm(self, hdfs_path: str) -> None:
        self._run("dfs", "-rm", "-r", "-f", f"{self.base}{hdfs_path}")

    def exists(self, hdfs_path: str) -> bool:
        try:
            self._run("dfs", "-test", "-e", f"{self.base}{hdfs_path}")
            return True
        except StorageError:
            return False


def get_storage():
    """Factory honouring EARTHSCAPE_MODE; always falls back to local."""
    if MODE == "hadoop":
        try:
            st = RemoteHDFS()
            log.info("Storage backend: real HDFS at %s", st.base)
            return st
        except StorageError as exc:
            log.warning("%s -- falling back to local HDFS simulation.", exc)
    st = LocalHDFS()
    log.info("Storage backend: LocalHDFS at %s", st.root)
    return st


# ---------------------------------------------------------------------------
# Partitioned ingestion helper
# ---------------------------------------------------------------------------
def partition_and_store(df: pd.DataFrame, dataset: str, date_col: str,
                        storage=None) -> List[str]:
    """
    Split `df` by year/month of `date_col` and write CSV part-files as
        /climate/<dataset>/year=YYYY/month=MM/part-00000.csv
    Returns the list of HDFS paths written.
    """
    storage = storage or get_storage()
    written: List[str] = []
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col])
    for (year, month), group in work.groupby([work[date_col].dt.year,
                                              work[date_col].dt.month]):
        path = (f"/climate/{dataset}/year={int(year)}/month={int(month):02d}"
                f"/part-00000.csv")
        # The date column stays inside the part-file so consumers keep full
        # daily granularity; partition folders only accelerate pruning.
        storage.put_dataframe(group, path)
        written.append(path)
    log.info("Stored %d partition(s) for dataset '%s'", len(written), dataset)
    return written
