"""Orchestrates summarization: window fetch -> cache check -> summarize ->
persist (ai_summaries) -> Redis cache -> stream events over WebSocket."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.summarizer import get_summarizer
from app.core.config import settings
from app.models.models import AISummary, Message
from app.realtime import redis_bus
from app.realtime.manager import manager
from app.schemas.schemas import SummaryOut

_WINDOW_HOURS = {"1h": 1, "6h": 6, "12h": 12, "24h": 24, "7d": 168}


async def _fetch_window(
    db: AsyncSession, channel_id: uuid.UUID, window: str
) -> list[dict]:
    hours = _WINDOW_HOURS.get(window, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(Message)
            .where(
                Message.channel_id == channel_id,
                Message.created_at >= since,
                Message.type == "text",
            )
            .order_by(Message.id.asc())
            .limit(settings.ai_summary_window_messages)
        )
    ).scalars().all()
    return [{"id": m.id, "content": m.content} for m in rows]


async def summarize_channel(
    db: AsyncSession, channel_id: uuid.UUID, window: str = "24h"
) -> SummaryOut:
    cid = str(channel_id)

    # 1) Redis cache hit -> return instantly
    cached = await redis_bus.cache_get(cid, window)
    if cached:
        data = json.loads(cached)
        return SummaryOut(**data, cached=True)

    # 2) Build window + summarize
    messages = await _fetch_window(db, channel_id, window)
    summarizer = get_summarizer()
    result = await summarizer.summarize(messages, window)

    # 3) Persist for citation + audit
    row = AISummary(
        channel_id=channel_id,
        window=window,
        model=summarizer.name,
        summary=result.text,
        source_message_ids=result.source_ids,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    out = SummaryOut(
        summary_id=str(row.id),
        channel_id=cid,
        window=window,
        model=summarizer.name,
        summary=result.text,
        sources=result.source_ids,
        cached=False,
    )

    # 4) Cache in Redis (stored without the volatile `cached` flag)
    payload = out.model_dump(mode="json")
    payload.pop("cached", None)
    await redis_bus.cache_set(cid, window, json.dumps(payload))

    # 5) Stream over WebSocket so connected clients render live
    await _broadcast(cid, out)
    return out


async def _broadcast(channel_id: str, out: SummaryOut) -> None:
    # token-by-token for live rendering, then a done event with sources
    for token in out.summary.split(" "):
        await manager.publish(
            channel_id,
            {"type": "ai_token", "channel_id": channel_id, "delta": token + " "},
        )
    await manager.publish(
        channel_id,
        {
            "type": "ai_done",
            "channel_id": channel_id,
            "summary_id": out.summary_id,
            "sources": out.sources,
        },
    )
