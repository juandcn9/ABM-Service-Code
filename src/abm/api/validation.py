"""Strict transport validation helpers (SEC-03, SEC-04, TEST-23, TEST-24). Failures raise InvalidValue."""

from __future__ import annotations

import json
import math
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


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):  # 1e999 is Infinity written another way
        raise InvalidValue("numbers must be finite")
    return value


def _require_encodable(value: object) -> None:
    """Every decoded string (and key) must be valid Unicode, so later logging and SQL cannot fail."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            item.encode(
                "utf-8"
            )  # a lone surrogate from an escape raises UnicodeEncodeError
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def strict_json(raw: bytes | bytearray | str) -> object:
    """Decode a JSON body, refusing anything ambiguous or unsafe downstream.

    Rejected: non-text input, invalid UTF-8, duplicate keys, NaN and Infinity (including
    overflowing literals such as 1e999), lone surrogates, over-long integers, excessive
    nesting, and trailing text. Body size is limited at the transport layer.
    """
    if not isinstance(raw, bytes | bytearray | str):
        raise InvalidValue("body must be text or bytes")
    try:
        text = raw if isinstance(raw, str) else bytes(raw).decode("utf-8")
        decoded = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        _require_encodable(decoded)
        return decoded
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
