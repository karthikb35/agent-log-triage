"""Correlator agent -- collapse many failures into a few incidents.

The whole point of triage is de-duplication: 200 failing steps caused by one
dead dependency should be *one* incident, not 200 tickets. We group by
``(service, category, signature)`` -- the signature already has volatile tokens
stripped during ingest, so the same bug across many tests lands in one bucket.
"""

from __future__ import annotations

from ..schema import Incident, TriageState


def correlate_node(state: TriageState) -> TriageState:
    """LangGraph node: group failures into correlated incidents."""

    buckets: dict[tuple[str, str, str], Incident] = {}
    for f in state.get("failures", []):
        key = (f.service, f.category, f.signature)
        incident = buckets.get(key)
        if incident is None:
            incident = Incident(
                service=f.service,
                category=f.category,
                signature=f.signature,
                count=0,
            )
            buckets[key] = incident
        incident.count += 1
        if f.test_nodeid not in incident.tests:
            incident.tests.append(f.test_nodeid)

    # Most impactful incidents first.
    incidents = sorted(buckets.values(), key=lambda i: i.count, reverse=True)
    return {"incidents": incidents}
