# SDLC-Automation Platform

A production-ready Python backend platform with authentication, rate limiting,
real-time WebSocket features, and analytics — built as part of the AI-assisted
SDLC automation pipeline.

## Repository Structure

```
auth/            JWT token generation and validation (RS256)
middleware/      Redis sliding-window rate limiting
realtime/        WebSocket connection manager + Redis Pub/Sub scaling
analytics/       Buffered event pipeline with live streaming
scripts/         Utility and migration scripts
tests/           Unit and integration tests
```

## Modules

### Authentication (`auth/`)
- `jwt_handler.py` — JWT token pair management (access 15 min + refresh 7 days)
- RS256 asymmetric signing; FastAPI `Depends` integration

### Rate Limiting (`middleware/`)
- `rate_limiter.py` — Redis sliding-window algorithm
- Per-IP (100 req/min) and per-user (1000 req/min) limits
- Configurable via `RATE_LIMIT_RPM` env variable
- HTTP 429 with `Retry-After` and `X-RateLimit-*` headers

### Real-Time (`realtime/`)
- `websocket_manager.py` — WebSocket connection manager
- Redis Pub/Sub for horizontal multi-instance broadcasting
- Heartbeat every 30 s; automatic dead-connection cleanup

### Analytics (`analytics/`)
- `pipeline.py` — Buffered event pipeline (flush at 1000 events or 5 s)
- PostgreSQL batch writes; Redis `analytics:live` channel for dashboards
- `track_page_view()`, `track_api_call()` helpers

## Environment Variables

```env
RATE_LIMIT_RPM=100        # requests/min per IP (default)
REDIS_HOST=localhost
REDIS_PORT=6379
DATABASE_URL=postgresql://user:pass@localhost/db
```

## Quick Start

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Architecture Docs

Full design documentation lives in Confluence (Software Development space):
- System Architecture Overview
- API Design Standards
- Database Schema and Migrations
- Security and Authentication Guidelines
- Real-Time Features and WebSocket Scaling
