import pytest

from app.models.models import Shipment

pytestmark = pytest.mark.asyncio


async def test_shipment_lookup(client, auth, db_session):
    db_session.add(Shipment(
        id="SHP-10293", status="delayed", origin="Mumbai",
        destination="Kolkata", carrier="BlueDart", weight_kg=1250,
    ))
    await db_session.commit()

    headers, _ = await auth("looker")
    r = await client.get("/shipments/SHP-10293", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "delayed"

    # case-insensitive id, and unknown -> 404
    assert (await client.get("/shipments/shp-10293", headers=headers)).status_code == 200
    assert (await client.get("/shipments/SHP-99999", headers=headers)).status_code == 404


async def test_shipment_entity_extraction_links(client, auth, db_session):
    db_session.add(Shipment(
        id="SHP-10293", status="delayed", origin="A", destination="B",
        carrier="X", weight_kg=10,
    ))
    await db_session.commit()
    admin_h, _ = await auth("ops", make_admin=True)
    ch = (await client.post(
        "/channels", json={"name": "dispatch"}, headers=admin_h
    )).json()
    r = await client.post(
        f"/channels/{ch['id']}/messages",
        json={"content": "SHP-10293 is delayed at customs"}, headers=admin_h,
    )
    assert r.json()["shipment_ids"] == ["SHP-10293"]
