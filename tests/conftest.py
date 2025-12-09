"""
Shared pytest fixtures for Lab Extraction System tests.

Provides mocked dependencies to avoid actual API calls and external services.
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock, patch, MagicMock

import pytest
from PIL import Image
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Environment Setup
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    os.environ["TESTING"] = "true"
    os.environ["GEMINI_API_KEY"] = "test-api-key"
    yield


# =============================================================================
# Image Fixtures
# =============================================================================

@pytest.fixture
def sample_image() -> Image.Image:
    """Create a sample test image (simulating a lab report)."""
    # Create a white image with some text-like patterns
    img_array = np.ones((800, 600, 3), dtype=np.uint8) * 255
    
    # Add some dark horizontal lines to simulate text rows
    for y in range(100, 700, 50):
        img_array[y:y+10, 50:550] = 30  # Dark gray text lines
    
    return Image.fromarray(img_array, 'RGB')


@pytest.fixture
def blurry_image(sample_image: Image.Image) -> Image.Image:
    """Create a blurry version of the sample image."""
    from PIL import ImageFilter
    return sample_image.filter(ImageFilter.GaussianBlur(radius=10))


@pytest.fixture
def low_contrast_image() -> Image.Image:
    """Create a low contrast image."""
    # Gray image with minimal variation
    img_array = np.ones((800, 600, 3), dtype=np.uint8) * 128
    img_array[100:700, 50:550] = 120  # Very low contrast
    return Image.fromarray(img_array, 'RGB')


@pytest.fixture
def test_image_path(sample_image: Image.Image, tmp_path: Path) -> str:
    """Save sample image to temp file and return path."""
    image_path = tmp_path / "test_lab_report.png"
    sample_image.save(str(image_path))
    return str(image_path)


@pytest.fixture
def blurry_image_path(blurry_image: Image.Image, tmp_path: Path) -> str:
    """Save blurry image to temp file and return path."""
    image_path = tmp_path / "blurry_lab_report.png"
    blurry_image.save(str(image_path))
    return str(image_path)


# =============================================================================
# Mock Redis
# =============================================================================

@pytest.fixture
def mock_redis():
    """Create a mock Redis client using fakeredis."""
    try:
        import fakeredis
        return fakeredis.FakeRedis()
    except ImportError:
        # Fallback to Mock if fakeredis not available
        mock = Mock()
        mock.get.return_value = None
        mock.set.return_value = True
        mock.delete.return_value = 1
        return mock


# =============================================================================
# Mock Gemini API
# =============================================================================

@pytest.fixture
def sample_gemini_extraction_response() -> Dict[str, Any]:
    """Sample Gemini API extraction response."""
    return {
        "patient_info": {
            "patient_name": "John Doe",
            "patient_id": "P12345",
            "age": "45 years",
            "gender": "Male",
            "sample_date": "2024-01-15"
        },
        "lab_results": [
            {
                "test_name": "Hemoglobin",
                "value": "14.5",
                "unit": "g/dL",
                "reference_range": "13.0 - 17.0",
                "flag": ""
            },
            {
                "test_name": "WBC",
                "value": "8500",
                "unit": "/uL",
                "reference_range": "4000 - 11000",
                "flag": ""
            },
            {
                "test_name": "RBC",
                "value": "5.2",
                "unit": "million/uL",
                "reference_range": "4.5 - 5.5",
                "flag": ""
            },
            {
                "test_name": "Platelet Count",
                "value": "250000",
                "unit": "/uL",
                "reference_range": "150000 - 400000",
                "flag": ""
            },
            {
                "test_name": "Creatinine",
                "value": "1.8",
                "unit": "mg/dL",
                "reference_range": "0.7 - 1.3",
                "flag": "H"
            }
        ]
    }


@pytest.fixture
def mock_gemini_model(sample_gemini_extraction_response: Dict[str, Any]):
    """Mock Gemini generative model."""
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = json.dumps(sample_gemini_extraction_response)
    mock_model.generate_content.return_value = mock_response
    return mock_model


@pytest.fixture
def mock_gemini_configure(mock_gemini_model):
    """Patch genai.configure and GenerativeModel."""
    with patch('google.generativeai.configure') as mock_configure, \
         patch('google.generativeai.GenerativeModel', return_value=mock_gemini_model):
        yield mock_configure


# =============================================================================
# Test Mappings
# =============================================================================

@pytest.fixture
def sample_test_mappings() -> Dict[str, Any]:
    """Sample test name mappings for normalizer testing."""
    return {
        "version": "1.0",
        "mappings": {
            "hemoglobin": {
                "canonical_name": "Hemoglobin",
                "loinc_code": "718-7",
                "category": "Hematology",
                "unit": "g/dL",
                "aliases": ["hb", "hgb", "haemoglobin"]
            },
            "white_blood_cells": {
                "canonical_name": "White Blood Cell Count",
                "loinc_code": "6690-2",
                "category": "Hematology",
                "unit": "/uL",
                "aliases": ["wbc", "wbc count", "leukocytes"]
            },
            "red_blood_cells": {
                "canonical_name": "Red Blood Cell Count",
                "loinc_code": "789-8",
                "category": "Hematology",
                "unit": "million/uL",
                "aliases": ["rbc", "rbc count", "erythrocytes"]
            },
            "rdw": {
                "canonical_name": "Red Cell Distribution Width",
                "loinc_code": "788-0",
                "category": "Hematology",
                "unit": "%",
                "aliases": ["rdw", "rdw-cv"]
            },
            "creatinine": {
                "canonical_name": "Creatinine",
                "loinc_code": "2160-0",
                "category": "Renal Panel",
                "unit": "mg/dL",
                "aliases": ["creatinine", "creat"]
            }
        }
    }


# =============================================================================
# Raw Test Data
# =============================================================================

@pytest.fixture
def sample_raw_rows() -> list:
    """Sample raw extraction rows for normalizer testing."""
    return [
        {"test_name": "Hemoglobin", "value": "14.5", "unit": "g/dL", "reference_range": "13.0 - 17.0", "flag": ""},
        {"test_name": "WBC", "value": "8500", "unit": "/uL", "reference_range": "4000 - 11000", "flag": ""},
        {"test_name": "RBC", "value": "5.2", "unit": "million/uL", "reference_range": "4.5 - 5.5", "flag": ""},
        {"test_name": "Creatinine", "value": "1.8", "unit": "mg/dL", "reference_range": "0.7 - 1.3", "flag": "HIGH"},
    ]


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def test_database_url(tmp_path: Path) -> str:
    """Create temporary SQLite database URL."""
    db_path = tmp_path / "test.db"
    return f"sqlite:///{db_path}"


@pytest.fixture
def test_session(test_database_url: str):
    """Create test database session."""
    from sqlmodel import SQLModel, create_engine, Session
    
    engine = create_engine(test_database_url, echo=False)
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


# =============================================================================
# FastAPI Test Client
# =============================================================================

@pytest.fixture
def test_client(mock_gemini_configure, mock_redis, test_database_url: str):
    """Create FastAPI test client with mocked dependencies."""
    from fastapi.testclient import TestClient
    
    # Patch database and redis before importing app
    with patch.dict(os.environ, {"DATABASE_URL": test_database_url}):
        with patch('backend.core.database.get_redis_client', return_value=mock_redis):
            from backend.main import app
            client = TestClient(app)
            yield client


# =============================================================================
# Cache Manager Fixtures (Standalone implementations)
# =============================================================================

@pytest.fixture
def cache_config():
    """Cache configuration for testing (standalone)."""
    from dataclasses import dataclass
    
    @dataclass
    class CacheConfig:
        redis_enabled: bool = True
        disk_enabled: bool = False
        compression_enabled: bool = False
        redis_ttl_hours: int = 1
        disk_cache_dir: str = "storage/cache"
        max_disk_cache_size_mb: int = 5000
        hash_algorithm: str = "sha256"
        phash_similarity_threshold: int = 5
    
    return CacheConfig()


@pytest.fixture
def cache_stats():
    """Cache statistics for testing."""
    from dataclasses import dataclass
    
    @dataclass
    class CacheStats:
        redis_hits: int = 0
        redis_misses: int = 0
        disk_hits: int = 0
        disk_misses: int = 0
        cache_writes: int = 0
        
        @property
        def total_hits(self):
            return self.redis_hits + self.disk_hits
        
        @property
        def total_requests(self):
            return self.redis_hits + self.redis_misses + self.disk_hits + self.disk_misses
        
        @property
        def hit_rate(self):
            if self.total_requests == 0:
                return 0.0
            return self.total_hits / self.total_requests
    
    return CacheStats


@pytest.fixture
def cache_manager(mock_redis, cache_config):
    """Create cache manager with mocked Redis (standalone)."""
    import hashlib
    import json
    
    class CacheManager:
        def __init__(self, redis_client=None, config=None):
            self.redis = redis_client
            self.config = config
            self._stats = {
                "redis_hits": 0,
                "redis_misses": 0,
                "disk_hits": 0,
                "disk_misses": 0,
                "cache_writes": 0
            }
        
        def get_image_hash(self, image_path: str) -> str:
            with open(image_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        
        def get_cached_result(self, image_hash: str):
            if self.redis:
                result = self.redis.get(f"cache:{image_hash}")
                if result:
                    self._stats["redis_hits"] += 1
                    return json.loads(result)
                self._stats["redis_misses"] += 1
            return None
        
        def cache_result(self, image_hash: str, result, metadata=None):
            if self.redis and self.config.redis_enabled:
                self.redis.set(
                    f"cache:{image_hash}",
                    json.dumps(result),
                    ex=self.config.redis_ttl_hours * 3600
                )
                self._stats["cache_writes"] += 1
        
        def cache_partial_result(self, image_hash: str, stage: str, result):
            if self.redis:
                self.redis.set(f"partial:{image_hash}:{stage}", json.dumps(result))
        
        def get_partial_result(self, image_hash: str, stage: str):
            if self.redis:
                result = self.redis.get(f"partial:{image_hash}:{stage}")
                if result:
                    return json.loads(result)
            return None
        
        def invalidate(self, image_hash: str):
            if self.redis:
                self.redis.delete(f"cache:{image_hash}")
        
        def get_stats(self):
            return {
                **self._stats,
                "hit_rate": self._stats["redis_hits"] / max(1, self._stats["redis_hits"] + self._stats["redis_misses"])
            }
    
    return CacheManager(redis_client=mock_redis, config=cache_config)


# =============================================================================
# Rate Limiter Fixtures
# =============================================================================

@pytest.fixture
def rate_limit_config():
    """Rate limiter configuration for testing."""
    # Import directly from module to avoid __init__.py chain
    import sys
    from unittest.mock import MagicMock
    
    # Mock the settings before importing rate_limiter
    mock_settings = MagicMock()
    mock_settings.gemini.rate_limit = 15
    sys.modules['backend.core.config'] = MagicMock()
    sys.modules['backend.core.config'].get_settings = MagicMock(return_value=mock_settings)
    
    from dataclasses import dataclass
    
    @dataclass
    class RateLimitConfig:
        requests_per_minute: int = 10
        window_seconds: float = 60.0
        adaptive_backoff: bool = True
        backoff_factor: float = 0.8
        recovery_threshold: int = 5
        min_requests_per_minute: int = 2
    
    return RateLimitConfig()


@pytest.fixture
def rate_limiter(rate_limit_config):
    """Create rate limiter for testing."""
    import sys
    from unittest.mock import MagicMock
    import time
    from collections import deque
    from threading import Lock
    import asyncio
    
    # Create a standalone rate limiter that doesn't depend on the package
    class AdaptiveRateLimiter:
        def __init__(self, config):
            self.config = config
            self._effective_rpm = config.requests_per_minute
            self._requests = deque()
            self._consecutive_successes = 0
            self._lock = Lock()
            self._async_lock = None
        
        def _clean_old_requests(self):
            cutoff = time.time() - self.config.window_seconds
            while self._requests and self._requests[0] < cutoff:
                self._requests.popleft()
        
        def _wait_time(self):
            self._clean_old_requests()
            if len(self._requests) < self._effective_rpm:
                return 0.0
            oldest = self._requests[0]
            return max(0.0, (oldest + self.config.window_seconds) - time.time())
        
        def acquire(self):
            with self._lock:
                wait_time = self._wait_time()
                if wait_time > 0:
                    time.sleep(wait_time)
                    self._clean_old_requests()
                self._requests.append(time.time())
        
        async def acquire_async(self):
            if self._async_lock is None:
                self._async_lock = asyncio.Lock()
            async with self._async_lock:
                with self._lock:
                    wait_time = self._wait_time()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                with self._lock:
                    self._clean_old_requests()
                    self._requests.append(time.time())
        
        def report_rate_limit_error(self):
            with self._lock:
                self._effective_rpm = max(
                    int(self._effective_rpm * self.config.backoff_factor),
                    self.config.min_requests_per_minute
                )
                self._consecutive_successes = 0
        
        def report_success(self):
            with self._lock:
                self._consecutive_successes += 1
                if (self._consecutive_successes >= self.config.recovery_threshold and
                    self._effective_rpm < self.config.requests_per_minute):
                    self._effective_rpm = min(
                        int(self._effective_rpm / self.config.backoff_factor),
                        self.config.requests_per_minute
                    )
                    self._consecutive_successes = 0
        
        def get_stats(self):
            with self._lock:
                self._clean_old_requests()
                return {
                    "current_requests": len(self._requests),
                    "effective_rpm": self._effective_rpm,
                    "max_rpm": self.config.requests_per_minute,
                    "is_throttled": self._effective_rpm < self.config.requests_per_minute
                }
        
        def reset(self):
            with self._lock:
                self._requests.clear()
                self._effective_rpm = self.config.requests_per_minute
                self._consecutive_successes = 0
    
    return AdaptiveRateLimiter(config=rate_limit_config)


# =============================================================================
# Normalizer Fixtures
# =============================================================================

@pytest.fixture
def mock_normalizer(sample_test_mappings, tmp_path: Path):
    """Create StrictNormalizer with test mappings."""
    import yaml
    
    # Write test mappings to temp file
    yaml_path = tmp_path / "test_mappings.yaml"
    with open(yaml_path, 'w') as f:
        yaml.dump(sample_test_mappings, f)
    
    # Patch Gemini for LLM fallback
    with patch('google.generativeai.configure'), \
         patch('google.generativeai.GenerativeModel') as mock_model:
        mock_response = Mock()
        mock_response.text = "hemoglobin"  # Default LLM response
        mock_model.return_value.generate_content.return_value = mock_response
        
        from workers.extraction.strict_normalizer import StrictNormalizer
        normalizer = StrictNormalizer(yaml_path=str(yaml_path))
        yield normalizer


# =============================================================================
# Extractor Fixtures
# =============================================================================

@pytest.fixture
def mock_extractor(mock_gemini_model, mock_redis, sample_gemini_extraction_response):
    """Create SingleVisionExtractor with mocked dependencies."""
    with patch('google.generativeai.configure'), \
         patch('google.generativeai.GenerativeModel', return_value=mock_gemini_model), \
         patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
        
        mock_cache.return_value.get_cached_result.return_value = None
        mock_cache.return_value.cache_result.return_value = None
        
        from workers.extraction.single_vision_extractor import SingleVisionExtractor
        extractor = SingleVisionExtractor()
        yield extractor
