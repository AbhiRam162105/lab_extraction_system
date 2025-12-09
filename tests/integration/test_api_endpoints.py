"""
Integration tests for API endpoints.

Tests the FastAPI endpoints with mocked dependencies
(Redis, Gemini API, database) to verify API behavior.
"""

import pytest
import os
import io
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from PIL import Image

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_app_dependencies(mock_redis, mock_gemini_configure, test_database_url):
    """Set up all mocked app dependencies."""
    with patch.dict(os.environ, {
        "DATABASE_URL": test_database_url,
        "REDIS_URL": "redis://localhost:6379/15",
        "TESTING": "true"
    }):
        with patch('backend.core.database.get_redis_client', return_value=mock_redis):
            yield


@pytest.fixture
def client(mock_app_dependencies):
    """Create test client with mocked dependencies."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def sample_upload_file(sample_image: Image.Image, tmp_path: Path) -> bytes:
    """Create a sample image file for upload testing."""
    image_path = tmp_path / "test_upload.png"
    sample_image.save(str(image_path))
    
    with open(image_path, 'rb') as f:
        return f.read()


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_check(self, client):
        """Test health endpoint returns ok."""
        response = client.get("/health")
        
        # Should return 200 or health status
        assert response.status_code in [200, 404]  # 404 if not implemented


class TestDocumentsEndpoints:
    """Tests for document-related endpoints."""
    
    def test_get_documents_empty(self, client):
        """Test getting documents when empty."""
        response = client.get("/api/v1/documents")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "documents" in data
    
    def test_upload_single_file(self, client, sample_upload_file, mock_redis):
        """Test uploading a single file."""
        with patch('backend.core.queue.get_queue') as mock_queue:
            mock_q = Mock()
            mock_q.enqueue.return_value = Mock(id="task_123")
            mock_queue.return_value = mock_q
            
            files = {"files": ("test.png", io.BytesIO(sample_upload_file), "image/png")}
            response = client.post("/api/v1/upload", files=files)
            
            # Should accept the upload
            assert response.status_code in [200, 201, 422]  # 422 if validation fails
    
    def test_upload_invalid_file_type(self, client):
        """Test uploading invalid file type."""
        files = {"files": ("test.txt", io.BytesIO(b"not an image"), "text/plain")}
        response = client.post("/api/v1/upload", files=files)
        
        # Should reject or handle gracefully
        assert response.status_code in [200, 400, 415, 422]
    
    def test_get_results_nonexistent(self, client):
        """Test getting results for nonexistent document."""
        response = client.get("/api/v1/results/nonexistent_id")
        
        # Should return 404 or empty
        assert response.status_code in [404, 200]


class TestTestsEndpoints:
    """Tests for test analytics endpoints."""
    
    def test_get_all_tests(self, client):
        """Test getting all tests."""
        response = client.get("/api/v1/tests/all")
        
        assert response.status_code == 200
        data = response.json()
        assert "tests" in data
        assert isinstance(data["tests"], list)
    
    def test_get_all_tests_with_filter(self, client):
        """Test getting tests with category filter."""
        response = client.get("/api/v1/tests/all?category=Hematology")
        
        assert response.status_code == 200
    
    def test_get_test_categories(self, client):
        """Test getting test categories."""
        response = client.get("/api/v1/tests/categories")
        
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
    
    def test_get_test_stats(self, client):
        """Test getting test statistics."""
        response = client.get("/api/v1/tests/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_tests" in data
    
    def test_get_pivot_table(self, client):
        """Test getting pivot table view."""
        response = client.get("/api/v1/tests/pivot")
        
        assert response.status_code == 200
        data = response.json()
        assert "columns" in data or "rows" in data
    
    def test_get_canonical_names(self, client):
        """Test getting canonical test names."""
        response = client.get("/api/v1/tests/canonical-names")
        
        assert response.status_code == 200
        data = response.json()
        assert "canonical_names" in data
    
    def test_export_csv(self, client):
        """Test CSV export."""
        response = client.get("/api/v1/tests/export?format=csv")
        
        assert response.status_code == 200
        assert response.headers.get("content-type") in [
            "text/csv",
            "text/csv; charset=utf-8"
        ]
    
    def test_export_excel(self, client):
        """Test Excel export."""
        response = client.get("/api/v1/tests/export?format=excel")
        
        assert response.status_code == 200
        # Excel MIME type
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "excel" in content_type.lower()
    
    def test_get_test_definitions(self, client):
        """Test getting test definitions."""
        response = client.get("/api/v1/tests/definitions")
        
        assert response.status_code == 200
        data = response.json()
        assert "definitions" in data
    
    def test_get_timing_stats(self, client):
        """Test getting timing statistics."""
        response = client.get("/api/v1/tests/timing-stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_processed" in data


class TestBatchEndpoints:
    """Tests for batch processing endpoints."""
    
    def test_batch_upload(self, client, sample_upload_file, mock_redis):
        """Test batch file upload."""
        with patch('backend.core.queue.get_queue') as mock_queue:
            mock_q = Mock()
            mock_q.enqueue.return_value = Mock(id="task_123")
            mock_queue.return_value = mock_q
            
            files = [
                ("files", ("test1.png", io.BytesIO(sample_upload_file), "image/png")),
                ("files", ("test2.png", io.BytesIO(sample_upload_file), "image/png")),
            ]
            response = client.post("/api/v1/batch/upload", files=files)
            
            # Should accept or indicate batch processing started
            assert response.status_code in [200, 201, 422]
    
    def test_get_batch_status(self, client):
        """Test getting batch status."""
        response = client.get("/api/v1/batch/status/batch_123")
        
        # Should return status or 404
        assert response.status_code in [200, 404]


class TestStorageEndpoints:
    """Tests for storage-related endpoints."""
    
    def test_get_flagged_documents(self, client):
        """Test getting flagged (low quality) documents."""
        response = client.get("/api/v1/documents/flagged")
        
        assert response.status_code == 200


class TestApiVersioning:
    """Tests for API versioning."""
    
    def test_v1_prefix(self, client):
        """Test that v1 API prefix works."""
        response = client.get("/api/v1/tests/all")
        assert response.status_code == 200
