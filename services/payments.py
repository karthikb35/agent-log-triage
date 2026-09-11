"""Mock of the TicketHub ``payments`` service (Python service in the real repo)."""

from __future__ import annotations

from typing import Any


class PaymentDeclined(RuntimeError):
    """Domain rejection -- a business rule, not an outage."""


class PaymentService:
    """In-memory stand-in for the payments API.

    ``authorize`` accepts a ``transient`` exception raised only on the first call
    for an order (a recoverable gateway blip). ``PaymentDeclined`` passed as the
    transient is *not* recoverable and is re-raised every attempt.
    """

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], int] = {}
        self.charges: dict[str, dict[str, Any]] = {}

    def _bump(self, key: tuple[str, str]) -> int:
        self._attempts[key] = self._attempts.get(key, 0) + 1
        return self._attempts[key]

    def authorize(
        self, order_id: str, amount: float, *, transient: Exception | None = None
    ) -> dict[str, Any]:
        if transient is not None:
            # A declined card never clears on retry; a gateway blip does.
            if isinstance(transient, PaymentDeclined) or self._bump(("auth", order_id)) == 1:
                raise transient
        self.charges[order_id] = {"amount": amount, "status": "authorized"}
        return dict(self.charges[order_id])

    def capture(self, order_id: str) -> dict[str, Any]:
        self.charges[order_id]["status"] = "captured"
        return dict(self.charges[order_id])
