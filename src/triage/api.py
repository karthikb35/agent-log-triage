"""The asynchronous triage API.

Contract (internal, cluster-only)::

    POST /v1/triage/runs             -> 202 {run_id, poll_url}
    GET  /v1/triage/runs/{run_id}    -> {run_id, status, ...}
    GET  /v1/triage/runs/{id}/result -> {run_id, summary}   (404 until terminal)
    GET  /healthz  /readyz

The API never runs the pipeline: it validates, stashes the report bundle in
Redis under a fresh ``run_id``, enqueues a tiny task, and returns immediately.
Workers do the work; clients poll by ``run_id``.  This keeps a pytest client's
HTTP call short and lets triage scale independently behind the queue.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from .queue import TaskQueue
from .runtime import Settings, get_settings, redis_from_env
from .schema import TriageRunState, TriageTask
from .store import RedisStore


class SubmitRequest(BaseModel):
    reports: list[dict] = Field(..., description="Raw pytest step-log report bundles.")
    fail_under: float = Field(0.5, ge=0.0, le=1.0)


class SubmitResponse(BaseModel):
    run_id: str
    status: str
    poll_url: str


class StatusResponse(BaseModel):
    run_id: str
    status: str
    attempts: int
    error: str | None = None


class ResultResponse(BaseModel):
    run_id: str
    summary: dict


def _deps(settings: Settings) -> tuple[RedisStore, TaskQueue]:
    client = redis_from_env(settings)
    return RedisStore(client), TaskQueue(client)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store, queue = _deps(settings)
    # Create the consumer group up front so the very first submit can enqueue
    # even before any worker has started (and regardless of ASGI startup events).
    try:
        queue.ensure_group()
    except Exception:  # noqa: BLE001 -- readiness probe surfaces a dead Redis
        pass
    app = FastAPI(title="Agentic Log Triage API", version="1.0.0")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if settings.api_token is None:
            return
        expected = f"Bearer {settings.api_token}"
        if authorization != expected:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token")

    @app.post(
        "/v1/triage/runs",
        response_model=SubmitResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit(
        body: SubmitRequest,
        response: Response,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: None = Depends(require_token),
    ) -> SubmitResponse:
        # Back-pressure: shed load before Redis is overwhelmed so clients retry.
        if queue.pending_count() >= settings.max_pending:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "triage backlog full; retry later"
            )

        run_id = str(uuid.uuid4())
        if idempotency_key:
            run_id = store.claim_idempotency_key(idempotency_key, run_id)
            existing = store.get_run(run_id)
            if existing is not None:
                # Duplicate submit collapsed onto the in-flight run.
                response.status_code = status.HTTP_202_ACCEPTED
                return SubmitResponse(
                    run_id=run_id,
                    status=existing.status,
                    poll_url=f"/v1/triage/runs/{run_id}",
                )

        store.put_reports(run_id, body.reports)
        store.put_run(TriageRunState(run_id=run_id, status="queued"))
        queue.publish(TriageTask(run_id=run_id, fail_under=body.fail_under))
        return SubmitResponse(
            run_id=run_id, status="queued", poll_url=f"/v1/triage/runs/{run_id}"
        )

    @app.get("/v1/triage/runs/{run_id}", response_model=StatusResponse)
    def get_status(run_id: str) -> StatusResponse:
        state = store.get_run(run_id)
        if state is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown or expired run")
        return StatusResponse(
            run_id=state.run_id,
            status=state.status,
            attempts=state.attempts,
            error=state.error,
        )

    @app.get("/v1/triage/runs/{run_id}/result", response_model=ResultResponse)
    def get_result(run_id: str) -> ResultResponse:
        state = store.get_run(run_id)
        if state is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown or expired run")
        if state.status != "succeeded" or state.summary is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"run not ready (status={state.status})"
            )
        return ResultResponse(run_id=run_id, summary=state.summary)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        try:
            redis_from_env(settings).ping()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"redis unavailable: {exc}"
            )
        return {"status": "ready"}

    return app
