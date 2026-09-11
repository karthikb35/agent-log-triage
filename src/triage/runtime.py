"""Shared runtime configuration for the API and worker processes.

All knobs come from the environment so the same image runs as either role with
no code change -- the Deployment just sets ``args`` and env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from redis import Redis


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv("TRIAGE_REDIS_URL", "redis://localhost:6379/0")
    # Redis Sentinel HA: a comma-separated list of ``host:port`` sentinels. When
    # set it takes precedence over ``redis_url`` and the client follows failover.
    redis_sentinels: str | None = os.getenv("TRIAGE_REDIS_SENTINELS") or None
    redis_master_name: str = os.getenv("TRIAGE_REDIS_MASTER_NAME", "triage")
    redis_password: str | None = os.getenv("TRIAGE_REDIS_PASSWORD") or None
    redis_db: int = int(os.getenv("TRIAGE_REDIS_DB", "0"))
    # Back-pressure: reject new submits once this many tasks are unacked.
    max_pending: int = int(os.getenv("TRIAGE_MAX_PENDING", "5000"))
    # Optional bearer token the API requires on write paths.
    api_token: str | None = os.getenv("TRIAGE_API_TOKEN") or None
    # Worker identity for the consumer group; defaults to the pod hostname.
    worker_name: str = os.getenv("HOSTNAME", "worker-local")
    # Ticket opening: off by default; even when on, dry-run unless told otherwise.
    open_tickets: bool = os.getenv("TRIAGE_OPEN_TICKETS", "0") == "1"
    tickets_dry_run: bool = os.getenv("TRIAGE_TICKETS_DRY_RUN", "1") != "0"


def get_settings() -> Settings:
    return Settings()


def _parse_sentinels(spec: str) -> list[tuple[str, int]]:
    nodes: list[tuple[str, int]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.partition(":")
        nodes.append((host, int(port or 26379)))
    return nodes


def redis_from_env(settings: Settings | None = None) -> Redis:
    """Build a Redis client, following Sentinel failover when configured.

    With ``TRIAGE_REDIS_SENTINELS`` set, the returned client is bound to whatever
    node Sentinel currently reports as master, so it survives a master failover
    transparently. Without it, we connect straight to ``redis_url`` (the
    single-instance baseline).
    """

    settings = settings or get_settings()
    if settings.redis_sentinels:
        from redis.sentinel import Sentinel

        sentinel = Sentinel(
            _parse_sentinels(settings.redis_sentinels),
            socket_timeout=0.5,
            password=settings.redis_password,
            sentinel_kwargs={"password": settings.redis_password},
        )
        return sentinel.master_for(
            settings.redis_master_name,
            db=settings.redis_db,
            password=settings.redis_password,
        )
    return Redis.from_url(settings.redis_url)
