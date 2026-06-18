# Hemut — Real-Time Logistics Collaboration Platform

A Slack-style collaboration platform for logistics teams: channels, DMs,
real-time messaging, presence, inline shipment context, and one AI feature
(**channel thread summarization**). Built to the attached HLD/LLD.

**Stack:** Next.js 14 (App Router, TypeScript) · FastAPI (Python 3.12, async) ·
PostgreSQL 16 · Redis 7 · native WebSockets · SQLAlchemy 2.0 + Alembic.

---

## Project docs

| Doc | What's in it |
| --- | --- |
| [README.md](./README.md) | This file — setup, architecture, AI feature, tradeoffs. |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Full deploy guide (Docker / AWS), env vars, scaling, go-live checklist. |
| [CODE_REVIEW.md](./CODE_REVIEW.md) | Requirements + rubric assessment with per-item evidence and remediation status. |
| [backend/TEST_RESULTS.md](./backend/TEST_RESULTS.md) | Test run results, coverage, and what each test proves. |

---

## Quick start (local dev)

You need Docker (for Postgres + Redis), **Python 3.11–3.12**, and Node 18+.

> Python note: 3.13+ can fail to build `pydantic-core` / `asyncpg` wheels
> without a toolchain — 3.12 is the tested target.

### 1. Start Postgres + Redis

```bash
docker compose up -d        # brings up postgres:16 and redis:7
```

(No Docker? Install Postgres and Redis locally and point `DATABASE_URL` /
`REDIS_URL` at them — see DEPLOYMENT.md.)

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example .env      # then edit if needed (defaults work with docker compose)

alembic upgrade head         # create tables
python seed.py               # demo users, channels, shipments, messages

uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs.

### 3. Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                  # http://localhost:3000
```

### 4. Log in

Seeded users (password `password123`): **dispatch_admin** (admin),
**priya**, **rahul**. Open `#route-east`, post a message mentioning
`SHP-10293`, watch it appear in real time, and click **✨ Catch me up (24h)**.

---

## Running the tests

```bash
cd backend
pip install -r requirements.txt
pytest -q                                  # 39 tests, ~2.5s
pytest --cov=app --cov-report=term-missing # with coverage (~76%)
```

**39 tests, all passing, fully offline** against in-memory SQLite + fakeredis
with the LLM mocked — deterministic and non-billable. Coverage includes failure
paths, not just happy paths:

- **auth** — register/login/refresh, bad password, missing-token guard.
- **channels** — admin enforcement, join/leave/list, unread counts, read-cursor
  monotonicity.
- **messaging** — ordering, idempotency, `after_id`/`before_id` pagination,
  server-derived sender, rate-limit `429`, shipment webhook fire, DM idempotency.
- **realtime** — cross-worker Redis fan-out, dead-socket eviction, presence TTL,
  rate-limit counters (`test_realtime.py`).
- **AI** — mocked at both the interface and the real Anthropic SDK seam:
  hallucinated-citation filtering, prompt-injection posture, empty-window
  refusal, Redis cache short-circuit, provider selection by API key.
- **config** — fails closed in production with the dev JWT secret.

See [backend/TEST_RESULTS.md](./backend/TEST_RESULTS.md) for the full breakdown.

---

## Architecture overview

Three-tier app with a real-time fan-out bus. Stateless FastAPI workers each
hold a pool of WebSocket connections. Because any worker may hold a given
user's socket, **every message and presence event is published to Redis
(`chan:{channel_id}`)** and re-broadcast by all workers to their locally
connected subscribers. This is what lets the system scale horizontally toward
10k+ connections behind a sticky-session load balancer.

```
Next.js (XHR + WebSocket)
        │ HTTPS / WSS
   Load balancer (sticky)
        │
  FastAPI workers (W1..Wn, each with a WS pool)
        │  publish/subscribe          ┌── PostgreSQL (durable: users, channels,
        └────────── Redis ────────────┤    memberships, messages, shipments, …)
            (pub/sub, presence TTL,    └── (AI summaries cached in Redis + DB)
             rate-limit, summary cache)
```

- **Postgres** is the durable store. `messages.id` is `BIGSERIAL`, giving a
  monotonic ordering + replay cursor. Composite index on
  `messages(channel_id, id)` powers in-order pagination and `after_id` replay;
  a unique `(channel_id, client_msg_id)` enforces idempotent inserts. Schema is
  Alembic-managed (`41b307bfe8f2` initial → `0002` referential-integrity
  policy + indexes) with an explicit `ON DELETE` rule on every foreign key
  (CASCADE for join/child rows, RESTRICT to preserve authorship, SET NULL for
  soft links).
