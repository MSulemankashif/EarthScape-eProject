"""
Database layer for EarthScape Climate Agency
============================================
Provides a SINGLE interface over two interchangeable backends:

  * MongoBackend  - used when EARTHSCAPE_MONGO_URI points to a live MongoDB
                    (matches the spec's "MongoDB Compass and Shell" tool)
  * JsonBackend   - zero-dependency fallback that stores collections as JSON
                    files under data/db/ so the eProject always runs

Collections managed:
  users     - authentication accounts with roles (admin / analyst)
  alerts    - notifications produced by the alert engine
  feedback  - support tickets and user feedback
  readings  - live sensor readings (recent window for fast dashboard loads)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DATA_DIR, MONGO_URI
from src.utils.logger import get_logger

log = get_logger("earthscape.db")

DB_DIR = DATA_DIR / "db"


class BaseBackend:
    """Minimal document-store contract used by the application."""

    name = "base"

    def insert(self, collection: str, doc: dict) -> str:      raise NotImplementedError
    def find(self, collection: str, query: dict | None = None,
             limit: int = 100, sort: str | None = None) -> list[dict]:  raise NotImplementedError
    def find_one(self, collection: str, query: dict) -> dict | None:    raise NotImplementedError
    def update(self, collection: str, query: dict, updates: dict) -> int: raise NotImplementedError
    def delete(self, collection: str, query: dict) -> int:    raise NotImplementedError
    def count(self, collection: str, query: dict | None = None) -> int: raise NotImplementedError


# ---------------------------------------------------------------------------
# JSON file backend (default fallback - works everywhere)
# ---------------------------------------------------------------------------
class JsonBackend(BaseBackend):
    """Collections stored as <data/db>/<collection>.json (list of dicts)."""

    name = "json"

    def __init__(self, root: Path = DB_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0

    def _path(self, collection: str) -> Path:
        safe = "".join(c for c in collection if c.isalnum() or c in "_-")
        return self.root / f"{safe}.json"

    def _read(self, collection: str) -> list[dict]:
        path = self._path(collection)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Corrupt collection %s - starting fresh", collection)
            return []

    def _write(self, collection: str, docs: list[dict]) -> None:
        path = self._path(collection)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(docs, indent=2, default=str),
                       encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, expected in (query or {}).items():
            actual = doc.get(key)
            if isinstance(expected, dict):          # supports $in / $gt / $lt
                for op, val in expected.items():
                    if op == "$in" and actual not in val:
                        return False
                    if op == "$gt" and not (actual is not None and actual > val):
                        return False
                    if op == "$lt" and not (actual is not None and actual < val):
                        return False
                    if op == "$ne" and actual == val:
                        return False
            elif actual != expected:
                return False
        return True

    def insert(self, collection: str, doc: dict) -> str:
        with self._lock:
            docs = self._read(collection)
            self._seq += 1
            doc = dict(doc)
            doc.setdefault("_id", f"{collection}-{len(docs) + 1}-{self._seq}")
            docs.append(doc)
            self._write(collection, docs)
            return doc["_id"]

    def find(self, collection: str, query: dict | None = None,
             limit: int = 100, sort: str | None = None) -> list[dict]:
        with self._lock:
            docs = [d for d in self._read(collection) if self._matches(d, query)]
        if sort:
            docs.sort(key=lambda d: d.get(sort) or "", reverse=True)
        return docs[:limit]

    def find_one(self, collection: str, query: dict) -> dict | None:
        docs = self.find(collection, query, limit=1)
        return docs[0] if docs else None

    def update(self, collection: str, query: dict, updates: dict) -> int:
        with self._lock:
            docs = self._read(collection)
            changed = 0
            for doc in docs:
                if self._matches(doc, query):
                    doc.update(updates)
                    changed += 1
            if changed:
                self._write(collection, docs)
            return changed

    def delete(self, collection: str, query: dict) -> int:
        with self._lock:
            docs = self._read(collection)
            keep = [d for d in docs if not self._matches(d, query)]
            removed = len(docs) - len(keep)
            if removed:
                self._write(collection, keep)
            return removed

    def count(self, collection: str, query: dict | None = None) -> int:
        with self._lock:
            docs = self._read(collection)
        if not query:
            return len(docs)
        return sum(1 for d in docs if self._matches(d, query))


# ---------------------------------------------------------------------------
# MongoDB backend (used when a real MongoDB is reachable)
# ---------------------------------------------------------------------------
class MongoBackend(BaseBackend):
    name = "mongodb"

    def __init__(self, uri: str = MONGO_URI, db_name: str = "earthscape"):
        from pymongo import MongoClient          # imported lazily

        self.client = MongoClient(uri, serverSelectionTimeoutMS=2500)
        self.client.admin.command("ping")        # fail fast if unreachable
        self.db = self.client[db_name]
        log.info("Connected to MongoDB %s (db=%s)", uri, db_name)

    def insert(self, collection: str, doc: dict) -> str:
        doc = dict(doc)
        doc.pop("_id", None)
        result = self.db[collection].insert_one(doc)
        return str(result.inserted_id)

    def find(self, collection: str, query: dict | None = None,
             limit: int = 100, sort: str | None = None) -> list[dict]:
        cursor = self.db[collection].find(query or {})
        if sort:
            cursor = cursor.sort(sort, -1)
        return list(cursor.limit(limit))

    def find_one(self, collection: str, query: dict) -> dict | None:
        return self.db[collection].find_one(query)

    def update(self, collection: str, query: dict, updates: dict) -> int:
        result = self.db[collection].update_many(query, {"$set": updates})
        return result.modified_count

    def delete(self, collection: str, query: dict) -> int:
        result = self.db[collection].delete_many(query)
        return result.deleted_count

    def count(self, collection: str, query: dict | None = None) -> int:
        return self.db[collection].count_documents(query or {})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_backend: BaseBackend | None = None


def get_db() -> BaseBackend:
    """Return the configured backend, trying MongoDB first when requested."""
    global _backend
    if _backend is not None:
        return _backend

    if MONGO_URI:
        try:
            _backend = MongoBackend(MONGO_URI)
            return _backend
        except Exception as exc:
            log.warning("MongoDB unavailable (%s); using JSON fallback.", exc)

    _backend = JsonBackend()
    log.info("Database backend: JSON store at %s", _backend.root)
    return _backend


def reset_backend() -> None:
    """Testing helper: drop the cached backend instance."""
    global _backend
    _backend = None
