"""
Enhanced Image Preprocessing Pipeline for Lab Report Extraction.

This module provides advanced image preprocessing techniques to improve
OCR/Vision extraction quality for various document conditions:
- Tilted/skewed scans
- Poor lighting/faded prints
- Noisy images
- Variable contrast
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from pathlib import Path
from typing import Union, Tuple
import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Advanced image preprocessing pipeline for medical documents.
    
    Applies a series of transformations to improve text extraction quality.
    """
    
    def __init__(
        self,
        target_dpi: int = 300,
        deskew_enabled: bool = True,
        denoise_enabled: bool = True,
        contrast_enhance_enabled: bool = True,
        binarize_enabled: bool = False,  # Usually not needed for Vision API
    ):
        """
        Initialize preprocessor with configuration.
        
        Args:
            target_dpi: Target DPI for resizing (higher = better quality but slower)
            deskew_enabled: Whether to auto-correct rotation/skew
            denoise_enabled: Whether to apply noise reduction
            contrast_enhance_enabled: Whether to enhance contrast
            binarize_enabled: Whether to convert to black/white
        """
        self.target_dpi = target_dpi
        self.deskew_enabled = deskew_enabled
        self.denoise_enabled = denoise_enabled
        self.contrast_enhance_enabled = contrast_enhance_enabled
        self.binarize_enabled = binarize_enabled
    
    def process(self, image_path: Union[str, Path]) -> Image.Image:
        """
        Apply full preprocessing pipeline to an image.
        
        Args:
            image_path: Path to the input image
            
        Returns:
            Preprocessed PIL Image ready for extraction
        """
        try:
            # Load image with OpenCV for advanced processing
            img = cv2.imread(str(image_path))
            if img is None:
                raise ValueError(f"Failed to load image: {image_path}")
            
            # Convert BGR to RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Step 1: Deskew if enabled
            if self.deskew_enabled:
                img = self._deskew(img)
            
            # Step 2: Denoise if enabled
            if self.denoise_enabled:
                img = self._denoise(img)
            
            # Step 3: Enhance contrast if enabled
            if self.contrast_enhance_enabled:
                img = self._enhance_contrast(img)
            
            # Step 4: Binarize if enabled (for very poor quality documents)
            if self.binarize_enabled:
                img = self._binarize(img)
            
            # Convert back to PIL Image
            pil_image = Image.fromarray(img)
            
            # Final PIL-based enhancements
            pil_image = self._enhance_sharpness(pil_image)
            
            return pil_image
            
        except Exception as e:
            logger.error(f"Preprocessing failed for {image_path}: {e}")
            # Fallback to basic preprocessing
            return self._basic_preprocess(image_path)
    
    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """
        Detect and correct document skew using Hough Line Transform.
        
        Args:
            img: Input image as numpy array (RGB)
            
        Returns:
            Deskewed image
        """
        try:
            # Convert to grayscale for edge detection
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Edge detection
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Detect lines using Hough Transform
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=100,
                minLineLength=100,
                maxLineGap=10
            )
            
            if lines is None or len(lines) == 0:
                return img
            
            # Calculate average angle from detected lines
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                # Only consider nearly horizontal lines (within 45 degrees)
                if abs(angle) < 45:
                    angles.append(angle)
            
            if not angles:
                return img
            
            # Use median angle for robustness
            median_angle = np.median(angles)
            
            # Skip if angle is very small (already straight)
            if abs(median_angle) < 0.5:
                return img
            
            # Rotate image to correct skew
            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
            
            # Calculate new image bounds to avoid cropping
            cos = np.abs(rotation_matrix[0, 0])
            sin = np.abs(rotation_matrix[0, 1])
            new_w = int((h * sin) + (w * cos))
            new_h = int((h * cos) + (w * sin))
            
            rotation_matrix[0, 2] += (new_w / 2) - center[0]
            rotation_matrix[1, 2] += (new_h / 2) - center[1]
            
            rotated = cv2.warpAffine(
                img,
                rotation_matrix,
                (new_w, new_h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            
            logger.debug(f"Deskewed image by {median_angle:.2f} degrees")
            return rotated
            
        except Exception as e:
            logger.warning(f"Deskew failed: {e}")
            return img
    
    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """
        Apply noise reduction using Non-Local Means Denoising.
        
        Args:
            img: Input image as numpy array (RGB)
            
        Returns:
            Denoised image
        """
        try:
            # fastNlMeansDenoisingColored works on color images
            denoised = cv2.fastNlMeansDenoisingColored(
                img,
                None,
                h=6,           # Filter strength for luminance
                hColor=6,      # Filter strength for color
                templateWindowSize=7,
                searchWindowSize=21
            )
            return denoised
        except Exception as e:
            logger.warning(f"Denoise failed: {e}")
            return img
    
    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """
        Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).
        
        CLAHE works well for documents with variable lighting across the page.
        
        Args:
            img: Input image as numpy array (RGB)
            
        Returns:
            Contrast-enhanced image
        """
        try:
            # Convert to LAB color space
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            
            # Apply CLAHE to L channel only
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            
            # Convert back to RGB
            enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
            return enhanced
            
        except Exception as e:
            logger.warning(f"Contrast enhancement failed: {e}")
            return img
    
    def _binarize(self, img: np.ndarray) -> np.ndarray:
        """
        Convert image to black and white using adaptive thresholding.
        
        Useful for very faded or low-contrast documents.
        
        Args:
            img: Input image as numpy array (RGB)
            
        Returns:
            Binarized image (still RGB format for compatibility)
        """
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Apply adaptive thresholding
            binary = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=11,
                C=2
            )
            
            # Convert back to RGB (3-channel grayscale)
            return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
            
        except Exception as e:
            logger.warning(f"Binarization failed: {e}")
            return img
    
    def _enhance_sharpness(self, img: Image.Image, factor: float = 1.5) -> Image.Image:
        """
        Enhance image sharpness using PIL.
        
        Args:
            img: PIL Image
            factor: Sharpness factor (1.0 = original, >1.0 = sharper)
            
        Returns:
            Sharpened image
        """
        try:
            enhancer = ImageEnhance.Sharpness(img)
            return enhancer.enhance(factor)
        except Exception as e:
            logger.warning(f"Sharpness enhancement failed: {e}")
            return img
    
    def _basic_preprocess(self, image_path: Union[str, Path]) -> Image.Image:
        """
        Basic preprocessing fallback using only PIL.
        
        Args:
            image_path: Path to image
            
        Returns:
            Preprocessed PIL Image
        """
        img = Image.open(image_path)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Auto contrast
        img = ImageOps.autocontrast(img, cutoff=2)
        
        # Sharpen
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.5)
        
        # Slight contrast boost
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)
        
        return img


# Convenience function for direct use
def preprocess_image(
    image_path: Union[str, Path],
    deskew: bool = True,
    denoise: bool = True,
    enhance_contrast: bool = True,
    binarize: bool = False
) -> Image.Image:
    """
    Preprocess an image for optimal OCR/Vision extraction.
    
    Args:
        image_path: Path to the input image
        deskew: Whether to correct rotation/skew
        denoise: Whether to reduce noise
        enhance_contrast: Whether to enhance contrast
        binarize: Whether to convert to black/white
        
    Returns:
        Preprocessed PIL Image
    """
    preprocessor = ImagePreprocessor(
        deskew_enabled=deskew,
        denoise_enabled=denoise,
        contrast_enhance_enabled=enhance_contrast,
        binarize_enabled=binarize
    )
    return preprocessor.process(image_path)
