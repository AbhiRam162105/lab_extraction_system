"""
Shared pytest fixtures and configuration for all tests.
"""
import os
import sys
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator, Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import fakeredis for Redis mocking
try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_data_dir(project_root) -> Path:
    """Return the test data directory."""
    data_dir = project_root / "tests" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.get = MagicMock(return_value=None)
    session.exec = MagicMock()
    return session


@pytest.fixture
def mock_document():
    """Create a mock Document object."""
    doc = MagicMock()
    doc.id = "test-doc-123"
    doc.filename = "test_report.png"
    doc.status = "queued"
    doc.processing_stage = None
    doc.file_path = "storage/lab-reports/test_report.png"
    doc.content_type = "image/png"
    doc.upload_date = datetime.utcnow()
    return doc


@pytest.fixture
def mock_extraction_result():
    """Create a mock ExtractionResult object."""
    result = MagicMock()
    result.id = "result-123"
    result.document_id = "test-doc-123"
    result.raw_text = "Sample raw text"
    result.structured_data = {
        "patient_info": {"name": "John Doe", "age": 45},
        "tests": [
            {"name": "Hemoglobin", "value": "14.5", "unit": "g/dL", "reference_range": "13.5-17.5"}
        ]
    }
    result.confidence_score = 0.95
    result.processing_time = 2.5
    result.needs_review = False
    return result


# =============================================================================
# Redis Fixtures
# =============================================================================

@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    if FAKEREDIS_AVAILABLE:
        return fakeredis.FakeRedis(decode_responses=True)
    else:
        redis = MagicMock()
        redis.get = MagicMock(return_value=None)
        redis.set = MagicMock(return_value=True)
        redis.setex = MagicMock(return_value=True)
        redis.delete = MagicMock(return_value=1)
        redis.exists = MagicMock(return_value=False)
        redis.keys = MagicMock(return_value=[])
        redis.ping = MagicMock(return_value=True)
        return redis


@pytest.fixture
def cache_manager_with_mock_redis(mock_redis):
    """Create a CacheManager with mocked Redis."""
    with patch('workers.extraction.cache_manager.redis.from_url', return_value=mock_redis):
        from workers.extraction.cache_manager import CacheManager, CacheConfig
        config = CacheConfig(
            redis_url="redis://localhost:6379/0",
            disk_cache_path="/tmp/test_cache",
            result_ttl=3600
        )
        manager = CacheManager(config)
        manager.redis_client = mock_redis
        yield manager


# =============================================================================
# Image Fixtures
# =============================================================================

@pytest.fixture
def sample_image() -> Image.Image:
    """Create a sample test image."""
    # Create a simple white image with some text-like patterns
    img = Image.new('RGB', (800, 600), color='white')
    return img


@pytest.fixture
def sample_image_path(sample_image, tmp_path) -> Path:
    """Save sample image and return its path."""
    path = tmp_path / "test_image.png"
    sample_image.save(path)
    return path


