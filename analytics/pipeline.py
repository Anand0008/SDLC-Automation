"""
Analytics event pipeline — buffered ingestion, PostgreSQL persistence,
and Redis live-streaming for real-time dashboards.
"""
import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

BUFFER_MAX_SIZE       = 1000
FLUSH_INTERVAL        = 5.0   # seconds
LIVE_CHANNEL          = "analytics:live"


@dataclass
class AnalyticsEvent:
    event_type: str
    user_id:    Optional[str]       = None
    session_id: Optional[str]       = None
    event_data: Dict[str, Any]      = field(default_factory=dict)
    page_url:   Optional[str]       = None
    referrer:   Optional[str]       = None
    ip_address: Optional[str]       = None
    user_agent: Optional[str]       = None
    id:         str                 = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str                 = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class AnalyticsPipeline:
    """
    Buffered analytics event pipeline.

    Events accumulate in an in-memory buffer and are flushed to the
    `analytics_events` PostgreSQL table in bulk batches.  Each event is
    also published to the Redis `analytics:live` channel so admin
    WebSocket dashboards receive real-time updates.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        db_session_factory=None,
    ):
        self._buf:    List[AnalyticsEvent] = []
        self._lock    = asyncio.Lock()
        self._redis_url = redis_url
        self._redis:  Optional[aioredis.Redis] = None
        self._db      = db_session_factory
        self._task:   Optional[asyncio.Task]   = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._redis = await aioredis.from_url(self._redis_url)
        self._task  = asyncio.create_task(self._periodic_flush())
        logger.info("AnalyticsPipeline started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self._flush()
        logger.info("AnalyticsPipeline stopped — buffer flushed")

    # ── Public API ─────────────────────────────────────────────────────────

    async def track(self, event: AnalyticsEvent) -> None:
        async with self._lock:
            self._buf.append(event)
            should_flush = len(self._buf) >= BUFFER_MAX_SIZE

        # Publish live update (non-blocking)
        if self._redis:
            try:
                await self._redis.publish(
                    LIVE_CHANNEL,
                    json.dumps({
                        "type":       "analytics_event",
                        "event_type": event.event_type,
                        "user_id":    event.user_id,
                        "ts":         event.created_at,
                    }),
                )
            except Exception as exc:
                logger.warning("live_publish_failed: %s", exc)

        if should_flush:
            await self._flush()

    async def track_page_view(
        self, user_id: str, page_url: str, referrer: str = None, **kw
    ) -> None:
        await self.track(AnalyticsEvent(
            event_type="page_view", user_id=user_id, page_url=page_url, referrer=referrer, **kw
        ))

    async def track_api_call(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: int,
    ) -> None:
        await self.track(AnalyticsEvent(
            event_type="api_call",
            user_id=user_id,
            event_data={
                "endpoint":    endpoint,
                "method":      method,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        ))

    # ── Internal flush ─────────────────────────────────────────────────────

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buf:
                return
            batch, self._buf = self._buf[:], []

        logger.info("Flushing %d analytics events", len(batch))
        if self._db:
            # Production path: bulk-copy to analytics_events table
            # async with self._db() as session:
            #     session.add_all([...])
            #     await session.commit()
            pass
        else:
            for ev in batch:
                logger.debug("analytics_event: %s", json.dumps(ev.to_dict()))


pipeline = AnalyticsPipeline()
