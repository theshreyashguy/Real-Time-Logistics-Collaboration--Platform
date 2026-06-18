"""AI summary trigger endpoint. Streams tokens over WS; returns final result."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.service import summarize_channel
from app.core.db import get_db
from app.core.deps import get_current_user, require_membership
from app.models.models import User
from app.schemas.schemas import SummaryOut

router = APIRouter(prefix="/channels", tags=["ai"])


@router.post("/{channel_id}/summarize", response_model=SummaryOut)
async def summarize(
    channel_id: uuid.UUID,
    window: str = Query(default="24h"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_membership(channel_id, user, db)
    return await summarize_channel(db, channel_id, window)
