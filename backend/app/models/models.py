"""SQLAlchemy models matching the LLD schema.

Tables: users, channels, memberships, messages, shipments,
message_shipments (join), ai_summaries (cache).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.types import GUID

# BIGSERIAL on Postgres, but SQLite only autoincrements INTEGER PKs, so use a
# dialect variant to keep the same model portable for tests.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String(80))
    presence: Mapped[str] = mapped_column(String(10), default="offline")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(String(10), default="member")  # member|admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(String(80), unique=True)  # null for DMs
    type: Mapped[str] = mapped_column(String(10), default="public")    # public|dm
    topic: Mapped[str | None] = mapped_column(String(255))
    # RESTRICT: don't silently orphan a channel by deleting its creator.
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_membership"),
        Index("ix_membership_user", "user_id"),
        Index("ix_membership_channel", "channel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    # A membership is a pure join row: cascade it away with either parent.
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE")
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("channels.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(10), default="member")  # member|admin
    # FK to messages.id so a read cursor can't dangle; null it if the message goes.
    last_read_message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # in-order pagination + after_id replay
        Index("ix_messages_channel_id", "channel_id", "id"),
        # idempotent inserts
        UniqueConstraint("channel_id", "client_msg_id", name="uq_msg_idempotency"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # Deleting a channel takes its messages with it.
    channel_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("channels.id", ondelete="CASCADE")
    )
    # RESTRICT: preserve message authorship; a user with messages can't be
    # hard-deleted (reassign / soft-delete first).
    sender_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    content: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(10), default="text")  # text|ai|system
    client_msg_id: Mapped[str | None] = mapped_column(String(64))
    # Self-referential FK for threaded replies; unlink if the parent is removed.
    reply_to_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. SHP-10293
    status: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String)
    destination: Mapped[str] = mapped_column(String)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    carrier: Mapped[str] = mapped_column(String)
    weight_kg: Mapped[float | None] = mapped_column(Numeric)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MessageShipment(Base):
    __tablename__ = "message_shipments"
    __table_args__ = (
        UniqueConstraint("message_id", "shipment_id", name="uq_msg_shipment"),
        # fetch_history looks links up by message_id; index it (avoids N+1 scans).
        Index("ix_message_shipments_message_id", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    # Link dies with the message; a referenced shipment can't be deleted.
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE")
    )
    shipment_id: Mapped[str] = mapped_column(
        String, ForeignKey("shipments.id", ondelete="RESTRICT")
    )


class AISummary(Base):
    __tablename__ = "ai_summaries"
    __table_args__ = (
        # summaries are looked up by (channel, window); cascade with the channel.
        Index("ix_ai_summaries_channel_window", "channel_id", "window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("channels.id", ondelete="CASCADE")
    )
    window: Mapped[str] = mapped_column(String(40))  # e.g. "24h"
    model: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(Text)
    source_message_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
