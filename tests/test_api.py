"""Integration tests for the Flask REST API (in-process test client)."""

import pytest

from src import auth, db
from src.db import JsonBackend


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client with an isolated JSON backend and temp HDFS."""
    from src.hadoop.storage import LocalHDFS

    monkeypatch.setattr(db, "_backend", JsonBackend(tmp_path / "db"))
    monkeypatch.setattr("src.api.app.get_storage",
                        lambda: LocalHDFS(tmp_path / "hdfs"))
    monkeypatch.setattr("src.api.app._weather_df",
                        lambda limit=None: empty_df())

    from src.api.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        auth.seed_default_users()
        yield c


def empty_df():
    import pandas as pd
    return pd.DataFrame()


def login(client, username="admin", password="admin@123"):
    res = client.post("/api/auth/login",
                      json={"username": username, "password": password})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["token"]


def authed(client, token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health(client):
    res = client.get("/api/health")
    body = res.get_json()
    assert res.status_code == 200
    assert body["status"] == "ok"
    assert body["storage_backend"] == "local-hdfs-sim"
    assert body["database_backend"] == "json"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_login_success_and_failure(client):
    assert client.post("/api/auth/login", json={
        "username": "admin", "password": "admin@123"}).status_code == 200

    res = client.post("/api/auth/login",
                      json={"username": "admin", "password": "bad"})
    assert res.status_code == 401
    assert "error" in res.get_json()


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    token = login(client)
    res = client.get("/api/auth/me", headers=authed(client, token))
    assert res.status_code == 200
    assert res.get_json()["user"]["role"] == "admin"


def test_register_and_duplicate(client):
    res = client.post("/api/auth/register", json={
        "username": "newuser", "email": "n@x.com", "password": "secret1"})
    assert res.status_code == 201

    res = client.post("/api/auth/register", json={
        "username": "newuser", "email": "n@x.com", "password": "secret1"})
    assert res.status_code == 400


def test_register_cannot_self_promote_to_admin(client):
    client.post("/api/auth/register", json={
        "username": "sneaky", "email": "s@x.com", "password": "secret1",
        "role": "admin"})
    token = login(client, "sneaky", "secret1")
    me = client.get("/api/auth/me", headers=authed(client, token))
    assert me.get_json()["user"]["role"] == "analyst", \
        "anonymous registration must not grant admin"


def test_users_endpoint_is_admin_only(client):
    analyst = login(client, "analyst", "analyst@123")
    assert client.get("/api/auth/users",
                      headers=authed(client, analyst)).status_code == 403
    admin = login(client)
    assert client.get("/api/auth/users",
                      headers=authed(client, admin)).status_code == 200


def test_role_change(client):
    admin = login(client)
    res = client.patch("/api/auth/users/analyst/role",
                       json={"role": "admin"}, headers=authed(client, admin))
    assert res.status_code == 200
    assert client.patch("/api/auth/users/ghost/role", json={"role": "admin"},
                        headers=authed(client, admin)).status_code == 404


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------
def test_datasets_empty_by_default(client):
    token = login(client)
    res = client.get("/api/data/datasets", headers=authed(client, token))
    assert res.status_code == 200
    assert res.get_json()["datasets"] == []


def test_readings_hint_when_empty(client):
    token = login(client)
    res = client.get("/api/data/readings", headers=authed(client, token))
    assert res.status_code == 200
    assert "hint" in res.get_json()


def test_ingest_with_no_raw_files(client):
    """Ingestion must fail gracefully with a 500 + message, not a traceback."""
    token = login(client)
    res = client.post("/api/data/ingest", headers=authed(client, token))
    assert res.status_code == 500
    assert "error" in res.get_json()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def test_jobs_list(client):
    token = login(client)
    res = client.get("/api/analytics/jobs", headers=authed(client, token))
    names = {j["name"] for j in res.get_json()["jobs"]}
    assert {"monthly_aggregation", "anomaly_detection"} <= names


def test_run_unknown_job_is_400(client):
    token = login(client)
    res = client.post("/api/analytics/jobs/run", json={"job": "nope"},
                      headers=authed(client, token))
    assert res.status_code == 400


def test_run_job_with_sample_csv(client, tmp_path):
    csv = tmp_path / "sample.csv"
    csv.write_text(
        "station_id,city,date,temperature_c,humidity_pct,rainfall_mm,"
        "co2_ppm,pm25,wind_speed_kph,sea_level_mm\n"
        "STN-001,K,2024-01-01,20,70,0,415,50,10,-4\n"
        "STN-001,K,2024-01-02,21,72,1,416,52,11,-4\n",
        encoding="utf-8")
    token = login(client)
    res = client.post("/api/analytics/jobs/run",
                      json={"job": "monthly_aggregation", "input": str(csv)},
                      headers=authed(client, token))
    body = res.get_json()
    assert res.status_code == 200
    assert body["rows"] > 0
    assert body["preview"]


def test_ml_status(client):
    token = login(client)
    res = client.get("/api/analytics/ml/status", headers=authed(client, token))
    assert res.status_code == 200
    assert "anomaly_model_trained" in res.get_json()


def test_forecast_without_model_is_404(client):
    token = login(client)
    res = client.get("/api/analytics/ml/forecast?metric=temperature_c",
                     headers=authed(client, token))
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
def test_alert_rules_visible_to_analyst(client):
    token = login(client, "analyst", "analyst@123")
    res = client.get("/api/alerts/rules", headers=authed(client, token))
    assert res.status_code == 200
    assert len(res.get_json()["rules"]) >= 10


def test_add_rule_admin_only(client):
    analyst = login(client, "analyst", "analyst@123")
    res = client.post("/api/alerts/rules",
                      json={"name": "r1", "metric": "co2_ppm",
                            "comparator": "gt", "threshold": 500},
                      headers=authed(client, analyst))
    assert res.status_code == 403

    admin = login(client)
    res = client.post("/api/alerts/rules",
                      json={"name": "r1", "metric": "co2_ppm",
                            "comparator": "gt", "threshold": 500},
                      headers=authed(client, admin))
    assert res.status_code == 201

    # Toggle + delete round trip
    assert client.post("/api/alerts/rules/r1/disable",
                       headers=authed(client, admin)).status_code == 200
    assert client.delete("/api/alerts/rules/r1",
                         headers=authed(client, admin)).status_code == 200
    assert client.delete("/api/alerts/rules/r1",
                         headers=authed(client, admin)).status_code == 404


def test_invalid_rule_is_400(client):
    admin = login(client)
    res = client.post("/api/alerts/rules", json={"name": "x"},
                      headers=authed(client, admin))
    assert res.status_code == 400


def test_alert_history(client):
    token = login(client)
    res = client.get("/api/alerts/history", headers=authed(client, token))
    assert res.status_code == 200
    assert "alerts" in res.get_json()


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------
def test_stream_latest_and_series(client):
    from src import streaming
    with streaming._LOCK:
        streaming._LATEST.clear()
    streaming.stream_once()

    token = login(client)
    res = client.get("/api/stream/latest?limit=5",
                     headers=authed(client, token))
    assert res.status_code == 200
    assert res.get_json()["count"] >= 1

    res = client.get("/api/stream/series?metric=temperature_c",
                     headers=authed(client, token))
    assert res.status_code == 200
    assert "values" in res.get_json()


def test_stream_control_admin_only(client):
    analyst = login(client, "analyst", "analyst@123")
    assert client.post("/api/stream/start",
                       headers=authed(client, analyst)).status_code == 403
    admin = login(client)
    assert client.post("/api/stream/start",
                       headers=authed(client, admin)).status_code == 200
    assert client.post("/api/stream/stop",
                       headers=authed(client, admin)).status_code == 200


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
def test_feedback_flow(client):
    token = login(client, "analyst", "analyst@123")

    res = client.post("/api/feedback",
                      json={"subject": "Help", "message": "It broke"},
                      headers=authed(client, token))
    assert res.status_code == 201

    res = client.get("/api/feedback", headers=authed(client, token))
    tickets = res.get_json()["tickets"]
    assert len(tickets) == 1
    assert tickets[0]["status"] == "open"

    ticket_id = tickets[0]["_id"]
    admin = login(client)
    res = client.patch(f"/api/feedback/{ticket_id}",
                       json={"status": "resolved"}, headers=authed(client, admin))
    assert res.status_code == 200

    res = client.get("/api/feedback", headers=authed(client, token))
    assert res.get_json()["tickets"][0]["status"] == "resolved"


def test_feedback_requires_message(client):
    token = login(client)
    res = client.post("/api/feedback", json={"message": "   "},
                      headers=authed(client, token))
    assert res.status_code == 400


def test_feedback_invalid_status_is_400(client):
    token = login(client, "analyst", "analyst@123")
    client.post("/api/feedback", json={"message": "hi"},
                headers=authed(client, token))
    admin = login(client)
    ticket = client.get("/api/feedback",
                        headers=authed(client, admin)).get_json()["tickets"][0]
    res = client.patch(f"/api/feedback/{ticket['_id']}",
                       json={"status": "weird"}, headers=authed(client, admin))
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
def test_system_stats_admin_visible(client):
    token = login(client)
    res = client.get("/api/system/stats", headers=authed(client, token))
    body = res.get_json()
    assert res.status_code == 200
    assert "uptime_seconds" in body
    assert "alerts" in body
    assert "models" in body
