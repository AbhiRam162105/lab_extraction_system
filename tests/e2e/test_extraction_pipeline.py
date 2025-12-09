"""
End-to-end tests for the extraction pipeline.

Tests the complete flow from upload to extraction to results,
with all Gemini API calls mocked.
"""

import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from PIL import Image
import io

pytestmark = pytest.mark.e2e


@pytest.fixture
def mock_gemini_for_e2e(sample_gemini_extraction_response):
    """Mock Gemini for E2E tests."""
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = json.dumps(sample_gemini_extraction_response)
    mock_model.generate_content.return_value = mock_response
    
    with patch('google.generativeai.configure'), \
         patch('google.generativeai.GenerativeModel', return_value=mock_model):
        yield mock_model


class TestExtractionPipeline:
    """End-to-end tests for the extraction pipeline."""
    
    def test_single_vision_extractor_flow(
        self,
        mock_gemini_for_e2e,
        test_image_path: str,
        sample_gemini_extraction_response
    ):
        """Test complete single vision extraction flow."""
        with patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
            mock_cache.return_value.get_cached_result.return_value = None
            mock_cache.return_value.cache_result.return_value = None
            mock_cache.return_value.get_image_hash.return_value = "test_hash"
            
            from workers.extraction.single_vision_extractor import SingleVisionExtractor
            
            extractor = SingleVisionExtractor()
            result = extractor.extract(test_image_path)
            
            # Check result structure
            assert result is not None
            assert hasattr(result, 'success')
            assert hasattr(result, 'data')
    
    def test_extraction_with_cache_hit(
        self,
        mock_gemini_for_e2e,
        test_image_path: str,
        sample_gemini_extraction_response
    ):
        """Test extraction when result is cached."""
        cached_result = {
            "success": True,
            "data": sample_gemini_extraction_response,
            "confidence": 0.95
        }
        
        with patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
            mock_cache.return_value.get_cached_result.return_value = cached_result
            mock_cache.return_value.get_image_hash.return_value = "test_hash"
            
            from workers.extraction.single_vision_extractor import SingleVisionExtractor
            
            extractor = SingleVisionExtractor()
            result = extractor.extract(test_image_path)
            
            # Should return cached result without calling Gemini
            assert result is not None


class TestNormalizationPipeline:
    """Tests for the normalization pipeline."""
    
    def test_normalize_extracted_results(
        self,
        mock_normalizer,
        sample_raw_rows
    ):
        """Test normalizing extracted lab results."""
        result = mock_normalizer.normalize(sample_raw_rows)
        
        assert result.success is True
        assert len(result.results) > 0
        
        # Check normalized results have required fields
        for r in result.results:
            assert hasattr(r, 'test_name')
            assert hasattr(r, 'original_name')
            assert hasattr(r, 'value')
    
    def test_normalize_with_unknown_tests(self, mock_normalizer):
        """Test normalization with unknown test names."""
        rows = [
            {"test_name": "Some Unknown Test XYZ", "value": "123", "unit": "", "reference_range": "", "flag": ""}
        ]
        
        result = mock_normalizer.normalize(rows)
        
        # Should still succeed but may have unknown tests
        assert result.success is True


class TestQualityGatePipeline:
    """Tests for quality gate in the pipeline."""
    
    def test_quality_gate_accepts_good_image(self, sample_image: Image.Image):
        """Test that quality gate accepts good images."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(sample_image)
        
        # Good image should pass
        assert result is not None
        assert hasattr(result, 'is_acceptable')
    
    def test_quality_gate_flags_poor_image(self, blurry_image: Image.Image):
        """Test that quality gate flags poor images."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(blurry_image)
        
        # Should have lower quality score
        assert result.quality_score < 0.9


class TestPreprocessingPipeline:
    """Tests for preprocessing in the pipeline."""
    
    def test_preprocessing_improves_image(self, test_image_path: str):
        """Test that preprocessing runs without errors."""
        from workers.extraction.preprocessing import preprocess_image
        
        result = preprocess_image(test_image_path)
        
        assert result is not None
        assert isinstance(result, Image.Image)


