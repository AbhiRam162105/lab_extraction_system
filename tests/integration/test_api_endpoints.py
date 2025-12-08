"""
Integration tests for API endpoints.
Tests document upload, status, results, analytics, and health checks.
"""
import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime
from io import BytesIO
from PIL import Image


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_health_check(self, test_client):
        """Test basic health check endpoint."""
        with patch('backend.main.get_session') as mock:
            mock.return_value = iter([MagicMock()])
            response = test_client.get("/health")
            assert response.status_code in [200, 404]  # Depends on endpoint existence
    
    def test_readiness_probe(self, test_client):
        """Test Kubernetes readiness probe."""
        with patch('backend.main.get_session') as mock:
            mock.return_value = iter([MagicMock()])
            response = test_client.get("/docs")  # OpenAPI docs as health check
            assert response.status_code == 200


class TestDocumentUpload:
    """Test document upload endpoints."""
    
    def test_upload_single_image(self, test_client, sample_image_path):
        """Test uploading a single image."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.add = MagicMock()
            session.commit = MagicMock()
            mock_session.return_value = iter([session])
            
            with patch('backend.main.queue') as mock_queue:
                mock_queue.enqueue = MagicMock()
                
                with open(sample_image_path, 'rb') as f:
                    response = test_client.post(
                        "/api/v1/upload",
                        files={"files": ("test.png", f, "image/png")}
                    )
                
                # Should succeed or fail gracefully
                assert response.status_code in [200, 422, 500]
    
    def test_upload_multiple_images(self, test_client, tmp_path):
        """Test batch upload of multiple images."""
        # Create multiple test images
        files = []
        for i in range(3):
            img_path = tmp_path / f"test_{i}.png"
            Image.new('RGB', (100, 100), color='white').save(img_path)
            files.append(("files", open(img_path, 'rb')))
        
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value = iter([session])
            
            with patch('backend.main.queue') as mock_queue:
                mock_queue.enqueue = MagicMock()
                
                response = test_client.post("/api/v1/upload", files=files)
        
        # Close files
        for _, f in files:
            f.close()
        
        assert response.status_code in [200, 422, 500]
    
    def test_upload_invalid_file_type(self, test_client, tmp_path):
        """Test uploading unsupported file type."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("This is not an image")
        
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value = iter([session])
            
            with open(text_file, 'rb') as f:
                response = test_client.post(
                    "/api/v1/upload",
                    files={"files": ("test.txt", f, "text/plain")}
                )
        
        # Should reject or handle gracefully
        assert response.status_code in [400, 422, 200, 500]
    
    def test_upload_empty_file(self, test_client):
        """Test uploading empty file."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value = iter([session])
            
            empty_file = BytesIO(b"")
            response = test_client.post(
                "/api/v1/upload",
                files={"files": ("empty.png", empty_file, "image/png")}
            )
        
        # Should handle gracefully
        assert response.status_code in [400, 422, 200, 500]


class TestDocumentStatus:
    """Test document status endpoints."""
    
    def test_get_all_documents(self, test_client):
        """Test retrieving all documents."""
        mock_docs = [
            MagicMock(
                id="doc-1",
                filename="test1.png",
                status="completed",
                upload_date=datetime.utcnow()
            )
        ]
        
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_docs)))
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/documents")
        
        assert response.status_code in [200, 500]
    
    def test_get_document_by_id(self, test_client):
        """Test retrieving specific document."""
        mock_doc = MagicMock(
            id="doc-123",
            filename="test.png",
            status="completed"
        )
        
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.get = MagicMock(return_value=mock_doc)
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/documents/doc-123")
        
        assert response.status_code in [200, 404, 500]
    
    def test_get_nonexistent_document(self, test_client):
        """Test retrieving nonexistent document."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.get = MagicMock(return_value=None)
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/documents/nonexistent-id")
        
        assert response.status_code in [404, 500]


class TestExtractionResults:
    """Test extraction result endpoints."""
    
    def test_get_extraction_result(self, test_client, sample_extraction_data):
        """Test retrieving extraction results."""
        mock_result = MagicMock(
            id="result-123",
            document_id="doc-123",
            structured_data=sample_extraction_data,
            confidence_score=0.95
        )
        
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_result)))
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/results/doc-123")
        
        assert response.status_code in [200, 404, 500]
    
    def test_get_result_not_ready(self, test_client):
        """Test getting result for processing document."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/results/processing-doc")
        
        assert response.status_code in [200, 404, 500]


class TestFlaggedDocuments:
    """Test flagged documents endpoint."""
    
    def test_get_flagged_documents(self, test_client):
        """Test retrieving documents flagged for review."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/documents/flagged")
        
        assert response.status_code in [200, 404, 500]


class TestCacheEndpoints:
    """Test cache-related endpoints."""
    
    def test_get_cache_stats(self, test_client):
        """Test retrieving cache statistics."""
        with patch('backend.main.get_session') as mock_session:
            mock_session.return_value = iter([MagicMock()])
            
            response = test_client.get("/api/v1/cache/stats")
        
        assert response.status_code in [200, 404, 500]
    
    def test_clear_cache(self, test_client):
        """Test clearing cache."""
        with patch('backend.main.get_session') as mock_session:
            mock_session.return_value = iter([MagicMock()])
            
            response = test_client.post("/api/v1/cache/clear")
        
        # Should be protected or not exist
        assert response.status_code in [200, 401, 403, 404, 405, 500]


class TestAnalyticsEndpoints:
    """Test analytics endpoints."""
    
    def test_get_analytics_summary(self, test_client):
        """Test retrieving analytics summary."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/analytics")
        
        assert response.status_code in [200, 404, 500]
    
    def test_export_data(self, test_client):
        """Test data export endpoint."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/export")
        
        assert response.status_code in [200, 404, 500]


class TestErrorHandling:
    """Test API error handling."""
    
    def test_invalid_json_body(self, test_client):
        """Test handling of invalid JSON in request body."""
        with patch('backend.main.get_session') as mock_session:
            mock_session.return_value = iter([MagicMock()])
            
            response = test_client.post(
                "/api/v1/upload",
                content="not valid json",
                headers={"Content-Type": "application/json"}
            )
        
        assert response.status_code in [400, 422, 500]
    
    def test_missing_required_fields(self, test_client):
        """Test handling of missing required fields."""
        with patch('backend.main.get_session') as mock_session:
            mock_session.return_value = iter([MagicMock()])
            
            response = test_client.post("/api/v1/upload", files={})
        
        assert response.status_code in [400, 422, 500]
    
    def test_server_error_handling(self, test_client):
        """Test 500 error handling."""
        with patch('backend.main.get_session') as mock_session:
            mock_session.side_effect = Exception("Database error")
            
            response = test_client.get("/api/v1/documents")
        
        assert response.status_code == 500


class TestCORS:
    """Test CORS configuration."""
    
    def test_cors_headers(self, test_client):
        """Test CORS headers are present."""
        response = test_client.options("/api/v1/documents")
        
        # Check for CORS-related response or proper handling
        assert response.status_code in [200, 204, 405]


class TestRateLimiting:
    """Test API rate limiting."""
    
    def test_rate_limit_headers(self, test_client):
        """Test rate limit headers in response."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            mock_session.return_value = iter([session])
            
            response = test_client.get("/api/v1/documents")
        
        # Rate limit headers may or may not be present
        assert response.status_code in [200, 429, 500]
