"""TASK-26: structured events, TEST-29 redaction and bounded labels, TEST-41 read evidence, TEST-39 scan."""

from __future__ import annotations

import io
import json
import pathlib
import sqlite3
import sys
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient

from abm.main import create_app
from abm.observability.events import ALLOWED_FIELDS, EventSink, token
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import MIGRATIONS, NOW, fund, register

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from scan_aged_items import open_read_only, run_scan  # type: ignore[import-not-found]

PAYER = {
    "X-Caller-Id": "pay-1",
    "X-Caller-Role": "payment_orchestrator",
    "X-Correlation-Id": "corr-p",
}
READER = {
    "X-Caller-Id": "rd-1",
    "X-Caller-Role": "account_reader",
    "X-Correlation-Id": "corr-r",
    "X-Account-Scope": "acct-a",
}
RECON = {
    "X-Caller-Id": "recon-1",
    "X-Caller-Role": "reconciliation_reader",
    "X-Correlation-Id": "corr-t",
}


@pytest.fixture
def stack(tmp_path: pathlib.Path):
    db = tmp_path / "abm.sqlite3"
    started = start_database(db, MIGRATIONS, NOW, check_same_thread=False)
    assert started.connection is not None
    uow = SqliteUnitOfWork(started.connection)
    clock = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    register(uow, clock, "acct-a")
    register(uow, clock, "acct-b")
    fund(uow, clock, "acct-a", 500)
    stream = io.StringIO()
    client = TestClient(
        create_app(uow, clock, events=EventSink(stream)), raise_server_exceptions=False
    )
    yield {
        "db": db,
        "client": client,
        "clock": clock,
        "stream": stream,
        "conn": started.connection,
    }
    client.close()
    started.connection.close()


def lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


# --- the sink: allowlist, bounded labels, tokens -------------------------------------------------


def test_the_sink_refuses_a_field_outside_the_allowlist():
    with pytest.raises(ValueError):
        EventSink(io.StringIO()).emit(event="request", body='{"amount_cents": 1}')


@pytest.mark.parametrize(
    "fields",
    [
        {"event": "anything_else"},
        {"event": "request", "decision": "maybe"},
        {"event": "request", "caller_role": "root"},
    ],
)
def test_the_sink_refuses_a_label_outside_its_bounded_set(fields):
    with pytest.raises(ValueError):
        EventSink(io.StringIO()).emit(**fields)


def test_identifiers_leave_only_as_stable_one_way_tokens():
    assert token("acct-a") == token("acct-a")
    assert token("acct-a") != token("acct-b")
    assert "acct-a" not in token("acct-a")
    assert set(ALLOWED_FIELDS) >= {"caller_token", "account_token", "item_token"}


# --- TEST-29 and TEST-41 over HTTP ---------------------------------------------------------------


def test_each_request_emits_one_line_with_allowed_fields_only(stack):
    stack["client"].get("/health/live")
    stack["client"].get("/v1/accounts/acct-a", headers=READER)
    for entry in lines(stack["stream"]):
        # the sink stamps ts and severity; callers may not supply them
        assert set(entry) <= ALLOWED_FIELDS | {"ts", "severity"}, entry
        assert entry["event"] in {"request", "read"}
        assert entry["ts"].endswith("Z") and len(entry["ts"]) == 20
        assert entry["severity"] in {"INFO", "WARNING", "ERROR"}


def test_severity_follows_the_safe_result(stack):
    stack["client"].get("/v1/accounts/acct-a")  # no caller context: rejected
    stack["client"].get("/health/live")  # permitted
    severities = [
        e["severity"] for e in lines(stack["stream"]) if e["event"] == "request"
    ]
    assert severities == ["WARNING", "INFO"]


