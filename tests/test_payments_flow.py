"""Payment-authorization flow tests against the mock payments service.

Same shape as the orders flow: authorize -> capture, with a transient gateway
fault injected on ``authorize`` for some cases. Adds ``payments`` failures so the
triage engine has more than one service to correlate across.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from services.payments import PaymentService

from .records import ServiceCall


@dataclass
class Case:
    id: str
    amount: float
    transient: Callable[[], Exception] | None


def _gateway_timeout() -> Exception:
    return TimeoutError("payment gateway deadline exceeded after 3s")


def _bad_gateway() -> Exception:
    return ConnectionError("502 Bad Gateway from card-network upstream")


def _weird() -> Exception:
    return RuntimeError("nonce mismatch anomaly in settlement path")


PAYMENT_CASES: list[Case] = (
    [Case(f"pay-clean-{i}", 49.99, None) for i in range(6)]
    + [Case(f"pay-timeout-{i}", 79.00, _gateway_timeout) for i in range(3)]
    + [Case(f"pay-502-{i}", 120.00, _bad_gateway) for i in range(3)]
    + [Case(f"pay-weird-{i}", 15.00, _weird) for i in range(1)]
)


@pytest.mark.parametrize("case", PAYMENT_CASES, ids=lambda c: c.id)
def test_payments_flow(steplog, case: Case) -> None:
    svc = PaymentService()

    def run() -> None:
        steplog.reset_attempt()

        with steplog("authorize payment"):
            try:
                svc.authorize(
                    case.id, case.amount,
                    transient=case.transient() if case.transient else None,
                )
                steplog.record(ServiceCall("payments", "/api/payments/authorize", "ok", 9.0))
            except Exception:
                steplog.record(ServiceCall("payments", "/api/payments/authorize", "error", 9.0))
                raise

        with steplog("capture payment"):
            svc.capture(case.id)
            steplog.record(ServiceCall("payments", "/api/payments/capture", "ok", 4.0))

    for attempt in range(2):
        try:
            run()
            return
        except Exception:
            if attempt == 1:
                raise
