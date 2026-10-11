"""Read-only query for aged pending items (TEST-39, BT-07; DEC-0061, DEC-0063)."""

from __future__ import annotations

import sqlite3

# Non-terminal states: money or a hold is still open, so elapsed time alone changes nothing.
PENDING_STATES = ("pending", "accepted_with_hold", "submitted", "authorized_with_hold")
PENDING_TYPES = ("incoming_ach", "outgoing_ach", "card")


def aged_pending(
    conn: sqlite3.Connection, cutoff: str
) -> list[tuple[str, str, str, str]]:
    """(movement_id, account_id, state, created_at) for pending items created at or before cutoff.

    cutoff is an ISO UTC instant (YYYY-MM-DDTHH:MM:SSZ), the same format as created_at.
    """
    states = ",".join("?" * len(PENDING_STATES))
    types = ",".join("?" * len(PENDING_TYPES))
    return conn.execute(
        f"SELECT movement_id, account_id, state, created_at FROM movements "
        f"WHERE state IN ({states}) AND movement_type IN ({types}) AND created_at <= ? "
        f"ORDER BY created_at, movement_id",
        (*PENDING_STATES, *PENDING_TYPES, cutoff),
    ).fetchall()
