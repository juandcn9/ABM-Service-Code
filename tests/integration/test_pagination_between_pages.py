"""Writes committed by another connection between pages never cross the cutoff or duplicate/skip history (TEST-47)."""

from __future__ import annotations

import pathlib
from typing import Any

from abm.application.caller import CallerContext
from abm.application.reads import get_history, get_trace
from abm.application.transfers import internal_transfer
from abm.domain.results import Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import clock, fund, open_started, register


def payload(result: object) -> dict[str, Any]:
    """The success data of a read, typed for the assertions in this module."""
    assert isinstance(result, Success)
    return dict(result.value.data)


PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
RECON = CallerContext("recon-1", "reconciliation_reader", "corr-t")
READER = CallerContext("rd-1", "account_reader", "corr-d", account_scope="acct-a")


def move(
    uow: SqliteUnitOfWork, now: ControllableClock, n: int, cents: int = 10
) -> None:
    result = internal_transfer(
        uow,
        now,
        PAYER,
        f"k-m{n}",
        {
            "instruction_id": f"ins-m{n}",
            "movement_id": f"mv-m{n}",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": cents,
            "currency": "USD",
        },
    )
    assert isinstance(result, Success)


def test_trace_walk_with_writes_between_pages_stays_on_the_cutoff(
    tmp_path: pathlib.Path,
):
    path = tmp_path / "abm.sqlite3"
    reader_conn = open_started(path)
    reader = SqliteUnitOfWork(reader_conn)
    now = clock()
    register(reader, now, "acct-a")
    register(reader, now, "acct-b")
    fund(reader, now, "acct-a", 1000)
    for n in range(1, 4):
        move(reader, now, n)

    # the reference walk, before any concurrent write
    full = get_trace(reader, RECON, 0, 100)
    assert isinstance(full, Success)
    expected = [item["sequence"] for item in payload(full)["items"]]

    first = get_trace(reader, RECON, 0, 2)
    assert isinstance(first, Success)
    cutoff = payload(first)["cutoff_sequence"]
    seen = [item["sequence"] for item in payload(first)["items"]]
    cursor = payload(first)["next_after_sequence"]

    # another connection commits between the pages
    writer_conn = open_started(path)
    writer = SqliteUnitOfWork(writer_conn)
    move(writer, now, 4)
    move(writer, now, 5)

    while cursor is not None:
        page = get_trace(reader, RECON, cursor, 2, cutoff)
        assert isinstance(page, Success)
        seen += [item["sequence"] for item in payload(page)["items"]]
        cursor = payload(page)["next_after_sequence"]

    assert seen == expected  # no gap, no duplicate, nothing past the cutoff
    assert all(s <= cutoff for s in seen)
    writer_conn.close()
    reader_conn.close()


def walk_history(
    reader: SqliteUnitOfWork, cursor: int, size: int
) -> tuple[list[int], int | None]:
    """Collect history sequences from `cursor` in pages of `size`; return them and the last cursor."""
    seen: list[int] = []
    while True:
        page = get_history(reader, READER, "acct-a", cursor, size)
        assert isinstance(page, Success)
        seen += [item["sequence"] for item in payload(page)["items"]]
        nxt = payload(page)["next_after_sequence"]
        if nxt is None:
            return seen, cursor
        cursor = nxt


def test_history_walk_with_writes_between_pages_neither_skips_nor_repeats(
    tmp_path: pathlib.Path,
):
    path = tmp_path / "abm.sqlite3"
    reader_conn = open_started(path)
    reader = SqliteUnitOfWork(reader_conn)
    now = clock()
    register(reader, now, "acct-a")
    register(reader, now, "acct-b")
    fund(reader, now, "acct-a", 1000)
    for n in range(1, 4):
        move(reader, now, n)

    # the reference: every history row committed before any concurrent write
    reference, _ = walk_history(reader, 0, 100)
    assert len(reference) == len(set(reference)) and reference == sorted(reference)

    prefix = get_history(reader, READER, "acct-a", 0, 2)
    assert isinstance(prefix, Success)
    seen = [item["sequence"] for item in payload(prefix)["items"]]
    cursor = payload(prefix)["next_after_sequence"]

    writer_conn = open_started(path)
    writer = SqliteUnitOfWork(writer_conn)
    move(writer, now, 4)

    if cursor is not None:
        rest, _ = walk_history(reader, cursor, 2)
        seen += rest

    # no row is skipped or repeated: the reference is a prefix, and any extra rows come after it
    assert seen[: len(reference)] == reference
    assert seen[len(reference) :] == sorted(seen[len(reference) :])
    assert len(seen) == len(set(seen))
    writer_conn.close()
    reader_conn.close()
