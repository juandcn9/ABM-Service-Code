"""Trusted caller context: identity, role, and scope come only from here, never a payload (INV-13)."""

from __future__ import annotations

from dataclasses import dataclass

from abm.domain.identifiers import opaque_id


@dataclass(frozen=True)
class CallerContext:
    """Facts injected by the trusted harness or ingress. Values are validated opaque strings.

    account_scope is the one account an account_reader may read; other roles carry none.
    """

    caller_id: str
    role: str
    correlation_id: str
    account_scope: str | None = None

    def __post_init__(self) -> None:
        opaque_id(self.caller_id)
        opaque_id(self.role)
        opaque_id(self.correlation_id)
        if self.account_scope is not None:
            opaque_id(self.account_scope)
