"""Aged pending items: the TEST-39 escalation scan and the TASK-26 evidence manifest (DEC-0061 to DEC-0064).

Usage (from the repository root):
  python scripts/scan_aged_items.py DB_PATH --older-than-hours HOURS [--manifest PATH]
      --spec-version VERSION --spec-commit SHA --code-commit SHA

The threshold is required (DEC-0061). The database is opened read-only, so the scan cannot post,
release a hold, or change state (BT-07, INV-12). Each aged item and a summary are written as JSON
lines on stdout (DEC-0062). The manifest, when requested, records the exact revisions and the scan
result (DEC-0064).
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abm.observability.events import EventSink, token
from abm.persistence.aged import aged_pending
from abm.persistence.migrations import load_migrations

_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def run_scan(
    conn: sqlite3.Connection, sink: EventSink, now: datetime, threshold_hours: float
) -> int:
    """Emit one aged_item event per aged pending item, then a summary. Returns the item count."""
    cutoff = (now - timedelta(hours=threshold_hours)).strftime(_FORMAT)
    rows = aged_pending(conn, cutoff)
    for movement_id, account_id, state, created_at in rows:
        created = datetime.strptime(created_at, _FORMAT).replace(tzinfo=UTC)
        sink.emit(
            event="aged_item",
            item_token=token(movement_id),
            account_token=token(account_id),
            state=state,
            age_hours=round((now - created).total_seconds() / 3600, 3),
            threshold_hours=threshold_hours,
        )
    sink.emit(event="scan_summary", count=len(rows), threshold_hours=threshold_hours)
    return len(rows)


def build_manifest(
    migrations: list[dict[str, Any]],
    spec_version: str,
    spec_commit: str,
    code_commit: str,
    generated_at: str,
    count: int,
    threshold_hours: float,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "spec_version": spec_version,
        "spec_commit": spec_commit,
        "code_commit": code_commit,
        "migrations": migrations,
        "aged_scan": {"threshold_hours": threshold_hours, "count": count},
    }


def _hours(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a positive, finite number of hours")
    return value


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("database", type=pathlib.Path)
    parser.add_argument("--older-than-hours", type=_hours, required=True)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--spec-version", default="")
    parser.add_argument("--spec-commit", default="")
    parser.add_argument("--code-commit", default="")
    args = parser.parse_args(argv)
    if args.manifest is not None and not (
        args.spec_version and args.spec_commit and args.code_commit
    ):
        parser.error("--manifest needs --spec-version, --spec-commit and --code-commit")

    now = datetime.now(UTC)
    conn = sqlite3.connect(f"file:{args.database.as_posix()}?mode=ro", uri=True)
    try:
        count = run_scan(conn, EventSink(sys.stdout), now, args.older_than_hours)
    finally:
        conn.close()

    if args.manifest is not None:
        migrations = [
            {"version": m.version, "name": m.name, "checksum": m.checksum}
            for m in load_migrations(ROOT / "migrations")
        ]
        manifest = build_manifest(
            migrations,
            args.spec_version,
            args.spec_commit,
            args.code_commit,
            now.strftime(_FORMAT),
            count,
            args.older_than_hours,
        )
        args.manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
