"""HTTP binding for the application commands and reads (TASK-25, specs/04-api.md, contracts/openapi.yaml).

Every route reads trusted caller facts from headers only (SEC-01), parses the body strictly
(SEC-05), calls one application function, and returns the contract envelope. Application
failures are values; this module maps their stable codes to HTTP statuses and never adds detail.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from abm.domain.results import Failure, Result, failure

# contract status per stable error code (contracts/openapi.yaml x-error-codes)
STATUS_BY_CODE: dict[str, int] = {
    "VALIDATION_ERROR": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN_SCOPE": 403,
    "ACCOUNT_NOT_FOUND": 404,
    "MOVEMENT_NOT_FOUND": 404,
    "DUPLICATE_ACCOUNT": 409,
    "INVALID_TRANSITION": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "ACCOUNT_CLOSED": 422,
    "AMOUNT_MISMATCH": 422,
    "CLOSURE_PRECONDITION_FAILED": 422,
    "INSUFFICIENT_FUNDS": 422,
    "OUTGOING_BLOCKED": 422,
    "SERVICE_BUSY": 503,
    "SERVICE_UNREADY": 503,
    "INTERNAL_ERROR": 500,
}
NO_CORRELATION = "not-provided"


_CORRELATION = re.compile(
    r"[A-Za-z0-9._~-]{1,128}"
)  # ResponseMeta.correlation_id pattern


def correlation_of(request: Request) -> str:
    value = request.headers.get("x-correlation-id", "")
    return value if _CORRELATION.fullmatch(value) else NO_CORRELATION


def _error_body(result: Failure, correlation: str) -> dict[str, Any]:
    error = result.error
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.safe_message,
            "retryable": error.retryable,
        },
        "meta": {"correlation_id": correlation},
    }


def envelope(result: Result[Any], correlation: str) -> JSONResponse:
    """Success or typed error, in the contract envelope, with the contract status."""
    if isinstance(result, Failure):
        status = STATUS_BY_CODE.get(result.error.code, 500)
        return JSONResponse(_error_body(result, correlation), status_code=status)
    response = result.value
    body: dict[str, Any] = {
        "ok": True,
        "data": dict(response.data),
        "meta": {"correlation_id": correlation},
    }
    if result.replayed:
        body["meta"]["replayed"] = True
    return JSONResponse(body, status_code=response.status)


def unauthorized(request: Request) -> JSONResponse:
    # the same generic denial the application layer uses; no detail about which header failed
    denied = failure("UNAUTHORIZED", "Trusted caller context is missing or malformed.")
    return envelope(denied, correlation_of(request))


def invalid_body(request: Request) -> JSONResponse:
    return envelope(
        failure("VALIDATION_ERROR", "The request is not valid."),
        correlation_of(request),
    )
