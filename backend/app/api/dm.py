"""Direct messages, modeled as 2-member channels (type='dm').

A deterministic DM channel name (dm:<sorted uuid pair>) lets us find-or-create
the conversation idempotently and reuse all channel/message machinery.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.message_service import fetch_history, post_message
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.models import Channel, Membership, User
from app.schemas.schemas import MessageCreate, MessageOut

router = APIRouter(prefix="/dm", tags=["dm"])


def _dm_name(a: uuid.UUID, b: uuid.UUID) -> str:
    lo, hi = sorted([str(a), str(b)])
    return f"dm:{lo}:{hi}"


async def get_or_create_dm(
    db: AsyncSession, me: User, other_id: uuid.UUID
) -> Channel:
    if me.id == other_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot DM yourself")
    other = await db.get(User, other_id)
    if not other:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    name = _dm_name(me.id, other_id)
    channel = await db.scalar(select(Channel).where(Channel.name == name))
    if channel:
        return channel
    channel = Channel(name=name, type="dm", created_by=me.id)
    db.add(channel)
    await db.flush()
    db.add(Membership(user_id=me.id, channel_id=channel.id))
    db.add(Membership(user_id=other_id, channel_id=channel.id))
    await db.commit()
    await db.refresh(channel)
    return channel


@router.post("/{user_id}/messages", response_model=MessageOut, status_code=201)
async def post_dm(
    user_id: uuid.UUID,
    body: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = await get_or_create_dm(db, user, user_id)
    return await post_message(
        db,
        channel_id=channel.id,
        sender=user,
        content=body.content,
        client_msg_id=body.client_msg_id,
    )


@router.get("/{user_id}/messages", response_model=list[MessageOut])
async def get_dm(
    user_id: uuid.UUID,
    after_id: int | None = Query(default=None),
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = await get_or_create_dm(db, user, user_id)
    return await fetch_history(
        db, channel_id=channel.id, after_id=after_id, before_id=before_id, limit=limit
    )
