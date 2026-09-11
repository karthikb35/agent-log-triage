"""Redis-backed state store for asynchronous triage runs.

Object storage is intentionally *not* a dependency: at 10--15 KB per report
bundle the whole payload lives in Redis under ``run_id`` with a short TTL, which
keeps the deployment to a single stateful component. Three key families:

* ``triage:reports:{run_id}`` -- the raw report bundle (deleted once consumed);
* ``triage:run:{run_id}``     -- the queryable :class:`TriageRunState` a client polls;
* ``triage:idem:{key}``       -- maps a client idempotency key to an existing run.

Everything carries a TTL so the store self-cleans: there is no durability
requirement beyond the few minutes a client needs to collect its result.
"""

from __future__ import annotations

import json
from typing import Any

from redis import Redis

from .schema import RunStatus, TriageRunState

# TTLs (seconds). The run-state key must outlive queue + processing + the
# client's poll window; the report blob only needs to survive until a worker
# consumes it, and is deleted on success regardless.
_RUN_TTL = 900          # 15 min
_REPORT_TTL = 600       # 10 min
_IDEM_TTL = 900         # 15 min

_RUN_PREFIX = "triage:run:"
_REPORT_PREFIX = "triage:reports:"
_IDEM_PREFIX = "triage:idem:"
_TICKET_PREFIX = "triage:ticket:"


class RedisStore:
    """Thin, typed wrapper over the Redis keys the triage flow uses."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    # -- report payloads ---------------------------------------------------

    def put_reports(self, run_id: str, reports: list[dict[str, Any]]) -> None:
        self._r.set(
            _REPORT_PREFIX + run_id,
            json.dumps(reports, separators=(",", ":")),
            ex=_REPORT_TTL,
        )

    def get_reports(self, run_id: str) -> list[dict[str, Any]] | None:
        raw = self._r.get(_REPORT_PREFIX + run_id)
        if raw is None:
            return None
        return json.loads(raw)

    def delete_reports(self, run_id: str) -> None:
        self._r.delete(_REPORT_PREFIX + run_id)

    # -- run state ---------------------------------------------------------

    def put_run(self, state: TriageRunState) -> None:
        self._r.set(
            _RUN_PREFIX + state.run_id,
            json.dumps(state.to_dict(), separators=(",", ":")),
            ex=_RUN_TTL,
        )

    def get_run(self, run_id: str) -> TriageRunState | None:
        raw = self._r.get(_RUN_PREFIX + run_id)
        if raw is None:
            return None
        return TriageRunState.from_dict(json.loads(raw))

    def set_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
        attempts: int | None = None,
    ) -> TriageRunState | None:
        """Idempotently patch a run's status; safe to call on redelivery."""

        import time

        state = self.get_run(run_id)
        if state is None:
            return None
        state.status = status
        state.updated_at = time.time()
        if summary is not None:
            state.summary = summary
        if error is not None:
            state.error = error
        if attempts is not None:
            state.attempts = attempts
        self.put_run(state)
        return state

    # -- idempotency -------------------------------------------------------

    def claim_idempotency_key(self, key: str, run_id: str) -> str:
        """Bind *key* to *run_id* once; return the winning run_id.

        Uses ``SET NX`` so concurrent duplicate submits collapse onto the first
        run instead of enqueuing the same work twice.
        """

        won = self._r.set(_IDEM_PREFIX + key, run_id, nx=True, ex=_IDEM_TTL)
        if won:
            return run_id
        existing = self._r.get(_IDEM_PREFIX + key)
        return existing.decode() if isinstance(existing, bytes) else str(existing)

    # -- ticket dedupe -----------------------------------------------------

    def claim_ticket(self, dedupe_key: str) -> bool:
        """Claim the right to open one ticket for *dedupe_key*.

        Returns ``True`` exactly once per key (via ``SET NX``); redelivery of the
        same run finds the key already set and returns ``False``, so an
        at-least-once task never opens a duplicate ticket.
        """

        return bool(self._r.set(_TICKET_PREFIX + dedupe_key, "1", nx=True, ex=_RUN_TTL))
