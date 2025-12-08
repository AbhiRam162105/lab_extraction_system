"""
Fast Image Preprocessing with Parallel Processing.

Features:
- Parallel preprocessing using ThreadPoolExecutor
- Quick quality check to skip unnecessary processing
- Smart resizing (only if dimensions > 2048px)
- Compressed JPEG output to reduce API payload size
- Batch preprocessing for multiple images
"""

import io
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps, ImageFilter

# Try OpenCV for advanced preprocessing
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PreprocessConfig:
    """Preprocessing configuration."""
    max_dimension: int = 2048
    jpeg_quality: int = 85
    quality_threshold: float = 100.0  # Laplacian variance
    parallel_workers: int = 8
    enable_deskew: bool = True
    enable_denoise: bool = True
    enable_contrast: bool = True


@dataclass
class PreprocessResult:
    """Result of preprocessing."""
    image: Image.Image
    bytes: Optional[bytes] = None
    original_size: Tuple[int, int] = (0, 0)
    final_size: Tuple[int, int] = (0, 0)
    quality_score: float = 0.0
    was_resized: bool = False
    processing_time: float = 0.0


class FastPreprocessor:
    """
    Fast image preprocessor with parallel processing support.
    
    Optimizes images for vision API extraction while minimizing
    processing time and output size.
    """
    
    def __init__(self, config: Optional[PreprocessConfig] = None):
        self.config = config or PreprocessConfig()
        self._executor = ThreadPoolExecutor(max_workers=self.config.parallel_workers)
        logger.info(f"FastPreprocessor initialized: workers={self.config.parallel_workers}")
    
    def preprocess(
        self,
        image_path: str,
        return_bytes: bool = False
    ) -> PreprocessResult:
        """
        Preprocess a single image.
        
        Args:
            image_path: Path to image file
            return_bytes: If True, also return compressed JPEG bytes
            
        Returns:
            PreprocessResult with processed image
        """
        import time
        start = time.time()
        
        # Load image
        img = Image.open(image_path)
        original_size = img.size
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Check quality - skip heavy processing if already good
        quality_score = self._check_quality(img)
        
        if quality_score >= self.config.quality_threshold:
            # Image is high quality, just resize if needed
            img, was_resized = self._smart_resize(img)
            logger.debug(f"High quality image, minimal processing: {quality_score:.1f}")
        else:
            # Apply full preprocessing pipeline
            if OPENCV_AVAILABLE:
                img = self._process_with_opencv(img)
            else:
                img = self._process_with_pil(img)
            
            img, was_resized = self._smart_resize(img)
        
        # Convert to bytes if requested
        img_bytes = None
        if return_bytes:
            img_bytes = self._to_jpeg_bytes(img)
        
        return PreprocessResult(
            image=img,
            bytes=img_bytes,
            original_size=original_size,
            final_size=img.size,
            quality_score=quality_score,
            was_resized=was_resized,
            processing_time=time.time() - start
        )
    
    def preprocess_batch(
        self,
        image_paths: List[str],
        return_bytes: bool = False
    ) -> List[Tuple[str, PreprocessResult]]:
        """
        Preprocess multiple images in parallel.
        
        Args:
            image_paths: List of image file paths
            return_bytes: If True, also return compressed JPEG bytes
            
        Returns:
            List of (path, PreprocessResult) tuples
        """
        results = []
        
        futures = {
            self._executor.submit(self.preprocess, path, return_bytes): path
            for path in image_paths
        }
        
        for future in as_completed(futures):
            path = futures[future]
            try:
                result = future.result()
                results.append((path, result))
            except Exception as e:
                logger.error(f"Preprocessing failed for {path}: {e}")
                # Return original image on failure
                try:
                    img = Image.open(path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    results.append((path, PreprocessResult(
                        image=img,
                        original_size=img.size,
                        final_size=img.size
                    )))
                except:
                    pass
        
        logger.info(f"Batch preprocessing complete: {len(results)}/{len(image_paths)} successful")
        return results
    
    def _check_quality(self, img: Image.Image) -> float:
        """
        Check image quality using Laplacian variance.
        
        Higher value = sharper image.
        """
        if not OPENCV_AVAILABLE:
            return 0.0
        
        try:
            # Convert to grayscale numpy array
            gray = np.array(img.convert('L'))
            
            # Compute Laplacian variance (measure of sharpness)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            variance = laplacian.var()
            
            return float(variance)
        except Exception as e:
            logger.debug(f"Quality check failed: {e}")
            return 0.0
    
    def _smart_resize(self, img: Image.Image) -> Tuple[Image.Image, bool]:
        """
        Resize image only if dimensions exceed max.
        
        Maintains aspect ratio.
        """
        width, height = img.size
        max_dim = self.config.max_dimension
        
        if width <= max_dim and height <= max_dim:
            return img, False
        
        # Calculate new size maintaining aspect ratio
        if width > height:
            new_width = max_dim
            new_height = int(height * max_dim / width)
        else:
            new_height = max_dim
            new_width = int(width * max_dim / height)
        
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.debug(f"Resized: {width}x{height} -> {new_width}x{new_height}")
        
        return img, True
    
    def _process_with_opencv(self, img: Image.Image) -> Image.Image:
        """Apply OpenCV-based preprocessing."""
        # Convert to numpy
        img_array = np.array(img)
        
        try:
            # Denoise
            if self.config.enable_denoise:
                img_array = cv2.fastNlMeansDenoisingColored(
                    img_array, None, 10, 10, 7, 21
                )
            
            # Convert to LAB for CLAHE
            if self.config.enable_contrast:
                lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
                l, a, b = cv2.split(lab)
                
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l = clahe.apply(l)
                
                lab = cv2.merge([l, a, b])
                img_array = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
            
            return Image.fromarray(img_array)
            
        except Exception as e:
            logger.warning(f"OpenCV processing failed, using PIL: {e}")
            return self._process_with_pil(img)
    
    def _process_with_pil(self, img: Image.Image) -> Image.Image:
        """Apply PIL-based preprocessing (fallback)."""
        # Auto contrast
        img = ImageOps.autocontrast(img, cutoff=2)
        
        # Sharpen
        if self.config.enable_contrast:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.5)
            
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
        
        return img
    
    def _to_jpeg_bytes(self, img: Image.Image) -> bytes:
        """Convert image to compressed JPEG bytes."""
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=self.config.jpeg_quality, optimize=True)
        return buffer.getvalue()
    
    def close(self):
        """Shutdown thread pool."""
        self._executor.shutdown(wait=False)


# Global preprocessor instance
_preprocessor: Optional[FastPreprocessor] = None


def get_preprocessor() -> FastPreprocessor:
    """Get or create global preprocessor."""
    global _preprocessor
    
    if _preprocessor is None:
        from backend.core.config import get_settings
        settings = get_settings()
        
        config = PreprocessConfig(
            parallel_workers=8,
            max_dimension=2048,
            jpeg_quality=85
        )
        _preprocessor = FastPreprocessor(config)
    
    return _preprocessor


def preprocess_image(image_path: str) -> Image.Image:
    """
    Convenience function for single image preprocessing.
    
    Compatible with existing code that expects Image return.
    """
    preprocessor = get_preprocessor()
    result = preprocessor.preprocess(image_path)
    return result.image


def preprocess_batch(image_paths: List[str]) -> List[Tuple[str, Image.Image]]:
    """
    Preprocess multiple images in parallel.
    
    Returns list of (path, image) tuples.
    """
    preprocessor = get_preprocessor()
    results = preprocessor.preprocess_batch(image_paths)
    return [(path, result.image) for path, result in results]
