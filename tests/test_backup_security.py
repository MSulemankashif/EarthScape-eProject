"""
Tests for the requirements-audit additions:
  * automated data backups (Reliability / Data Backup NFR)
  * login brute-force lockout (Data Security NFR)
  * security response headers (Data Security NFR)
  * data-processing-time tracking (Performance Monitoring NFR)
  * model freshness metadata (ML NFR: "regularly update models")
"""

from __future__ import annotations

import time
import zipfile

import pytest

from src import auth
from src.utils import backup


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
def test_create_backup_produces_valid_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    result = backup.create_backup(label="unit test!")

    archive = tmp_path / "backups" / result["file"]
    assert archive.exists()
    assert result["files"] > 0
    assert result["size_bytes"] > 0
    # Label is sanitised (no spaces / punctuation in the filename)
    assert "unit_test" in result["file"]
    assert " " not in result["file"]

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    # Regenerable HDFS sim is deliberately excluded to keep archives small
    assert not any(n.startswith("data/hdfs_sim/") for n in names)
    assert any(n.startswith("data/") or n.startswith("logs/") for n in names)


def test_list_backups_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    first = backup.create_backup("first")
    second = backup.create_backup("second")

    items = backup.list_backups()
    assert len(items) == 2
    assert items[0]["file"] == second["file"]
    assert items[1]["file"] == first["file"]


def test_prune_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    for i in range(5):
        backup.create_backup(f"b{i}")

    removed = backup.prune(keep=2)
    assert removed == 3
    assert len(backup.list_backups()) == 2


def test_verify_backup_detects_corruption(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    result = backup.create_backup("verify")
    ok = backup.verify_backup(result["file"])
    assert ok["valid"] is True

    with pytest.raises(FileNotFoundError):
        backup.verify_backup("does_not_exist.zip")


def test_backup_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    assert backup.main([]) == 0
    assert "files" in capsys.readouterr().out

    assert backup.main(["--list"]) == 0
    assert backup.main(["--prune", "1"]) == 0
    assert backup.main(["--bogus"]) == 1


# ---------------------------------------------------------------------------
# Login lockout
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_lockout_state():
    auth.clear_failures()
    yield
    auth.clear_failures()


def test_five_failures_lock_the_account():
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        assert auth.authenticate("admin", "wrong-password") is None

    status = auth.lockout_status("admin")
    assert status["locked"] is True
    assert status["locked_for_seconds"] > 0

    # Even the CORRECT password is rejected while locked
    assert auth.authenticate("admin", "admin@123") is None


def test_lockout_is_per_username():
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth.authenticate("admin", "nope")
    # A different user is unaffected
    assert auth.authenticate("analyst", "analyst@123") is not None


def test_successful_login_clears_failures():
    for _ in range(3):
        auth.authenticate("admin", "nope")
    assert auth.lockout_status("admin")["failed_count"] == 3
    assert auth.authenticate("admin", "admin@123") is not None
    assert auth.lockout_status("admin")["failed_count"] == 0


def test_lockout_expires(monkeypatch):
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth.authenticate("admin", "nope")
    assert auth.lockout_status("admin")["locked"] is True

    # Simulate the lockout window elapsing
    attempt = auth._failed_attempts["admin"]
    attempt["until"] = time.time() - 1
    assert auth.authenticate("admin", "admin@123") is not None


# ---------------------------------------------------------------------------
# API-level behaviour (headers, lockout responses, timing, backups)
# ---------------------------------------------------------------------------
def test_security_headers_present(client):
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert res.headers["Cache-Control"] == "no-store"


def test_login_lockout_response_423(client):
    # First four failures are plain 401s...
    for _ in range(auth.MAX_LOGIN_ATTEMPTS - 1):
        res = client.post("/api/auth/login",
                          json={"username": "admin", "password": "bad"})
        assert res.status_code == 401

    # ...the fifth failure trips the lock and says so (423 Locked)
    res = client.post("/api/auth/login",
                      json={"username": "admin", "password": "bad"})
    assert res.status_code == 423
    assert res.get_json()["lockout"]["locked"] is True

    # Even the correct password is refused while locked
    res = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin@123"})
    assert res.status_code == 423
    assert "locked" in res.get_json()["error"].lower()
    auth.clear_failures("admin")


def test_job_run_reports_processing_time(client, auth_headers):
    res = client.post("/api/analytics/jobs/run",
                      json={"job": "anomaly_detection"}, headers=auth_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["duration_seconds"] > 0
    assert "in " in body["message"] and "s." in body["message"]


def test_system_stats_include_processing_and_backups(client, auth_headers):
    client.post("/api/analytics/jobs/run",
                json={"job": "data_summary"}, headers=auth_headers)
    res = client.get("/api/system/stats", headers=auth_headers)
    assert res.status_code == 200
    stats = res.get_json()

    processing = stats["processing"]
    assert processing["job_count"] >= 1
    assert processing["recent_jobs"][0]["duration_seconds"] > 0
    assert "backups" in stats
    assert "count" in stats["backups"]


def test_backup_endpoints_require_admin(client, analyst_headers):
    res = client.post("/api/system/backup", headers=analyst_headers)
    assert res.status_code == 403

    res = client.get("/api/system/backups", headers=analyst_headers)
    assert res.status_code == 403


def test_backup_roundtrip_via_api(client, auth_headers):
    res = client.post("/api/system/backup",
                      json={"label": "pytest"}, headers=auth_headers)
    assert res.status_code == 201
    created = res.get_json()["backup"]
    assert created["files"] > 0

    res = client.get("/api/system/backups", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["count"] >= 1

    res = client.get(f"/api/system/backups/{created['file']}/verify",
                     headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["valid"] is True

    res = client.get("/api/system/backups/nope.zip/verify",
                     headers=auth_headers)
    assert res.status_code == 404


def test_ml_status_reports_freshness(client, auth_headers, monkeypatch):
    # Give the trainer a small but real weather history to work with
    import pandas as pd
    dates = pd.date_range("2024-01-01", periods=120, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "station_id": ["STN-001"] * len(dates),
        "temperature_c": [18 + 6 * (i % 30) / 30 for i in range(len(dates))],
        "co2_ppm": [410 + i * 0.1 for i in range(len(dates))],
        "rainfall_mm": [max(0.0, (i % 7) - 2) for i in range(len(dates))],
    })
    monkeypatch.setattr("src.api.app._weather_df", lambda limit=None: df)

    res = client.post("/api/analytics/ml/train", headers=auth_headers)
    assert res.status_code == 200, res.get_json()
    freshness = res.get_json()["freshness"]
    assert freshness["rows_used"] == len(df)
    assert freshness["duration_seconds"] > 0
    assert freshness["trained_at"]

    res = client.get("/api/analytics/ml/status", headers=auth_headers)
    assert res.get_json()["freshness"]["trained_at"] == freshness["trained_at"]
