"""MCP-style tools the agents are allowed to call.

In a full deployment these are exposed over the Model Context Protocol so any
MCP-aware client (the agents here, or an IDE, or another service) calls them
through one typed, sandboxed interface instead of reaching into databases or
APIs directly.

Each tool is:

* **pure / deterministic** -- same input, same output, so a triage run is replayable;
* **typed** -- a JSON-serialisable signature, ready to publish as an MCP tool schema;
* **side-effect free by default** -- ``open_ticket`` runs in dry-run unless told otherwise.

``server.py`` wraps these same functions in a real MCP server when the optional
``mcp`` extra is installed. The agents never know the difference.
"""

from __future__ import annotations

from typing import Any

# A static knowledge base mapping a failure category to a probable cause and the
# runbook a human would otherwise look up by hand. This is the institutional
# knowledge that turns a raw failure into an actionable incident.
_RUNBOOKS: dict[str, dict[str, str]] = {
    "timeout": {
        "probable_cause": "Downstream dependency slow or saturated; request exceeded the client deadline.",
        "runbook": "Check dependency p99 latency and saturation. Verify the client timeout budget and retry policy. Scale the dependency or raise the deadline.",
    },
    "dependency_unavailable": {
        "probable_cause": "A required downstream service was unreachable (connection refused / 5xx).",
        "runbook": "Confirm the dependency Pods are Ready and its Service endpoints are populated. Check NetworkPolicy and DNS. Roll back the last dependency deploy if it correlates.",
    },
    "assertion": {
        "probable_cause": "Observed response did not match the expected contract.",
        "runbook": "Diff the actual vs expected payload. Check for a breaking API change on the provider; run the contract tests for this pair.",
    },
    "business_rule": {
        "probable_cause": "A domain rule rejected the operation (e.g. payment declined, insufficient stock).",
        "runbook": "Usually expected behaviour, not an outage. Confirm test fixtures seed valid data; only escalate if the rejection rate spikes.",
    },
    "infrastructure": {
        "probable_cause": "Node, scheduler, or cluster-level disruption rather than app logic.",
        "runbook": "Check node conditions and Pod evictions/preemptions. Re-run; if it recurs on one node, cordon and drain it.",
    },
    "unknown": {
        "probable_cause": "No rule matched the error signature.",
        "runbook": "Route to a human. Add a rule for this signature once the root cause is known so it auto-triages next time.",
    },
}


def lookup_runbook(category: str) -> dict[str, str]:
    """Return the probable cause and remediation runbook for a category.

    MCP tool: ``lookup_runbook(category: str) -> {probable_cause, runbook}``.
    """

    return dict(_RUNBOOKS.get(category, _RUNBOOKS["unknown"]))


def query_failures(
    failures: list[dict[str, Any]],
    *,
    service: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Filter a failure list by service and/or category.

    MCP tool: ``query_failures(failures, service?, category?) -> failures``.
    """

    out = failures
    if service is not None:
        out = [f for f in out if f.get("service") == service]
    if category is not None:
        out = [f for f in out if f.get("category") == category]
    return list(out)


def open_ticket(
    incident: dict[str, Any],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Open (or, by default, simulate opening) a tracking ticket for an incident.

    MCP tool: ``open_ticket(incident, dry_run=True) -> ticket``. Side effects are
    gated behind ``dry_run=False`` so triage runs are safe by default.
    """

    ticket = {
        "title": f"[{incident.get('service')}] {incident.get('category')}: {incident.get('signature', '')[:80]}",
        "body": incident.get("runbook", ""),
        "count": incident.get("count", 0),
        "dry_run": dry_run,
    }
    if dry_run:
        ticket["status"] = "simulated"
    else:  # pragma: no cover - real integration is environment specific
        ticket["status"] = "created"
    return ticket


# The registry an MCP server iterates to publish tool schemas.
TOOLS = {
    "lookup_runbook": lookup_runbook,
    "query_failures": query_failures,
    "open_ticket": open_ticket,
}
