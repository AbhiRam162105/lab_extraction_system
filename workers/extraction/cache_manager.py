"""
Intelligent Caching Layer for Lab Report Extraction.

Two-tier caching system:
- Tier 1: Redis cache (fast, 24-hour expiry)
- Tier 2: Disk cache (persistent, in storage/cache/)

Features:
- SHA-256 hash of image file as cache key
- Stores both raw extraction and standardized results
- Cache hit/miss metrics
- Automatic cache invalidation
"""

import os
import json
import hashlib
import logging
import pickle
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Cache configuration."""
    redis_enabled: bool = True
    disk_enabled: bool = True
    redis_ttl_hours: int = 24
    disk_cache_dir: str = "storage/cache"
    max_disk_cache_size_mb: int = 5000  # 5GB
    hash_algorithm: str = "sha256"


@dataclass
class CacheStats:
    """Cache statistics."""
    redis_hits: int = 0
    redis_misses: int = 0
    disk_hits: int = 0
    disk_misses: int = 0
    cache_writes: int = 0
    
    @property
    def total_hits(self) -> int:
        return self.redis_hits + self.disk_hits
    
    @property
    def total_requests(self) -> int:
        return self.redis_hits + self.redis_misses
    
    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_hits / self.total_requests


class CacheManager:
    """
    Two-tier cache manager for extraction results.
    
    Tier 1 (Redis): Fast in-memory cache with TTL
    Tier 2 (Disk): Persistent file-based cache
    
    Usage:
        cache = CacheManager(redis_client=redis.Redis())
        
        # Check cache before API call
        image_hash = cache.get_image_hash("/path/to/image.jpg")
        cached = cache.get_cached_result(image_hash)
        
        if cached:
            return cached
        
        # Process and cache result
        result = process_image(...)
        cache.cache_result(image_hash, result)
    """
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        config: Optional[CacheConfig] = None
    ):
        """
        Initialize cache manager.
        
        Args:
            redis_client: Redis client instance (optional)
            config: Cache configuration
        """
        self.config = config or CacheConfig()
        self.redis = redis_client
        self.stats = CacheStats()
        
        # Ensure disk cache directory exists
        if self.config.disk_enabled:
            self._cache_dir = Path(self.config.disk_cache_dir)
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"CacheManager initialized: redis={self.config.redis_enabled and redis_client is not None}, "
            f"disk={self.config.disk_enabled}"
        )
    
    def get_image_hash(self, image_path: str) -> str:
        """
        Generate SHA-256 hash of image file.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Hex digest of image hash
        """
        hasher = hashlib.new(self.config.hash_algorithm)
        
        with open(image_path, 'rb') as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def get_cached_result(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get cached extraction result.
        
        Checks Redis first, then disk cache.
        
        Args:
            image_hash: SHA-256 hash of image
            
        Returns:
            Cached result dict or None if not found
        """
        # Try Redis first (Tier 1)
        if self.config.redis_enabled and self.redis:
            result = self._get_from_redis(image_hash)
            if result:
                self.stats.redis_hits += 1
                logger.debug(f"Cache HIT (Redis): {image_hash[:16]}...")
                return result
            self.stats.redis_misses += 1
        
        # Try disk cache (Tier 2)
        if self.config.disk_enabled:
            result = self._get_from_disk(image_hash)
            if result:
                self.stats.disk_hits += 1
                logger.debug(f"Cache HIT (Disk): {image_hash[:16]}...")
                
                # Promote to Redis for faster future access
                if self.config.redis_enabled and self.redis:
                    self._set_to_redis(image_hash, result)
                
                return result
            self.stats.disk_misses += 1
        
        logger.debug(f"Cache MISS: {image_hash[:16]}...")
        return None
    
    def cache_result(
        self,
        image_hash: str,
        result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Cache extraction result to both tiers.
        
        Args:
            image_hash: SHA-256 hash of image
            result: Extraction result to cache
            metadata: Optional metadata (timestamp, version, etc.)
        """
        cache_entry = {
            "result": result,
            "cached_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        # Write to Redis (Tier 1)
        if self.config.redis_enabled and self.redis:
            self._set_to_redis(image_hash, cache_entry)
        
        # Write to disk (Tier 2)
        if self.config.disk_enabled:
            self._set_to_disk(image_hash, cache_entry)
        
        self.stats.cache_writes += 1
        logger.debug(f"Cached result: {image_hash[:16]}...")
    
    def invalidate(self, image_hash: str) -> None:
        """
        Invalidate cache entry.
        
        Args:
            image_hash: Hash of image to invalidate
        """
        # Remove from Redis
        if self.config.redis_enabled and self.redis:
            try:
                self.redis.delete(f"lab_cache:{image_hash}")
            except Exception as e:
                logger.warning(f"Failed to invalidate Redis cache: {e}")
        
        # Remove from disk
        if self.config.disk_enabled:
            cache_file = self._get_disk_path(image_hash)
            if cache_file.exists():
                cache_file.unlink()
        
        logger.debug(f"Invalidated cache: {image_hash[:16]}...")
    
    def clear_all(self) -> int:
        """
        Clear all cached data.
        
        Returns:
            Number of entries cleared
        """
        count = 0
        
        # Clear Redis
        if self.config.redis_enabled and self.redis:
            try:
                keys = self.redis.keys("lab_cache:*")
                if keys:
                    count += self.redis.delete(*keys)
            except Exception as e:
                logger.warning(f"Failed to clear Redis cache: {e}")
        
        # Clear disk
        if self.config.disk_enabled and self._cache_dir.exists():
            for cache_file in self._cache_dir.glob("*.cache"):
                cache_file.unlink()
                count += 1
        
        logger.info(f"Cleared {count} cache entries")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        disk_size = 0
        disk_count = 0
        
        if self.config.disk_enabled and self._cache_dir.exists():
            for cache_file in self._cache_dir.glob("*.cache"):
                disk_size += cache_file.stat().st_size
                disk_count += 1
        
        return {
            "redis_hits": self.stats.redis_hits,
            "redis_misses": self.stats.redis_misses,
            "disk_hits": self.stats.disk_hits,
            "disk_misses": self.stats.disk_misses,
            "total_hits": self.stats.total_hits,
            "total_requests": self.stats.total_requests,
            "hit_rate": f"{self.stats.hit_rate:.1%}",
            "cache_writes": self.stats.cache_writes,
            "disk_cache_size_mb": disk_size / (1024 * 1024),
            "disk_cache_count": disk_count
        }
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _get_from_redis(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """Get from Redis cache."""
        try:
            key = f"lab_cache:{image_hash}"
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")
        return None
    
    def _set_to_redis(self, image_hash: str, data: Dict[str, Any]) -> None:
        """Set to Redis cache with TTL."""
        try:
            key = f"lab_cache:{image_hash}"
            ttl_seconds = self.config.redis_ttl_hours * 3600
            self.redis.setex(key, ttl_seconds, json.dumps(data))
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")
    
    def _get_disk_path(self, image_hash: str) -> Path:
        """Get disk cache file path."""
        # Use first 2 chars as subdirectory for better distribution
        subdir = self._cache_dir / image_hash[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{image_hash}.cache"
    
    def _get_from_disk(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """Get from disk cache."""
        try:
            cache_file = self._get_disk_path(image_hash)
            if cache_file.exists():
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
        except Exception as e:
            logger.warning(f"Disk cache read failed: {e}")
        return None
    
    def _set_to_disk(self, image_hash: str, data: Dict[str, Any]) -> None:
        """Set to disk cache."""
        try:
            cache_file = self._get_disk_path(image_hash)
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"Disk cache write failed: {e}")


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    Get or create the global cache manager.
    
    Returns:
        Shared CacheManager instance
    """
    global _cache_manager
    
    if _cache_manager is None:
        # Try to get Redis connection
        redis_client = None
        try:
            from backend.core.config import get_settings
            settings = get_settings()
            
            import redis
            redis_client = redis.from_url(settings.redis.url)
            redis_client.ping()  # Test connection
        except Exception as e:
            logger.warning(f"Redis not available for caching: {e}")
        
        _cache_manager = CacheManager(redis_client=redis_client)
    
    return _cache_manager
