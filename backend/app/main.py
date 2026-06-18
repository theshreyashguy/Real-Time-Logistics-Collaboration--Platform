"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, channels, dm, messages, shipments, summarize
from app.core.config import settings
from app.realtime import redis_bus, ws
from app.realtime.manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()
    yield
    await manager.stop()
    await redis_bus.close_redis()


app = FastAPI(title="Hemut Logistics Chat", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(messages.router)
app.include_router(dm.router)
app.include_router(shipments.router)
app.include_router(summarize.router)
app.include_router(ws.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
