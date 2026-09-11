"""Structured data model shared across the triage pipeline.

Everything the agents pass around is a plain dataclass or a ``TypedDict`` so the
whole workflow is serialisable, replayable, and deterministic. No hidden state.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict

# Failure categories the classifier can assign. Kept small and stable on
# purpose -- a fixed taxonomy is what makes automated triage auditable.
Category = Literal[
    "timeout",
    "dependency_unavailable",
    "assertion",
    "business_rule",
    "infrastructure",
    "unknown",
]

# Lifecycle of one asynchronous triage run as seen by a polling client.
# ``queued`` and ``running`` are transient; the last three are terminal.
RunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "dead_letter",
]


@dataclass
class Failure:
    """One failed step extracted from a step-log report."""

    test_nodeid: str
    step: str
    attempt: int
    error: str
    service: str
    resumed: bool = False
    # Filled in by the classifier agent.
    category: Category = "unknown"
    signature: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Incident:
    """A correlated group of failures that share a root cause."""

    service: str
    category: Category
    signature: str
    count: int
    tests: list[str] = field(default_factory=list)
    probable_cause: str = ""
    runbook: str = ""
    auto_triaged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TriageState(TypedDict, total=False):
    """The state object threaded through the LangGraph workflow.

    Each agent node reads the keys it needs and returns a partial update. Using
    ``total=False`` lets nodes return only the slice they own.
    """

    reports: list[dict[str, Any]]
    failures: list[Failure]
    incidents: list[Incident]
    summary: dict[str, Any]


@dataclass
class TriageTask:
    """The unit of work the API enqueues and a worker consumes.

    The report payload is *not* carried here -- it is stored once in the state
    backend under ``run_id`` and referenced, so the queue message stays tiny and
    the same run is replayable and idempotent on redelivery.
    """

    run_id: str
    submitted_at: float = field(default_factory=time.time)
    fail_under: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriageTask:
        return cls(
            run_id=str(data["run_id"]),
            submitted_at=float(data.get("submitted_at", time.time())),
            fail_under=float(data.get("fail_under", 0.5)),
        )


@dataclass
class TriageRunState:
    """The queryable status + result of a run, keyed by ``run_id``.

    This is what the API returns to a polling client. ``summary`` is ``None``
    until the run reaches ``succeeded``; ``error`` is set on a terminal failure.
    """

    run_id: str
    status: RunStatus = "queued"
    attempts: int = 0
    submitted_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    summary: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriageRunState:
        return cls(
            run_id=str(data["run_id"]),
            status=data.get("status", "queued"),  # type: ignore[arg-type]
            attempts=int(data.get("attempts", 0)),
            submitted_at=float(data.get("submitted_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            summary=data.get("summary"),
            error=data.get("error"),
        )
