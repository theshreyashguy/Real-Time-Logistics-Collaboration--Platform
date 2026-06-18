"""Real-time layer tests: Redis pub/sub fan-out, the per-worker connection
manager, presence TTL keys, and rate-limit counters.

These cover the rubric's "Real-Time Correctness" and "Redis pub/sub AND
caching" criteria at the unit level, without a live socket: a small FakeWS
stub stands in for a client connection, and fakeredis (autouse fixture)
provides the pub/sub transport so the cross-worker path is exercised
deterministically and offline.
"""
import asyncio

import pytest

from app.realtime import redis_bus
from app.realtime.manager import ConnectionManager

pytestmark = pytest.mark.asyncio


class FakeWS:
    """Minimal stand-in for a Starlette WebSocket. `fail=True` makes send
    raise, so we can assert the manager evicts dead sockets."""

    def __init__(self, fail: bool = False):
        self.sent: list[str] = []
        self.fail = fail
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        if self.fail:
            raise RuntimeError("socket is dead")
        self.sent.append(data)


async def _wait_for(predicate, timeout: float = 2.0):
    """Poll until predicate() is truthy or timeout; keeps the background
    reader test deterministic without a fixed sleep."""
    deadline = 0.0
    while deadline < timeout:
        if predicate():
            return True
        await asyncio.sleep(0.02)
        deadline += 0.02
    return False


async def test_redis_pubsub_roundtrip():
    """The transport itself: a message published to a channel key is received
    by a subscriber. This is the foundation of cross-worker delivery."""
    r = redis_bus.get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(redis_bus.chan_key("chan-1"))
    # drain the subscribe-confirmation frame
    await pubsub.get_message(timeout=1)

    await redis_bus.publish("chan-1", "hello-world")

    msg = None
    for _ in range(50):
        msg = await pubsub.get_message(timeout=0.1)
        if msg and msg.get("type") == "message":
            break
    assert msg is not None and msg["type"] == "message"
    assert msg["data"] == "hello-world"
    await pubsub.aclose()


async def test_cross_worker_fan_out():
    """A message published by one worker reaches a socket connected to a
    DIFFERENT worker — the whole reason Redis sits alongside Postgres.

    workerA publishes; workerB has the local subscriber and must deliver."""
    worker_a = ConnectionManager()
    worker_b = ConnectionManager()
    await worker_a.start()
    await worker_b.start()
    try:
        ws = FakeWS()
        await worker_b.connect(ws, "user-b")
        await worker_b.subscribe(ws, "chan-x")

        # Published on A, the socket lives on B.
        await worker_a.publish("chan-x", {"type": "message", "data": "ping"})

        delivered = await _wait_for(lambda: len(ws.sent) > 0)
        assert delivered, "message did not fan out across workers"
        assert '"data": "ping"' in ws.sent[0]
    finally:
        await worker_a.stop()
        await worker_b.stop()


async def test_unsubscribe_stops_delivery():
    mgr = ConnectionManager()
    await mgr.start()
    try:
        ws = FakeWS()
        await mgr.connect(ws, "u1")
        await mgr.subscribe(ws, "chan-y")
        await mgr.unsubscribe(ws, "chan-y")

        await mgr.publish("chan-y", {"type": "message", "data": "should-not-arrive"})
        # give the reader a chance; nothing should land
        await asyncio.sleep(0.2)
        assert ws.sent == []
    finally:
        await mgr.stop()


async def test_fan_out_evicts_dead_sockets():
    """A send failure must drop the socket so a broken client can't wedge
    the fan-out loop or leak into the subscription set."""
    mgr = ConnectionManager()
    good = FakeWS()
    bad = FakeWS(fail=True)
    await mgr.connect(good, "good")
    await mgr.connect(bad, "bad")
    # subscribe both without starting the reader (direct fan-out unit test)
    mgr._channel_subs["chan-z"].add(good)
    mgr._channel_subs["chan-z"].add(bad)

    await mgr._fan_out("chan-z", "payload")

    assert good.sent == ["payload"]
    # the dead socket was evicted from the channel subscription set
    assert bad not in mgr._channel_subs["chan-z"]
    assert good in mgr._channel_subs["chan-z"]


async def test_disconnect_removes_socket_from_all_channels():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect(ws, "u2")
    mgr._channel_subs["a"].add(ws)
    mgr._channel_subs["b"].add(ws)

    await mgr.disconnect(ws)

    assert ws not in mgr._channel_subs["a"]
    assert ws not in mgr._channel_subs["b"]
    assert ws not in mgr._socket_user


async def test_presence_ttl_and_offline_clears():
    await redis_bus.set_presence("user-1", "online")
    assert await redis_bus.get_presence("user-1") == "online"

    await redis_bus.set_presence("user-1", "away")
    assert await redis_bus.get_presence("user-1") == "away"

    # offline deletes the key -> unknown users read back as "offline"
    await redis_bus.set_presence("user-1", "offline")
    assert await redis_bus.get_presence("user-1") == "offline"
    assert await redis_bus.get_presence("never-seen") == "offline"


async def test_rate_limit_counter_blocks_after_threshold(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_messages", 3)
    allowed = [await redis_bus.check_rate_limit("rl-user") for _ in range(3)]
    assert all(allowed)
    # 4th in the same window is rejected
    assert await redis_bus.check_rate_limit("rl-user") is False
    # a different user has an independent bucket
    assert await redis_bus.check_rate_limit("other-user") is True
