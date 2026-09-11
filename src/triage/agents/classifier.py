"""Classifier agent -- assign a stable category to every failure.

Rule-based and ordered: the first matching rule wins, so the outcome is
deterministic and easy to audit. Each rule is a (category, keywords, confidence)
triple. Adding institutional knowledge = adding a rule, not retraining a model.
"""

from __future__ import annotations

from ..schema import Category, Failure, TriageState

# Ordered most-specific to least. Order matters: a "connection timed out" is a
# timeout, checked before the generic dependency rule.
_RULES: list[tuple[Category, tuple[str, ...], float]] = [
    ("timeout", ("timeout", "timed out", "deadline exceeded", "context deadline"), 0.9),
    ("dependency_unavailable",
     ("connection refused", "connection reset", "unreachable", "no route",
      "econnrefused", "503", "502", "504", "service unavailable"), 0.85),
    ("business_rule",
     ("declined", "insufficient", "out of stock", "rejected", "not allowed",
      "invalid card", "payment failed"), 0.8),
    ("assertion",
     ("assertionerror", "assert ", "expected", "did not match", "does not equal"), 0.75),
    ("infrastructure",
     ("evicted", "oomkilled", "preempted", "node not ready", "disruption"), 0.8),
]


def classify_one(failure: Failure) -> Failure:
    """Return *failure* with ``category`` and ``confidence`` filled in."""

    text = failure.error.lower()
    for category, keywords, confidence in _RULES:
        if any(k in text for k in keywords):
            failure.category = category
            failure.confidence = confidence
            return failure
    failure.category = "unknown"
    failure.confidence = 0.0
    return failure


def classify_node(state: TriageState) -> TriageState:
    """LangGraph node: classify every failure in the state."""

    failures = [classify_one(f) for f in state.get("failures", [])]
    return {"failures": failures}
