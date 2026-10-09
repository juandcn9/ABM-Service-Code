"""Parse trusted caller-context headers (SEC-01, TEST-21). Headers are the only source; payloads never are."""

from __future__ import annotations

from collections.abc import Mapping

from abm.application.caller import CallerContext
from abm.domain.errors import InvalidValue
from abm.domain.results import Result, Success, failure

_REQUIRED = {
    "x-caller-id": "caller_id",
    "x-caller-role": "role",
    "x-correlation-id": "correlation_id",
}
_SCOPE = "x-account-scope"


def parse_caller_context(headers: Mapping[str, str]) -> Result[CallerContext]:
    """Missing, malformed, duplicated (case-insensitively), or non-string headers give UNAUTHORIZED.

    Extra transport headers are ignored. A scope header is optional here; authorization
    requires it for account reads.
    """
    denied = failure("UNAUTHORIZED", "Trusted caller context is missing or malformed.")
    if not isinstance(headers, Mapping):
        return denied
    seen: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower() if type(name) is str else ""
        wanted = key in _REQUIRED or key == _SCOPE
        if wanted and (key in seen or type(value) is not str):
            return denied  # two spellings of one header, or a multi-valued/binary value
        if wanted:
            seen[key] = value
    if not all(key in seen for key in _REQUIRED):
        return denied
    try:
        return Success(
            CallerContext(
                **{field: seen[key] for key, field in _REQUIRED.items()},
                account_scope=seen.get(_SCOPE),
            )
        )
    except InvalidValue:
        return denied
