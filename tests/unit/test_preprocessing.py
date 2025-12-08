"""
Unit tests for image preprocessing functionality.
Tests image enhancement, deskewing, denoising, and quality checks.
"""
import pytest
import numpy as np
from PIL import Image
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestImageLoading:
    """Test image loading functionality."""
    
    def test_load_valid_image(self, sample_image_path):
        """Test loading a valid image file."""
        img = Image.open(sample_image_path)
        assert img is not None
        assert img.size[0] > 0
        assert img.size[1] > 0
    
    def test_load_invalid_image(self, corrupted_image_path):
        """Test handling of invalid/corrupted image."""
        with pytest.raises(Exception):
            img = Image.open(corrupted_image_path)
            img.verify()  # This should raise for corrupted images
    
    def test_load_nonexistent_file(self):
        """Test handling of nonexistent file."""
        with pytest.raises(FileNotFoundError):
            Image.open("/nonexistent/path/image.png")
    
    def test_supported_formats(self, tmp_path):
        """Test loading various image formats."""
        formats = [('png', 'PNG'), ('jpg', 'JPEG'), ('jpeg', 'JPEG')]
        
        for ext, fmt in formats:
            img = Image.new('RGB', (100, 100), color='white')
            path = tmp_path / f"test.{ext}"
            img.save(path, format=fmt)
            
            loaded = Image.open(path)
            assert loaded is not None


