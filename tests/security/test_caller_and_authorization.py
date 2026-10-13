"""Caller context, role/scope matrix, and strict transport validation (TEST-21, TEST-22, TEST-23, TEST-24)."""

from __future__ import annotations

import pytest

from abm.api.caller_context import parse_caller_context
from abm.api.validation import exact_fields, same_account, strict_json
from abm.application.authorization import (
    ACCOUNT_SCOPED,
    PERMISSIONS,
    Operation,
    authorize,
)
from abm.application.caller import CallerContext
from abm.domain.errors import InvalidValue
from abm.domain.results import Failure, Success

GOOD = {
    "X-Caller-Id": "harness-1",
    "X-Caller-Role": "payment_orchestrator",
    "X-Correlation-Id": "corr-1",
}


def parsed(headers: dict[str, str]) -> Success[CallerContext] | Failure:
    return parse_caller_context(headers)


def ctx(role: str, scope: str | None = None) -> CallerContext:
    return CallerContext("caller-1", role, "corr-1", scope)


# TEST-21: missing, malformed, unknown, or contradictory context is denied before any transaction


def test_valid_context_is_parsed_from_headers() -> None:
    result = parsed(
        {**GOOD, "X-Account-Scope": "acct-1", "Content-Type": "application/json"}
    )
    assert isinstance(result, Success)
    assert result.value == CallerContext(
        "harness-1", "payment_orchestrator", "corr-1", "acct-1"
    )
    assert parsed(
        {k.lower(): v for k, v in GOOD.items()}
    ).ok  # header names are case-insensitive


def test_scope_is_optional_for_parsing() -> None:
    result = parsed(GOOD)
    assert isinstance(result, Success) and result.value.account_scope is None


@pytest.mark.parametrize("missing", list(GOOD))
def test_missing_required_header_is_unauthorized(missing: str) -> None:
    result = parsed({k: v for k, v in GOOD.items() if k != missing})
    assert isinstance(result, Failure)
    assert result.error.code == "UNAUTHORIZED" and result.error.retryable is False


def test_malformed_values_are_unauthorized() -> None:
    bad_values = [
        "",
        " ",
        "a b",
        "x" * 129,
        "café",
        "a/b",
        "a\nb",
        "a;b",
        "'; DROP--",
        "%41",
    ]
    for header in (*GOOD, "X-Account-Scope"):
        for value in bad_values:
            result = parsed({**GOOD, header: value})
            assert isinstance(result, Failure), (header, value)
            assert result.error.code == "UNAUTHORIZED"


def test_contradictory_or_non_string_headers_are_unauthorized() -> None:
    twice = {**GOOD, "x-caller-id": "someone-else"}  # same header spelled two ways
    assert isinstance(parsed(twice), Failure)
    multi: dict[str, object] = {
        **GOOD,
        "X-Caller-Role": ["account_registrar", "account_reader"],
    }
    assert isinstance(parse_caller_context(multi), Failure)  # type: ignore[arg-type]
    binary: dict[str, object] = {**GOOD, "X-Caller-Id": b"harness-1"}
    assert isinstance(parse_caller_context(binary), Failure)  # type: ignore[arg-type]


def test_denial_message_leaks_nothing() -> None:
    result = parsed({**GOOD, "X-Caller-Id": "'; DROP TABLE accounts;--"})
    assert isinstance(result, Failure)
    assert (
        "DROP" not in result.error.safe_message
        and "accounts" not in result.error.safe_message
    )


def test_a_payload_cannot_supply_identity() -> None:
    # context exists only as headers; a body carrying caller fields is an unknown field
    with pytest.raises(InvalidValue):
        exact_fields(
            {"account_id": "a1", "caller_id": "x", "caller_role": "account_registrar"},
            {"account_id"},
        )


# TEST-22: each role succeeds only on its matrix operations


def test_matrix_matches_the_security_specification_exactly() -> None:
    expected_api = {f"API-{n:02d}" for n in [*range(1, 20), 22, 23, 24]}
    granted = [op for ops in PERMISSIONS.values() for op in ops]
    assert {op.value for op in granted} - {"LEGAL-HOLD"} == expected_api
    assert len(granted) == len(set(granted)), "an operation is granted to two roles"
    assert PERMISSIONS["retention_controller"] == {Operation.LEGAL_HOLD}
    assert set(PERMISSIONS) == {
        "account_registrar",
        "account_reader",
        "payment_orchestrator",
        "card_orchestrator",
        "correction_authority",
        "risk_controller",
        "reconciliation_reader",
        "retention_controller",
    }


