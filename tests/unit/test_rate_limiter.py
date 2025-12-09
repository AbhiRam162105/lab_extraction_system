"""
Unit tests for AdaptiveRateLimiter.

Tests the sliding window rate limiting with adaptive backoff
and recovery mechanisms for Gemini API calls.

Note: These tests use fixtures from conftest.py that provide
standalone implementations to avoid import chain issues.
"""

import pytest
import time
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestAdaptiveRateLimiter:
    """Tests for AdaptiveRateLimiter class."""
    
    def test_init_default_config(self, rate_limiter):
        """Test initialization with config."""
        assert rate_limiter is not None
        assert rate_limiter._effective_rpm == rate_limiter.config.requests_per_minute
    
    def test_init_custom_config(self, rate_limit_config, rate_limiter):
        """Test initialization with custom config."""
        assert rate_limiter._effective_rpm == 10
        assert rate_limiter.config.backoff_factor == 0.8
    
    def test_acquire_under_limit(self, rate_limiter):
        """Test acquire when under rate limit."""
        # Should not block when under limit
        start = time.time()
        rate_limiter.acquire()
        elapsed = time.time() - start
        
        # Should complete almost instantly
        assert elapsed < 0.1
    
    def test_acquire_multiple_under_limit(self, rate_limiter):
        """Test multiple acquires under limit."""
        # Acquire several times (less than limit)
        for _ in range(5):
            rate_limiter.acquire()
        
        stats = rate_limiter.get_stats()
        assert stats["current_requests"] <= 5
    
    def test_report_rate_limit_error_reduces_rpm(self, rate_limiter):
        """Test that 429 error reduces effective RPM."""
        initial_rpm = rate_limiter._effective_rpm
        
        rate_limiter.report_rate_limit_error()
        
        # RPM should be reduced by backoff_factor (0.8)
        expected_rpm = int(initial_rpm * 0.8)
        assert rate_limiter._effective_rpm == expected_rpm
    
    def test_report_rate_limit_error_minimum_rpm(self, rate_limiter, rate_limit_config):
        """Test that RPM doesn't go below minimum."""
        # Force multiple errors to hit minimum
        for _ in range(10):
            rate_limiter.report_rate_limit_error()
        
        assert rate_limiter._effective_rpm >= rate_limit_config.min_requests_per_minute
    
    def test_report_success_increments_counter(self, rate_limiter):
        """Test that success increments consecutive success counter."""
        rate_limiter.report_success()
        
        assert rate_limiter._consecutive_successes == 1
    
    def test_report_success_recovery(self, rate_limiter, rate_limit_config):
        """Test RPM recovery after successful requests."""
        # First, reduce RPM
        rate_limiter.report_rate_limit_error()
        reduced_rpm = rate_limiter._effective_rpm
        
        # Then report enough successes to trigger recovery
        for _ in range(rate_limit_config.recovery_threshold):
            rate_limiter.report_success()
        
        # RPM should have recovered (increased)
        assert rate_limiter._effective_rpm > reduced_rpm
    
    def test_reset(self, rate_limiter):
        """Test reset clears all state."""
        # Add some state
        rate_limiter.acquire()
        rate_limiter.report_rate_limit_error()
        
        # Reset
        rate_limiter.reset()
        
        # State should be cleared
        assert rate_limiter._consecutive_successes == 0
        assert rate_limiter._effective_rpm == rate_limiter.config.requests_per_minute
    
    def test_get_stats(self, rate_limiter):
        """Test get_stats returns expected fields."""
        rate_limiter.acquire()
        
        stats = rate_limiter.get_stats()
        
        assert "current_requests" in stats
        assert "effective_rpm" in stats
        assert "max_rpm" in stats
        assert "is_throttled" in stats
    
    def test_is_throttled_after_error(self, rate_limiter):
        """Test is_throttled flag after rate limit error."""
        # Initially not throttled
        stats = rate_limiter.get_stats()
        assert stats["is_throttled"] is False
        
        # After error, should be throttled
        rate_limiter.report_rate_limit_error()
        stats = rate_limiter.get_stats()
        assert stats["is_throttled"] is True


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass - using fixture-provided config."""
    
    def test_default_values(self, rate_limit_config):
        """Test configuration values (fixture defaults)."""
        assert rate_limit_config.requests_per_minute == 10
        assert rate_limit_config.window_seconds == 60.0
        assert rate_limit_config.adaptive_backoff is True
        assert rate_limit_config.backoff_factor == 0.8
        assert rate_limit_config.recovery_threshold == 5
        assert rate_limit_config.min_requests_per_minute == 2
    
    def test_config_has_required_fields(self, rate_limit_config):
        """Test that config has all required fields."""
        assert hasattr(rate_limit_config, 'requests_per_minute')
        assert hasattr(rate_limit_config, 'window_seconds')
        assert hasattr(rate_limit_config, 'adaptive_backoff')
        assert hasattr(rate_limit_config, 'backoff_factor')
        assert hasattr(rate_limit_config, 'recovery_threshold')
        assert hasattr(rate_limit_config, 'min_requests_per_minute')


@pytest.mark.asyncio
class TestAsyncRateLimiter:
    """Tests for async rate limiter functionality."""
    
    async def test_acquire_async_under_limit(self, rate_limiter):
        """Test async acquire when under limit."""
        await rate_limiter.acquire_async()
        
        stats = rate_limiter.get_stats()
        assert stats["current_requests"] >= 1
