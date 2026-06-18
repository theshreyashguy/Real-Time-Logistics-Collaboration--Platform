"""WebSocket gateway: single multiplexed socket at /ws?token=<jwt>.

Client ops: subscribe / unsubscribe / ping. Server pushes message, presence,
ai_token, ai_done, pong. Presence is tracked via Redis TTL keys refreshed by
heartbeats and broadcast to the channels the user belongs to.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import decode_token
from app.models.models import Membership, User
from app.realtime import redis_bus
from app.realtime.manager import manager

router = APIRouter()


async def _user_channels(user_id: uuid.UUID) -> list[str]:
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Membership.channel_id).where(Membership.user_id == user_id)
            )
        ).scalars().all()
        return [str(c) for c in rows]


async def _is_member(user_id: uuid.UUID, channel_id: str) -> bool:
    async with SessionLocal() as db:
        m = await db.scalar(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.channel_id == uuid.UUID(channel_id),
            )
        )
        return m is not None


async def _set_presence(user_id: str, state: str) -> None:
    # Redis (TTL key) is the authoritative source of live presence — readers
    # overlay it (see auth.list_users / auth.me), so a crashed worker's stale
    # state expires on its own. The DB write is a durable "last seen" record
    # and a best-effort fallback, not the source of truth.
    await redis_bus.set_presence(user_id, state)
    async with SessionLocal() as db:
        u = await db.get(User, uuid.UUID(user_id))
        if u:
            u.presence = state
            u.last_seen_at = datetime.now(timezone.utc)
            await db.commit()
    for cid in await _user_channels(uuid.UUID(user_id)):
        await manager.publish(
            cid, {"type": "presence", "user_id": user_id, "state": state}
        )


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    token = ws.query_params.get("token", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await ws.close(code=4401)
        return
    user_id = payload["sub"]

    await manager.connect(ws, user_id)
    await _set_presence(user_id, "online")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            op = msg.get("op")
            if op == "subscribe":
                cid = msg.get("channel_id")
                if cid and await _is_member(uuid.UUID(user_id), cid):
                    await manager.subscribe(ws, cid)
            elif op == "unsubscribe":
                cid = msg.get("channel_id")
                if cid:
                    await manager.unsubscribe(ws, cid)
            elif op == "ping":
                await redis_bus.set_presence(user_id, "online")
                await ws.send_text(json.dumps({"type": "pong"}))
            elif op == "away":
                await _set_presence(user_id, "away")
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
        await _set_presence(user_id, "offline")
