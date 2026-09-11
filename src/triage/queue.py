"""Redis Streams work queue for triage tasks.

A Redis Stream with a consumer group gives us exactly the at-least-once
semantics this pipeline needs without standing up Kafka:

* ``XADD``        -- the API enqueues a :class:`TriageTask` (just the ``run_id``);
* ``XREADGROUP``  -- a worker in group ``triage-workers`` claims the next task;
* ``XACK``        -- the worker acknowledges *after* the result is persisted;
* ``XAUTOCLAIM``  -- a worker reclaims tasks abandoned by a crashed peer.

Because ack is the last step, a crash before ack simply redelivers the task; the
pipeline is deterministic and the store upserts on ``run_id``, so reprocessing is
safe.  KEDA scales the worker Deployment on this stream's pending-entry count.
"""

from __future__ import annotations

from typing import Any

from redis import Redis
from redis.exceptions import ResponseError

from .schema import TriageTask

STREAM = "triage:tasks"
GROUP = "triage-workers"

# A task reclaimed after this many ms of no ack is assumed orphaned by a dead
# worker and redelivered to a healthy one.
_MIN_IDLE_MS = 60_000
# Give up on a poison message after this many deliveries.
MAX_DELIVERIES = 3


class TaskQueue:
    """Producer/consumer over a single Redis Stream with one consumer group."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    def ensure_group(self) -> None:
        """Create the consumer group, tolerating races and re-runs."""

        try:
            self._r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    # -- producer ----------------------------------------------------------

    def publish(self, task: TriageTask) -> str:
        return self._r.xadd(STREAM, {"run_id": task.run_id})

    def pending_count(self) -> int:
        """Entries delivered but not yet acked -- the KEDA scaling signal."""

        try:
            summary = self._r.xpending(STREAM, GROUP)
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                return 0
            raise
        return int(summary["pending"]) if summary else 0

    # -- consumer ----------------------------------------------------------

    def read(
        self, consumer: str, *, count: int = 1, block_ms: int = 5000
    ) -> list[tuple[str, str, int]]:
        """Claim new tasks. Returns ``(message_id, run_id, delivery_count)``."""

        resp = self._r.xreadgroup(
            GROUP, consumer, {STREAM: ">"}, count=count, block=block_ms
        )
        return self._flatten(resp)

    def reclaim(self, consumer: str, *, count: int = 10) -> list[tuple[str, str, int]]:
        """Take over tasks abandoned by a crashed worker (``XAUTOCLAIM``)."""

        _, messages, _ = self._r.xautoclaim(
            STREAM, GROUP, consumer, min_idle_time=_MIN_IDLE_MS, count=count
        )
        return self._decode_messages(messages)

    def ack(self, message_id: str) -> None:
        self._r.xack(STREAM, GROUP, message_id)

    def delivery_count(self, message_id: str) -> int:
        info = self._r.xpending_range(STREAM, GROUP, message_id, message_id, 1)
        return int(info[0]["times_delivered"]) if info else 1

    # -- helpers -----------------------------------------------------------

    def _flatten(self, resp: Any) -> list[tuple[str, str, int]]:
        if not resp:
            return []
        out: list[tuple[str, str, int]] = []
        for _stream, messages in resp:
            out.extend(self._decode_messages(messages))
        return out

    def _decode_messages(self, messages: Any) -> list[tuple[str, str, int]]:
        out: list[tuple[str, str, int]] = []
        for message_id, fields in messages:
            mid = message_id.decode() if isinstance(message_id, bytes) else message_id
            run_id = fields.get(b"run_id") or fields.get("run_id")
            if isinstance(run_id, bytes):
                run_id = run_id.decode()
            out.append((mid, str(run_id), self.delivery_count(mid)))
        return out
