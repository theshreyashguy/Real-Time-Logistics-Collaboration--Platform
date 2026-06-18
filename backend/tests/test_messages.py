import pytest

pytestmark = pytest.mark.asyncio


async def _channel_with_member(client, auth):
    admin_h, _ = await auth("madmin", make_admin=True)
    ch = (await client.post(
        "/channels", json={"name": "route-east"}, headers=admin_h
    )).json()
    return admin_h, ch


async def test_post_and_fetch_in_order(client, auth):
    headers, ch = await _channel_with_member(client, auth)
    for i in range(5):
        r = await client.post(
            f"/channels/{ch['id']}/messages",
            json={"content": f"msg {i}"}, headers=headers,
        )
        assert r.status_code == 201
    msgs = (await client.get(
        f"/channels/{ch['id']}/messages", headers=headers
    )).json()
    ids = [m["id"] for m in msgs]
    assert ids == sorted(ids)                 # monotonic order
    assert [m["content"] for m in msgs] == [f"msg {i}" for i in range(5)]


async def test_idempotent_client_msg_id(client, auth):
    headers, ch = await _channel_with_member(client, auth)
    body = {"content": "hi", "client_msg_id": "abc-123"}
    r1 = await client.post(f"/channels/{ch['id']}/messages", json=body, headers=headers)
    r2 = await client.post(f"/channels/{ch['id']}/messages", json=body, headers=headers)
    assert r1.json()["id"] == r2.json()["id"]   # same row, no duplicate
    all_msgs = (await client.get(
        f"/channels/{ch['id']}/messages", headers=headers
    )).json()
    assert len(all_msgs) == 1


async def test_after_id_replay(client, auth):
    """Simulates a reconnecting client requesting only missed messages."""
    headers, ch = await _channel_with_member(client, auth)
    ids = []
    for i in range(6):
        r = await client.post(
            f"/channels/{ch['id']}/messages",
            json={"content": f"m{i}"}, headers=headers,
        )
        ids.append(r.json()["id"])
    cursor = ids[2]
    replayed = (await client.get(
        f"/channels/{ch['id']}/messages?after_id={cursor}", headers=headers
    )).json()
    assert [m["id"] for m in replayed] == ids[3:]


async def test_sender_is_server_derived(client, auth):
    """Client cannot spoof sender_id; server uses the JWT subject."""
    headers, ch = await _channel_with_member(client, auth)
    r = await client.post(
        f"/channels/{ch['id']}/messages",
        json={"content": "x", "sender_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    # the bogus sender_id is ignored (extra field), real sender recorded
    msgs = (await client.get(
        f"/channels/{ch['id']}/messages", headers=headers
    )).json()
    assert msgs[0]["sender_id"] != "00000000-0000-0000-0000-000000000000"


async def test_before_id_pagination(client, auth):
    """Scroll-back pagination: before_id returns the page of older messages
    in ascending display order."""
    headers, ch = await _channel_with_member(client, auth)
    ids = []
    for i in range(10):
        r = await client.post(
            f"/channels/{ch['id']}/messages",
            json={"content": f"m{i}"}, headers=headers,
        )
        ids.append(r.json()["id"])
    # ask for the 3 messages older than ids[5]
    page = (await client.get(
        f"/channels/{ch['id']}/messages?before_id={ids[5]}&limit=3", headers=headers
    )).json()
    returned = [m["id"] for m in page]
    assert returned == ids[2:5]                 # the 3 immediately before ids[5]
    assert returned == sorted(returned)         # ascending for display


async def test_rate_limit_returns_429(client, auth, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "rate_limit_messages", 3)

    headers, ch = await _channel_with_member(client, auth)
    codes = []
    for i in range(5):
        r = await client.post(
            f"/channels/{ch['id']}/messages",
            json={"content": f"spam {i}"}, headers=headers,
        )
        codes.append(r.status_code)
    assert codes[:3] == [201, 201, 201]
    assert 429 in codes[3:]                      # limit kicks in


async def test_shipment_message_fires_webhook(client, auth, db_session, monkeypatch):
    """When a shipment-tagged message is posted and a webhook URL is set, the
    platform pings the external service (optional spec requirement)."""
    from app.models.models import Shipment
    db_session.add(Shipment(
        id="SHP-55555", status="in_transit", origin="A", destination="B",
        carrier="X", weight_kg=5,
    ))
    await db_session.commit()

    from app.api import message_service
    monkeypatch.setattr(message_service.settings, "shipment_webhook_url",
                        "http://hooks.local/notify")

    calls = []

    class _FakeAsyncClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None):
            calls.append({"url": url, "json": json})

    monkeypatch.setattr(message_service.httpx, "AsyncClient", _FakeAsyncClient)

    headers, ch = await _channel_with_member(client, auth)
    await client.post(
        f"/channels/{ch['id']}/messages",
        json={"content": "SHP-55555 departed the yard"}, headers=headers,
    )
    assert len(calls) == 1
    assert calls[0]["url"] == "http://hooks.local/notify"
    assert calls[0]["json"]["shipment_ids"] == ["SHP-55555"]
    assert calls[0]["json"]["event"] == "shipment_message"


async def test_dm_roundtrip(client, auth):
    a_h, a_id = await auth("anna")
    b_h, b_id = await auth("ben")
    r = await client.post(
        f"/dm/{b_id}/messages", json={"content": "hey ben"}, headers=a_h
    )
    assert r.status_code == 201
    # ben sees the same DM conversation
    msgs = (await client.get(f"/dm/{a_id}/messages", headers=b_h)).json()
    assert len(msgs) == 1 and msgs[0]["content"] == "hey ben"


async def test_dm_is_idempotent_not_duplicated(client, auth):
    """Repeated DMs between the same pair reuse one channel (no duplicate
    conversations), and cannot DM yourself."""
    a_h, a_id = await auth("cara")
    b_h, b_id = await auth("dan")
    await client.post(f"/dm/{b_id}/messages", json={"content": "1"}, headers=a_h)
    await client.post(f"/dm/{a_id}/messages", json={"content": "2"}, headers=b_h)
    msgs = (await client.get(f"/dm/{b_id}/messages", headers=a_h)).json()
    assert [m["content"] for m in msgs] == ["1", "2"]   # one shared thread

    self_dm = await client.post(
        f"/dm/{a_id}/messages", json={"content": "me"}, headers=a_h
    )
    assert self_dm.status_code == 400                    # cannot DM yourself
