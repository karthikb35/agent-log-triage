"""Mock of the TicketHub ``orders`` service (Go service in the real repo)."""

from __future__ import annotations

from typing import Any


class OrderService:
    """In-memory stand-in for the orders API.

    ``reserve_inventory`` accepts a ``transient`` exception that is raised only on
    the *first* call for a given order, then clears -- simulating a downstream
    inventory blip that a retry recovers from.
    """

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], int] = {}
        self.orders: dict[str, dict[str, Any]] = {}

    def _bump(self, key: tuple[str, str]) -> int:
        self._attempts[key] = self._attempts.get(key, 0) + 1
        return self._attempts[key]

    def create_order(self, order_id: str, item: str, qty: int) -> dict[str, Any]:
        self.orders[order_id] = {"item": item, "qty": qty, "status": "created"}
        return dict(self.orders[order_id])

    def reserve_inventory(
        self, order_id: str, item: str, qty: int, *, transient: Exception | None = None
    ) -> dict[str, Any]:
        if transient is not None and self._bump(("reserve", order_id)) == 1:
            raise transient
        self.orders[order_id]["reserved"] = qty
        return {"order_id": order_id, "reserved": qty}

    def confirm(self, order_id: str) -> dict[str, Any]:
        self.orders[order_id]["status"] = "confirmed"
        return dict(self.orders[order_id])
