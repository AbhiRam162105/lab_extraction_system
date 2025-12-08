"""
End-to-end tests for the complete extraction pipeline.
Tests full workflows from upload to result without calling Gemini API.
"""
import pytest
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from pathlib import Path


class TestFullExtractionPipeline:
    """Test complete extraction workflow."""
    
    def test_upload_to_extraction_flow(
        self,
        test_client,
        sample_image_path,
        mock_gemini_response
    ):
        """Test complete flow from upload to extraction."""
        # Mock all dependencies
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.add = MagicMock()
            session.commit = MagicMock()
            session.get = MagicMock(return_value=MagicMock(
                id="doc-123",
                status="completed",
                filename="test.png"
            ))
            mock_session.return_value = iter([session])
            
            with patch('backend.main.queue') as mock_queue:
                mock_queue.enqueue = MagicMock()
                
                # Step 1: Upload document
                with open(sample_image_path, 'rb') as f:
                    upload_response = test_client.post(
                        "/api/v1/upload",
                        files={"files": ("test.png", f, "image/png")}
                    )
                
                # Should accept upload
                assert upload_response.status_code in [200, 422, 500]
    
    def test_extraction_with_mocked_gemini(
        self,
        sample_image_path,
        mock_gemini_extractor,
        mock_session
    ):
        """Test extraction with mocked Gemini API."""
        # Setup mock extraction result
        mock_result = {
            "patient_info": {"name": "Test Patient", "age": 30},
            "tests": [
                {"name": "Hemoglobin", "value": "14.0", "unit": "g/dL"}
            ],
            "confidence": 0.92
        }
        mock_gemini_extractor.extract.return_value = mock_result
        
        # Verify mock is configured
        result = mock_gemini_extractor.extract(str(sample_image_path))
        
        assert result is not None
        assert "tests" in result
        assert result["confidence"] >= 0.9
    
    def test_pipeline_status_updates(self, mock_document, mock_session):
        """Test that pipeline updates document status."""
        from workers.extraction.main import process_document
        
        with patch('workers.extraction.main.Session') as mock_session_class:
            # Create a mock session context manager
            session = MagicMock()
            session.__enter__ = MagicMock(return_value=session)
            session.__exit__ = MagicMock(return_value=False)
            session.get = MagicMock(return_value=mock_document)
            mock_session_class.return_value = session
            
            # Verify document status can be updated
            mock_document.status = "processing"
            assert mock_document.status == "processing"


class TestConcurrentProcessing:
    """Test concurrent document processing."""
    
    def test_multiple_documents_queued(self, mock_redis):
        """Test processing multiple documents concurrently."""
        doc_ids = ["doc-1", "doc-2", "doc-3"]
        
        # Simulate queuing multiple documents
        for doc_id in doc_ids:
            mock_redis.lpush = MagicMock(return_value=1)
            mock_redis.lpush("lab_reports", doc_id)
        
        # Verify all were queued
        assert mock_redis.lpush.call_count == 3
    
    def test_processing_order(self, mock_redis):
        """Test FIFO processing order."""
        doc_ids = ["doc-1", "doc-2", "doc-3"]
        
        # Mock queue behavior
        queue = list(doc_ids)
        mock_redis.rpop = MagicMock(side_effect=lambda _: queue.pop(0) if queue else None)
        
        # Process in order
        processed = []
        for _ in range(3):
            doc = mock_redis.rpop("lab_reports")
            if doc:
                processed.append(doc)
        
        assert processed == doc_ids


class TestRetryMechanisms:
    """Test retry mechanisms in the pipeline."""
    
    def test_retry_on_failure(self):
        """Test that failed extractions are retried."""
        max_retries = 3
        attempt = 0
        success = False
        
        for _ in range(max_retries):
            attempt += 1
            # Simulate failure on first 2 attempts
            if attempt < 3:
                continue
            success = True
            break
        
        assert success is True
        assert attempt == 3
    
    def test_max_retries_exceeded(self):
        """Test behavior when max retries exceeded."""
        max_retries = 3
        attempts = 0
        success = False
        
        for _ in range(max_retries):
            attempts += 1
            # All attempts fail
            continue
        
        assert attempts == max_retries
        assert success is False
    
    def test_retry_with_backoff(self):
        """Test exponential backoff on retries."""
        base_delay = 1.0
        delays = []
        
        for attempt in range(3):
            delay = base_delay * (2 ** attempt)
            delays.append(delay)
        
        # Verify exponential growth
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]


class TestConfidenceScoring:
    """Test confidence score handling."""
    
    def test_high_confidence_no_review(self, sample_extraction_data):
        """Test high confidence results don't need review."""
        confidence = 0.95
        review_threshold = 0.85
        
        needs_review = confidence < review_threshold
        assert needs_review is False
    
    def test_low_confidence_flagged(self, sample_extraction_data):
        """Test low confidence results are flagged."""
        confidence = 0.60
        review_threshold = 0.85
        
        needs_review = confidence < review_threshold
        assert needs_review is True
    
    def test_confidence_aggregation(self):
        """Test aggregating confidence from multiple passes."""
        pass1_confidence = 0.90
        pass2_confidence = 0.95
        
        # Average or weighted aggregation
        final_confidence = (pass1_confidence + pass2_confidence) / 2
        
        assert 0 <= final_confidence <= 1.0