def test_no_raw_identifier_or_body_value_is_logged(stack):
    stack["client"].post(
        "/v1/accounts/acct-a/ach/incoming",
        json={
            "instruction_id": "ins-x",
            "movement_id": "mv-secret-7",
            "amount_cents": 4321,
            "currency": "USD",
            "external_reference": "ext-x",
        },
        headers={**PAYER, "Idempotency-Key": "k-x"},
    )
    stack["client"].get("/v1/accounts/acct-a", headers=READER)
    output = stack["stream"].getvalue()
    for raw in (
        "pay-1",
        "rd-1",
        "acct-a",
        "mv-secret-7",
        "4321",
        "amount_cents",
        "ext-x",
    ):
        assert raw not in output, raw


def test_a_permitted_read_and_a_rejected_read_are_both_attributable(stack):
    stack["client"].get("/v1/accounts/acct-a", headers=READER)
    stack["client"].get("/v1/accounts/acct-a")  # no caller context: rejected
    reads = [entry for entry in lines(stack["stream"]) if entry["event"] == "read"]
    assert [entry["decision"] for entry in reads] == ["permitted", "rejected"]
    assert all(entry["account_token"] == token("acct-a") for entry in reads)
    assert reads[0]["caller_token"] == token("rd-1")
    assert "caller_token" not in reads[1]


def test_trace_reads_emit_a_read_event_without_an_account_token(stack):
    stack["client"].get("/v1/reconciliation/trace", headers=RECON)
    reads = [entry for entry in lines(stack["stream"]) if entry["event"] == "read"]
    assert len(reads) == 1 and "account_token" not in reads[0]


def test_an_unknown_role_is_logged_as_none_not_refused(stack):
    response = stack["client"].get(
        "/v1/accounts/acct-a",
        headers={
            "X-Caller-Id": "x-1",
            "X-Caller-Role": "not_a_role",
            "X-Correlation-Id": "corr-u",
        },
    )
    assert response.status_code == 403
    request_line = [
        entry for entry in lines(stack["stream"]) if entry["event"] == "request"
    ][-1]
    assert request_line["caller_role"] == "none"


# --- TEST-39 aged-item scan ----------------------------------------------------------------------


def _pending_incoming(stack, movement_id: str) -> None:
    stack["client"].post(
        "/v1/accounts/acct-a/ach/incoming",
        json={
            "instruction_id": f"ins-{movement_id}",
            "movement_id": movement_id,
            "amount_cents": 25,
            "currency": "USD",
            "external_reference": f"ext-{movement_id}",
        },
        headers={**PAYER, "Idempotency-Key": f"k-{movement_id}"},
    )


def _snapshot(conn: sqlite3.Connection) -> list[list[Any]]:
    return [
        conn.execute("SELECT * FROM movements ORDER BY movement_id").fetchall(),
        conn.execute("SELECT * FROM holds ORDER BY hold_id").fetchall(),
        conn.execute("SELECT * FROM ledger_entries ORDER BY sequence").fetchall(),
        conn.execute("SELECT * FROM accounts ORDER BY account_id").fetchall(),
    ]


def test_the_scan_reports_only_items_older_than_the_threshold_and_changes_nothing(
    stack,
):
    _pending_incoming(stack, "mv-old")
    stack["clock"].advance(48 * 3600)
    _pending_incoming(stack, "mv-new")
    before = _snapshot(stack["conn"])

    reader = sqlite3.connect(f"file:{stack['db'].as_posix()}?mode=ro", uri=True)
    sink = EventSink(io.StringIO())
    now = datetime(2026, 10, 12, 12, 0, 0, tzinfo=UTC)
    try:
        count = run_scan(reader, sink, now, threshold_hours=24)
    finally:
        reader.close()

    assert count == 1
    assert _snapshot(stack["conn"]) == before


def test_the_scan_refuses_writes_through_its_read_only_connection(stack):
    # the entry point opens its database through open_read_only, so this tests the shipped path
    reader = open_read_only(stack["db"])
    try:
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("UPDATE movements SET state = 'expired'")
    finally:
        reader.close()