def test_every_role_operation_pair_is_decided_by_the_matrix() -> None:
    for role in PERMISSIONS:
        for operation in Operation:
            scoped = operation in ACCOUNT_SCOPED
            caller = ctx(role, "acct-1" if scoped else None)
            result = authorize(caller, operation, "acct-1" if scoped else None)
            if operation in PERMISSIONS[role]:
                assert result is None, (role, operation)
            else:
                assert isinstance(result, Failure), (role, operation)
                assert result.error.code == "FORBIDDEN_SCOPE"


def test_unknown_and_look_alike_roles_are_denied() -> None:
    for role in (
        "",
        "admin",
        "root",
        "ACCOUNT_READER",
        "account_reader ",
        "account-reader",
        "payment_orchestrator2",
    ):
        for operation in Operation:
            try:
                caller = ctx(role, "acct-1")
            except InvalidValue:
                continue  # not even constructible as a context
            assert isinstance(authorize(caller, operation, "acct-1"), Failure), (
                role,
                operation,
            )


def test_account_reader_is_limited_to_its_one_trusted_account() -> None:
    reader = ctx("account_reader", "acct-1")
    assert authorize(reader, Operation.READ_ACCOUNT, "acct-1") is None
    assert authorize(reader, Operation.READ_HISTORY, "acct-1") is None
    for account in ("acct-2", "acct-1x", "ACCT-1", "acct-1 ", None):
        assert isinstance(
            authorize(reader, Operation.READ_ACCOUNT, account), Failure
        ), account
    assert isinstance(
        authorize(ctx("account_reader"), Operation.READ_ACCOUNT, "acct-1"), Failure
    )
    assert isinstance(
        authorize(ctx("account_reader", None), Operation.READ_ACCOUNT, None), Failure
    )


def test_scope_does_not_grant_other_roles_anything() -> None:
    assert isinstance(
        authorize(
            ctx("payment_orchestrator", "acct-1"), Operation.READ_ACCOUNT, "acct-1"
        ),
        Failure,
    )
    assert isinstance(
        authorize(
            ctx("reconciliation_reader", "acct-1"), Operation.CLOSE_ACCOUNT, "acct-1"
        ),
        Failure,
    )


def test_all_denials_are_indistinguishable() -> None:
    unknown_role = authorize(ctx("nobody", "acct-1"), Operation.READ_ACCOUNT, "acct-1")
    wrong_op = authorize(ctx("risk_controller"), Operation.CLOSE_ACCOUNT, "acct-1")
    wrong_scope = authorize(
        ctx("account_reader", "acct-1"), Operation.READ_ACCOUNT, "acct-2"
    )
    assert unknown_role == wrong_op == wrong_scope


# TEST-23 and TEST-24 transport half


def test_path_and_body_account_must_agree_exactly() -> None:
    same_account("acct-1", "acct-1")
    for body in ("acct-2", "ACCT-1", "acct-1 ", "acct-1\n", ""):
        with pytest.raises(InvalidValue):
            same_account("acct-1", body)


def test_exact_fields_rejects_unknown_missing_and_non_objects() -> None:
    assert exact_fields({"a": 1, "b": 2}, {"a"}, {"b"}) == {"a": 1, "b": 2}
    assert exact_fields({"a": 1}, {"a"}, {"b"}) == {"a": 1}
    for body in (
        {},
        {"b": 2},
        {"a": 1, "extra": 2},
        {"a": 1, "A": 2},
        [],
        "a",
        None,
        1,
        [{"a": 1}],
    ):
        with pytest.raises(InvalidValue):
            exact_fields(body, {"a"}, {"b"})


def test_strict_json_refuses_ambiguous_documents() -> None:
    assert strict_json(b'{"a": 1}') == {"a": 1}
    assert strict_json('{"amount_cents": 500}') == {"amount_cents": 500}
    bad = [
        b'{"a": 1, "a": 2}',  # duplicate key
        b'{"a": NaN}',
        b'{"a": Infinity}',
        b'{"a": -Infinity}',
        b'{"a": 1} trailing',
        b"",
        b"\xff\xfe{}",  # not UTF-8
        b'{"a": ',
        b"[" * 100_000,  # recursion bomb
        b'{"a": ' + b"9" * 5000 + b"}",  # integer beyond the interpreter digit limit
    ]
    for raw in bad:
        with pytest.raises(InvalidValue):
            strict_json(raw)