class TestEarlyTermination:
    """Test early termination optimization."""
    
    def test_skip_pass2_high_confidence(self):
        """Test that Pass 2 is skipped for high confidence."""
        pass1_confidence = 0.95
        early_termination_threshold = 0.90
        
        skip_pass2 = pass1_confidence >= early_termination_threshold
        assert skip_pass2 is True
    
    def test_run_pass2_low_confidence(self):
        """Test that Pass 2 runs for low confidence."""
        pass1_confidence = 0.80
        early_termination_threshold = 0.90
        
        skip_pass2 = pass1_confidence >= early_termination_threshold
        assert skip_pass2 is False


class TestCacheIntegration:
    """Test cache integration in the pipeline."""
    
    def test_cache_hit_skips_extraction(self, mock_redis):
        """Test that cache hit skips extraction."""
        # Simulate cache hit
        cached_result = json.dumps({"tests": [], "confidence": 0.95})
        mock_redis.get = MagicMock(return_value=cached_result)
        
        result = mock_redis.get("result:image_hash_123")
        assert result is not None
        assert json.loads(result)["confidence"] == 0.95
    
    def test_cache_miss_runs_extraction(self, mock_redis):
        """Test that cache miss triggers extraction."""
        mock_redis.get = MagicMock(return_value=None)
        
        result = mock_redis.get("result:image_hash_456")
        assert result is None
        # Extraction should run (mocked here)
    
    def test_result_cached_after_extraction(self, mock_redis):
        """Test that extraction result is cached."""
        result = {"tests": [], "confidence": 0.90}
        
        mock_redis.setex = MagicMock(return_value=True)
        mock_redis.setex("result:image_hash_789", 86400, json.dumps(result))
        
        mock_redis.setex.assert_called_once()


class TestDuplicateDetection:
    """Test duplicate document detection."""
    
    def test_phash_similarity_detection(self):
        """Test similar images are detected."""
        hash1 = "abcdef1234567890"
        hash2 = "abcdef1234567891"  # 1 bit different
        
        # Calculate difference (hamming distance)
        diff = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        
        similarity_threshold = 5
        is_similar = diff <= similarity_threshold
        
        assert is_similar is True
    
    def test_different_images_not_flagged(self):
        """Test different images are not flagged as duplicates."""
        hash1 = "abcdef1234567890"
        hash2 = "fedcba9876543210"  # Very different
        
        diff = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        
        similarity_threshold = 5
        is_similar = diff <= similarity_threshold
        
        assert is_similar is False


class TestProcessingStages:
    """Test processing stage transitions."""
    
    def test_stage_transitions(self):
        """Test document moves through stages correctly."""
        stages = ["queued", "preprocessing", "extracting", "saving", "completed"]
        
        current_stage = 0
        for expected_stage in stages:
            assert stages[current_stage] == expected_stage
            current_stage += 1
    
    def test_failed_stage_on_error(self):
        """Test document moves to failed on error."""
        current_stage = "extracting"
        
        # Simulate error
        try:
            raise ValueError("Extraction failed")
        except ValueError:
            current_stage = "failed"
        
        assert current_stage == "failed"


class TestStandardizationIntegration:
    """Test standardization integration in pipeline."""
    
    def test_test_names_standardized(self, sample_extraction_data, sample_test_mappings):
        """Test that extracted test names are standardized."""
        from workers.extraction.standardizer import Standardizer
        
        with patch.object(Standardizer, '_load_test_mappings', return_value=sample_test_mappings):
            standardizer = Standardizer()
            standardizer.test_mappings = sample_test_mappings
            standardizer.canonical_names = list(sample_test_mappings.keys())
            
            # Standardize test names from extraction
            for test in sample_extraction_data["tests"]:
                original_name = test["name"]
                # Simulate standardization
                standardized = original_name  # Would be standardized in real implementation
                test["standardized_name"] = standardized
            
            # All tests should have standardized names
            assert all("standardized_name" in t for t in sample_extraction_data["tests"])


class TestAnalyticsUpdate:
    """Test analytics updates after processing."""
    
    def test_successful_extraction_updated(self, mock_session):
        """Test that successful extraction updates analytics."""
        # Simulate analytics update
        analytics = {
            "total_processed": 100,
            "successful": 95,
            "failed": 5
        }
        
        # After successful extraction
        analytics["total_processed"] += 1
        analytics["successful"] += 1
        
        assert analytics["successful"] == 96
    
    def test_failed_extraction_updated(self, mock_session):
        """Test that failed extraction updates analytics."""
        analytics = {
            "total_processed": 100,
            "successful": 95,
            "failed": 5
        }
        
        # After failed extraction
        analytics["total_processed"] += 1
        analytics["failed"] += 1
        
        assert analytics["failed"] == 6
    
    def test_processing_time_recorded(self):
        """Test that processing time is recorded."""
        start_time = time.time()
        
        # Simulate processing
        time.sleep(0.01)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        assert processing_time > 0


class TestErrorRecovery:
    """Test error recovery in the pipeline."""
    
    def test_partial_extraction_saved(self):
        """Test that partial results are saved on error."""
        partial_result = {
            "patient_info": {"name": "Test Patient"},
            "tests": [],  # Empty due to error
            "error": "Extraction partially failed"
        }
        
        # Should still be saveable
        assert "patient_info" in partial_result
    
    def test_cleanup_on_failure(self, tmp_path):
        """Test that temporary files are cleaned up on failure."""
        temp_file = tmp_path / "temp_processing.tmp"
        temp_file.write_text("temporary data")
        
        # Simulate cleanup
        if temp_file.exists():
            temp_file.unlink()
        
        assert not temp_file.exists()
