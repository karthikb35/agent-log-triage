# Testing & Step-Logs

The triage engine is only as good as the logs it eats. Those logs come from a
`pytest` suite instrumented with
[`pytest-resumable-stepmetrics`](https://pypi.org/project/pytest-resumable-stepmetrics/).

## What the suite tests

Two **mock** services standing in for the real TicketHub microservices:

- [`services/orders.py`](https://github.com/karthikb35/agentic-log-triage/blob/main/services/orders.py) —
  a 3-step saga: *create order → reserve inventory → confirm*.
- [`services/payments.py`](https://github.com/karthikb35/agentic-log-triage/blob/main/services/payments.py) —
  *authorize → capture*.

Each test injects a **transient fault** on one step so it fails on attempt 1 and
recovers on attempt 2 — the exact shape resume-on-retry tracking is built for.

## The `steplog` fixture

Every logical step is wrapped so it gets a name, status, duration, and attempt:

```python
def test_orders_flow(steplog, case):
    svc = OrderService()

    def run():
        steplog.reset_attempt()                 # first line of each attempt

        # Idempotent → skipped_on_retry (never double-creates)
        steplog.run("create order", lambda: svc.create_order(...))

        # Stateful → re-runs each attempt; this is where the fault bites
        with steplog("reserve inventory"):
            svc.reserve_inventory(..., transient=case.transient())

        with steplog("confirm order"):
            svc.confirm(...)

    for attempt in range(2):                     # any retry mechanism works
        try:
            run(); return
        except Exception:
            if attempt == 1: raise
```

Result for a transient case:

| Step | Attempt | Status |
| --- | --- | --- |
| create order | 1 | passed |
| reserve inventory | 1 | **failed** |
| create order | 2 | `skipped_on_retry` |
| reserve inventory | 2 | passed |
| confirm order | 2 | passed |

The **attempt-1 failure** is what the triage engine consumes; the test itself is
green.

## Custom records — attributing failures to a service

A dataclass registered with `@steplog_record` becomes its own array in the JSON:

```python
@steplog_record(key="service_calls", stamp=("attempt",))
@dataclass
class ServiceCall:
    service: str
    endpoint: str
    status: str
    duration_ms: float
    attempt: int = 1
```

`ingest.py` reads `service_calls` to attribute each failure to `orders` or
`payments`. The `attempt` field is stamped automatically.

## Producing logs and triaging them

```bash
pytest --steplog-json --steplog-json-dir=reports   # write one JSON per test
triage run --reports reports --format md --fail-under 0.5
```

## Rich sample data

[`examples/sample_steplogs/`](https://github.com/karthikb35/agentic-log-triage/tree/main/examples/sample_steplogs)
contains canned reports covering the **full taxonomy** — including a permanent
`dependency_unavailable` outage and an `unknown` failure that routes to a human — so
you can run `triage run --reports examples/sample_steplogs` with no test run at all.
