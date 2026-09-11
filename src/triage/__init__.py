"""The triage engine package.

A deterministic multi-agent workflow that ingests high-volume structured
step-logs (produced by ``pytest-resumable-stepmetrics``) and triages the
failures into a small set of actionable incidents.
"""

from .schema import Failure, Incident, TriageState  # noqa: F401

__all__ = ["Failure", "Incident", "TriageState"]
__version__ = "0.1.0"