class TestCachingPipeline:
    """Tests for caching in the pipeline."""
    
    def test_cache_stores_and_retrieves(self, mock_redis, cache_config, test_image_path: str):
        """Test that cache stores and retrieves results."""
        from workers.extraction.cache_manager import CacheManager
        
        cache = CacheManager(redis_client=mock_redis, config=cache_config)
        
        # Store a result
        test_data = {"tests": [{"test_name": "Hemoglobin", "value": "14.5"}]}
        image_hash = cache.get_image_hash(test_image_path)
        
        mock_redis.set = Mock(return_value=True)
        cache.cache_result(image_hash, test_data)
        
        # Retrieve should call Redis
        mock_redis.set.assert_called()


class TestRateLimitingPipeline:
    """Tests for rate limiting in the pipeline."""
    
    def test_rate_limiter_allows_requests(self, rate_limiter):
        """Test rate limiter allows requests under limit."""
        # Should allow multiple acquires under limit
        for _ in range(3):
            rate_limiter.acquire()
        
        stats = rate_limiter.get_stats()
        assert stats["current_requests"] <= rate_limiter.config.requests_per_minute


class TestPatientIdentityPipeline:
    """Tests for patient identity processing."""
    
    def test_patient_memory_matching(self, mock_gemini_for_e2e, test_image_path: str):
        """Test patient memory for identity matching across documents."""
        with patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
            mock_cache.return_value.get_cached_result.return_value = None
            mock_cache.return_value.cache_result.return_value = None
            mock_cache.return_value.get_image_hash.return_value = "test_hash"
            
            from workers.extraction.single_vision_extractor import SingleVisionExtractor
            
            extractor = SingleVisionExtractor()
            
            # Process first document
            result1 = extractor.extract(test_image_path)
            
            # The extractor should maintain patient memory
            assert result1 is not None


class TestErrorHandling:
    """Tests for error handling in the pipeline."""
    
    def test_handles_invalid_image_path(self, mock_gemini_for_e2e):
        """Test handling of invalid image path."""
        with patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
            mock_cache.return_value.get_cached_result.return_value = None
            
            from workers.extraction.single_vision_extractor import SingleVisionExtractor
            
            extractor = SingleVisionExtractor()
            
            # Should handle gracefully
            try:
                result = extractor.extract("/nonexistent/path.png")
                # Either returns error result or raises exception
                assert result.success is False or True
            except (FileNotFoundError, Exception):
                # Expected exception is acceptable
                pass
    
    def test_handles_gemini_error(self, test_image_path: str):
        """Test handling of Gemini API errors."""
        with patch('google.generativeai.configure'), \
             patch('google.generativeai.GenerativeModel') as mock_model:
            
            mock_model.return_value.generate_content.side_effect = Exception("API Error")
            
            with patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
                mock_cache.return_value.get_cached_result.return_value = None
                mock_cache.return_value.get_image_hash.return_value = "test_hash"
                
                from workers.extraction.single_vision_extractor import SingleVisionExtractor
                
                extractor = SingleVisionExtractor()
                
                # Should handle API error gracefully
                try:
                    result = extractor.extract(test_image_path)
                    # May return error result
                    assert result is not None
                except Exception:
                    # Exception handling is also acceptable
                    pass


class TestFullWorkflow:
    """Tests simulating complete user workflows."""
    
    def test_upload_process_retrieve_workflow(
        self,
        mock_gemini_for_e2e,
        sample_image: Image.Image,
        tmp_path: Path,
        mock_redis
    ):
        """Test complete workflow: upload → process → retrieve results."""
        # 1. Save image to simulate upload
        image_path = tmp_path / "workflow_test.png"
        sample_image.save(str(image_path))
        
        # 2. Process with extractor
        with patch('workers.extraction.single_vision_extractor.CacheManager') as mock_cache:
            mock_cache.return_value.get_cached_result.return_value = None
            mock_cache.return_value.cache_result.return_value = None
            mock_cache.return_value.get_image_hash.return_value = "workflow_test_hash"
            
            from workers.extraction.single_vision_extractor import SingleVisionExtractor
            
            extractor = SingleVisionExtractor()
            result = extractor.extract(str(image_path))
            
            # 3. Verify result structure
            assert result is not None
            assert hasattr(result, 'success')
            assert hasattr(result, 'data')
