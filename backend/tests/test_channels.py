import pytest

pytestmark = pytest.mark.asyncio


async def _create_channel(client, headers, name="route-east"):
    return await client.post("/channels", json={"name": name}, headers=headers)


async def test_admin_can_create_channel(client, auth):
    headers, _ = await auth("admin1", make_admin=True)
    r = await _create_channel(client, headers)
    assert r.status_code == 201
    assert r.json()["name"] == "route-east"


async def test_member_cannot_create_channel(client, auth):
    headers, _ = await auth("member1")
    r = await _create_channel(client, headers)
    assert r.status_code == 403


async def test_join_leave_and_list(client, auth):
    admin_h, _ = await auth("admin2", make_admin=True)
    ch = (await _create_channel(client, admin_h, "warehouse-mumbai")).json()

    member_h, _ = await auth("member2")
    # not joined yet -> not in list
    assert (await client.get("/channels", headers=member_h)).json() == []

    assert (await client.post(
        f"/channels/{ch['id']}/join", headers=member_h
    )).status_code == 204
    listed = (await client.get("/channels", headers=member_h)).json()
    assert len(listed) == 1 and listed[0]["id"] == ch["id"]

    assert (await client.post(
        f"/channels/{ch['id']}/leave", headers=member_h
    )).status_code == 204
    assert (await client.get("/channels", headers=member_h)).json() == []


async def test_non_member_cannot_post(client, auth):
    admin_h, _ = await auth("admin3", make_admin=True)
    ch = (await _create_channel(client, admin_h, "secret")).json()
    outsider_h, _ = await auth("outsider")
    r = await client.post(
        f"/channels/{ch['id']}/messages",
        json={"content": "hello"}, headers=outsider_h,
    )
    assert r.status_code == 403


async def test_unread_count_and_mark_read(client, auth):
    """A member who joins after messages exist sees them as unread; marking
    read advances the cursor and clears the badge."""
    admin_h, _ = await auth("admin4", make_admin=True)
    ch = (await _create_channel(client, admin_h, "route-north")).json()

    member_h, _ = await auth("reader1")
    await client.post(f"/channels/{ch['id']}/join", headers=member_h)

    ids = []
    for i in range(3):
        r = await client.post(
            f"/channels/{ch['id']}/messages",
            json={"content": f"u{i}"}, headers=admin_h,
        )
        ids.append(r.json()["id"])

    listed = (await client.get("/channels", headers=member_h)).json()
    assert listed[0]["unread"] == 3

    # mark read up to the 2nd message -> 1 still unread
    await client.post(
        f"/channels/{ch['id']}/read", json={"last_id": ids[1]}, headers=member_h
    )
    listed = (await client.get("/channels", headers=member_h)).json()
    assert listed[0]["unread"] == 1

    # mark read to the latest -> 0 unread
    await client.post(
        f"/channels/{ch['id']}/read", json={"last_id": ids[2]}, headers=member_h
    )
    listed = (await client.get("/channels", headers=member_h)).json()
    assert listed[0]["unread"] == 0


async def test_mark_read_never_moves_cursor_backwards(client, auth):
    """A stale/out-of-order read receipt must not resurrect already-read
    messages as unread."""
    admin_h, _ = await auth("admin5", make_admin=True)
    ch = (await _create_channel(client, admin_h, "route-west")).json()
    member_h, _ = await auth("reader2")
    await client.post(f"/channels/{ch['id']}/join", headers=member_h)
    ids = []
    for i in range(3):
        r = await client.post(
            f"/channels/{ch['id']}/messages",
            json={"content": f"w{i}"}, headers=admin_h,
        )
        ids.append(r.json()["id"])

    await client.post(
        f"/channels/{ch['id']}/read", json={"last_id": ids[2]}, headers=member_h
    )
    # a late, lower receipt arrives — must be ignored
    await client.post(
        f"/channels/{ch['id']}/read", json={"last_id": ids[0]}, headers=member_h
    )
    listed = (await client.get("/channels", headers=member_h)).json()
    assert listed[0]["unread"] == 0
