"""Seed demo data: users, logistics channels, memberships, mock shipments,
and a few sample messages so the AI summary has something to chew on.

Run after migrations:  python seed.py
"""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.models import (
    Channel,
    Membership,
    Message,
    Shipment,
    User,
)

PASSWORD = "password123"


async def seed():
    async with SessionLocal() as db:
        if await db.scalar(select(User).limit(1)):
            print("Data already present — skipping seed.")
            return

        # --- users ---
        admin = User(
            username="dispatch_admin", email="admin@hemut.test",
            password_hash=hash_password(PASSWORD), display_name="Dispatch Admin",
            role="admin",
        )
        priya = User(
            username="priya", email="priya@hemut.test",
            password_hash=hash_password(PASSWORD), display_name="Priya (Mumbai)",
        )
        rahul = User(
            username="rahul", email="rahul@hemut.test",
            password_hash=hash_password(PASSWORD), display_name="Rahul (Route East)",
        )
        db.add_all([admin, priya, rahul])
        await db.flush()

        # --- channels ---
        route_east = Channel(name="route-east", type="public",
                             topic="Eastern corridor dispatch", created_by=admin.id)
        warehouse = Channel(name="warehouse-mumbai", type="public",
                            topic="Mumbai warehouse ops", created_by=admin.id)
        db.add_all([route_east, warehouse])
        await db.flush()

        # --- memberships ---
        for ch in (route_east, warehouse):
            for u in (admin, priya, rahul):
                db.add(Membership(user_id=u.id, channel_id=ch.id,
                                  role="admin" if u is admin else "member"))

        # --- mock shipments ---
        now = datetime.now(timezone.utc)
        db.add_all([
            Shipment(id="SHP-10293", status="delayed", origin="Mumbai",
                     destination="Kolkata", eta=now + timedelta(hours=8),
                     carrier="BlueDart", weight_kg=1250),
            Shipment(id="SHP-10311", status="in_transit", origin="Pune",
                     destination="Delhi", eta=now + timedelta(hours=20),
                     carrier="Delhivery", weight_kg=860),
            Shipment(id="SHP-10350", status="delivered", origin="Chennai",
                     destination="Hyderabad", eta=now - timedelta(hours=3),
                     carrier="Gati", weight_kg=430),
        ])

        # --- sample messages (so summaries have content) ---
        samples = [
            (rahul, route_east, "Morning all — SHP-10293 is delayed at the Nagpur hub, customs hold."),
            (admin, route_east, "Noted. Can we reroute SHP-10293 via the southern lane?"),
            (rahul, route_east, "Reroute approved by ops. New ETA pushed by ~8h."),
            (priya, warehouse, "Warehouse-mumbai: dock 3 breakdown, SHP-10311 loading delayed."),
            (priya, warehouse, "SHP-10350 delivered to Hyderabad, POD uploaded."),
        ]
        base = now - timedelta(hours=2)
        for i, (sender, ch, text) in enumerate(samples):
            db.add(Message(channel_id=ch.id, sender_id=sender.id, content=text,
                           created_at=base + timedelta(minutes=5 * i)))

        await db.commit()
        print("Seeded users (password: %s), channels, shipments, messages." % PASSWORD)


if __name__ == "__main__":
    asyncio.run(seed())
