"""Unit tests for the analytics event pipeline."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

with patch("redis.asyncio.from_url", AsyncMock()):
    from analytics.pipeline import AnalyticsPipeline, AnalyticsEvent


@pytest.fixture
def pipeline():
    p = AnalyticsPipeline(redis_url="redis://localhost:6379")
    p._redis = AsyncMock()
    p._redis.publish = AsyncMock(return_value=1)
    return p


class TestBuffering:
    @pytest.mark.asyncio
    async def test_events_buffered(self, pipeline):
        await pipeline.track(AnalyticsEvent(event_type="page_view", user_id="u1"))
        await pipeline.track(AnalyticsEvent(event_type="api_call",  user_id="u2"))
        assert len(pipeline._buf) == 2

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self, pipeline):
        await pipeline.track(AnalyticsEvent(event_type="page_view", user_id="u1"))
        await pipeline._flush()
        assert len(pipeline._buf) == 0

    @pytest.mark.asyncio
    async def test_buffer_flushes_at_max_size(self, pipeline):
        from analytics.pipeline import BUFFER_MAX_SIZE
        # Fill buffer to max — flush should trigger automatically
        for i in range(BUFFER_MAX_SIZE):
            await pipeline.track(AnalyticsEvent(event_type="test", user_id=f"u{i}"))
        assert len(pipeline._buf) == 0  # auto-flushed

    @pytest.mark.asyncio
    async def test_live_event_published_to_redis(self, pipeline):
        await pipeline.track(AnalyticsEvent(event_type="page_view", user_id="u1"))
        pipeline._redis.publish.assert_called_once()
        channel, payload_json = pipeline._redis.publish.call_args[0]
        assert channel == "analytics:live"
        payload = json.loads(payload_json)
        assert payload["event_type"] == "page_view"


class TestHelpers:
    @pytest.mark.asyncio
    async def test_track_page_view(self, pipeline):
        await pipeline.track_page_view("u1", "https://example.com/home", referrer="https://google.com")
        ev = pipeline._buf[0]
        assert ev.event_type == "page_view"
        assert ev.page_url   == "https://example.com/home"

    @pytest.mark.asyncio
    async def test_track_api_call(self, pipeline):
        await pipeline.track_api_call("u1", "/api/users", "GET", 200, 42)
        ev = pipeline._buf[0]
        assert ev.event_type == "api_call"
        assert ev.event_data["status_code"] == 200
        assert ev.event_data["duration_ms"] == 42

    @pytest.mark.asyncio
    async def test_graceful_stop_flushes(self, pipeline):
        await pipeline.track(AnalyticsEvent(event_type="test", user_id="u1"))
        assert len(pipeline._buf) == 1
        await pipeline.stop()
        assert len(pipeline._buf) == 0
