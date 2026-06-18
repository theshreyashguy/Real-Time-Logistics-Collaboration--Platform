"""Redis access layer: pub/sub fan-out, presence TTL keys, rate-limit
counters, and AI-summary cache. A single async client is shared per worker.

In tests this module is monkeypatched to use fakeredis, so all callers go
through `get_redis()` rather than importing a client directly.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---- channel keys -------------------------------------------------------
def chan_key(channel_id: str) -> str:
    return f"chan:{channel_id}"


def presence_key(user_id: str) -> str:
    return f"presence:{user_id}"


def rl_key(user_id: str, window: int) -> str:
    return f"rl:{user_id}:{window}"


def summary_key(channel_id: str, window: str) -> str:
    return f"sum:{channel_id}:{window}"


# ---- pub/sub ------------------------------------------------------------
async def publish(channel_id: str, payload: str) -> None:
    await get_redis().publish(chan_key(channel_id), payload)


# ---- presence -----------------------------------------------------------
async def set_presence(user_id: str, state: str) -> None:
    r = get_redis()
    if state == "offline":
        await r.delete(presence_key(user_id))
    else:
        await r.set(presence_key(user_id), state, ex=settings.presence_ttl)


async def get_presence(user_id: str) -> str:
    return await get_redis().get(presence_key(user_id)) or "offline"


# ---- rate limiting ------------------------------------------------------
async def check_rate_limit(user_id: str) -> bool:
    """Return True if the action is allowed, False if the limit is exceeded."""
    r = get_redis()
    bucket = rl_key(user_id, settings.rate_limit_window)
    count = await r.incr(bucket)
    if count == 1:
        await r.expire(bucket, settings.rate_limit_window)
    return count <= settings.rate_limit_messages


# ---- AI summary cache ---------------------------------------------------
async def cache_get(channel_id: str, window: str) -> str | None:
    return await get_redis().get(summary_key(channel_id, window))


async def cache_set(channel_id: str, window: str, value: str) -> None:
    await get_redis().set(
        summary_key(channel_id, window), value, ex=settings.ai_summary_cache_ttl
    )
