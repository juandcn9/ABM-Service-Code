"""Startup and fail-closed readiness (INV-18, NFR-02, SEC-10; specs/05-data-model.md section 7, specs/07 sections 3 and 4).

Every check is read-only. A problem is reported as a controlled reason code, never repaired,
and never with paths, SQL text, counts, row data, or raw check output.
"""

from __future__ import annotations

import functools
import pathlib
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from abm.persistence.database import (
    DEFAULT_BUSY_TIMEOUT_MS,
    DatabaseUnavailable,
    open_database,
    to_failure,
)
from abm.persistence.migrations import (
    Migration,
    MigrationError,
    apply_migrations,
    retained_history_protected,
)

# the controlled reason codes of the HealthResponse schema
CONFIG_INVALID = "CONFIG_INVALID"
DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"
INTEGRITY_FAILED = "INTEGRITY_FAILED"
FOREIGN_KEY_FAILED = "FOREIGN_KEY_FAILED"
DATABASE_BUSY = "DATABASE_BUSY"

# Each statement returns a row exactly when the stored data is inconsistent (specs/05 section 7).
_INCONSISTENCIES: tuple[str, ...] = (
    # every account projection equals the signed sum of its ledger entries
    (
        "SELECT 1 FROM accounts a WHERE a.current_balance_cents <> COALESCE((SELECT SUM(CASE l.direction"
        " WHEN 'credit' THEN l.amount_cents ELSE -l.amount_cents END) FROM ledger_entries l"
        " WHERE l.account_id = a.account_id), 0) LIMIT 1"
    ),
    # an active hold exists only for an outgoing ACH accepted or submitted, or an authorized card
    (
        "SELECT 1 FROM holds h JOIN movements m ON m.movement_id = h.movement_id WHERE h.state = 'active'"
        " AND NOT ((m.movement_type = 'outgoing_ach' AND m.state IN ('accepted_with_hold', 'submitted'))"
        " OR (m.movement_type = 'card' AND m.state = 'authorized_with_hold')) LIMIT 1"
    ),
    # ... and every such movement has its active hold
    (
        "SELECT 1 FROM movements m WHERE ((m.movement_type = 'outgoing_ach'"
        " AND m.state IN ('accepted_with_hold', 'submitted'))"
        " OR (m.movement_type = 'card' AND m.state = 'authorized_with_hold'))"
        " AND NOT EXISTS (SELECT 1 FROM holds h WHERE h.movement_id = m.movement_id"
        " AND h.state = 'active') LIMIT 1"
    ),
    # a hold reserves funds of its own movement's account
    (
        "SELECT 1 FROM holds h JOIN movements m ON m.movement_id = h.movement_id"
        " WHERE h.account_id <> m.account_id LIMIT 1"
    ),
    # a closed account has no active hold
    (
        "SELECT 1 FROM holds h JOIN accounts a ON a.account_id = h.account_id"
        " WHERE a.status = 'closed' AND h.state = 'active' LIMIT 1"
    ),
    # after closure only permitted late evidence is posted (INV-16). shortcut: same-second
    # effects are not ordered against closed_at; upgrade by storing a ledger sequence at closure
    (
        "SELECT 1 FROM ledger_entries e JOIN accounts a ON a.account_id = e.account_id"
        " LEFT JOIN movements m ON m.movement_id = e.movement_id"
        " WHERE a.status = 'closed' AND e.created_at > a.closed_at AND (e.effect_kind IN"
        " ('incoming_settlement','outgoing_settlement','transfer_source_debit',"
        "'transfer_destination_credit') OR (e.effect_kind = 'card_clearing'"
        " AND m.state NOT IN ('late_cleared','refunded'))) LIMIT 1"
    ),
    # a transfer's source debits equal its destination credits
    (
        "SELECT 1 FROM movements m WHERE m.movement_type = 'internal_transfer'"
        " AND COALESCE((SELECT SUM(amount_cents) FROM ledger_entries"
        " WHERE movement_id = m.movement_id AND effect_kind = 'transfer_source_debit'), 0)"
        " <> COALESCE((SELECT SUM(amount_cents) FROM ledger_entries"
        " WHERE movement_id = m.movement_id AND effect_kind = 'transfer_destination_credit'), 0) LIMIT 1"
    ),
    # every account has its registration trace and its retention row
    (
        "SELECT 1 FROM accounts a WHERE NOT EXISTS (SELECT 1 FROM audit_trace t"
        " WHERE t.account_id = a.account_id AND t.operation = 'register_account') LIMIT 1"
    ),
    (
        "SELECT 1 FROM accounts a WHERE NOT EXISTS (SELECT 1 FROM retention_metadata r"
        " WHERE r.account_id = a.account_id) LIMIT 1"
    ),
    # every accepted trace has its committed successful idempotency outcome
    (
        "SELECT 1 FROM audit_trace t WHERE NOT EXISTS (SELECT 1 FROM idempotency_outcomes i"
        " WHERE i.instruction_id = t.instruction_id AND i.outcome_class = 'success') LIMIT 1"
    ),
)

