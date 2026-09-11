"""Unit tests for Sentinel-aware Redis client selection.

No real Redis/Sentinel is needed: we assert that the factory picks the Sentinel
path only when sentinels are configured, and passes the right nodes and master
name through.
"""

from __future__ import annotations

import redis.sentinel as rs

from triage.runtime import Settings, _parse_sentinels, redis_from_env


def test_parse_sentinels_handles_ports_and_defaults():
    assert _parse_sentinels("a:26379, b:26380 ,c") == [
        ("a", 26379),
        ("b", 26380),
        ("c", 26379),
    ]


def test_sentinel_path_selected_when_configured(monkeypatch):
    captured: dict = {}

    class FakeSentinel:
        def __init__(self, nodes, **kwargs):
            captured["nodes"] = nodes
            captured["kwargs"] = kwargs

        def master_for(self, name, **kwargs):
            captured["master_name"] = name
            captured["master_kwargs"] = kwargs
            return "MASTER_CLIENT"

    monkeypatch.setattr(rs, "Sentinel", FakeSentinel)

    settings = Settings(
        redis_sentinels="s1:26379,s2:26379",
        redis_master_name="triage",
        redis_db=0,
    )
    client = redis_from_env(settings)

    assert client == "MASTER_CLIENT"
    assert captured["nodes"] == [("s1", 26379), ("s2", 26379)]
    assert captured["master_name"] == "triage"


def test_single_instance_path_when_no_sentinels():
    from redis import Redis

    client = redis_from_env(Settings(redis_url="redis://localhost:6379/0"))
    assert isinstance(client, Redis)
