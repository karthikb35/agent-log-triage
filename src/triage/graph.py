"""Wire the agents into a LangGraph ``StateGraph``.

The topology is fixed and small::

        classify
           |
     (any failures?) --no--> summarize --> END
           | yes
        correlate --> root_cause --> summarize --> END

A fixed DAG with deterministic nodes is what makes the workflow *replayable*:
same step-logs in, same triage out, every time.

If ``langgraph`` is not importable, :func:`run_pipeline` falls back to running
the exact same nodes in sequence -- the demo still works, offline, with zero
optional dependencies.
"""

from __future__ import annotations

from typing import Any

from .agents import (
    classify_node,
    correlate_node,
    root_cause_node,
    summarize_node,
)
from .schema import TriageState


def _route_after_classify(state: TriageState) -> str:
    """Skip correlation/root-cause entirely when there is nothing to triage."""

    return "correlate" if state.get("failures") else "summarize"


def build_graph() -> Any:
    """Build and compile the LangGraph workflow."""

    from langgraph.graph import END, StateGraph

    graph = StateGraph(TriageState)
    graph.add_node("classify", classify_node)
    graph.add_node("correlate", correlate_node)
    graph.add_node("root_cause", root_cause_node)
    graph.add_node("summarize", summarize_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {"correlate": "correlate", "summarize": "summarize"},
    )
    graph.add_edge("correlate", "root_cause")
    graph.add_edge("root_cause", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


def _run_sequential(state: TriageState) -> TriageState:
    """Deterministic fallback that mirrors the compiled graph exactly."""

    state = {**state, **classify_node(state)}
    if _route_after_classify(state) == "correlate":
        state = {**state, **correlate_node(state)}
        state = {**state, **root_cause_node(state)}
    state = {**state, **summarize_node(state)}
    return state


def run_pipeline(state: TriageState) -> TriageState:
    """Run the triage workflow, preferring LangGraph, falling back to sequential."""

    try:
        app = build_graph()
    except Exception:
        return _run_sequential(state)
    return app.invoke(state)
