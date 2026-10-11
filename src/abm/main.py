"""Composition root: builds the HTTP application from the ports and the application services (TASK-25)."""

from __future__ import annotations

import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from abm.api.caller_context import parse_caller_context
from abm.api.http import correlation_of, envelope, invalid_body, unauthorized
from abm.api.validation import strict_json
from abm.application.reads import get_account
from abm.application.registration import register_account
from abm.domain.errors import InvalidValue
from abm.domain.results import Failure, failure
from abm.ports.clock import Clock
from abm.ports.storage import UnitOfWork


def create_app(uow: UnitOfWork, clock: Clock) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # one connection serves every request thread; the lock keeps each command's transaction whole
    guard = threading.Lock()

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        # TEST-28: no stack, path, SQL or financial detail leaves the process
        internal = failure("INTERNAL_ERROR", "An unexpected error occurred.")
        return envelope(internal, correlation_of(request))

    @app.post("/v1/accounts/registrations")
    async def register(request: Request) -> JSONResponse:
        caller = parse_caller_context(dict(request.headers))
        if isinstance(caller, Failure):
            return unauthorized(request)
        key = request.headers.get("idempotency-key", "")
        try:
            body = strict_json(await request.body())
        except InvalidValue:
            return invalid_body(request)
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

    return app
