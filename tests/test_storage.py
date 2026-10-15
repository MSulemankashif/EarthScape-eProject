"""Tests for the HDFS storage abstraction (LocalHDFS backend)."""

import pandas as pd
import pytest

from src.hadoop.storage import LocalHDFS, StorageError, partition_and_store


@pytest.fixture()
def store(tmp_path):
    return LocalHDFS(tmp_path / "hdfs")


def test_put_get_roundtrip(store, tmp_path):
    src = tmp_path / "sample.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")

    store.put(src, "/climate/test/part-00000.csv")
    assert store.exists("/climate/test/part-00000.csv")

    dest = tmp_path / "restored.csv"
    store.get("/climate/test/part-00000.csv", dest)
    assert dest.read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_missing_file_raises(store):
    with pytest.raises(StorageError):
        store.get("/climate/nope.csv", "out.csv")


def test_put_and_read_dataframe(store):
    df = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", None]})
    store.put_dataframe(df, "/climate/live/part-00000.csv")
    back = store.read_dataframe("/climate/live/part-00000.csv")
    assert len(back) == 3
    assert back["x"].tolist() == [1, 2, 3]
    assert pd.isna(back["y"][2])  # null round-trips


def test_glob_returns_posix_paths(store):
    for m in (1, 2, 3):
        store.put_dataframe(pd.DataFrame({"v": [m]}),
                            f"/climate/w/year=2024/month={m:02d}/part-00000.csv")
    files = store.glob("/climate/w/**/*.csv")
    assert len(files) == 3
    assert all("/" in f and "\\" not in f for f in files), \
        "glob must return HDFS-style forward-slash paths"


def test_read_dataset_concatenates_partitions(store):
    for m in (1, 2):
        store.put_dataframe(pd.DataFrame({"v": [m, m * 10]}),
                            f"/climate/w/year=2024/month={m:02d}/part-00000.csv")
    df = store.read_dataset("/climate/w/**/*.csv")
    assert sorted(df["v"].tolist()) == [1, 2, 10, 20]


def test_partition_and_store(tmp_path):
    store = LocalHDFS(tmp_path / "hdfs")
    df = pd.DataFrame({
        "date": ["2024-01-05", "2024-01-20", "2024-02-10"],
        "value": [1, 2, 3],
    })
    written = partition_and_store(df, "demo", "date", store)
    assert len(written) == 2  # Jan + Feb
    assert all("year=" in p and "month=" in p for p in written)
    # date column preserved for full granularity
    back = store.read_dataset("/climate/demo/**/*.csv")
    assert "date" in back.columns
    assert len(back) == 3


def test_du_and_rm(store):
    store.put_dataframe(pd.DataFrame({"a": range(100)}),
                        "/climate/big/part-00000.csv")
    assert store.du("/climate/big") > 0
    store.rm("/climate/big")
    assert not store.exists("/climate/big")


def test_path_traversal_is_blocked(store, tmp_path):
    src = tmp_path / "secret.csv"
    src.write_text("x\n1\n", encoding="utf-8")
    store.put(src, "/climate/ok/part.csv")
    # .. must be stripped, never escape the root
    escaped = store._full("/../../etc/passwd")
    assert str(store.root) in str(escaped)
