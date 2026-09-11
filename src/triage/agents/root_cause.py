"""Root-cause agent -- attach a probable cause and runbook to each incident.

This is where the agent *uses a tool* instead of hard-coding knowledge: it calls
the MCP ``lookup_runbook`` tool. An incident is considered ``auto_triaged`` when
we have a confident, non-"unknown" category -- those never reach a human.
"""

from __future__ import annotations

from ..mcp.tools import lookup_runbook
from ..schema import TriageState


def root_cause_node(state: TriageState) -> TriageState:
    """LangGraph node: enrich each incident with cause + runbook via MCP."""

    incidents = state.get("incidents", [])
    for incident in incidents:
        info = lookup_runbook(incident.category)
        incident.probable_cause = info["probable_cause"]
        incident.runbook = info["runbook"]
        incident.auto_triaged = incident.category != "unknown"
    return {"incidents": incidents}
