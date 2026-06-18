"""Pydantic request/response models."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---- auth ----
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    display_name: str
    role: str
    presence: str


# ---- channels ----
class ChannelCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    topic: str | None = None


class ChannelOut(BaseModel):
    id: str
    name: str | None
    type: str
    topic: str | None
    unread: int = 0


# ---- messages ----
class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_msg_id: str | None = Field(default=None, max_length=64)
    reply_to_id: int | None = None


class MessageOut(BaseModel):
    id: int
    channel_id: str
    sender_id: str
    sender_name: str | None = None
    content: str
    type: str
    client_msg_id: str | None = None
    reply_to_id: int | None = None
    created_at: datetime
    shipment_ids: list[str] = []


# ---- shipments ----
class ShipmentCreate(BaseModel):
    id: str = Field(min_length=2, max_length=40)
    status: str = Field(default="in_transit", pattern=r"^(in_transit|delayed|delivered|pending)$")
    origin: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    carrier: str = Field(min_length=1, max_length=80)
    eta: datetime | None = None
    weight_kg: float | None = None


class ShipmentUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(in_transit|delayed|delivered|pending)$")
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: str | None = Field(default=None, min_length=1, max_length=120)
    carrier: str | None = Field(default=None, min_length=1, max_length=80)
    eta: datetime | None = None
    weight_kg: float | None = None


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    origin: str
    destination: str
    eta: datetime | None
    carrier: str
    weight_kg: float | None


class ShipmentPage(BaseModel):
    items: list[ShipmentOut]
    total: int
    page: int
    page_size: int


# ---- AI ----
class SummaryOut(BaseModel):
    summary_id: str | None = None
    channel_id: str
    window: str
    model: str
    summary: str
    sources: list[int]
    cached: bool = False