# stored idempotency outcomes must hold valid JSON (specs/05 s7); json_valid never raises
_INVALID_JSON = (
    "SELECT 1 FROM idempotency_outcomes WHERE NOT json_valid(response_json) LIMIT 1"
)


def readiness_reasons(
    conn: sqlite3.Connection, migrations: Sequence[Migration]
) -> list[str]:
    """Sorted reason codes; an empty list means ready. Never writes, never repairs."""
    reasons: set[str] = set()
    try:
        if not _schema_supported(conn, migrations):
            # nothing else can be trusted on an unknown or missing schema
            return [SCHEMA_UNSUPPORTED]
        if _objects(conn) != _shipped_objects(tuple(migrations)):
            # a table, index or trigger is missing or extra: the data checks cannot be trusted
            return [INTEGRITY_FAILED]
        if conn.execute(_INVALID_JSON).fetchone() is not None:
            # integrity_check raises on malformed stored JSON, so it is not run in that case
            reasons.add(INTEGRITY_FAILED)
        elif conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            reasons.add(INTEGRITY_FAILED)
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            reasons.add(FOREIGN_KEY_FAILED)
        if any(conn.execute(sql).fetchone() is not None for sql in _INCONSISTENCIES):
            reasons.add(INTEGRITY_FAILED)
        if not retained_history_protected(conn):
            reasons.add(
                INTEGRITY_FAILED
            )  # a retained table or guard trigger was altered outside the runner
        if not _can_begin_write(conn):
            reasons.add(DATABASE_BUSY)
    except sqlite3.Error as exc:
        failure = to_failure(exc)
        if failure.error.code == "SERVICE_BUSY":
            reasons.add(DATABASE_BUSY)
        elif failure.error.code == "SERVICE_UNREADY":
            reasons.add(INTEGRITY_FAILED)  # corrupt, unreadable, or full storage
        else:
            reasons.add(DATABASE_UNAVAILABLE)
    return sorted(reasons)


_SHAPE_APPLIED_AT = (
    "2000-01-01T00:00:00Z"  # any valid instant; only the object names matter here
)


def _objects(conn: sqlite3.Connection) -> frozenset[tuple[str, str]]:
    """Every named table, index, view and trigger, excluding SQLite's own sqlite_* objects."""
    return frozenset(
        conn.execute(
            "SELECT type, name FROM sqlite_master WHERE substr(name, 1, 7) <> 'sqlite_'"
        )
    )


@functools.lru_cache(maxsize=8)
def _shipped_objects(migrations: tuple[Migration, ...]) -> frozenset[tuple[str, str]]:
    """The objects the reviewed migrations create, built once in memory."""
    shipped = sqlite3.connect(":memory:", isolation_level=None)
    try:
        apply_migrations(shipped, migrations, _SHAPE_APPLIED_AT)
        return _objects(shipped)
    finally:
        shipped.close()


def _schema_supported(
    conn: sqlite3.Connection, migrations: Sequence[Migration]
) -> bool:
    has_history = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if has_history is None:
        return False
    applied = [
        (row[0], row[1], row[2])
        for row in conn.execute(
            "SELECT version, migration_name, checksum FROM schema_version ORDER BY version"
        )
    ]
    return applied == [(m.version, m.name, m.checksum) for m in migrations]


def _can_begin_write(conn: sqlite3.Connection) -> bool:
    """True if a write transaction can start within the busy timeout (specs/07 section 4)."""
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        if to_failure(exc).error.code == "SERVICE_BUSY":
            return False
        raise
    conn.execute("ROLLBACK")  # nothing was written; this only releases the lock
    return True


@dataclass(frozen=True)
class StartupResult:
    connection: sqlite3.Connection | None
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.connection is not None and not self.reasons


def start_database(
    path: str | pathlib.Path,
    migrations: Sequence[Migration],
    applied_at: str,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    check_same_thread: bool = True,
) -> StartupResult:
    """Open with the required settings, apply reviewed forward migrations, then run readiness.

    Ready only if every step passes. On any failure the result carries safe reason codes and
    no usable connection; a fully committed migration is the only financial-adjacent change.
    """
    try:
        conn = open_database(path, busy_timeout_ms, check_same_thread)
    except DatabaseUnavailable:
        return StartupResult(None, (DATABASE_UNAVAILABLE,))
    try:
        apply_migrations(conn, migrations, applied_at)
    except MigrationError as err:
        conn.close()
        busy = isinstance(err.__cause__, sqlite3.OperationalError) and (
            to_failure(err.__cause__).error.code == "SERVICE_BUSY"
        )
        if busy:
            return StartupResult(None, (DATABASE_BUSY,))
        if err.code == "MIGRATION_FAILED":
            return StartupResult(None, (DATABASE_UNAVAILABLE,))
        return StartupResult(None, (SCHEMA_UNSUPPORTED,))
    reasons = readiness_reasons(conn, migrations)
    if reasons:
        conn.close()
        return StartupResult(None, tuple(reasons))
    return StartupResult(conn, ())
