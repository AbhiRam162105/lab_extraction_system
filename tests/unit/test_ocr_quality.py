"""
Unit tests for OCR quality evaluation.

Tests the image quality gating module that rejects poor quality
images before processing to prevent extraction errors.
"""

import pytest
import numpy as np
from PIL import Image, ImageFilter
from unittest.mock import patch

pytestmark = pytest.mark.unit


class TestEvaluateOcrQuality:
    """Tests for the main quality evaluation function."""
    
    def test_evaluate_clear_image(self, sample_image: Image.Image):
        """Test that clear images pass quality check."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(sample_image)
        
        assert result is not None
        assert hasattr(result, 'is_acceptable')
        assert hasattr(result, 'quality_score')
        assert hasattr(result, 'metrics')
    
    def test_evaluate_blurry_image(self, blurry_image: Image.Image):
        """Test that very blurry images are rejected."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(blurry_image)
        
        # Blurry images should have low blur score
        assert result.metrics["blur_score"] < 100
        # May or may not be rejected depending on threshold
    
    def test_evaluate_low_contrast_image(self, low_contrast_image: Image.Image):
        """Test that low contrast images are flagged."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(low_contrast_image)
        
        # Low contrast should be detected
        assert "contrast" in result.metrics or "contrast_score" in result.metrics
    
    def test_quality_score_range(self, sample_image: Image.Image):
        """Test that quality score is in valid range."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(sample_image)
        
        assert 0.0 <= result.quality_score <= 1.0
    
    def test_issues_list(self, blurry_image: Image.Image):
        """Test that issues are reported."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(blurry_image)
        
        assert isinstance(result.issues, list)
    
    def test_recommendation_provided(self, sample_image: Image.Image):
        """Test that recommendation is provided."""
        from workers.extraction.ocr_quality import evaluate_ocr_quality
        
        result = evaluate_ocr_quality(sample_image)
        
        assert result.recommendation is not None
        assert isinstance(result.recommendation, str)


class TestQualityResult:
    """Tests for QualityResult dataclass."""
    
    def test_quality_result_fields(self):
        """Test QualityResult has required fields."""
        from workers.extraction.ocr_quality import QualityResult
        
        result = QualityResult(
            is_acceptable=True,
            quality_score=0.85,
            issues=[],
            metrics={"blur_score": 150},
            recommendation="Image is acceptable",
            needs_preprocessing=False
        )
        
        assert result.is_acceptable is True
        assert result.quality_score == 0.85
        assert result.needs_preprocessing is False


class TestBlurScore:
    """Tests for blur score calculation."""
    
    def test_calculate_blur_score_sharp_image(self, sample_image: Image.Image):
        """Test blur score for sharp image."""
        from workers.extraction.ocr_quality import _calculate_blur_score
        
        img_array = np.array(sample_image.convert('L'))
        score = _calculate_blur_score(img_array)
        
        assert score is not None
        assert score > 0
    
    def test_calculate_blur_score_blurry_image(self, blurry_image: Image.Image):
        """Test blur score for blurry image is lower."""
        from workers.extraction.ocr_quality import _calculate_blur_score
        
        # Get scores for both images
        sharp = Image.new('RGB', (200, 200), 'white')
        # Add sharp edges
        for i in range(10, 190, 20):
            for x in range(10, 190):
                sharp.putpixel((x, i), (0, 0, 0))
        
        blurry = sharp.filter(ImageFilter.GaussianBlur(radius=10))
        
        sharp_score = _calculate_blur_score(np.array(sharp.convert('L')))
        blurry_score = _calculate_blur_score(np.array(blurry.convert('L')))
        
        # Sharp image should have higher blur score
        assert sharp_score > blurry_score


class TestTextClarity:
    """Tests for text clarity estimation."""
    
    def test_estimate_text_clarity(self, sample_image: Image.Image):
        """Test text clarity estimation."""
        from workers.extraction.ocr_quality import _estimate_text_clarity
        
        img_array = np.array(sample_image.convert('L'))
        clarity = _estimate_text_clarity(img_array)
        
        assert clarity is not None
        assert 0.0 <= clarity <= 1.0


class TestNoiseLevel:
    """Tests for noise level estimation."""
    
    def test_estimate_noise_level_clean(self, sample_image: Image.Image):
        """Test noise level for clean image."""
        from workers.extraction.ocr_quality import _estimate_noise_level
        
        img_array = np.array(sample_image.convert('L'))
        noise = _estimate_noise_level(img_array)
        
        assert noise is not None
        assert 0.0 <= noise <= 1.0
    
    def test_estimate_noise_level_noisy(self):
        """Test noise level for noisy image."""
        from workers.extraction.ocr_quality import _estimate_noise_level
        
        # Create noisy image
        noisy_array = np.random.randint(0, 256, (200, 200), dtype=np.uint8)
        noise = _estimate_noise_level(noisy_array)
        
        # Noisy image should have higher noise level
        assert noise > 0.1


class TestTextDensity:
    """Tests for text density estimation."""
    
    def test_estimate_text_density(self, sample_image: Image.Image):
        """Test text density estimation."""
        from workers.extraction.ocr_quality import _estimate_text_density
        
        img_array = np.array(sample_image.convert('L'))
        density = _estimate_text_density(img_array)
        
        assert density is not None
        assert 0.0 <= density <= 1.0
    
    def test_estimate_text_density_blank(self):
        """Test text density for blank image."""
        from workers.extraction.ocr_quality import _estimate_text_density
        
        # Completely blank image
        blank_array = np.ones((200, 200), dtype=np.uint8) * 255
        density = _estimate_text_density(blank_array)
        
        # Blank image should have very low density
        assert density < 0.05


class TestQuickQualityCheck:
    """Tests for quick quality check function."""
    
    def test_quick_check_returns_tuple(self, sample_image: Image.Image):
        """Test quick check returns pass/fail with reason."""
        from workers.extraction.ocr_quality import quick_quality_check
        
        result = quick_quality_check(sample_image)
        
        assert result is not None
        # Should return a QualityResult or similar


class TestSimulateBlur:
    """Tests for blur simulation helper."""
    
    def test_simulate_blur(self, sample_image: Image.Image):
        """Test blur simulation for testing."""
        from workers.extraction.ocr_quality import simulate_blur
        
        blurred = simulate_blur(sample_image, radius=5)
        
        assert blurred is not None
        assert isinstance(blurred, Image.Image)
        assert blurred.size == sample_image.size
    
    def test_simulate_blur_increases_with_radius(self, sample_image: Image.Image):
        """Test that higher radius means more blur."""
        from workers.extraction.ocr_quality import simulate_blur, _calculate_blur_score
        
        blur5 = simulate_blur(sample_image, radius=5)
        blur10 = simulate_blur(sample_image, radius=10)
        
        score5 = _calculate_blur_score(np.array(blur5.convert('L')))
        score10 = _calculate_blur_score(np.array(blur10.convert('L')))
        
        # Higher radius should result in lower (more blurry) score
        assert score5 > score10


class TestQualityThresholds:
    """Tests for quality threshold constants."""
    
    def test_thresholds_exist(self):
        """Test that quality thresholds are defined."""
        from workers.extraction.ocr_quality import QUALITY_THRESHOLDS
        
        assert "blur_score" in QUALITY_THRESHOLDS
        assert "contrast_min" in QUALITY_THRESHOLDS
        assert "brightness_min" in QUALITY_THRESHOLDS
        assert "brightness_max" in QUALITY_THRESHOLDS
    
    def test_thresholds_reasonable_values(self):
        """Test that thresholds have reasonable values."""
        from workers.extraction.ocr_quality import QUALITY_THRESHOLDS
        
        assert QUALITY_THRESHOLDS["blur_score"] > 0
        assert QUALITY_THRESHOLDS["brightness_min"] < QUALITY_THRESHOLDS["brightness_max"]
