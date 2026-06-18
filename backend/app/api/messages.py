"""Channel message endpoints: post + paginated history (after_id/before_id)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.message_service import fetch_history, post_message
from app.core.db import get_db
from app.core.deps import get_current_user, require_membership
from app.models.models import User
from app.schemas.schemas import MessageCreate, MessageOut

router = APIRouter(prefix="/channels", tags=["messages"])


@router.get("/{channel_id}/messages", response_model=list[MessageOut])
async def get_messages(
    channel_id: uuid.UUID,
    after_id: int | None = Query(default=None),
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_membership(channel_id, user, db)
    return await fetch_history(
        db, channel_id=channel_id, after_id=after_id, before_id=before_id, limit=limit
    )


@router.post("/{channel_id}/messages", response_model=MessageOut, status_code=201)
async def create_message(
    channel_id: uuid.UUID,
    body: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_membership(channel_id, user, db)
    return await post_message(
        db,
        channel_id=channel_id,
        sender=user,
        content=body.content,
        client_msg_id=body.client_msg_id,
        reply_to_id=body.reply_to_id,
    )
