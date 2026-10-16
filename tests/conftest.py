"""Pytest configuration: make the project root importable and provide
shared API fixtures (Flask test client + auth headers) for every module."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client with an isolated JSON backend and temp HDFS."""
    from src import auth, db
    from src.db import JsonBackend
    from src.hadoop.storage import LocalHDFS
    from src.ml.models import ClimateModelRegistry

    monkeypatch.setattr(db, "_backend", JsonBackend(tmp_path / "db"))
    monkeypatch.setattr("src.api.app.get_storage",
                        lambda: LocalHDFS(tmp_path / "hdfs"))
    monkeypatch.setattr("src.api.app._weather_df", _empty_df)
    monkeypatch.setattr("src.api.app.list_datasets", lambda: {})
    monkeypatch.setattr("src.api.app.registry",
                        ClimateModelRegistry(model_dir=tmp_path / "models"))
    # Backups created by API tests land in tmp, never the repo's backups/
    monkeypatch.setattr("src.utils.backup.BACKUP_DIR", tmp_path / "backups")

    # Start every test with a clean brute-force lockout slate
    auth.clear_failures()

    from src.api.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        auth.seed_default_users()
        yield c
    auth.clear_failures()


def _empty_df():
    import pandas as pd
    return pd.DataFrame()


@pytest.fixture()
def auth_headers(client):
    """Authorization header for the seeded admin account."""
    res = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin@123"})
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['token']}"}


@pytest.fixture()
def analyst_headers(client):
    """Authorization header for the seeded analyst account."""
    res = client.post("/api/auth/login",
                      json={"username": "analyst", "password": "analyst@123"})
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['token']}"}
