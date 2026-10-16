"""
Automated data backup
=====================
Implements the "Data Backup" non-functional requirement:

    "Regular automated data backups must be performed to prevent data loss
     in case of system failures."

What is backed up
-----------------
Everything that cannot be regenerated quickly or at all:
    * data/db/         - users, alerts, feedback tickets (Mongo/JSON store)
    * data/models/     - trained ML models (joblib)
    * data/processed/  - MapReduce outputs + dataset catalog
    * data/raw/        - source test datasets
    * logs/            - application logs

What is *not* backed up (regenerable): data/hdfs_sim/ — rebuilt by
`python -m src.ingestion.pipeline`, so it would only bloat the archives.

Usage
-----
    python -m src.utils.backup              # create one backup now
    python -m src.utils.backup --list       # list available backups
    python -m src.utils.backup --prune 10   # keep only the newest 10

Retention: the newest RETENTION_COUNT backups are kept; older ones are
pruned automatically (default 14). Point-in-time restores are done by
unzipping an archive over the project root.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from src.config import BASE_DIR, LOGS_DIR, MODELS_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.utils.logger import get_logger

log = get_logger("earthscape.backup")

BACKUP_DIR = BASE_DIR / "backups"
RETENTION_COUNT = 14

# Relative to the project root; missing entries are simply skipped
BACKUP_TARGETS = [
    "data/db",
    "data/models",
    "data/processed",
    "data/raw",
    "logs",
]


def _targets() -> list[Path]:
    return [BASE_DIR / rel for rel in BACKUP_TARGETS if (BASE_DIR / rel).exists()]


def create_backup(label: str = "") -> dict:
    """Zip every backup target into backups/earthscape_YYYYmmdd_HHMMSS.zip"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(c for c in label if c.isalnum() or c in "-_")[:30]
    name = f"earthscape_{stamp}{('_' + safe_label) if safe_label else ''}.zip"
    archive = BACKUP_DIR / name

    files = 0
    total_bytes = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for target in _targets():
            for path in target.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix == ".tmp":        # in-flight writes
                    continue
                arcname = path.relative_to(BASE_DIR).as_posix()
                zf.write(path, arcname)
                files += 1
                total_bytes += path.stat().st_size

    size = archive.stat().st_size
    log.info("Backup created: %s (%d files, %.1f KB -> %.1f KB compressed)",
             name, files, total_bytes / 1024, size / 1024)

    # Auto-prune so backups never fill the disk
    pruned = prune(RETENTION_COUNT)

    return {
        "file": name,
        "path": str(archive),
        "files": files,
        "size_bytes": size,
        "uncompressed_bytes": total_bytes,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pruned": pruned,
    }


def list_backups() -> list[dict]:
    """Newest-first inventory of available archives."""
    if not BACKUP_DIR.exists():
        return []
    items = []
    for path in sorted(BACKUP_DIR.glob("earthscape_*.zip"), reverse=True):
        stat = path.stat()
        items.append({
            "file": path.name,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime)
                                .isoformat(timespec="seconds"),
        })
    return items


def prune(keep: int = RETENTION_COUNT) -> int:
    """Delete all but the newest `keep` archives. Returns count removed."""
    if not BACKUP_DIR.exists():
        return 0
    archives = sorted(BACKUP_DIR.glob("earthscape_*.zip"), reverse=True)
    removed = 0
    for path in archives[keep:]:
        try:
            path.unlink()
            removed += 1
        except OSError as exc:                      # pragma: no cover
            log.warning("Could not prune %s: %s", path.name, exc)
    if removed:
        log.info("Pruned %d old backup(s), kept newest %d", removed, keep)
    return removed


def latest_backup() -> dict | None:
    items = list_backups()
    return items[0] if items else None


def verify_backup(name: str) -> dict:
    """Open the archive and confirm it is readable (integrity check)."""
    archive = BACKUP_DIR / name
    if not archive.exists():
        raise FileNotFoundError(f"Backup not found: {name}")
    with zipfile.ZipFile(archive, "r") as zf:
        bad = zf.testzip()          # returns first corrupt member or None
        count = len(zf.namelist())
    if bad:
        raise IOError(f"Corrupt member in {name}: {bad}")
    log.info("Backup %s verified OK (%d members)", name, count)
    return {"file": name, "members": count, "valid": True}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        result = create_backup("manual")
        print(json.dumps(result, indent=2))
        return 0
    if argv[0] == "--list":
        print(json.dumps(list_backups(), indent=2))
        return 0
    if argv[0] == "--prune":
        keep = int(argv[1]) if len(argv) > 1 else RETENTION_COUNT
        print(f"Pruned {prune(keep)} backup(s), keeping {keep}")
        return 0
    if argv[0] == "--verify" and len(argv) > 1:
        print(json.dumps(verify_backup(argv[1]), indent=2))
        return 0
    print("Usage: python -m src.utils.backup [--list | --prune N | --verify FILE]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