- **Redis** does two distinct jobs: (1) cross-worker pub/sub fan-out, and
  (2) lightweight caching — presence TTL keys, rate-limit counters, and the AI
  summary cache. Clear separation of concerns.
- **WebSockets** push new messages, presence changes, and AI tokens. The client
  keeps a single multiplexed socket, heart-beats every 20s, and reconnects with
  exponential backoff, replaying missed messages via `GET …?after_id=X`.

The `backend/` tree mirrors the LLD: `api/` (routers), `core/` (config,
security, deps, db), `models/`, `realtime/` (ws gateway, manager, redis bus),
`ai/` (summarizer + orchestration), `schemas/`.

### Why raw XMLHttpRequest?

All auth/form submissions go through `frontend/lib/xhr.ts` — a hand-rolled
`XMLHttpRequest` wrapper (the assignment's one tooling constraint). It exposes
the full request lifecycle that fetch/axios hide: upload `progress`, `timeout`,
`abort`, and `error` events, surfaced as a Promise with typed `HttpError`s.

---

## AI feature — thread summarization ("Catch me up")

**Why this feature.** In logistics, dispatchers and shift managers return to
channels with hundreds of overnight messages about delays, reroutes, and
handoffs. A "Catch me up on #route-east (last 24h)" summary removes a recurring,
concrete time sink — far higher value than chasing novelty.

**How it's implemented.** Triggered from the channel header. The backend pulls
the message window from Postgres (capped at 500 msgs / window), checks the Redis
summary cache, and if missed runs the summarizer. The result (text +
`source_message_ids`) is persisted to `ai_summaries` for citation/audit, cached
in Redis, and streamed over WebSocket (`ai_token` deltas → `ai_done` with
sources) so the UI renders live. Each summary is visually labeled and links back
to the cited `[#id]` source messages.

**A note on the LLM (per the chosen scope).** This build ships a deterministic,
**offline extractive summarizer** as the default so local dev and CI never make
billable calls. It scores messages by logistics signal words + shipment refs,
and grounds every line in a real `[#id]` — it never invents shipment data. The
`Summarizer` interface is the seam for a real model: set `ANTHROPIC_API_KEY` and
`get_summarizer()` returns the Claude-backed implementation, which uses the same
citation contract and treats chat content strictly as untrusted *data* (prompt-
injection mitigation), refusing out-of-context queries.

**What would change in production.**
- Move from on-demand to **incremental** summarization (rolling summary updated
  as messages arrive) to cut latency and cost.
- Add **RAG** over BOLs / shipment docs so summaries cite documents, not just
  chat.
- Per-org model routing, usage metering, and guardrail/eval pipelines before
  responses surface.

---

## Logistics domain awareness

Channel naming (`#route-east`, `#warehouse-mumbai`), mock shipments
(`SHP-10293` …), automatic shipment **entity extraction** that links messages to
shipments and (optionally) fires a webhook, an inline **shipment preview card**,
a **`/shipment <id>` slash command**, and an AI feature scoped to a real
dispatcher pain point.

---

## Design tradeoffs

| Decision | Chosen | Tradeoff accepted |
| --- | --- | --- |
| Message ordering | DB `BIGSERIAL` monotonic id | Single-writer ordering vs distributed-clock complexity |
| Delivery guarantee | At-least-once + idempotency key | Client dedupes; simpler than exactly-once |
| Presence | Redis TTL + heartbeats | Slight delay on offline detection vs constant polling |
| AI summarization | On-demand + cache | Not instant on first call; far lower cost than always-on |
| DMs | Modeled as 2-member channels | Reuses all channel logic; minor over-generalization |
| AI provider | Extractive default, Claude opt-in | Zero-cost/offline CI; real LLM is a one-env-var switch |

## Security

JWT (access + refresh) with role claims; argon2 password hashing; server always
derives `sender_id` from the token (no client spoofing); every query is scoped
by membership; admin-only channel creation guarded by a FastAPI dependency;
Redis rate-limiting on login and message posts; AI treats retrieved chat as
untrusted data. The app **fails closed** — it refuses to boot with
`APP_ENV=production` while the JWT secret is still the dev placeholder, so a
misconfigured deploy can never sign forgeable tokens. See DEPLOYMENT.md for the
rest of the production hardening (httpOnly cookies, HTTPS, secrets management,
audit logging).

## Deployment

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for the full guide: provisioning
Postgres + Redis (Docker or AWS RDS/ElastiCache), migrations, environment
variables, container build, scaling behind a load balancer, and a go-live
checklist.
