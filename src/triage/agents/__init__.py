"""The agent nodes of the triage workflow.

Each agent is a pure function ``TriageState -> partial TriageState``. They are
deliberately small and deterministic so the whole graph is replayable and
auditable. The optional LLM adapter (:mod:`triage.llm`) can enrich the summary,
but never changes routing or classification.
"""

from .classifier import classify_node
from .correlator import correlate_node
from .root_cause import root_cause_node
from .summarizer import summarize_node

__all__ = [
    "classify_node",
    "correlate_node",
    "root_cause_node",
    "summarize_node",
]
