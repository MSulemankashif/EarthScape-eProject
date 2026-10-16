"""
Authentication & authorization
==============================
Implements the "User Authentication and Authorization" functional requirement:

  * secure password storage (PBKDF2-SHA256 via werkzeug, salted per user)
  * two roles:  admin   -> full access incl. user management & rule editing
                analyst -> read/write analytics, no admin functions
  * token-based sessions (signed, expiring) so the React SPA can call the
    REST API statelessly
  * role guard decorator for Flask endpoints

Seed accounts (created on first run):
  admin   / admin@123   (role: admin)
  analyst / analyst@123 (role: analyst)
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from src.config import SECRET_KEY, SESSION_LIFETIME_HOURS
from src.db import get_db
from src.utils.logger import get_logger

log = get_logger("earthscape.auth")

COLLECTION = "users"
ROLES = ("admin", "analyst")
TOKEN_SALT = "earthscape-auth"

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt=TOKEN_SALT)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
def create_user(username: str, email: str, password: str,
                role: str = "analyst") -> dict:
    """Register a new user. Raises ValueError on validation failure."""
    username = (username or "").strip().lower()
    email = (email or "").strip().lower()
    if not username or not email:
        raise ValueError("Username and email are required.")
    if role not in ROLES:
        raise ValueError(f"Role must be one of {ROLES}.")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    db = get_db()
    if db.find_one(COLLECTION, {"username": username}):
        raise ValueError(f"Username '{username}' already exists.")

    user = {
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": role,
        "active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "last_login": None,
    }
    db.insert(COLLECTION, user)
    log.info("User created: %s (%s)", username, role)
    return {"username": username, "email": email, "role": role}


def authenticate(username: str, password: str) -> dict | None:
    """
    Verify credentials; returns the user dict (sans hash) or None.

    Brute-force protection: after MAX_LOGIN_ATTEMPTS consecutive failures
    for one username, further attempts are rejected for LOCKOUT_SECONDS
    even if the password is correct (security requirement).
    """
    username = (username or "").strip().lower()

    # --- lockout check ---------------------------------------------------
    attempt = _failed_attempts.get(username)
    if attempt and attempt["until"] > time.time():
        remaining = int(attempt["until"] - time.time())
        log.warning("Locked-out account accessed: %s (%ss left)", username, remaining)
        return None

    db = get_db()
    user = db.find_one(COLLECTION, {"username": username})
    if not user or not user.get("active", True):
        return None
    if not check_password_hash(user.get("password_hash", ""), password or ""):
        _record_failure(username)
        return None

    # Success: clear the failure counter
    _failed_attempts.pop(username, None)
    db.update(COLLECTION, {"username": user["username"]},
              {"last_login": datetime.now().isoformat(timespec="seconds")})
    return {k: v for k, v in user.items() if k != "password_hash"}


# In-memory failed-attempt tracker: {username: {count, until, last}}
_failed_attempts: dict[str, dict] = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
FAIL_WINDOW_SECONDS = 900        # strikes older than 15 min stop counting


def _record_failure(username: str) -> None:
    """Count one failed login; lock the account after MAX_LOGIN_ATTEMPTS."""
    now = time.time()
    attempt = _failed_attempts.get(username)
    if attempt is None:
        attempt = {"count": 0, "until": 0.0, "last": 0.0}
    elif attempt.get("until", 0.0) > 0 and attempt["until"] < now:
        # A previous lockout has expired — start a fresh window
        attempt = {"count": 0, "until": 0.0, "last": 0.0}
    elif now - attempt.get("last", 0.0) > FAIL_WINDOW_SECONDS:
        # Too long since the last failure — old strikes no longer count
        attempt = {"count": 0, "until": 0.0, "last": 0.0}
    attempt["count"] += 1
    attempt["last"] = now
    if attempt["count"] >= MAX_LOGIN_ATTEMPTS:
        attempt["until"] = now + LOCKOUT_SECONDS
        log.warning("Account locked for %ss after %d failed logins: %s",
                    LOCKOUT_SECONDS, attempt["count"], username)
    _failed_attempts[username] = attempt


def clear_failures(username: str | None = None) -> None:
    """Testing helper: reset lockout state."""
    if username is None:
        _failed_attempts.clear()
    else:
        _failed_attempts.pop(username, None)


def lockout_status(username: str) -> dict:
    """How many failures remain before lockout (surfaced by the API)."""
    attempt = _failed_attempts.get(username or "", {"count": 0, "until": 0.0})
    remaining_time = max(0.0, attempt["until"] - time.time())
    return {
        "failed_count": attempt["count"],
        "locked": remaining_time > 0,
        "locked_for_seconds": int(remaining_time),
        "attempts_before_lockout": max(0, MAX_LOGIN_ATTEMPTS - attempt["count"]),
    }


def list_users() -> list[dict]:
    db = get_db()
    users = db.find(COLLECTION, limit=500)
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in users]


def change_role(username: str, role: str) -> bool:
    if role not in ROLES:
        return False
    return get_db().update(COLLECTION, {"username": username}, {"role": role}) > 0


def deactivate_user(username: str) -> bool:
    return get_db().update(COLLECTION, {"username": username},
                           {"active": False}) > 0


def seed_default_users() -> None:
    """Create the demo admin/analyst accounts if missing."""
    db = get_db()
    if not db.find_one(COLLECTION, {"username": "admin"}):
        create_user("admin", "admin@earthscape.agency", "admin@123", "admin")
        log.info("Seeded default admin account (admin / admin@123)")
    if not db.find_one(COLLECTION, {"username": "analyst"}):
        create_user("analyst", "analyst@earthscape.agency", "analyst@123", "analyst")
        log.info("Seeded default analyst account (analyst / analyst@123)")


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def issue_token(user: dict) -> str:
    """Signed token carrying identity + role, valid for the configured window."""
    return _serializer.dumps({
        "username": user["username"],
        "role": user["role"],
        "issued_at": datetime.now().isoformat(timespec="seconds"),
    })


def verify_token(token: str) -> dict | None:
    """Decode a token; returns payload or None when invalid/expired."""
    if not token:
        return None
    try:
        return _serializer.loads(
            token, max_age=SESSION_LIFETIME_HOURS * 3600)
    except BadSignature:
        return None


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    # Fallback: query param (handy for charts/images in the browser)
    return request.args.get("token")


# ---------------------------------------------------------------------------
# Flask guards
# ---------------------------------------------------------------------------
def current_user() -> dict | None:
    """Resolve the authenticated user for the current request (or None)."""
    return verify_token(_extract_token())


def login_required(view):
    """Decorator: reject anonymous requests with 401."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Authentication required.",
                            "code": "unauthenticated"}), 401
        request.user = user          # type: ignore[attr-defined]
        return view(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """Decorator factory: require one of the given roles (else 403)."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Authentication required.",
                                "code": "unauthenticated"}), 401
            if user.get("role") not in roles:
                return jsonify({
                    "error": f"Role '{user.get('role')}' may not access this "
                             f"resource (needs {', '.join(roles)}).",
                    "code": "forbidden",
                }), 403
            request.user = user      # type: ignore[attr-defined]
            return view(*args, **kwargs)
        return wrapper
    return decorator


admin_required = role_required("admin")


def random_password(length: int = 12) -> str:
    """Helper for generating strong demo passwords."""
    return secrets.token_urlsafe(length)