def test_json_numbers_never_become_money_by_accident() -> None:
    from abm.domain.money import Money

    for raw, ok in (
        (b'{"v": 500}', True),
        (b'{"v": 500.0}', False),
        (b'{"v": 1e2}', False),
        (b'{"v": "500"}', False),
    ):
        value = strict_json(raw)
        assert isinstance(value, dict)
        if ok:
            assert Money.positive(value["v"]).cents == 500
        else:
            with pytest.raises(InvalidValue):
                Money.positive(value["v"])


# Independent literals from specs/06-security.md section 4, so the tests do not read the table they check

SPEC_MATRIX = {
    "account_registrar": {"API-01", "API-18"},
    "account_reader": {"API-02", "API-03"},
    "payment_orchestrator": {
        f"API-{n:02d}" for n in (4, 5, 6, 7, 8, 9, 10, 11, 12, 22)
    },
    "card_orchestrator": {"API-13", "API-14", "API-15", "API-23", "API-24"},
    "correction_authority": {"API-16"},
    "risk_controller": {"API-17"},
    "reconciliation_reader": {"API-19"},
    "retention_controller": {"LEGAL-HOLD"},
}


def test_each_role_holds_exactly_the_operations_the_specification_assigns_it() -> None:
    held = {role: {op.value for op in ops} for role, ops in PERMISSIONS.items()}
    assert held == SPEC_MATRIX
    # spot checks that name the dangerous swaps explicitly
    assert authorize(ctx("payment_orchestrator"), Operation.INTERNAL_TRANSFER) is None
    assert isinstance(
        authorize(ctx("card_orchestrator"), Operation.INTERNAL_TRANSFER), Failure
    )
    assert isinstance(
        authorize(ctx("payment_orchestrator"), Operation.CARD_AUTHORIZE), Failure
    )
    assert isinstance(authorize(ctx("risk_controller"), Operation.CORRECTION), Failure)


def test_only_the_two_account_reads_are_scoped_to_one_account() -> None:
    assert ACCOUNT_SCOPED == {Operation("API-02"), Operation("API-03")}
    assert Operation.READ_HISTORY in ACCOUNT_SCOPED


def test_history_reads_are_limited_to_the_trusted_account_exactly_like_balance_reads() -> (
    None
):
    reader = ctx("account_reader", "acct-1")
    assert authorize(reader, Operation.READ_HISTORY, "acct-1") is None
    for account in ("acct-2", "ACCT-1", "acct-1 ", "acct-1x", "", None):
        assert isinstance(
            authorize(reader, Operation.READ_HISTORY, account), Failure
        ), account
    assert isinstance(
        authorize(ctx("account_reader"), Operation.READ_HISTORY, "acct-1"), Failure
    )
    assert isinstance(authorize(ctx("account_reader"), Operation.READ_HISTORY), Failure)
    assert isinstance(
        authorize(
            ctx("reconciliation_reader", "acct-1"), Operation.READ_HISTORY, "acct-1"
        ),
        Failure,
    )


def test_strict_json_rejects_non_text_input_with_the_validation_error() -> None:
    for raw in (None, 1, 1.5, [], {}, memoryview(b"{}"), object()):
        with pytest.raises(InvalidValue):
            strict_json(raw)  # type: ignore[arg-type]
    assert strict_json(bytearray(b'{"a": 1}')) == {"a": 1}


def test_strict_json_rejects_values_that_are_unsafe_downstream() -> None:
    unsafe = [
        b'{"a": 1e999}',  # Infinity by another spelling
        b'{"a": -1e999}',
        b'{"a": 1E+99999999999}',
        rb'{"a": "\ud800"}',  # lone surrogate cannot be encoded to UTF-8
        rb'{"\udfff": 1}',
        rb'["ok", {"nested": ["\ud83d"]}]',
    ]
    for raw in unsafe:
        with pytest.raises(InvalidValue):
            strict_json(raw)
    assert strict_json(rb'{"a": 1.5, "b": "\ud83d\ude00"}') == {
        "a": 1.5,
        "b": "\U0001f600",
    }


def test_non_mapping_header_input_is_unauthorized_not_an_exception() -> None:
    for headers in (None, [], [("X-Caller-Id", "a")], "headers", 5):
        result = parse_caller_context(headers)  # type: ignore[arg-type]
        assert isinstance(result, Failure) and result.error.code == "UNAUTHORIZED"


def test_a_mapping_that_raises_on_iteration_is_unauthorized_not_an_exception() -> None:
    from collections.abc import Iterator, Mapping

    class Hostile(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise KeyError(key)

        def __iter__(self) -> Iterator[str]:
            raise RuntimeError("boom")

        def __len__(self) -> int:
            return 0

    result = parse_caller_context(Hostile())
    assert isinstance(result, Failure) and result.error.code == "UNAUTHORIZED"
