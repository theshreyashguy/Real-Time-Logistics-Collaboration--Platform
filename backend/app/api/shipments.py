"""Shipment lookup and creation."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.models.models import Shipment, User
from app.schemas.schemas import ShipmentCreate, ShipmentOut, ShipmentPage, ShipmentUpdate

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("", response_model=ShipmentPage)
async def list_shipments(
    q: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(Shipment)
    if q:
        base = base.where(
            or_(
                Shipment.id.ilike(f"%{q}%"),
                Shipment.origin.ilike(f"%{q}%"),
                Shipment.destination.ilike(f"%{q}%"),
                Shipment.carrier.ilike(f"%{q}%"),
            )
        )
    if status:
        base = base.where(Shipment.status == status)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(Shipment.id).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=ShipmentOut, status_code=status.HTTP_201_CREATED)
async def create_shipment(
    body: ShipmentCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.get(Shipment, body.id.upper())
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Shipment {body.id} already exists")
    shipment = Shipment(
        id=body.id.upper(),
        status=body.status,
        origin=body.origin,
        destination=body.destination,
        carrier=body.carrier,
        eta=body.eta,
        weight_kg=body.weight_kg,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(shipment)
    await db.commit()
    await db.refresh(shipment)
    return shipment


@router.patch("/{shipment_id}", response_model=ShipmentOut)
async def update_shipment(
    shipment_id: str,
    body: ShipmentUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    shipment = await db.get(Shipment, shipment_id.upper())
    if not shipment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(shipment, field, value)
    shipment.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(shipment)
    return shipment


@router.get("/{shipment_id}", response_model=ShipmentOut)
async def get_shipment(
    shipment_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    shipment = await db.get(Shipment, shipment_id.upper())
    if not shipment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found")
    return shipment
