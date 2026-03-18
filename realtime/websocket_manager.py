"""
WebSocket connection manager with Redis Pub/Sub for horizontal scaling.
Each backend instance holds its own connection table; Redis fan-out
delivers messages across instances.
"""
import asyncio
import json
import logging
from typing import Dict, Optional, Set

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30   # seconds
MAX_MESSAGE_BYTES  = 64 * 1024  # 64 KB


class ConnectionManager:
    """Thread-safe WebSocket manager with Redis Pub/Sub broadcasting."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def startup(self) -> None:
        self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        asyncio.create_task(self._run_subscriber())
        logger.info("ConnectionManager started (redis=%s)", self._redis_url)

    # ── Connection handling ────────────────────────────────────────────────

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, set()).add(ws)
        logger.info("ws_connect user=%s total=%d", user_id, self.total)

    def disconnect(self, ws: WebSocket, user_id: str) -> None:
        bucket = self._connections.get(user_id, set())
        bucket.discard(ws)
        if not bucket:
            self._connections.pop(user_id, None)
        logger.info("ws_disconnect user=%s total=%d", user_id, self.total)

    @property
    def total(self) -> int:
        return sum(len(v) for v in self._connections.values())

    # ── Sending ────────────────────────────────────────────────────────────

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """Deliver message to all sockets for a user. Returns delivery count."""
        bucket = self._connections.get(user_id, set())
        dead, delivered = set(), 0
        for ws in bucket.copy():
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:
                dead.add(ws)
        bucket -= dead
        return delivered

    async def broadcast(self, message: dict) -> None:
        """Deliver to every connected user on this instance."""
        for uid in list(self._connections):
            await self.send_to_user(uid, message)

    async def publish(self, channel: str, message: dict) -> None:
        """Publish to Redis — all instances receive via subscriber."""
        if self._redis:
            await self._redis.publish(channel, json.dumps(message))

    # ── Redis Pub/Sub subscriber ───────────────────────────────────────────

    async def _run_subscriber(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("notifications:*", "analytics:live", "broadcast:all")
        logger.info("Redis subscriber listening")
        async for msg in pubsub.listen():
            if msg["type"] not in ("pmessage", "message"):
                continue
            try:
                channel: str = msg.get("channel") or msg.get("pattern", "")
                data = json.loads(msg["data"])
                if channel.startswith("notifications:"):
                    await self.send_to_user(channel.split(":", 1)[1], data)
                elif channel in ("analytics:live", "broadcast:all"):
                    await self.broadcast(data)
            except Exception as exc:
                logger.error("subscriber_error: %s", exc)

    # ── Heartbeat helper ───────────────────────────────────────────────────

    @staticmethod
    async def heartbeat(ws: WebSocket) -> None:
        """Keep connection alive with periodic pings."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                return


manager = ConnectionManager()
