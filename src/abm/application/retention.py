"""Retention dates and their evaluation (FR-16, INV-12, DEC-0008, DEC-0012, DEC-0046).

Closure and each permitted late event after closure store `final_at` and `eligible_after`
seven calendar years later, in the same transaction. Nothing here deletes anything.
"""

from __future__ import annotations

from abm.domain.identifiers import format_instant, parse_instant
from abm.ports.storage import ReadTransaction, WriteTransaction

RETENTION_YEARS = 7


def seven_years_after(final_at: str) -> str:
    """Seven calendar years later; February 29 maps to February 28 in a non-leap year."""
    moment = parse_instant(final_at)
    try:
        target = moment.replace(year=moment.year + RETENTION_YEARS)
    except ValueError:  # February 29 in a non-leap target year
        target = moment.replace(year=moment.year + RETENTION_YEARS, day=28)
    return format_instant(target)


def finalize(tx: WriteTransaction, account_id: str, now: str) -> None:
    """Set or advance the retention dates once the account is closed (DEC-0046).

    Before closure both dates stay null. Call this after the event's own writes, so the
    account snapshot reflects closure when closure is the event.
    """
    account = tx.account_snapshot(account_id)
    if account is not None and account.status == "closed":
        tx.set_retention_dates(account_id, now, seven_years_after(now))


def evaluate(tx: ReadTransaction, account_id: str, at: str) -> dict[str, object] | None:
    """Read-only view of retention at one instant. eligible needs both dates, the seven-year
    period to have ended, and no legal hold (TEST-19). Nothing here deletes or changes data."""
    record = tx.get_retention(account_id)
    if record is None:
        return None
    eligible = (
        record.eligible_after is not None
        and at >= record.eligible_after
        and not record.legal_hold
    )
    return {
        "account_id": account_id,
        "final_at": record.final_at,
        "eligible_after": record.eligible_after,
        "legal_hold": record.legal_hold,
        "eligible": eligible,
    }
