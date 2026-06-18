import pytest

pytestmark = pytest.mark.asyncio


async def test_register_and_login_happy_path(client):
    r = await client.post("/auth/register", json={
        "username": "bob", "email": "bob@example.com",
        "password": "password123", "display_name": "Bob",
    })
    assert r.status_code == 201
    assert r.json()["username"] == "bob"

    r = await client.post("/auth/login", json={
        "username": "bob", "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_register_duplicate_username(client):
    body = {"username": "dup", "email": "dup@example.com",
            "password": "password123", "display_name": "Dup"}
    assert (await client.post("/auth/register", json=body)).status_code == 201
    body2 = {**body, "email": "other@example.com"}
    assert (await client.post("/auth/register", json=body2)).status_code == 409


async def test_login_bad_password(client):
    await client.post("/auth/register", json={
        "username": "carol", "email": "carol@example.com",
        "password": "password123", "display_name": "Carol",
    })
    r = await client.post("/auth/login", json={
        "username": "carol", "password": "wrongpass",
    })
    assert r.status_code == 401


async def test_protected_route_requires_token(client):
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get(
        "/auth/me", headers={"Authorization": "Bearer garbage"}
    )).status_code == 401


async def test_refresh_rotates_access(client):
    await client.post("/auth/register", json={
        "username": "dave", "email": "dave@example.com",
        "password": "password123", "display_name": "Dave",
    })
    login = (await client.post("/auth/login", json={
        "username": "dave", "password": "password123",
    })).json()
    r = await client.post("/auth/refresh", json={
        "refresh_token": login["refresh_token"],
    })
    assert r.status_code == 200
    assert "access_token" in r.json()
    # an access token cannot be used to refresh
    bad = await client.post("/auth/refresh", json={
        "refresh_token": login["access_token"],
    })
    assert bad.status_code == 401
