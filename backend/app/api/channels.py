"""Channel endpoints: list (with unread), create (admin), join, leave."""
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.models.models import Channel, Membership, Message, User
from app.schemas.schemas import ChannelCreate, ChannelOut

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelOut])
async def list_channels(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    # Unread count per channel as a correlated subquery so the whole listing is
    # ONE round-trip to the DB instead of N+1 (one COUNT per channel).
    unread_sq = (
        select(func.count(Message.id))
        .where(
            Message.channel_id == Channel.id,
            Message.id > func.coalesce(Membership.last_read_message_id, 0),
        )
        .correlate(Channel, Membership)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Channel, unread_sq.label("unread"))
            .join(Membership, Membership.channel_id == Channel.id)
            .where(Membership.user_id == user.id)
        )
    ).all()
    return [
        ChannelOut(
            id=str(channel.id),
            name=channel.name,
            type=channel.type,
            topic=channel.topic,
            unread=unread or 0,
        )
        for channel, unread in rows
    ]


@router.get("/all", response_model=list[ChannelOut])
async def list_all_public(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """All public channels (for discovery / joining), regardless of membership."""
    channels = (
        await db.scalars(select(Channel).where(Channel.type == "public"))
    ).all()
    return [
        ChannelOut(id=str(c.id), name=c.name, type=c.type, topic=c.topic, unread=0)
        for c in channels
    ]


@router.post("", response_model=ChannelOut, status_code=201)
async def create_channel(
    body: ChannelCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if await db.scalar(select(Channel).where(Channel.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Channel name taken")
    channel = Channel(
        name=body.name, topic=body.topic, type="public", created_by=user.id
    )
    db.add(channel)
    await db.flush()
    # creator auto-joins as channel admin
    db.add(
        Membership(user_id=user.id, channel_id=channel.id, role="admin")
    )
    await db.commit()
    return ChannelOut(
        id=str(channel.id), name=channel.name, type=channel.type, topic=channel.topic
    )


@router.post("/{channel_id}/join", status_code=204)
async def join_channel(
    channel_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = await db.get(Channel, channel_id)
    if not channel or channel.type == "dm":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    exists = await db.scalar(
        select(Membership).where(
            Membership.channel_id == channel_id, Membership.user_id == user.id
        )
    )
    if not exists:
        db.add(Membership(user_id=user.id, channel_id=channel_id))
        await db.commit()


@router.post("/{channel_id}/leave", status_code=204)
async def leave_channel(
    channel_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await db.scalar(
        select(Membership).where(
            Membership.channel_id == channel_id, Membership.user_id == user.id
        )
    )
    if m:
        await db.delete(m)
        await db.commit()


@router.post("/{channel_id}/read", status_code=204)
async def mark_read(
    channel_id: uuid.UUID,
    last_id: int = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await db.scalar(
        select(Membership).where(
            Membership.channel_id == channel_id,
            Membership.user_id == user.id,
        )
    )
    if m and last_id > (m.last_read_message_id or 0):
        m.last_read_message_id = last_id
        await db.commit()
