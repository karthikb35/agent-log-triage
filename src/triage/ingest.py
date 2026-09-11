"""Ingest step-log JSON reports and extract the failing steps.

``pytest-resumable-stepmetrics`` writes one ``report.json`` per test with a
stable schema::

    {
      "run":   {"test_nodeid", "status", "retry_count", ...},
      "steps": [{"name", "attempt", "resumed", "status", "error"}, ...],
      "service_calls": [{"service", "endpoint", "status", ...}, ...]  # our custom record
    }

We only care about steps whose ``status == "failed"``. ``skipped_on_retry`` steps
are *successes from a previous attempt* -- never failures -- so they are ignored.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema import Failure

# Strip volatile tokens (ids, timestamps, hex, numbers) so that the same bug
# across many tests collapses to one signature -- the basis for correlation.
_VOLATILE = re.compile(
    r"""
    (0x[0-9a-fA-F]+)            # hex ids
    | ([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})  # uuids
    | (\b\d+(\.\d+)?\b)         # bare numbers / latencies
    """,
    re.VERBOSE,
)


def load_reports(path: str | Path) -> list[dict[str, Any]]:
    """Load every ``report.json`` under *path* (file or directory)."""

    p = Path(path)
    files: list[Path]
    if p.is_dir():
        # pytest-resumable-stepmetrics writes one JSON per test; the filename is
        # derived from the node id, so match any *.json under the directory.
        files = sorted(p.rglob("*.json"))
    else:
        files = [p]

    reports: list[dict[str, Any]] = []
    for f in files:
        try:
            reports.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            # A corrupt report should never crash a triage run over thousands.
            continue
    return reports


def _service_for(report: dict[str, Any]) -> str:
    """Infer the service under test from a custom record or the node id."""

    for call in report.get("service_calls", []):
        svc = call.get("service")
        if svc:
            return str(svc)

    nodeid = report.get("run", {}).get("test_nodeid", "")
    m = re.search(r"test_(\w+?)_flow", nodeid)
    return m.group(1) if m else "unknown"


def signature_of(error: str) -> str:
    """Normalise an error message into a stable grouping key."""

    collapsed = _VOLATILE.sub("#", error or "")
    return " ".join(collapsed.split())[:200]


def extract_failures(reports: list[dict[str, Any]]) -> list[Failure]:
    """Pull every genuinely-failed step out of the loaded reports."""

    failures: list[Failure] = []
    for report in reports:
        service = _service_for(report)
        nodeid = report.get("run", {}).get("test_nodeid", "<unknown>")
        for step in report.get("steps", []):
            if step.get("status") != "failed":
                continue
            error = step.get("error") or ""
            failures.append(
                Failure(
                    test_nodeid=nodeid,
                    step=step.get("name", "<step>"),
                    attempt=int(step.get("attempt", 1)),
                    error=error,
                    service=service,
                    resumed=bool(step.get("resumed", False)),
                    signature=signature_of(error),
                )
            )
    return failures
