"""Composition root: builds the HTTP application from the ports and the application services (TASK-25).

Every route follows the contract order: schema (strict body), then trusted context (headers only),
then one application call under the process lock (DEC-0055). Application failures are values and
map to the contract envelope in abm.api.http.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response as RawResponse
from starlette.routing import Match

from abm.api.caller_context import parse_caller_context
from abm.api.http import correlation_of, envelope, invalid_body, unauthorized
from abm.api.validation import strict_json
from abm.application.cards import (
    authorize_card,
    clear_card,
    expire_card,
    refund_card,
    reverse_card,
)
from abm.application.closure import close_account
from abm.application.corrections import create_correction
from abm.application.idempotency import Response
from abm.application.incoming_ach import (
    create_incoming_ach,
    return_incoming_ach,
    settle_incoming_ach,
)
from abm.application.outgoing_ach import (
    cancel_outgoing_ach,
    create_outgoing_ach,
    reject_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.application.reads import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_TRACE_LIMIT,
    get_account,
    get_history,
    get_trace,
)
from abm.application.registration import register_account
from abm.application.risk import set_risk_restriction
from abm.application.transfers import internal_transfer
from abm.config import ConfigError, load_settings
from abm.domain.errors import InvalidValue
from abm.domain.identifiers import format_instant
from abm.domain.results import Failure, Result, failure
from abm.observability.events import BOUNDED_LABELS, EventSink, token
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import readiness_reasons, start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from abm.ports.clock import Clock
from abm.ports.storage import StorageFailure, UnitOfWork

Command = Callable[..., Result[Response]]

# the migrations are read from the source tree next to src/, in the image as well (TASK-27)
MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "migrations"

# HealthResponse.reason_codes enum (contracts/openapi.yaml)
READY_REASONS = frozenset(
    {
        "CONFIG_INVALID",
        "DATABASE_UNAVAILABLE",
        "SCHEMA_UNSUPPORTED",
        "INTEGRITY_FAILED",
        "FOREIGN_KEY_FAILED",
        "DATABASE_BUSY",
    }
)


_DIGITS = re.compile(r"[0-9]+")


def _int_query(value: str | None, default: int | None) -> object:
    """A canonical query integer (ASCII digits only). Anything else is passed through as text, so the
    application refuses it with VALIDATION_ERROR, as the contract's integer type requires."""
    if value is None:
        return default
    if not _DIGITS.fullmatch(value):
        return value
    try:
        return int(value)
    except (
        ValueError
    ):  # more digits than Python's int limit; the application refuses it
        return value


# Read routes whose permitted and rejected calls emit attributable security events (TEST-41).
READ_TEMPLATES = frozenset(
    {
        "/v1/accounts/{account_id}",
        "/v1/accounts/{account_id}/transactions",
        "/v1/reconciliation/trace",
    }
)


def _operation(app: FastAPI, request: Request) -> str:
    for route in app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return f"{request.method} {getattr(route, 'path', 'unmatched')}"
    return "unmatched"


def _result_code(body: bytes, status: int) -> str:
    try:
        error = json.loads(body).get("error")
    except ValueError:
        return f"HTTP_{status}"
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return "OK" if status < 300 else f"HTTP_{status}"


def _observe(
    app: FastAPI,
    events: EventSink,
    request: Request,
    status: int,
    body: bytes,
    started: float,
) -> None:
    caller = parse_caller_context(dict(request.headers))
    role = "none"
    fields: dict[str, Any] = {}
    if not isinstance(caller, Failure):
        fields["caller_token"] = token(caller.value.caller_id)
        if caller.value.role in BOUNDED_LABELS["caller_role"]:
            role = caller.value.role
    operation = _operation(app, request)
    decision = (
        "permitted" if status < 300 else "failed" if status >= 500 else "rejected"
    )
    events.emit(
        event="request",
        correlation_id=token(correlation_of(request)),
        operation=operation,
        status=status,
        result_code=_result_code(body, status),
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        caller_role=role,
        **fields,
    )
    if operation.split(" ", 1)[-1] in READ_TEMPLATES:
        parts = request.url.path.split("/")
        account = (
            {"account_token": token(parts[3])} if parts[2:3] == ["accounts"] else {}
        )
        events.emit(
            event="read", decision=decision, caller_role=role, **fields, **account
        )