@pytest.fixture
def sample_lab_report_image(tmp_path) -> Path:
    """Create a realistic lab report-like image."""
    # Create image with lab report dimensions
    img = Image.new('RGB', (1700, 2200), color='white')
    
    # Add some noise to simulate scanned document
    arr = np.array(img)
    noise = np.random.normal(0, 5, arr.shape).astype(np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    
    path = tmp_path / "lab_report.png"
    img.save(path, quality=95)
    return path


@pytest.fixture
def corrupted_image_path(tmp_path) -> Path:
    """Create a corrupted image file."""
    path = tmp_path / "corrupted.png"
    path.write_bytes(b"not a valid image file content")
    return path


# =============================================================================
# API Test Fixtures
# =============================================================================

@pytest.fixture
def test_client():
    """Create a FastAPI test client."""
    from fastapi.testclient import TestClient
    
    # Mock the database dependency
    with patch('backend.core.database.get_session') as mock_get_session:
        mock_session = MagicMock()
        mock_get_session.return_value = iter([mock_session])
        
        from backend.main import app
        client = TestClient(app)
        yield client


@pytest.fixture
def api_headers() -> Dict[str, str]:
    """Standard API headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_extraction_data() -> Dict[str, Any]:
    """Sample extraction result data."""
    return {
        "patient_info": {
            "name": "John Doe",
            "age": 45,
            "gender": "Male",
            "patient_id": "P12345"
        },
        "lab_info": {
            "lab_name": "Test Laboratory",
            "report_date": "2025-01-15",
            "sample_date": "2025-01-14"
        },
        "tests": [
            {
                "name": "Hemoglobin",
                "value": "14.5",
                "unit": "g/dL",
                "reference_range": "13.5-17.5",
                "status": "normal"
            },
            {
                "name": "White Blood Cells",
                "value": "8500",
                "unit": "/μL",
                "reference_range": "4000-11000",
                "status": "normal"
            },
            {
                "name": "Platelet Count",
                "value": "250000",
                "unit": "/μL",
                "reference_range": "150000-400000",
                "status": "normal"
            }
        ]
    }


@pytest.fixture
def sample_test_mappings() -> Dict[str, list]:
    """Sample test name mappings for standardization."""
    return {
        "Hemoglobin": ["Hb", "HGB", "Haemoglobin", "Hemoglobin (Hb)"],
        "White Blood Cells": ["WBC", "Leukocytes", "White Cell Count", "Total WBC"],
        "Red Blood Cells": ["RBC", "Erythrocytes", "Red Cell Count", "Total RBC"],
        "Platelet Count": ["PLT", "Platelets", "Thrombocytes", "Platelet"],
        "Blood Glucose Fasting": ["FBS", "Fasting Blood Sugar", "Fasting Glucose"],
        "Creatinine": ["Creat", "Serum Creatinine", "S. Creatinine"]
    }


@pytest.fixture
def canonical_test_names() -> list:
    """List of canonical test names."""
    return [
        "Hemoglobin",
        "White Blood Cells",
        "Red Blood Cells",
        "Platelet Count",
        "Hematocrit",
        "Mean Corpuscular Volume",
        "Mean Corpuscular Hemoglobin",
        "Blood Glucose Fasting",
        "Blood Glucose Random",
        "HbA1c",
        "Total Cholesterol",
        "LDL Cholesterol",
        "HDL Cholesterol",
        "Triglycerides",
        "Creatinine",
        "Blood Urea Nitrogen",
        "Uric Acid",
        "AST (SGOT)",
        "ALT (SGPT)",
        "Alkaline Phosphatase",
        "Total Bilirubin",
        "Direct Bilirubin",
        "Total Protein",
        "Albumin",
        "Globulin",
        "TSH",
        "T3",
        "T4",
        "Sodium",
        "Potassium",
        "Chloride",
        "Calcium",
        "Vitamin D",
        "Vitamin B12",
        "Iron",
        "Ferritin"
    ]


# =============================================================================
# Mock Fixtures for External Services
# =============================================================================

@pytest.fixture
def mock_gemini_response():
    """Mock Gemini API response - returns without calling API."""
    return {
        "patient_info": {"name": "Test Patient", "age": 30},
        "tests": [
            {"name": "Hemoglobin", "value": "14.0", "unit": "g/dL"}
        ],
        "confidence": 0.92
    }


@pytest.fixture
def mock_gemini_extractor(mock_gemini_response):
    """Mock the Gemini extractor to avoid API calls."""
    with patch('workers.extraction.gemini.LabReportExtractor') as mock_class:
        instance = MagicMock()
        instance.extract = MagicMock(return_value=mock_gemini_response)
        instance.preprocess_image = MagicMock(return_value=b"preprocessed_image_bytes")
        mock_class.return_value = instance
        yield instance


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_storage_dir(tmp_path) -> Path:
    """Create temporary storage directory structure."""
    storage = tmp_path / "storage"
    (storage / "lab-reports").mkdir(parents=True)
    (storage / "cache").mkdir(parents=True)
    return storage


# =============================================================================
# Performance Testing Fixtures
# =============================================================================

@pytest.fixture
def benchmark_config() -> Dict[str, Any]:
    """Configuration for performance benchmarks."""
    return {
        "warmup_rounds": 3,
        "rounds": 10,
        "min_time": 0.001,
        "max_time": 1.0,
        "timer": "perf_counter"
    }


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def cleanup_temp_files(tmp_path):
    """Automatically cleanup temporary files after each test."""
    yield
    # Cleanup is handled by pytest's tmp_path fixture


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("REDIS__URL", "redis://localhost:6379/15")
    os.environ.setdefault("DATABASE__URL", "sqlite:///./test.db")
    yield
    # Cleanup
    if os.path.exists("./test.db"):
        os.remove("./test.db")
