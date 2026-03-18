"""Unit tests for the Redis sliding-window rate limiter."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

# Patch redis before import
with patch("redis.Redis", MagicMock()):
    from middleware.rate_limiter import _sliding_window_check, ip_rate_limit_middleware


def _make_pipeline_mock(count: int):
    """Return a mock redis pipeline whose execute() yields [None, None, count, None]."""
    pipe = MagicMock()
    pipe.__enter__ = MagicMock(return_value=pipe)
    pipe.__exit__  = MagicMock(return_value=False)
    pipe.execute   = MagicMock(return_value=[None, None, count, None])
    pipe.zremrangebyscore = MagicMock()
    pipe.zadd             = MagicMock()
    pipe.zcard            = MagicMock()
    pipe.expire           = MagicMock()
    return pipe


class TestSlidingWindowCheck:
    def test_under_limit_returns_count(self):
        pipe = _make_pipeline_mock(50)
        with patch("middleware.rate_limiter.get_redis") as mock_redis:
            mock_redis.return_value.pipeline.return_value = pipe
            count, limit = _sliding_window_check("test:key", 100)
        assert count == 50
        assert limit == 100

    def test_at_limit_passes(self):
        pipe = _make_pipeline_mock(100)
        with patch("middleware.rate_limiter.get_redis") as mock_redis:
            mock_redis.return_value.pipeline.return_value = pipe
            count, limit = _sliding_window_check("test:key", 100)
        assert count == 100

    def test_over_limit_raises_429(self):
        pipe = _make_pipeline_mock(101)
        with patch("middleware.rate_limiter.get_redis") as mock_redis:
            mock_redis.return_value.pipeline.return_value = pipe
            with pytest.raises(HTTPException) as exc_info:
                _sliding_window_check("test:key", 100)
        assert exc_info.value.status_code == 429
        assert "RATE_LIMIT_EXCEEDED" in str(exc_info.value.detail)

    def test_redis_failure_fails_open(self):
        import redis as _redis
        with patch("middleware.rate_limiter.get_redis") as mock_redis:
            mock_redis.return_value.pipeline.side_effect = _redis.RedisError("conn refused")
            count, limit = _sliding_window_check("test:key", 100)
        # Should NOT raise — fail open
        assert count == 0
        assert limit == 100

    def test_retry_after_header_present(self):
        pipe = _make_pipeline_mock(999)
        with patch("middleware.rate_limiter.get_redis") as mock_redis:
            mock_redis.return_value.pipeline.return_value = pipe
            with pytest.raises(HTTPException) as exc_info:
                _sliding_window_check("test:key", 100)
        assert "Retry-After" in exc_info.value.headers
