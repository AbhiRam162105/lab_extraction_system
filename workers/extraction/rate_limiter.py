"""
Adaptive Rate Limiter for Gemini API.

Implements intelligent rate limiting with:
- Sliding window tracking (60-second window)
- Adaptive backoff on 429 errors (reduce to 80% of limit)
- Automatic recovery after successful requests
- Thread-safe and async-compatible
"""

import asyncio
import time
import logging
from collections import deque
from threading import Lock
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiter configuration."""
    requests_per_minute: int = 15  # Gemini free tier default
    window_seconds: float = 60.0
    adaptive_backoff: bool = True
    backoff_factor: float = 0.8  # Reduce to 80% on 429 errors
    recovery_threshold: int = 10  # Successful requests before recovery
    min_requests_per_minute: int = 5  # Never go below this


class AdaptiveRateLimiter:
    """
    Thread-safe adaptive rate limiter with sliding window.
    
    Features:
    - Tracks requests in a sliding 60-second window
    - Blocks when approaching limit
    - Reduces limit on 429 errors (adaptive backoff)
    - Recovers limit after successful requests
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._effective_rpm = self.config.requests_per_minute
        self._requests: deque = deque()
        self._consecutive_successes = 0
        self._lock = Lock()
        self._async_lock: Optional[asyncio.Lock] = None
        
        logger.info(f"RateLimiter: {self._effective_rpm} RPM")
    
    @property
    def _async_lock_instance(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock
    
    def _clean_old_requests(self) -> None:
        cutoff = time.time() - self.config.window_seconds
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()
    # cleans old requests from 60 seconds before 
    
    def _wait_time(self) -> float:
        self._clean_old_requests()
        if len(self._requests) < self._effective_rpm:
            return 0.0
        oldest = self._requests[0]
        return max(0.0, (oldest + self.config.window_seconds) - time.time())
    
    def acquire(self) -> None:
        """Acquire permission to make a request. Blocks if needed."""
        with self._lock:
            wait_time = self._wait_time()
            if wait_time > 0:
                logger.info(f"Rate limit: waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                self._clean_old_requests()
            self._requests.append(time.time())
    
    # async def acquire_async(self) -> None:
    #     """Async version of acquire."""
    #     async with self._async_lock_instance:
    #         with self._lock:
    #             wait_time = self._wait_time()
    #         if wait_time > 0:
    #             logger.info(f"Rate limit: waiting {wait_time:.1f}s")
    #             await asyncio.sleep(wait_time)
    #         with self._lock:
    #             self._clean_old_requests()
    #             self._requests.append(time.time())

    ## For future use 
    
    def report_rate_limit_error(self) -> None:
        """Report 429 error - triggers adaptive backoff."""
        if not self.config.adaptive_backoff:
            return
        with self._lock:
            old_rpm = self._effective_rpm
            self._effective_rpm = max(
                int(self._effective_rpm * self.config.backoff_factor),
                self.config.min_requests_per_minute
            )
            self._consecutive_successes = 0
            logger.warning(f"Rate limit error! {old_rpm} -> {self._effective_rpm} RPM")
    
    def report_success(self) -> None:
        """Report success - may trigger recovery."""
        if not self.config.adaptive_backoff:
            return
        with self._lock:
            self._consecutive_successes += 1
            if (self._consecutive_successes >= self.config.recovery_threshold and
                self._effective_rpm < self.config.requests_per_minute):
                old_rpm = self._effective_rpm
                self._effective_rpm = min(
                    int(self._effective_rpm / self.config.backoff_factor),
                    self.config.requests_per_minute
                )
                self._consecutive_successes = 0
                logger.info(f"Rate limit recovering: {old_rpm} -> {self._effective_rpm} RPM")
    
    def get_stats(self) -> dict:
        with self._lock:
            self._clean_old_requests()
            return {
                "current_requests": len(self._requests),
                "effective_rpm": self._effective_rpm,
                "max_rpm": self.config.requests_per_minute,
                "is_throttled": self._effective_rpm < self.config.requests_per_minute
            }
    
    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._effective_rpm = self.config.requests_per_minute
            self._consecutive_successes = 0


# Global instance
_rate_limiter: Optional[AdaptiveRateLimiter] = None


def get_rate_limiter(requests_per_minute: Optional[int] = None) -> AdaptiveRateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    
    if _rate_limiter is None:
        try:
            from backend.core.config import get_settings
            settings = get_settings()
            rpm = requests_per_minute or settings.gemini.rate_limit or 15
        except:
            rpm = requests_per_minute or 15
        
        config = RateLimitConfig(requests_per_minute=rpm)
        _rate_limiter = AdaptiveRateLimiter(config)
    
    return _rate_limiter