def test_the_scan_emits_safe_item_events_and_a_summary(stack):
    _pending_incoming(stack, "mv-aged-1")
    stack["clock"].advance(30 * 3600)
    reader = sqlite3.connect(f"file:{stack['db'].as_posix()}?mode=ro", uri=True)
    out = io.StringIO()
    try:
        run_scan(
            reader,
            EventSink(out),
            datetime(2026, 10, 11, 18, 0, 0, tzinfo=UTC),
            threshold_hours=24,
        )
    finally:
        reader.close()
    emitted = [json.loads(line) for line in out.getvalue().splitlines()]
    assert emitted[0]["event"] == "aged_item"
    assert emitted[0]["item_token"] == token("mv-aged-1")
    assert emitted[0]["state"] == "pending"
    summary = {k: v for k, v in emitted[-1].items() if k not in {"ts", "severity"}}
    assert summary == {"count": 1, "event": "scan_summary", "threshold_hours": 24}
    assert "mv-aged-1" not in out.getvalue() and "acct-a" not in out.getvalue()


def test_the_manifest_records_exact_revisions_migrations_and_the_scan_result(tmp_path):
    from scan_aged_items import main  # type: ignore[import-not-found]

    db = tmp_path / "manifest.sqlite3"
    started = start_database(db, MIGRATIONS, NOW, check_same_thread=False)
    started.connection.close()
    manifest = tmp_path / "manifest.json"
    code = main(
        [
            str(db),
            "--older-than-hours",
            "24",
            "--manifest",
            str(manifest),
            "--spec-version",
            "v1.9.11",
            "--spec-commit",
            "d2211b53a0570437b7fa9ddb1a1ba46969d6ac40",
            "--code-commit",
            "abc1234",
            "--test-summary",
            "945 passed, 1 warning",
        ]
    )
    assert code == 0
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["spec_version"] == "v1.9.11" and data["code_commit"] == "abc1234"
    assert data["aged_scan"] == {"threshold_hours": 24.0, "count": 0}
    assert data["migrations"] and all(
        len(m["checksum"]) == 64 for m in data["migrations"]
    )
    # TEST-35: the image digest is the toolchain pin; the test summary is the one supplied
    assert (
        data["image_digest"].startswith("sha256:") and len(data["image_digest"]) == 71
    )
    assert data["test_summary"] == "945 passed, 1 warning"


@pytest.mark.parametrize(
    "argv", [["--older-than-hours", "0"], ["--older-than-hours", "-1"], []]
)
def test_the_scan_refuses_a_missing_or_non_positive_threshold(tmp_path, argv):
    from scan_aged_items import main  # type: ignore[import-not-found]

    with pytest.raises(SystemExit):
        main([str(tmp_path / "none.sqlite3"), *argv])


def test_an_unhandled_error_emits_a_request_event_with_internal_error(
    stack, monkeypatch
):
    import abm.main as main_module

    def boom(*args, **kwargs):
        raise RuntimeError("sensitive detail that must not leave the process")

    monkeypatch.setattr(main_module, "get_account", boom)
    response = stack["client"].get("/v1/accounts/acct-a", headers=READER)
    assert response.status_code == 500
    request_line = [
        entry for entry in lines(stack["stream"]) if entry["event"] == "request"
    ][-1]
    assert (
        request_line["status"] == 500
        and request_line["result_code"] == "INTERNAL_ERROR"
    )
    assert "sensitive detail" not in stack["stream"].getvalue()
    read_line = [entry for entry in lines(stack["stream"]) if entry["event"] == "read"][
        -1
    ]
    assert read_line["decision"] == "failed"


