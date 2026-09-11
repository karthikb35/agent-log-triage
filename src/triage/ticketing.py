"""Idempotent ticket opening -- the one deliberate side effect of triage.

Ticket creation lives *outside* the deterministic LangGraph pipeline, in the
worker, so the graph stays pure and replayable. Correctness under at-least-once
delivery comes from a per-run dedupe key: a ticket for a given incident is
claimed via ``SET NX`` keyed on ``run_id + incident identity``, so a redelivered
task finds the key already set and skips it instead of opening a duplicate.

One incident yields at most one ticket -- the same de-duplication the correlator
already applies to failures, carried through to the tracking system.
"""

from __future__ import annotations

from typing import Any

from .mcp.tools import open_ticket
from .store import RedisStore


def _dedupe_key(run_id: str, incident: dict[str, Any]) -> str:
    return ":".join(
        (
            run_id,
            str(incident.get("service", "")),
            str(incident.get("category", "")),
            str(incident.get("signature", "")),
        )
    )


def open_incident_tickets(
    run_id: str,
    summary: dict[str, Any],
    store: RedisStore,
    *,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Open one ticket per incident in *summary*, guarded against duplicates.

    Returns the tickets opened *by this call*; incidents already ticketed for
    this run (e.g. on redelivery) are skipped and not returned.
    """

    opened: list[dict[str, Any]] = []
    for incident in summary.get("incidents", []):
        if not store.claim_ticket(_dedupe_key(run_id, incident)):
            continue
        ticket = open_ticket(incident, dry_run=dry_run)
        ticket["run_id"] = run_id
        opened.append(ticket)
    return opened