def create_app(
    uow: UnitOfWork,
    clock: Clock,
    readiness: Callable[[], list[str]] | None = None,
    events: EventSink | None = None,
) -> FastAPI:
    # the readiness check returns safe reason codes, empty when ready; with none supplied the
    # service reports unready (fails closed)
    ready_check: Callable[[], list[str]] = (
        readiness if readiness is not None else (lambda: ["DATABASE_UNAVAILABLE"])
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # one connection serves every request thread; the lock keeps each command's transaction whole
    guard = threading.Lock()

    @app.middleware("http")
    async def unexpected(request: Request, call_next: Callable[[Request], Any]) -> Any:
        # TEST-28: no stack, path, SQL or financial detail leaves the process. Caught here rather
        # than in an exception handler: Starlette's error middleware re-raises after a handler,
        # which would send the traceback to the server log (F2).
        try:
            return await call_next(request)
        except Exception:  # noqa: BLE001
            internal = failure("INTERNAL_ERROR", "An unexpected error occurred.")
            return envelope(internal, correlation_of(request))

    def command(path: str, fn: Command, *, with_movement: bool) -> None:
        async def endpoint(request: Request) -> JSONResponse:
            # the contract order is schema, then trusted context (specs/04 section 3.1)
            try:
                body = strict_json(await request.body())
            except InvalidValue:
                return invalid_body(request)
            caller = parse_caller_context(dict(request.headers))
            if isinstance(caller, Failure):
                return unauthorized(request)
            key = request.headers.get("idempotency-key", "")
            args: list[Any] = [request.path_params["account_id"]]
            if with_movement:
                args.append(request.path_params["movement_id"])
            with guard:
                result = fn(uow, clock, caller.value, key, *args, body)
            return envelope(result, caller.value.correlation_id)

        app.add_api_route(path, endpoint, methods=["POST"], name=f"command:{path}")

    def history_route(path: str) -> None:
        async def endpoint(request: Request) -> JSONResponse:
            caller = parse_caller_context(dict(request.headers))
            if isinstance(caller, Failure):
                return unauthorized(request)
            after = _int_query(request.query_params.get("after_sequence"), 0)
            limit = _int_query(request.query_params.get("limit"), DEFAULT_HISTORY_LIMIT)
            with guard:
                result = get_history(
                    uow, caller.value, request.path_params["account_id"], after, limit
                )
            return envelope(result, caller.value.correlation_id)

        app.add_api_route(path, endpoint, methods=["GET"], name=f"read:{path}")

    def trace_route(path: str) -> None:
        async def endpoint(request: Request) -> JSONResponse:
            caller = parse_caller_context(dict(request.headers))
            if isinstance(caller, Failure):
                return unauthorized(request)
            after = _int_query(request.query_params.get("after_sequence"), 0)
            limit = _int_query(request.query_params.get("limit"), DEFAULT_TRACE_LIMIT)
            cutoff = _int_query(request.query_params.get("cutoff_sequence"), None)
            with guard:
                result = get_trace(uow, caller.value, after, limit, cutoff)
            return envelope(result, caller.value.correlation_id)

        app.add_api_route(path, endpoint, methods=["GET"], name=f"read:{path}")

    @app.post("/v1/accounts/registrations")
    async def register(request: Request) -> JSONResponse:
        try:
            body = strict_json(await request.body())
        except InvalidValue:
            return invalid_body(request)
        caller = parse_caller_context(dict(request.headers))
        if isinstance(caller, Failure):
            return unauthorized(request)
        key = request.headers.get("idempotency-key", "")
        with guard:
            result = register_account(uow, clock, caller.value, key, body)
        return envelope(result, caller.value.correlation_id)

    @app.get("/v1/accounts/{account_id}")
    async def account(account_id: str, request: Request) -> JSONResponse:
        caller = parse_caller_context(dict(request.headers))
        if isinstance(caller, Failure):
            return unauthorized(request)
        with guard:
            result = get_account(uow, caller.value, account_id)
        return envelope(result, caller.value.correlation_id)

    # incoming ACH (API-04 to API-06)
    command(
        "/v1/accounts/{account_id}/ach/incoming",
        create_incoming_ach,
        with_movement=False,
    )
    command(
        "/v1/accounts/{account_id}/ach/incoming/{movement_id}/settlements",
        settle_incoming_ach,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/ach/incoming/{movement_id}/returns",
        return_incoming_ach,
        with_movement=True,
    )
    # outgoing ACH (API-07 to API-11, API-22)
    command(
        "/v1/accounts/{account_id}/ach/outgoing",
        create_outgoing_ach,
        with_movement=False,
    )
    command(
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/submissions",
        submit_outgoing_ach,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/settlements",
        settle_outgoing_ach,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/rejections",
        reject_outgoing_ach,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/cancellations",
        cancel_outgoing_ach,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/returns",
        return_outgoing_ach,
        with_movement=True,
    )
    # cards (API-13 to API-15, API-23, API-24)
    command(
        "/v1/accounts/{account_id}/card-authorizations",
        authorize_card,
        with_movement=False,
    )
    command(
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/clearings",
        clear_card,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/reversals",
        reverse_card,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/expirations",
        expire_card,
        with_movement=True,
    )
    command(
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/refunds",
        refund_card,
        with_movement=True,
    )
    # controls and lifecycle (API-16 to API-18)
    command(
        "/v1/accounts/{account_id}/corrections", create_correction, with_movement=False
    )
    command(
        "/v1/accounts/{account_id}/risk-restrictions",
        set_risk_restriction,
        with_movement=False,
    )
    command("/v1/accounts/{account_id}/closure", close_account, with_movement=False)
    # reads (API-03, API-19)
    history_route("/v1/accounts/{account_id}/transactions")
    trace_route("/v1/reconciliation/trace")

    @app.post("/v1/transfers/internal")
    async def transfer(request: Request) -> JSONResponse:
        try:
            body = strict_json(await request.body())
        except InvalidValue:
            return invalid_body(request)
        caller = parse_caller_context(dict(request.headers))
        if isinstance(caller, Failure):
            return unauthorized(request)
        key = request.headers.get("idempotency-key", "")
        with guard:
            result = internal_transfer(uow, clock, caller.value, key, body)
        return envelope(result, caller.value.correlation_id)

    @app.get("/health/live")
    async def live() -> JSONResponse:
        # API-20: process diagnostic only; no authorization, no data
        return JSONResponse({"status": "live"}, status_code=200)

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        # API-21: safe readiness result; a failing or raising check reports unready
        try:
            # only the contract's reason codes leave; anything else fails closed as INTEGRITY_FAILED
            reasons = sorted(
                {r if r in READY_REASONS else "INTEGRITY_FAILED" for r in ready_check()}
            )
        except Exception:  # noqa: BLE001
            reasons = ["DATABASE_UNAVAILABLE"]
        if reasons:
            return JSONResponse(
                {"status": "unready", "reason_codes": reasons}, status_code=503
            )
        return JSONResponse({"status": "ready"}, status_code=200)

    if events is not None:

        @app.middleware("http")
        async def observe(
            request: Request, call_next: Callable[[Request], Any]
        ) -> RawResponse:
            started = time.perf_counter()
            request.state.started = started
            response = await call_next(request)
            body = b"".join([chunk async for chunk in response.body_iterator])
            _observe(app, events, request, response.status_code, body, started)
            return RawResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

    return app


class SystemClock:
    """The wall clock as a UTC instant. Used only when ABM_CLOCK_MODE is system (TASK-27)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class UnavailableUnitOfWork:
    """Stands in when the database cannot open: every read and write answers SERVICE_UNREADY.

    Keeps the service up to report unready on /health/ready (NFR-02) instead of exiting.
    """

    @contextmanager
    def write(self) -> Iterator[Any]:
        raise StorageFailure(failure("SERVICE_UNREADY", "The service is not ready."))
        yield  # pragma: no cover

    @contextmanager
    def read(self) -> Iterator[Any]:
        raise StorageFailure(failure("SERVICE_UNREADY", "The service is not ready."))
        yield  # pragma: no cover


def app_from_environment() -> FastAPI:
    """ASGI factory for the container (TASK-27): settings only from ABM_*, the real readiness check.

    Refuses to start on a bad setting (CONFIG_INVALID, names only). A database that cannot open
    still starts, reporting unready, so the operator can see why (NFR-02).
    """
    try:
        settings = load_settings(os.environ)
    except ConfigError as exc:
        raise SystemExit(f"CONFIG_INVALID: {', '.join(exc.names)}") from None
    migrations = load_migrations(MIGRATIONS_DIR)
    started = start_database(
        settings.db_path,
        migrations,
        format_instant(datetime.now(UTC)),
        busy_timeout_ms=settings.busy_timeout_ms,
        check_same_thread=False,
    )
    clock: Clock = SystemClock()
    if started.connection is None:
        reasons = list(started.reasons) or ["DATABASE_UNAVAILABLE"]
        return create_app(UnavailableUnitOfWork(), clock, lambda: reasons)
    conn = started.connection
    app = create_app(
        SqliteUnitOfWork(conn),
        clock,
        lambda: readiness_reasons(conn, migrations),
        events=EventSink(sys.stdout),
    )
    app.state.connection = (
        conn  # so a caller can close the database handle (TASK-28 F-03)
    )
    return app
