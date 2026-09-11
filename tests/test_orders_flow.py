"""Order-placement flow tests against the mock orders service.

Every case runs a 3-step saga: create order -> reserve inventory -> confirm.
Some cases inject a **transient** fault on the reserve step so it fails on the
first attempt and recovers on the second. That produces:

* a ``failed`` step on attempt 1 (triage input),
* ``skipped_on_retry`` for the already-passed ``create order`` step,
* a green test overall.

The variety of injected errors (timeout / connection / unclassified) is what
gives the triage engine a realistic mix to classify and correlate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from services.orders import OrderService

from .records import ServiceCall


@dataclass
class Case:
    id: str
    item: str
    qty: int
    transient: Callable[[], Exception] | None


def _timeout() -> Exception:
    return TimeoutError("reserve inventory timed out after 2s (context deadline exceeded)")


def _refused() -> Exception:
    return ConnectionError("connection refused to inventory.tickethub.svc:8080")


def _weird() -> Exception:
    return RuntimeError("unclassified anomaly 0x9f while reserving stock")


# High-volume-ish, deterministic mix. Clean cases add passing volume; the rest
# inject transient faults across three error families.
ORDER_CASES: list[Case] = (
    [Case(f"ord-clean-{i}", "seat-A", 2, None) for i in range(6)]
    + [Case(f"ord-timeout-{i}", "seat-B", 1, _timeout) for i in range(4)]
    + [Case(f"ord-refused-{i}", "seat-C", 3, _refused) for i in range(4)]
    + [Case(f"ord-weird-{i}", "seat-D", 1, _weird) for i in range(2)]
)


@pytest.mark.parametrize("case", ORDER_CASES, ids=lambda c: c.id)
def test_orders_flow(steplog, case: Case) -> None:
    svc = OrderService()

    def run() -> None:
        steplog.reset_attempt()

        # Idempotent: created once, skipped on retry so we don't double-create.
        def create() -> None:
            svc.create_order(case.id, case.item, case.qty)
            steplog.record(ServiceCall("orders", "/api/orders", "ok", 5.0))

        steplog.run("create order", create)

        # Stateful: re-runs every attempt. This is where the transient fault bites.
        with steplog("reserve inventory"):
            try:
                svc.reserve_inventory(
                    case.id, case.item, case.qty,
                    transient=case.transient() if case.transient else None,
                )
                steplog.record(ServiceCall("orders", "/api/orders/reserve", "ok", 7.5))
            except Exception:
                steplog.record(ServiceCall("orders", "/api/orders/reserve", "error", 7.5))
                raise

        with steplog("confirm order"):
            svc.confirm(case.id)
            steplog.record(ServiceCall("orders", "/api/orders/confirm", "ok", 3.0))

    for attempt in range(2):
        try:
            run()
            return
        except Exception:
            if attempt == 1:
                raise
