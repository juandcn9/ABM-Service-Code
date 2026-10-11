"""Structured events: one JSON line per event, allowlisted fields, bounded labels (SEC-09, TEST-29; DEC-0062).

Nothing reaches the stream except the fields below. Identifiers leave only as one-way tokens.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TextIO

# Every field an event may carry. Anything else is refused before it is written.
ALLOWED_FIELDS = frozenset(
    {
        "event",
        "correlation_id",
        "operation",
        "status",
        "result_code",
        "duration_ms",
        "caller_role",
        "caller_token",
        "decision",
        "account_token",
        "item_token",
        "state",
        "age_hours",
        "threshold_hours",
        "count",
    }
)
# Bounded label sets: a label outside its set is refused, so cardinality cannot grow.
BOUNDED_LABELS: dict[str, frozenset[str]] = {
    "event": frozenset({"request", "read", "aged_item", "scan_summary"}),
    "decision": frozenset({"permitted", "rejected", "failed"}),
    "caller_role": frozenset(
        {
            "account_registrar",
            "payment_orchestrator",
            "card_orchestrator",
            "risk_controller",
            "correction_authority",
            "account_reader",
            "reconciliation_reader",
            "none",
        }
    ),
}
_TOKEN_SALT = b"abm-token-v1"


def token(value: str) -> str:
    """A one-way token for an identifier. Stable across runs so that events can be attributed.

    shortcut: fixed salt shared by every deployment, so a small identifier space can be brute-forced
    by someone holding the logs; upgrade to a deployment secret when a secret store exists (TASK-27).
    """
    return hashlib.sha256(_TOKEN_SALT + value.encode("utf-8")).hexdigest()[:16]


class EventSink:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def emit(self, **fields: Any) -> None:
        unknown = set(fields) - ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"event field(s) not allowed: {sorted(unknown)}")
        for name, allowed in BOUNDED_LABELS.items():
            if name in fields and fields[name] not in allowed:
                raise ValueError(f"label {name} outside its bounded set")
        self._stream.write(json.dumps(fields, sort_keys=True) + "\n")
        self._stream.flush()
