"""Per-worker WebSocket connection manager.

Each worker holds a set of live sockets. Because a message posted on one
worker must reach users connected to another, every event is published to
Redis (`chan:{channel_id}`) and a single background reader fans it out to
the locally-connected sockets subscribed to that channel.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket

from app.realtime import redis_bus


class ConnectionManager:
    def __init__(self) -> None:
        # channel_id -> set of local websockets
        self._channel_subs: dict[str, set[WebSocket]] = defaultdict(set)
        # websocket -> user_id
        self._socket_user: dict[WebSocket, str] = {}
        self._pubsub = None
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._pubsub is not None:
            return
        self._pubsub = redis_bus.get_redis().pubsub()
        self._reader_task = asyncio.create_task(self._reader())

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._pubsub:
            await self._pubsub.aclose()
        self._pubsub = None
        self._reader_task = None

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        await ws.accept()
        self._socket_user[ws] = user_id

    async def disconnect(self, ws: WebSocket) -> None:
        self._socket_user.pop(ws, None)
        for subs in self._channel_subs.values():
            subs.discard(ws)

    async def subscribe(self, ws: WebSocket, channel_id: str) -> None:
        async with self._lock:
            first_local = len(self._channel_subs[channel_id]) == 0
            self._channel_subs[channel_id].add(ws)
            if first_local and self._pubsub is not None:
                await self._pubsub.subscribe(redis_bus.chan_key(channel_id))

    async def unsubscribe(self, ws: WebSocket, channel_id: str) -> None:
        async with self._lock:
            self._channel_subs[channel_id].discard(ws)
            if not self._channel_subs[channel_id] and self._pubsub is not None:
                await self._pubsub.unsubscribe(redis_bus.chan_key(channel_id))

    async def publish(self, channel_id: str, event: dict) -> None:
        """Publish an event to Redis so every worker fans it out."""
        await redis_bus.publish(channel_id, json.dumps(event))

    async def _reader(self) -> None:
        assert self._pubsub is not None
        async for raw in self._pubsub.listen():
            if raw is None or raw.get("type") != "message":
                continue
            redis_chan: str = raw["channel"]
            channel_id = redis_chan.split("chan:", 1)[-1]
            data = raw["data"]
            await self._fan_out(channel_id, data)

    async def _fan_out(self, channel_id: str, data: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._channel_subs.get(channel_id, set())):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()
