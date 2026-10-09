"""Canonical request fingerprint for idempotency (INV-17, DEC-0011, specs/02-domain-and-invariants.md section 3)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from abm.domain.errors import InvalidValue
from abm.domain.identifiers import opaque_id


def fingerprint(operation: str, fields: Mapping[str, str | int | None]) -> str:
    """SHA-256 hex over the operation and every field that can change the requested effect.

    The caller decides which fields count (identifiers, amount, currency, destination,
    evidence or decision reference, lifecycle action). Key order never matters; an absent
    field and a null field differ, so callers must pass the same field set every time.
    The idempotency key itself is the lookup scope and is not part of the fingerprint.
    """
    clean: dict[str, str | int | None] = {}
    for name, value in fields.items():
        if type(name) is not str or not (value is None or type(value) in (str, int)):
            raise InvalidValue("fingerprint fields must be strings, integers, or null")
        clean[name] = value
    payload = {"operation": opaque_id(operation), "fields": clean}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
