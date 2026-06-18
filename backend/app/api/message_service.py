"""Shared message-posting logic for channel + DM messages.

Handles rate limiting, idempotent inserts (client_msg_id), shipment entity
extraction + linking, the optional outbound webhook, and Redis fan-out.
"""
from __future__ import annotations

import re
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Message, MessageShipment, Shipment, User
from app.realtime import redis_bus
from app.realtime.manager import manager
from app.schemas.schemas import MessageOut

SHIPMENT_RE = re.compile(r"\bSHP-\d{3,}\b", re.IGNORECASE)


def extract_shipment_ids(text: str) -> list[str]:
    return sorted({m.upper() for m in SHIPMENT_RE.findall(text)})


def to_out(msg: Message, sender_name: str | None, shipment_ids: list[str]) -> MessageOut:
    return MessageOut(
        id=msg.id,
        channel_id=str(msg.channel_id),
        sender_id=str(msg.sender_id),
        sender_name=sender_name,
        content=msg.content,
        type=msg.type,
        client_msg_id=msg.client_msg_id,
        reply_to_id=msg.reply_to_id,
        created_at=msg.created_at,
        shipment_ids=shipment_ids,
    )


async def _fire_webhook(shipment_ids: list[str], message_id: int, channel_id: str):
    if not settings.shipment_webhook_url or not shipment_ids:
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                settings.shipment_webhook_url,
                json={
                    "event": "shipment_message",
                    "message_id": message_id,
                    "channel_id": channel_id,
                    "shipment_ids": shipment_ids,
                },
            )
    except Exception:
        pass  # webhook is best-effort, never blocks the post


async def post_message(
    db: AsyncSession,
    *,
    channel_id: uuid.UUID,
    sender: User,
    content: str,
    client_msg_id: str | None,
    reply_to_id: int | None = None,
    msg_type: str = "text",
) -> MessageOut:
    # Rate limit (Redis counter)
    if not await redis_bus.check_rate_limit(str(sender.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")

    # Idempotency: return existing row if client_msg_id already used here.
    async def _existing():
        if not client_msg_id:
            return None
        return await db.scalar(
            select(Message).where(
                Message.channel_id == channel_id,
                Message.client_msg_id == client_msg_id,
            )
        )

    found = await _existing()
    if found:
        return to_out(found, sender.display_name, extract_shipment_ids(found.content))

    msg = Message(
        channel_id=channel_id,
        sender_id=sender.id,  # server-derived, never trusts client
        content=content,
        type=msg_type,
        client_msg_id=client_msg_id,
        reply_to_id=reply_to_id,
    )
    db.add(msg)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent retry with the same client_msg_id won the race and the
        # uq_msg_idempotency constraint fired. Roll back and return the row that
        # landed — keeps the post idempotent instead of surfacing a 500.
        await db.rollback()
        found = await _existing()
        if found:
            return to_out(found, sender.display_name, extract_shipment_ids(found.content))
        raise

    # Entity extraction -> link known shipments
    shipment_ids = extract_shipment_ids(content)
    linked: list[str] = []
    for sid in shipment_ids:
        if await db.get(Shipment, sid):
            db.add(MessageShipment(message_id=msg.id, shipment_id=sid))
            linked.append(sid)
    await db.commit()
    await db.refresh(msg)

    out = to_out(msg, sender.display_name, linked)
    await manager.publish(
        str(channel_id), {"type": "message", "channel_id": str(channel_id),
                          "data": out.model_dump(mode="json")}
    )
    await _fire_webhook(linked, msg.id, str(channel_id))
    return out


async def fetch_history(
    db: AsyncSession,
    *,
    channel_id: uuid.UUID,
    after_id: int | None,
    before_id: int | None,
    limit: int,
) -> list[MessageOut]:
    q = select(Message, User.display_name).join(
        User, User.id == Message.sender_id
    ).where(Message.channel_id == channel_id)
    if after_id is not None:
        q = q.where(Message.id > after_id).order_by(Message.id.asc())
    elif before_id is not None:
        q = q.where(Message.id < before_id).order_by(Message.id.desc())
    else:
        q = q.order_by(Message.id.desc())
    rows = (await db.execute(q.limit(limit))).all()

    msgs = [(m, name) for m, name in rows]
    if after_id is None:
        msgs = list(reversed(msgs))  # return ascending for display

    out: list[MessageOut] = []
    for m, name in msgs:
        links = (
            await db.execute(
                select(MessageShipment.shipment_id).where(
                    MessageShipment.message_id == m.id
                )
            )
        ).scalars().all()
        out.append(to_out(m, name, list(links)))
    return out
