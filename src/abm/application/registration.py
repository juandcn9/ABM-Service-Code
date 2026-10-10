"""Register one zero-state account (FR-01, API-01, BT-09, INV-02, INV-03, INV-17)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from abm.application.authorization import Operation, authorize
from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
from abm.domain.errors import InvalidValue
from abm.domain.fingerprint import fingerprint
from abm.domain.identifiers import opaque_id
from abm.domain.money import require_usd
from abm.domain.results import Result, Success, failure
from abm.ports.clock import Clock
from abm.ports.storage import NewAccount, TraceEntry, UnitOfWork, WriteTransaction

OPERATION = "register_account"
_FIELDS = frozenset(
    {"instruction_id", "account_id", "customer_id", "currency", "eligibility_reference"}
)


@dataclass(frozen=True)
class RegisterAccount:
    instruction_id: str
    account_id: str
    customer_id: str
    currency: str
    eligibility_reference: str

    @classmethod
    def from_mapping(cls, body: object) -> RegisterAccount:
        """Exactly the five contract fields, each valid; nothing else is accepted."""
        if type(body) is not dict or set(body) != _FIELDS:
            raise InvalidValue("registration body fields do not match the contract")
        return cls(
            instruction_id=opaque_id(body["instruction_id"]),
            account_id=opaque_id(body["account_id"]),
            customer_id=opaque_id(body["customer_id"]),
            currency=require_usd(body["currency"]),
            eligibility_reference=opaque_id(body["eligibility_reference"]),
        )


def _account_data(account_id: str) -> dict[str, object]:
    return {
        "account": {
            "account_id": account_id,
            "currency": "USD",
            "status": "open",
            "restriction": "none",
            "balances": {
                "account_id": account_id,
                "current_balance_cents": 0,
                "held_balance_cents": 0,
                "available_balance_cents": 0,
            },
            "active_holds": [],
        },
        "registration_state": "created",
    }


def register_account(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    body: Mapping[str, object] | object,
) -> Result[Response]:
    denied = authorize(caller, Operation.REGISTER_ACCOUNT)
    if denied is not None:
        return denied
    try:
        command = RegisterAccount.from_mapping(body)
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        if tx.registration_taken(command.account_id, command.customer_id):
            return failure(
                "DUPLICATE_ACCOUNT", "The account or customer is already registered."
            )
        tx.create_account(
            NewAccount(
                command.account_id, command.customer_id, command.eligibility_reference
            ),
            now,
        )
        tx.append_trace(
            TraceEntry(
                account_id=command.account_id,
                instruction_id=command.instruction_id,
                operation=OPERATION,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
            )
        )
        return Success(Response(201, _account_data(command.account_id)))

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(command.customer_id, OPERATION),
        key=key,
        fingerprint=fingerprint(
            OPERATION,
            {
                "instruction_id": command.instruction_id,
                "account_id": command.account_id,
                "customer_id": command.customer_id,
                "currency": command.currency,
                "eligibility_reference": command.eligibility_reference,
            },
        ),
        instruction_id=command.instruction_id,
        work=work,
    )