def test_a_caller_supplied_correlation_id_is_tokenized_not_logged(stack):
    stack["client"].get(
        "/v1/accounts/acct-a",
        headers={**READER, "X-Correlation-Id": "ACCT-SECRET-42"},
    )
    output = stack["stream"].getvalue()
    assert "ACCT-SECRET-42" not in output
    assert token("ACCT-SECRET-42") in output


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-1", "1e400"])
def test_the_scan_refuses_non_finite_or_non_positive_thresholds(tmp_path, value):
    from scan_aged_items import main  # type: ignore[import-not-found]

    with pytest.raises(SystemExit):
        main([str(tmp_path / "none.sqlite3"), "--older-than-hours", value])


def test_a_manifest_without_revisions_is_refused(tmp_path):
    from scan_aged_items import main  # type: ignore[import-not-found]

    db = tmp_path / "m.sqlite3"
    started = start_database(db, MIGRATIONS, NOW, check_same_thread=False)
    started.connection.close()
    with pytest.raises(SystemExit):
        main(
            [
                str(db),
                "--older-than-hours",
                "24",
                "--manifest",
                str(tmp_path / "m.json"),
            ]
        )


# --- review remediation: the other pending states, the error path, and rejected trace reads ------


@pytest.mark.parametrize(
    "setup, expected_state",
    [
        ("setup_submitted", "submitted"),
        ("setup_card_authorized", "authorized_with_hold"),
    ],
)
def test_the_scan_finds_submitted_outgoing_and_authorized_card_items(
    tmp_path, setup, expected_state
):
    from tests.integration import store_support

    db = tmp_path / "pending.sqlite3"
    getattr(store_support, setup)(db)
    reader = open_read_only(db)
    out = io.StringIO()
    try:
        # NOW is 2026-10-10T12:00Z; two days later the items are past a 24-hour threshold
        count = run_scan(
            reader, EventSink(out), datetime(2026, 10, 12, 12, 0, 0, tzinfo=UTC), 24
        )
    finally:
        reader.close()
    emitted = [json.loads(line) for line in out.getvalue().splitlines()]
    assert count == 1
    assert [e["state"] for e in emitted if e["event"] == "aged_item"] == [
        expected_state
    ]


def test_an_unhandled_error_is_not_re_raised_to_the_server(stack, monkeypatch):
    # F2: the client sees a 500 envelope; no exception escapes to the server (its log)
    import abm.main as main_module
    from abm.persistence.sqlite_store import SqliteUnitOfWork

    def boom(*args, **kwargs):
        raise RuntimeError("SELECT secret FROM ledger")

    monkeypatch.setattr(main_module, "get_account", boom)
    strict = TestClient(
        create_app(
            SqliteUnitOfWork(stack["conn"]),
            stack["clock"],
            events=EventSink(io.StringIO()),
        ),
        raise_server_exceptions=True,
    )
    response = strict.get("/v1/accounts/acct-a", headers=READER)
    assert response.status_code == 500
    assert response.json()["error"]["message"] == "An unexpected error occurred."
    assert "SELECT" not in response.text


def test_a_rejected_trace_read_is_attributable_without_an_account_token(stack):
    # PAYER may not read the reconciliation trace: a rejected trace read (F8)
    stack["client"].get("/v1/reconciliation/trace", headers=PAYER)
    read_line = [e for e in lines(stack["stream"]) if e["event"] == "read"][-1]
    assert read_line["decision"] == "rejected"
    assert read_line["caller_role"] == "payment_orchestrator"
    assert "account_token" not in read_line


def test_a_manifest_without_a_test_summary_is_refused(tmp_path):
    from scan_aged_items import main  # type: ignore[import-not-found]

    db = tmp_path / "t.sqlite3"
    started = start_database(db, MIGRATIONS, NOW, check_same_thread=False)
    started.connection.close()
    with pytest.raises(SystemExit):
        main(
            [
                str(db),
                "--older-than-hours",
                "24",
                "--manifest",
                str(tmp_path / "t.json"),
                "--spec-version",
                "v1.9.11",
                "--spec-commit",
                "d2211b53a0570437b7fa9ddb1a1ba46969d6ac40",
                "--code-commit",
                "abc1234",
            ]
        )
