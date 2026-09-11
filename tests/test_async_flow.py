"""Integration test for the asynchronous triage path (API + queue + worker).

Uses an in-process fake Redis so the full submit -> enqueue -> process -> poll
cycle runs with no external services. Both the API and the worker are pointed at
the *same* fake Redis server so a task published by one is consumed by the other.
"""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from triage import api as api_module
from triage import worker as worker_module
from triage.api import create_app
from triage.runtime import Settings
from triage.worker import Worker

_TIMEOUT_REPORT = {
    "run": {"test_nodeid": "tests/test_payments_flow.py::test_payments_flow", "status": "failed"},
    "steps": [
        {"name": "charge", "attempt": 1, "status": "failed", "error": "deadline exceeded after 30s"}
    ],
    "service_calls": [{"service": "payments", "endpoint": "/charge", "status": 504}],
}


@pytest.fixture
def fake_redis(monkeypatch):
    server = fakeredis.FakeServer()

    def _client(_settings=None):
        return fakeredis.FakeStrictRedis(server=server)

    # Point both roles at the same fake server.
    monkeypatch.setattr(api_module, "redis_from_env", _client)
    monkeypatch.setattr(worker_module, "redis_from_env", _client)
    return _client


@pytest.fixture
def client(fake_redis):
    return TestClient(create_app(Settings(api_token=None)))


def _drain_worker_once(fake_redis, settings: Settings | None = None):
    """Process every currently-queued task with a single worker, no blocking loop."""

    w = Worker(settings or Settings())
    w._queue.ensure_group()
    for message_id, run_id, deliveries in w._queue.read(w._name, count=10, block_ms=50):
        w._handle_task(message_id, run_id, deliveries)


def test_submit_returns_202_and_run_id(client):
    resp = client.post("/v1/triage/runs", json={"reports": [_TIMEOUT_REPORT]})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["run_id"]
    assert body["poll_url"].endswith(body["run_id"])


def test_full_cycle_submit_process_poll(client, fake_redis):
    run_id = client.post(
        "/v1/triage/runs", json={"reports": [_TIMEOUT_REPORT], "fail_under": 0.5}
    ).json()["run_id"]

    # Before processing: queued, and result not ready.
    assert client.get(f"/v1/triage/runs/{run_id}").json()["status"] == "queued"
    assert client.get(f"/v1/triage/runs/{run_id}/result").status_code == 409

    _drain_worker_once(fake_redis)

    status = client.get(f"/v1/triage/runs/{run_id}").json()
    assert status["status"] == "succeeded"

    result = client.get(f"/v1/triage/runs/{run_id}/result").json()
    summary = result["summary"]
    assert summary["total_failures"] == 1
    assert summary["total_incidents"] == 1


def test_unknown_run_is_404(client):
    assert client.get("/v1/triage/runs/does-not-exist").status_code == 404


def test_idempotency_key_collapses_duplicates(client):
    headers = {"Idempotency-Key": "ci-build-42"}
    first = client.post("/v1/triage/runs", json={"reports": [_TIMEOUT_REPORT]}, headers=headers)
    second = client.post("/v1/triage/runs", json={"reports": [_TIMEOUT_REPORT]}, headers=headers)
    assert first.json()["run_id"] == second.json()["run_id"]


def test_token_enforced_when_configured(fake_redis):
    app = create_app(Settings(api_token="s3cret"))
    guarded = TestClient(app)
    assert guarded.post("/v1/triage/runs", json={"reports": []}).status_code == 401
    ok = guarded.post(
        "/v1/triage/runs",
        json={"reports": [_TIMEOUT_REPORT]},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert ok.status_code == 202


def test_tickets_opened_when_enabled(client, fake_redis):
    run_id = client.post("/v1/triage/runs", json={"reports": [_TIMEOUT_REPORT]}).json()["run_id"]
    _drain_worker_once(fake_redis, Settings(open_tickets=True, tickets_dry_run=True))

    summary = client.get(f"/v1/triage/runs/{run_id}/result").json()["summary"]
    tickets = summary["tickets"]
    assert len(tickets) == 1                       # one incident -> one ticket
    assert tickets[0]["status"] == "simulated"     # dry-run by default
    assert tickets[0]["run_id"] == run_id


def test_tickets_not_opened_by_default(client, fake_redis):
    run_id = client.post("/v1/triage/runs", json={"reports": [_TIMEOUT_REPORT]}).json()["run_id"]
    _drain_worker_once(fake_redis)  # open_tickets defaults to False

    summary = client.get(f"/v1/triage/runs/{run_id}/result").json()["summary"]
    assert "tickets" not in summary


def test_ticket_opening_is_idempotent(fake_redis):
    from triage.store import RedisStore
    from triage.ticketing import open_incident_tickets

    store = RedisStore(fake_redis())
    summary = {
        "incidents": [
            {"service": "payments", "category": "timeout", "signature": "deadline exceeded", "runbook": "check p99"}
        ]
    }

    first = open_incident_tickets("run-1", summary, store, dry_run=True)
    second = open_incident_tickets("run-1", summary, store, dry_run=True)  # redelivery
    assert len(first) == 1
    assert second == []  # dedupe key already claimed -> no duplicate ticket

