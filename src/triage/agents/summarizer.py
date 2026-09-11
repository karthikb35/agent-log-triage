"""Summarizer agent -- turn incidents into a report and the headline metric.

The metric that matters: **triage automation rate** = share of failures that were
auto-triaged to a known root cause and therefore never needed a human. That is the
concrete, defensible version of "reduced operational triage effort by 50%".

We also estimate minutes saved using a simple, transparent model:
``minutes_saved = auto_triaged_failures * MANUAL_MINUTES_PER_FAILURE``.
"""

from __future__ import annotations

from ..llm import maybe_narrate
from ..schema import TriageState

# How long a human typically spends triaging one failure by hand (reading logs,
# finding the runbook, deciding severity). Conservative and configurable.
MANUAL_MINUTES_PER_FAILURE = 8


def summarize_node(state: TriageState) -> TriageState:
    """LangGraph node: compute metrics and assemble the triage summary."""

    failures = state.get("failures", [])
    incidents = state.get("incidents", [])

    total = len(failures)
    auto_incident_keys = {
        (i.service, i.category, i.signature) for i in incidents if i.auto_triaged
    }
    auto_failures = sum(
        1
        for f in failures
        if (f.service, f.category, f.signature) in auto_incident_keys
    )

    automation_rate = (auto_failures / total) if total else 1.0
    minutes_saved = auto_failures * MANUAL_MINUTES_PER_FAILURE

    summary: dict = {
        "total_failures": total,
        "total_incidents": len(incidents),
        "auto_triaged_failures": auto_failures,
        "automation_rate": round(automation_rate, 3),
        "estimated_minutes_saved": minutes_saved,
        "needs_human": [i.to_dict() for i in incidents if not i.auto_triaged],
        "incidents": [i.to_dict() for i in incidents],
    }
    # Optional LLM narration -- purely additive, never affects the numbers above.
    summary["narrative"] = maybe_narrate(summary)
    return {"summary": summary}