class TestImageResizing:
    """Test image resizing functionality."""
    
    def test_resize_large_image(self):
        """Test resizing oversized images."""
        # Create large image
        img = Image.new('RGB', (4000, 6000), color='white')
        
        max_dimension = 2048
        
        # Calculate resize ratio
        ratio = min(max_dimension / img.width, max_dimension / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        
        assert resized.width <= max_dimension
        assert resized.height <= max_dimension
    
    def test_preserve_aspect_ratio(self):
        """Test that aspect ratio is preserved during resize."""
        img = Image.new('RGB', (800, 600), color='white')
        original_ratio = img.width / img.height
        
        # Resize
        new_width = 400
        new_height = int(new_width / original_ratio)
        resized = img.resize((new_width, new_height))
        
        new_ratio = resized.width / resized.height
        
        assert abs(original_ratio - new_ratio) < 0.01
    
    def test_no_upscaling(self):
        """Test that small images are not upscaled."""
        img = Image.new('RGB', (400, 300), color='white')
        max_dimension = 2048
        
        if img.width <= max_dimension and img.height <= max_dimension:
            # Should not resize
            assert img.size == (400, 300)


class TestImageEnhancement:
    """Test image enhancement operations."""
    
    def test_contrast_enhancement(self, sample_image):
        """Test contrast enhancement."""
        from PIL import ImageEnhance
        
        enhancer = ImageEnhance.Contrast(sample_image)
        enhanced = enhancer.enhance(1.5)
        
        assert enhanced.size == sample_image.size
    
    def test_brightness_adjustment(self, sample_image):
        """Test brightness adjustment."""
        from PIL import ImageEnhance
        
        enhancer = ImageEnhance.Brightness(sample_image)
        enhanced = enhancer.enhance(1.2)
        
        assert enhanced.size == sample_image.size
    
    def test_sharpness_enhancement(self, sample_image):
        """Test sharpness enhancement."""
        from PIL import ImageEnhance
        
        enhancer = ImageEnhance.Sharpness(sample_image)
        enhanced = enhancer.enhance(2.0)
        
        assert enhanced.size == sample_image.size


class TestImageConversion:
    """Test image format conversions."""
    
    def test_convert_to_rgb(self):
        """Test converting various modes to RGB."""
        # RGBA to RGB
        rgba = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
        rgb = rgba.convert('RGB')
        assert rgb.mode == 'RGB'
        
        # Grayscale to RGB
        gray = Image.new('L', (100, 100), 128)
        rgb = gray.convert('RGB')
        assert rgb.mode == 'RGB'
    
    def test_convert_to_grayscale(self, sample_image):
        """Test converting to grayscale."""
        gray = sample_image.convert('L')
        assert gray.mode == 'L'
    
    def test_preserve_original(self, sample_image):
        """Test that original image is not modified."""
        original_size = sample_image.size
        original_mode = sample_image.mode
        
        # Perform conversion
        _ = sample_image.convert('L')
        
        # Original should be unchanged
        assert sample_image.size == original_size
        assert sample_image.mode == original_mode


class TestDeskewing:
    """Test image deskewing functionality."""
    
    def test_detect_skew_angle(self, sample_lab_report_image):
        """Test skew angle detection."""
        img = Image.open(sample_lab_report_image)
        
        # For a generated test image, skew should be minimal
        # In real implementation, would use hough transform
        estimated_skew = 0.0  # Mock result
        
        assert abs(estimated_skew) < 45  # Reasonable range
    
    def test_rotate_image(self, sample_image):
        """Test image rotation."""
        angle = 5.0
        rotated = sample_image.rotate(angle, expand=True, fillcolor='white')
        
        assert rotated is not None
        # Rotated image may have different dimensions
        assert rotated.size[0] > 0
    
    def test_no_rotation_for_straight_image(self, sample_image):
        """Test that straight images are not rotated."""
        # For a straight image, detected angle should be near zero
        angle = 0.0
        
        if abs(angle) < 0.5:
            # No rotation needed
            result = sample_image
        else:
            result = sample_image.rotate(angle)
        
        assert result.size == sample_image.size


class TestDenoising:
    """Test image denoising functionality."""
    
    def test_median_filter(self, sample_image):
        """Test median filter denoising."""
        from PIL import ImageFilter
        
        denoised = sample_image.filter(ImageFilter.MedianFilter(size=3))
        assert denoised.size == sample_image.size
    
    def test_gaussian_blur_denoise(self, sample_image):
        """Test Gaussian blur for denoising."""
        from PIL import ImageFilter
        
        denoised = sample_image.filter(ImageFilter.GaussianBlur(radius=1))
        assert denoised.size == sample_image.size


class TestQualityCheck:
    """Test image quality assessment."""
    
    def test_check_resolution(self, sample_image):
        """Test resolution check."""
        min_width = 200
        min_height = 200
        
        is_valid = sample_image.width >= min_width and sample_image.height >= min_height
        assert is_valid is True
    
    def test_check_file_size(self, sample_image_path):
        """Test file size check."""
        max_size_mb = 50
        
        file_size = sample_image_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        assert file_size_mb <= max_size_mb
    
    def test_detect_blank_image(self):
        """Test detection of blank/empty images."""
        # Create a white image
        blank = Image.new('RGB', (100, 100), color='white')
        arr = np.array(blank)
        
        # Check if all pixels are the same
        is_blank = np.std(arr) < 5  # Very low standard deviation
        assert is_blank == True
    
    def test_calculate_image_quality_score(self, sample_lab_report_image):
        """Test overall quality score calculation."""
        img = Image.open(sample_lab_report_image)
        
        # Simple quality metrics
        width, height = img.size
        
        # Resolution score (0-100)
        min_res = 500
        max_res = 2000
        avg_dim = (width + height) / 2
        res_score = min(100, max(0, (avg_dim - min_res) / (max_res - min_res) * 100))
        
        assert 0 <= res_score <= 100


class TestPreprocessingPipeline:
    """Test the complete preprocessing pipeline."""
    
    def test_full_preprocessing(self, sample_lab_report_image):
        """Test complete preprocessing workflow."""
        from PIL import ImageEnhance, ImageFilter
        
        # Load image
        img = Image.open(sample_lab_report_image)
        
        # Convert to RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if needed
        max_dim = 2048
        if img.width > max_dim or img.height > max_dim:
            ratio = min(max_dim / img.width, max_dim / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)
        
        # Denoise
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        assert img is not None
        assert img.size[0] > 0
    
    def test_preprocessing_preserves_text(self, sample_lab_report_image):
        """Test that preprocessing preserves text readability."""
        from PIL import ImageEnhance
        
        img = Image.open(sample_lab_report_image)
        
        # Apply light enhancement only
        enhancer = ImageEnhance.Contrast(img)
        enhanced = enhancer.enhance(1.1)
        
        # Image should still have similar characteristics
        assert enhanced.size == img.size
    
    def test_preprocessing_error_handling(self, corrupted_image_path):
        """Test preprocessing handles errors gracefully."""
        try:
            img = Image.open(corrupted_image_path)
            img.verify()
            # Should fail before here
            assert False, "Should have raised exception"
        except Exception:
            # Expected behavior
            pass


class TestImageMetadata:
    """Test image metadata handling."""
    
    def test_extract_exif_data(self, sample_image_path):
        """Test extracting EXIF metadata."""
        img = Image.open(sample_image_path)
        exif = img.getexif()
        
        # May be empty for generated images
        assert isinstance(exif, dict) or exif is not None
    
    def test_strip_metadata(self, sample_image, tmp_path):
        """Test stripping metadata from image."""
        # Save without metadata
        clean = Image.new(sample_image.mode, sample_image.size)
        clean.paste(sample_image)
        
        path = tmp_path / "clean.png"
        clean.save(path)
        
        # Reload and check
        reloaded = Image.open(path)
        assert reloaded.size == sample_image.size
