"""The long-running triage worker.

One worker is a member of the ``triage-workers`` consumer group. Its loop:

1. reclaim any tasks abandoned by a crashed peer (``XAUTOCLAIM``);
2. claim the next new task (``XREADGROUP``);
3. load the report bundle, run the deterministic pipeline;
4. **persist the result, then ack** -- never the other way round;
5. drop a poison message to ``dead_letter`` after :data:`MAX_DELIVERIES` tries.

Because ack is last and the store upserts on ``run_id``, a crash mid-run just
redelivers the task and the identical pipeline reproduces the identical result.
Workers are stateless and horizontally scaled by KEDA on the stream's pending
count; keeping a warm floor of replicas avoids cold-start latency.
"""

from __future__ import annotations

import logging
import signal
from types import FrameType

from .graph import run_pipeline
from .ingest import extract_failures
from .queue import MAX_DELIVERIES, TaskQueue
from .runtime import Settings, get_settings, redis_from_env
from .store import RedisStore
from .ticketing import open_incident_tickets

log = logging.getLogger("triage.worker")


class Worker:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        client = redis_from_env(self._settings)
        self._store = RedisStore(client)
        self._queue = TaskQueue(client)
        self._name = self._settings.worker_name
        self._running = True

    def _handle_task(self, message_id: str, run_id: str, deliveries: int) -> None:
        # Poison-message guard: a task that has failed repeatedly is parked in a
        # terminal state so a polling client stops waiting on it.
        if deliveries > MAX_DELIVERIES:
            self._store.set_status(
                run_id,
                "dead_letter",
                error=f"exceeded {MAX_DELIVERIES} delivery attempts",
                attempts=deliveries,
            )
            self._queue.ack(message_id)
            log.warning("dead-lettered run_id=%s after %d tries", run_id, deliveries)
            return

        reports = self._store.get_reports(run_id)
        if reports is None:
            # The blob expired or the run is unknown -- nothing to do but ack so
            # the message doesn't loop forever.
            self._store.set_status(run_id, "failed", error="report payload missing")
            self._queue.ack(message_id)
            return

        self._store.set_status(run_id, "running", attempts=deliveries)
        try:
            failures = extract_failures(reports)
            result = run_pipeline({"reports": reports, "failures": failures})
            summary = result["summary"]
            # Ticket opening is a side effect, so it runs here (not in the graph)
            # and is idempotent across redelivery via a per-run dedupe key.
            if self._settings.open_tickets:
                summary["tickets"] = open_incident_tickets(
                    run_id,
                    summary,
                    self._store,
                    dry_run=self._settings.tickets_dry_run,
                )
            self._store.set_status(run_id, "succeeded", summary=summary)
            self._store.delete_reports(run_id)
        except Exception as exc:  # noqa: BLE001 -- persist, don't crash the loop
            self._store.set_status(run_id, "failed", error=str(exc))
            log.exception("run_id=%s failed", run_id)
        finally:
            # Ack last: a crash before this point redelivers the (idempotent) task.
            self._queue.ack(message_id)

    def run_forever(self) -> None:
        self._queue.ensure_group()
        self._install_signal_handlers()
        log.info("worker %s started", self._name)
        while self._running:
            for message_id, run_id, deliveries in self._queue.reclaim(self._name):
                self._handle_task(message_id, run_id, deliveries)
            for message_id, run_id, deliveries in self._queue.read(self._name):
                self._handle_task(message_id, run_id, deliveries)
        log.info("worker %s stopped", self._name)

    def _install_signal_handlers(self) -> None:
        def _stop(_sig: int, _frame: FrameType | None) -> None:
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)


def main() -> None:  # pragma: no cover - runtime entrypoint
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Worker().run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
