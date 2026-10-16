"""Tests for the database layer, authentication and role guards."""

import pytest

from src import auth, db
from src.db import JsonBackend


@pytest.fixture()
def backend(tmp_path, monkeypatch):
    """Fresh JSON backend per test, isolated from the real data folder."""
    b = JsonBackend(tmp_path / "db")
    monkeypatch.setattr(db, "_backend", b)
    return b


# ---------------------------------------------------------------------------
# JSON backend
# ---------------------------------------------------------------------------
def test_insert_and_find(backend):
    backend.insert("things", {"name": "a", "n": 1})
    backend.insert("things", {"name": "b", "n": 2})

    assert backend.count("things") == 2
    assert backend.find_one("things", {"name": "b"})["n"] == 2
    assert backend.find("things", {"n": {"$gt": 1}})[0]["name"] == "b"


def test_update_and_delete(backend):
    backend.insert("things", {"name": "a", "v": 1})
    changed = backend.update("things", {"name": "a"}, {"v": 99})
    assert changed == 1
    assert backend.find_one("things", {"name": "a"})["v"] == 99

    removed = backend.delete("things", {"name": "a"})
    assert removed == 1
    assert backend.count("things") == 0


def test_find_sort_and_limit(backend):
    for i in range(5):
        backend.insert("logs", {"ts": f"2024-01-0{i}", "i": i})
    newest = backend.find("logs", limit=2, sort="ts")
    assert [d["i"] for d in newest] == [4, 3]


def test_corrupt_file_recovers(tmp_path):
    b = JsonBackend(tmp_path / "db")
    coll = tmp_path / "db" / "broken.json"
    coll.parent.mkdir(parents=True, exist_ok=True)
    coll.write_text("{not valid json", encoding="utf-8")
    assert b.find("broken") == []          # no crash
    b.insert("broken", {"ok": True})
    assert b.count("broken") == 1


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def test_create_and_authenticate(backend):
    auth.seed_default_users()

    user = auth.authenticate("admin", "admin@123")
    assert user is not None
    assert user["role"] == "admin"
    assert "password_hash" not in user


def test_wrong_password_rejected(backend):
    auth.seed_default_users()
    assert auth.authenticate("admin", "wrong-password") is None
    assert auth.authenticate("nobody", "x") is None


def test_duplicate_username_rejected(backend):
    auth.seed_default_users()
    with pytest.raises(ValueError):
        auth.create_user("admin", "other@x.com", "secret123")


def test_weak_password_rejected(backend):
    with pytest.raises(ValueError):
        auth.create_user("newbie", "n@x.com", "123")


def test_role_validation(backend):
    with pytest.raises(ValueError):
        auth.create_user("u", "u@x.com", "secret1", role="superuser")


def test_token_roundtrip(backend):
    auth.seed_default_users()
    user = auth.authenticate("analyst", "analyst@123")
    token = auth.issue_token(user)

    payload = auth.verify_token(token)
    assert payload is not None
    assert payload["username"] == "analyst"
    assert payload["role"] == "analyst"


def test_tampered_token_rejected():
    assert auth.verify_token("garbage.token.here") is None
    assert auth.verify_token("") is None


def test_list_users_hides_hash(backend):
    auth.seed_default_users()
    users = auth.list_users()
    assert len(users) >= 2
    assert all("password_hash" not in u for u in users)


def test_change_role(backend):
    auth.seed_default_users()
    assert auth.change_role("analyst", "admin")
    assert auth.authenticate("analyst", "analyst@123")["role"] == "admin"
    assert not auth.change_role("ghost", "admin")


# ---------------------------------------------------------------------------
# Flask guards (unit level, no server needed)
# ---------------------------------------------------------------------------
def test_role_required_allows_matching_role(monkeypatch):
    from flask import Flask

    from src.auth import role_required

    app = Flask(__name__)
    with app.test_request_context():
        monkeypatch.setattr(auth, "current_user",
                            lambda: {"username": "a", "role": "admin"})

        @role_required("admin")
        def view():
            return {"ok": True}

        result = view()
        # Allowed: the view's own return value comes back untouched
        assert result == {"ok": True}


def test_role_required_rejects_other_role(monkeypatch):
    from flask import Flask

    from src.auth import role_required

    app = Flask(__name__)
    with app.test_request_context():
        monkeypatch.setattr(auth, "current_user",
                            lambda: {"username": "a", "role": "analyst"})

        @role_required("admin")
        def view():
            return {"ok": True}

        response, status = view()
        assert status == 403


def test_login_required_rejects_anonymous(monkeypatch):
    from flask import Flask

    from src.auth import login_required

    app = Flask(__name__)
    with app.test_request_context():
        monkeypatch.setattr(auth, "current_user", lambda: None)

        @login_required
        def view():
            return {"ok": True}

        response, status = view()
        assert status == 401
