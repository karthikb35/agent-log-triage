"""A custom step-log record.

Registering a dataclass with ``@steplog_record`` makes ``pytest-resumable-stepmetrics``
emit it as its own array in ``report.json`` and render it as a per-attempt table
in the terminal -- zero extra wiring. The triage ingest reads the ``service_calls``
array to attribute each failure to a service.
"""

from __future__ import annotations

from dataclasses import dataclass

from pytest_resumable_stepmetrics import steplog_record


@steplog_record(key="service_calls", stamp=("attempt",))
@dataclass
class ServiceCall:
    service: str
    endpoint: str
    status: str  # "ok" | "error"
    duration_ms: float
    attempt: int = 1  # stamped automatically from the steplog context
