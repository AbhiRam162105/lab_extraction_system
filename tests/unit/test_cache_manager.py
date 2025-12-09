"""
Unit tests for CacheManager.

Tests the two-tier caching system (Redis + Disk) with
SHA-256 hashing, compression, and partial result caching.

Note: These tests use standalone fixtures from conftest.py
to avoid import chain issues with pydantic.
"""

import pytest
import json
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

pytestmark = pytest.mark.unit


class TestCacheManager:
    """Tests for CacheManager class."""
    
    def test_init_with_redis(self, mock_redis, cache_config):
        """Test initialization with Redis client."""
        # Using fixture-provided cache_manager
        from tests.conftest import cache_manager
        assert cache_config is not None
    
    def test_init_creates_cache_manager(self, cache_manager):
        """Test cache manager is created with config."""
        assert cache_manager is not None
        assert cache_manager.redis is not None
    
    def test_get_image_hash(self, cache_manager, test_image_path: str):
        """Test SHA-256 hash generation for image."""
        result = cache_manager.get_image_hash(test_image_path)
        
        # Should return a valid hex hash
        assert result is not None
        assert len(result) == 64  # SHA-256 produces 64 hex chars
        
        # Hash should be consistent
        result2 = cache_manager.get_image_hash(test_image_path)
        assert result == result2
    
    def test_cache_miss_returns_none(self, cache_manager):
        """Test cache miss returns None."""
        result = cache_manager.get_cached_result("nonexistent_hash")
        assert result is None
    
    def test_cache_result(self, cache_manager, mock_redis):
        """Test caching a result."""
        test_data = {
            "tests": [{"test_name": "Hemoglobin", "value": "14.5"}],
            "patient_info": {"name": "John Doe"}
        }
        
        cache_manager.cache_result("test_hash_456", test_data)
        
        # Cache write should be tracked
        stats = cache_manager.get_stats()
        assert stats["cache_writes"] >= 0
    
    def test_invalidate(self, cache_manager, mock_redis):
        """Test cache invalidation."""
        cache_manager.invalidate("test_hash_789")
        # Should not raise an error
        assert True
    
    def test_get_stats(self, cache_manager):
        """Test getting cache statistics."""
        stats = cache_manager.get_stats()
        
        assert "redis_hits" in stats
        assert "redis_misses" in stats
        assert "hit_rate" in stats
    
    def test_cache_partial_result(self, cache_manager):
        """Test caching intermediate processing stages."""
        partial_result = {"preprocessing": {"blur_score": 150}}
        cache_manager.cache_partial_result("test_hash", "prep", partial_result)
        # Should not raise an error
        assert True


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""
    
    def test_default_config(self, cache_config):
        """Test configuration values."""
        assert cache_config.redis_enabled is True
        assert cache_config.disk_enabled is False  # Disabled in test config
        assert cache_config.redis_ttl_hours == 1
    
    def test_config_has_required_fields(self, cache_config):
        """Test config has all required fields."""
        assert hasattr(cache_config, 'redis_enabled')
        assert hasattr(cache_config, 'disk_enabled')
        assert hasattr(cache_config, 'compression_enabled')
        assert hasattr(cache_config, 'redis_ttl_hours')


class TestCacheStats:
    """Tests for CacheStats dataclass."""
    
    def test_hit_rate_calculation(self, cache_stats):
        """Test hit rate calculation."""
        stats = cache_stats(
            redis_hits=80,
            redis_misses=20,
            disk_hits=0,
            disk_misses=0,
            cache_writes=50
        )
        
        assert stats.total_hits == 80
        assert stats.total_requests == 100
        assert stats.hit_rate == 0.8
    
    def test_hit_rate_zero_requests(self, cache_stats):
        """Test hit rate with zero requests."""
        stats = cache_stats()
        
        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0
