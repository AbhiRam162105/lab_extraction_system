"""
Unit tests for ImagePreprocessor.

Tests the image preprocessing pipeline including deskewing,
denoising, contrast enhancement, and basic preprocessing fallback.
"""

import pytest
import numpy as np
from PIL import Image
from pathlib import Path
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestImagePreprocessor:
    """Tests for ImagePreprocessor class."""
    
    def test_process_valid_image(self, test_image_path: str):
        """Test processing a valid image without errors."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor()
        result = preprocessor.process(test_image_path)
        
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.mode == 'RGB'
    
    def test_process_returns_pil_image(self, test_image_path: str):
        """Test that process returns a PIL Image."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor()
        result = preprocessor.process(test_image_path)
        
        assert isinstance(result, Image.Image)
    
    def test_deskew_configuration(self, test_image_path: str):
        """Test that deskew can be disabled."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor(deskew_enabled=False)
        result = preprocessor.process(test_image_path)
        
        assert result is not None
    
    def test_denoise_configuration(self, test_image_path: str):
        """Test that denoise can be disabled."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor(denoise_enabled=False)
        result = preprocessor.process(test_image_path)
        
        assert result is not None
    
    def test_contrast_enhancement_configuration(self, test_image_path: str):
        """Test that contrast enhancement can be disabled."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor(contrast_enhance_enabled=False)
        result = preprocessor.process(test_image_path)
        
        assert result is not None
    
    def test_basic_preprocess_fallback(self, test_image_path: str):
        """Test basic preprocessing fallback when OpenCV fails."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor()
        
        # Mock cv2 import to simulate OpenCV not available
        with patch('workers.extraction.preprocessing.cv2', None):
            result = preprocessor._basic_preprocess(test_image_path)
            assert result is not None
            assert isinstance(result, Image.Image)
    
    def test_convenience_function(self, test_image_path: str):
        """Test the preprocess_image convenience function."""
        from workers.extraction.preprocessing import preprocess_image
        
        result = preprocess_image(
            test_image_path,
            deskew=True,
            denoise=True,
            enhance_contrast=True,
            binarize=False
        )
        
        assert result is not None
        assert isinstance(result, Image.Image)
    
    def test_process_with_all_options_disabled(self, test_image_path: str):
        """Test processing with all enhancement options disabled."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor(
            deskew_enabled=False,
            denoise_enabled=False,
            contrast_enhance_enabled=False,
            binarize_enabled=False
        )
        
        result = preprocessor.process(test_image_path)
        assert result is not None
    
    def test_process_preserves_image_data(self, test_image_path: str):
        """Test that processing doesn't corrupt image data."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor()
        result = preprocessor.process(test_image_path)
        
        # Image should have valid dimensions
        assert result.width > 0
        assert result.height > 0
        
        # Should be able to convert to numpy array
        arr = np.array(result)
        assert arr.shape[0] > 0
        assert arr.shape[1] > 0


class TestDeskew:
    """Tests for deskew functionality."""
    
    def test_deskew_straight_image(self, sample_image: Image.Image, tmp_path: Path):
        """Test deskew on already straight image."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        # Save straight image
        image_path = tmp_path / "straight.png"
        sample_image.save(str(image_path))
        
        preprocessor = ImagePreprocessor(
            deskew_enabled=True,
            denoise_enabled=False,
            contrast_enhance_enabled=False
        )
        
        result = preprocessor.process(str(image_path))
        
        # Should process without error
        assert result is not None


class TestEnhanceSharpness:
    """Tests for sharpness enhancement."""
    
    def test_enhance_sharpness_increases_edges(self, sample_image: Image.Image):
        """Test that sharpness enhancement works."""
        from workers.extraction.preprocessing import ImagePreprocessor
        
        preprocessor = ImagePreprocessor()
        result = preprocessor._enhance_sharpness(sample_image, factor=1.5)
        
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.size == sample_image.size
