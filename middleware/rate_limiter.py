"""
Redis sliding-window rate limiting middleware for FastAPI.
Implements per-IP and per-user limits with standard RateLimit headers.
"""
import os
import time
import logging
from typing import Optional

import redis
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

RATE_LIMIT_RPM    = int(os.getenv("RATE_LIMIT_RPM", "100"))
AUTH_RATE_LIMIT   = int(os.getenv("AUTH_RATE_LIMIT_RPM", "1000"))
RATE_LIMIT_WINDOW = 60  # seconds
SKIP_PATHS        = {"/health", "/metrics", "/docs", "/openapi.json"}

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
            decode_responses=True,
        )
    return _redis_client


def _sliding_window_check(key: str, limit: int, window: int = RATE_LIMIT_WINDOW) -> tuple[int, int]:
    """
    Sliding window check via Redis sorted sets.
    Returns (current_count, limit). Raises HTTP 429 if exceeded.
    """
    r = get_redis()
    now = time.time()

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {f"{now}:{id(pipe)}": now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = pipe.execute()
        count = results[2]
    except redis.RedisError as exc:
        # Fail open — do not block traffic when Redis is unavailable
        logger.warning("redis_unavailable: %s — rate limit skipped", exc)
        return 0, limit

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please slow down.",
                "details": {"limit": limit, "window_seconds": window, "retry_after": window},
            },
            headers={
                "X-RateLimit-Limit":     str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset":     str(int(now + window)),
                "Retry-After":           str(window),
            },
        )
    return count, limit


async def ip_rate_limit_middleware(request: Request, call_next):
    """ASGI middleware: rate-limit by client IP, skip health/metrics paths."""
    if request.url.path in SKIP_PATHS:
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    count, limit = _sliding_window_check(f"rl:ip:{ip}", RATE_LIMIT_RPM)

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"]     = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
    return response


_bearer = HTTPBearer(auto_error=False)


def user_rate_limit(limit: int = AUTH_RATE_LIMIT):
    """FastAPI Depends factory: per-user rate limit using JWT sub claim."""
    async def _dep(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    ):
        if creds is None:
            return  # fall through to IP-level limit
        # Minimal sub extraction — replace with full jwt.decode() in production
        import base64, json as _json
        try:
            parts = creds.credentials.split(".")
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            sub = _json.loads(base64.urlsafe_b64decode(padded)).get("sub", "anon")
        except Exception:
            sub = "anon"
        _sliding_window_check(f"rl:user:{sub}", limit)
    return _dep
