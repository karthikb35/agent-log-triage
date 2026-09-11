"""Optional LLM adapter.

The platform is deterministic by default: with no configuration it returns a
templated narrative and the numbers are computed by pure Python. Set
``TRIAGE_LLM=1`` (and install the ``llm`` extra + provide an API key) to have a
real model write the human-readable narrative. The LLM only ever *describes* the
already-computed triage -- it never classifies, routes, or changes a metric.
That separation is what keeps "agentic" from meaning "non-deterministic".
"""

from __future__ import annotations

import os
from typing import Any


def _template_narrative(summary: dict[str, Any]) -> str:
    total = summary["total_failures"]
    if total == 0:
        return "No failures found. All step-logs are green."
    rate = summary["automation_rate"] * 100
    saved = summary["estimated_minutes_saved"]
    human = len(summary["needs_human"])
    top = summary["incidents"][0] if summary["incidents"] else None
    lead = (
        f"Triaged {total} failing steps into {summary['total_incidents']} incidents. "
        f"{rate:.0f}% were auto-resolved to a known root cause "
        f"(~{saved} min of manual triage avoided). "
        f"{human} incident(s) need a human."
    )
    if top:
        lead += (
            f" Top incident: {top['count']}x {top['category']} in "
            f"'{top['service']}' -- {top['probable_cause']}"
        )
    return lead


def maybe_narrate(summary: dict[str, Any]) -> str:
    """Return a narrative for the summary.

    Deterministic template unless ``TRIAGE_LLM`` is truthy and the optional
    dependencies/credentials are present.
    """

    if not os.getenv("TRIAGE_LLM"):
        return _template_narrative(summary)

    try:  # pragma: no cover - only runs when explicitly enabled
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(model=os.getenv("TRIAGE_LLM_MODEL", "gpt-4o-mini"), temperature=0)
        prompt = [
            SystemMessage(content="You summarise CI failure triage for on-call engineers. Be terse and factual. Do not invent numbers."),
            HumanMessage(content=str(summary)),
        ]
        return model.invoke(prompt).content
    except Exception:
        # Any failure (missing key, offline, bad extra) degrades gracefully to
        # the deterministic template. The platform must never hard-fail on the LLM.
        return _template_narrative(summary)
