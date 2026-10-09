"""Strict transport validation helpers (SEC-03, SEC-04, TEST-23, TEST-24). Failures raise InvalidValue."""

from __future__ import annotations

import json
from collections.abc import Collection

from abm.domain.errors import InvalidValue


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise InvalidValue("duplicate JSON key")
        out[key] = value
    return out


def _reject_constant(_name: str) -> object:
    raise InvalidValue("NaN and Infinity are not JSON numbers")


def strict_json(raw: bytes | str) -> object:
    """Decode a JSON body, refusing invalid UTF-8, duplicate keys, NaN/Infinity, and trailing text."""
    try:
        text = raw if isinstance(raw, str) else raw.decode("utf-8")
        return json.loads(
            text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant
        )
    except InvalidValue:
        raise
    except (
        ValueError,
        RecursionError,
    ) as exc:  # includes bad UTF-8 and over-long integers
        raise InvalidValue("body is not valid JSON") from exc


def exact_fields(
    body: object, required: Collection[str], optional: Collection[str] = ()
) -> dict[str, object]:
    """The body must be an object holding every required field and no field outside the allowed set."""
    if type(body) is not dict:
        raise InvalidValue("body must be a JSON object")
    allowed = set(required) | set(optional)
    if not set(required) <= body.keys() or not body.keys() <= allowed:
        raise InvalidValue("body fields do not match the operation")
    return body


def same_account(path_account_id: str, body_account_id: str) -> None:
    """A path account and a body account must be identical, byte for byte."""
    if path_account_id != body_account_id:
        raise InvalidValue("path and body accounts disagree")
