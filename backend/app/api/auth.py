"""Auth endpoints: register, login, refresh, me."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.models import User
from app.realtime import redis_bus
from app.schemas.schemas import (
    LoginIn,
    RefreshIn,
    RegisterIn,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        username=u.username,
        display_name=u.display_name,
        role=u.role,
        presence=u.presence,
    )


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(
        select(User).where(
            or_(User.username == body.username, User.email == body.email)
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already taken")
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    # Rate-limit login attempts to slow brute force.
    if not await redis_bus.check_rate_limit(f"login:{body.username}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    user = await db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenPair(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return TokenPair(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    # Reflect live presence from Redis (authoritative), not the stored column.
    out = _user_out(user)
    out.presence = await redis_bus.get_presence(str(user.id))
    return out


@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """All users except the caller — used to start DMs and show presence.
    Presence is read live from Redis (falls back to the stored value)."""
    rows = (await db.scalars(select(User).where(User.id != user.id))).all()
    out: list[UserOut] = []
    for u in rows:
        live = await redis_bus.get_presence(str(u.id))
        o = _user_out(u)
        o.presence = live
        out.append(o)
    return out
