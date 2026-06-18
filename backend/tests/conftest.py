"""Test fixtures: in-memory SQLite (StaticPool) + fakeredis, so the whole
suite runs offline, deterministically, and without Postgres/Redis/LLM."""
import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.realtime import redis_bus


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_bus, "_client", client)
    monkeypatch.setattr(redis_bus, "get_redis", lambda: client)
    yield client
    await client.flushall()


@pytest_asyncio.fixture
async def client(db_session):
    async def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth(client, db_session):
    """Register + login a user; return (headers, user_id).
    Pass make_admin=True to promote the user to global admin."""
    import uuid as _uuid

    from app.models.models import User

    async def _make(username="alice", make_admin=False):
        await client.post("/auth/register", json={
            "username": username, "email": f"{username}@example.com",
            "password": "password123", "display_name": username.title(),
        })
        login = await client.post("/auth/login", json={
            "username": username, "password": "password123",
        })
        tokens = login.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        me = await client.get("/auth/me", headers=headers)
        user_id = me.json()["id"]
        if make_admin:
            user = await db_session.get(User, _uuid.UUID(user_id))
            user.role = "admin"
            await db_session.commit()
            # re-login so the JWT carries the admin role claim
            login = await client.post("/auth/login", json={
                "username": username, "password": "password123",
            })
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        return headers, user_id
    return _make
