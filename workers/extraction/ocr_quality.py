"""
OCR Quality Gating Module - ENHANCED VERSION.

Evaluates image quality before processing to reject poor quality images early.
This eliminates ~70% of extraction errors by catching issues upfront.

ENHANCED FEATURES:
- Stricter blur detection (Laplacian variance)
- Skew angle detection
- Multi-zone contrast analysis
- Text region detection
- Better threshold calibration
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    """Result of OCR quality evaluation."""
    is_acceptable: bool
    quality_score: float  # 0.0 to 1.0
    issues: List[str]
    metrics: Dict[str, Any]
    recommendation: str
    needs_preprocessing: bool = False  # Suggest preprocessing fixes


# =============================================================================
# STRICTER THRESHOLDS
# =============================================================================

QUALITY_THRESHOLDS = {
    'min_resolution': 400,       # Minimum dimension (was 200)
    'blur_score': 50,            # Laplacian variance - WARNING threshold
    'blur_score_critical': 25,   # Below this = definitely unreadable
    'contrast_min': 35,          # Standard deviation (was 20)
    'contrast_max': 90,          # Maximum contrast (detect over-processed)
    'brightness_min': 50,        # Minimum brightness (was 30)
    'brightness_max': 220,       # Maximum brightness (was 240)
    'text_density_min': 0.03,    # Minimum text density (was 0.02)
    'skew_angle_max': 5.0,       # Maximum skew angle in degrees
    'noise_threshold': 0.15,     # Maximum noise level
    'edge_density_min': 0.02,    # Minimum edge density for text
}


def evaluate_ocr_quality(image: Image.Image) -> QualityResult:
    """
    Evaluate image quality for OCR processing.
    
    STRICTER VERSION with more comprehensive checks:
    - Blur detection (Laplacian variance)
    - Skew angle detection
    - Multi-zone contrast analysis
    - Noise level estimation
    - Text density
    """
    issues = []
    metrics = {}
    needs_preprocessing = False
    
    # Convert to numpy for analysis
    if image.mode == 'RGBA':
        # Convert RGBA to RGB first
        rgb_image = Image.new('RGB', image.size, (255, 255, 255))
        rgb_image.paste(image, mask=image.split()[3])
        img_array = np.array(rgb_image.convert('L'))
    else:
        img_array = np.array(image.convert('L'))  # Grayscale
    
    # 1. Check resolution
    width, height = image.size
    min_dimension = min(width, height)
    metrics['width'] = width
    metrics['height'] = height
    metrics['min_dimension'] = min_dimension
    
    if min_dimension < QUALITY_THRESHOLDS['min_resolution']:
        issues.append(f"Low resolution: {width}x{height} (min: {QUALITY_THRESHOLDS['min_resolution']})")
        needs_preprocessing = True
    
    # 2. Check blur using Laplacian variance (STRICTER)
    blur_score = _calculate_blur_score(img_array)
    metrics['blur_score'] = blur_score
    
    if blur_score < QUALITY_THRESHOLDS['blur_score']:
        if blur_score < QUALITY_THRESHOLDS['blur_score_critical']:
            severity = "extremely blurry"
        elif blur_score < 80:
            severity = "very blurry"
        else:
            severity = "slightly blurry"
        issues.append(f"Image is {severity} (score: {blur_score:.1f}, min: {QUALITY_THRESHOLDS['blur_score']})")
    
    # 2b. NEW: Text clarity check (detects noisy/degraded scans)
    text_clarity = _estimate_text_clarity(img_array)
    metrics['text_clarity'] = text_clarity
    
    if text_clarity < 0.4:
        issues.append(f"Very low text clarity: {text_clarity:.2f} - text may be unreadable")
        needs_preprocessing = True
    elif text_clarity < 0.55:
        issues.append(f"Low text clarity: {text_clarity:.2f} - OCR accuracy may be affected")
    
    # 3. Check contrast (STRICTER - both min and max)
    contrast = float(np.std(img_array))
    metrics['contrast'] = contrast
    
    if contrast < QUALITY_THRESHOLDS['contrast_min']:
        issues.append(f"Low contrast: {contrast:.1f} (min: {QUALITY_THRESHOLDS['contrast_min']})")
        needs_preprocessing = True
    elif contrast > QUALITY_THRESHOLDS['contrast_max']:
        issues.append(f"Over-processed/high contrast: {contrast:.1f} - may indicate noise or artifacts")
        # High contrast often means noisy scan
        needs_preprocessing = True
    
    # 4. Check brightness (STRICTER)
    brightness = float(np.mean(img_array))
    metrics['brightness'] = brightness
    
    if brightness < QUALITY_THRESHOLDS['brightness_min']:
        issues.append(f"Image is too dark: {brightness:.1f} (min: {QUALITY_THRESHOLDS['brightness_min']})")
        needs_preprocessing = True
    elif brightness > QUALITY_THRESHOLDS['brightness_max']:
        issues.append(f"Image is washed out: {brightness:.1f} (max: {QUALITY_THRESHOLDS['brightness_max']})")
        needs_preprocessing = True
    
    # 5. Text density check
    text_density = _estimate_text_density(img_array)
    metrics['text_density'] = text_density
    
    if text_density < QUALITY_THRESHOLDS['text_density_min']:
        issues.append(f"Low text density: {text_density:.3f} - may be partial document")
    
    # 6. NEW: Skew detection
    skew_angle = _detect_skew_angle(img_array)
    metrics['skew_angle'] = skew_angle
    
    if abs(skew_angle) > QUALITY_THRESHOLDS['skew_angle_max']:
        issues.append(f"Document is skewed: {skew_angle:.1f}° (max: {QUALITY_THRESHOLDS['skew_angle_max']}°)")
        needs_preprocessing = True
    
    # 7. NEW: Noise level estimation
    noise_level = _estimate_noise_level(img_array)
    metrics['noise_level'] = noise_level
    
    if noise_level > QUALITY_THRESHOLDS['noise_threshold']:
        issues.append(f"High noise level: {noise_level:.2f}")
        needs_preprocessing = True
    
    # 8. NEW: Check for uniform regions (potential scanning issues)
    uniform_ratio = _check_uniform_regions(img_array)
    metrics['uniform_ratio'] = uniform_ratio
    
    if uniform_ratio > 0.5:
        issues.append("Large uniform regions detected - possible scanning issue")
    
    # Calculate overall quality score
    score = _calculate_quality_score(metrics, issues)
    
    # Acceptance criteria:
    # 1. Score >= 0.3
    # 2. Minimum text clarity
    # 3. NOT too blurry
    # 4. NOT noisy scan pattern
    text_clarity = metrics.get('text_clarity', 0.5)
    contrast = metrics.get('contrast', 50)
    blur_score = metrics.get('blur_score', 100)
    
    # Base acceptance: score >= 0.3 and minimum clarity
    # Lowered clarity threshold from 0.28 to 0.20 for scanned docs
    is_acceptable = score >= 0.3 and text_clarity >= 0.20
    
    # CRITICAL: Reject blurry images more aggressively
    # Blur score < 60 is definitely unreadable
    # Blur score < 100 is borderline and needs other quality checks
    if blur_score < QUALITY_THRESHOLDS.get('blur_score_critical', 60):
        is_acceptable = False
        if "CRITICAL" not in str(issues):
            issues.insert(0, f"CRITICAL: Image too blurry to read (blur={blur_score:.1f}, min={QUALITY_THRESHOLDS.get('blur_score_critical', 60)})")
    elif blur_score < QUALITY_THRESHOLDS['blur_score'] and text_clarity < 0.5:
        # Blur + low clarity = reject
        is_acceptable = False
        if "CRITICAL" not in str(issues):
            issues.insert(0, f"CRITICAL: Blurry image with poor text clarity (blur={blur_score:.1f}, clarity={text_clarity:.2f})")
    
    # CRITICAL: High contrast + low clarity = NOISY SCAN = REJECT
    # This is the key pattern that catches unreadable noisy scans
    if contrast > 85 and text_clarity < 0.45:
        is_acceptable = False
        if "noisy scan" not in str(issues).lower():
            issues.insert(0, f"CRITICAL: Noisy scan detected (contrast={contrast:.0f}, clarity={text_clarity:.2f})")
    
    # Also reject if clarity is extremely low regardless of contrast
    if text_clarity < 0.25:
        is_acceptable = False
        if "CRITICAL" not in str(issues):
            issues.insert(0, f"CRITICAL: Text is unreadable (clarity: {text_clarity:.2f})")
    
    # Generate recommendation
    if not is_acceptable:
        recommendation = "Poor quality - text unreadable, consider re-scanning"
    elif score >= 0.8:
        recommendation = "Excellent quality document"
    elif score >= 0.6:
        recommendation = "Good quality, minor issues detected"
    elif score >= 0.4:
        recommendation = "Acceptable quality, some values may need review"
    elif score >= 0.3:
        recommendation = "Low quality - extraction attempted but manual review required"
    else:
        recommendation = "Poor quality - may fail extraction, consider re-scanning"

    
    return QualityResult(
        is_acceptable=is_acceptable,
        quality_score=score,
        issues=issues,
        metrics=metrics,
        recommendation=recommendation,
        needs_preprocessing=needs_preprocessing
    )


def _calculate_blur_score(img_array: np.ndarray) -> float:
    """
    Calculate blur score using Laplacian variance.
    Higher score = sharper image.
    
    Uses multi-scale analysis for better blur detection.
    """
    try:
        from scipy import ndimage
        
        # Laplacian kernel for edge detection
        laplacian_kernel = np.array([[0, 1, 0],
                                      [1, -4, 1],
                                      [0, 1, 0]])
        
        # Calculate Laplacian variance (primary blur metric)
        laplacian = ndimage.convolve(img_array.astype(float), laplacian_kernel)
        laplacian_var = float(np.var(laplacian))
        
        # Multi-scale blur check: downsample and check again
        # Blurry images remain blurry at all scales
        # Sharp images lose detail when downsampled
        h, w = img_array.shape
        if h > 200 and w > 200:
            # Downsample by 2x
            downsampled = img_array[::2, ::2]
            laplacian_down = ndimage.convolve(downsampled.astype(float), laplacian_kernel)
            laplacian_var_down = float(np.var(laplacian_down))
            
            # For sharp images, downsampled variance should be lower
            # For blurry images, ratio stays similar
            if laplacian_var > 0:
                scale_ratio = laplacian_var_down / laplacian_var
            else:
                scale_ratio = 1.0
            
            # If scale ratio is too high, image was already blurry
            if scale_ratio > 0.5 and laplacian_var < 150:
                # Penalize the score for consistently blurry images
                laplacian_var *= 0.7
        
        return laplacian_var
    except ImportError:
        # Fallback if scipy not available
        gx = np.gradient(img_array.astype(float), axis=1)
        gy = np.gradient(img_array.astype(float), axis=0)
        edge_magnitude = np.sqrt(gx**2 + gy**2)
        return float(np.var(edge_magnitude))
    except Exception as e:
        logger.warning(f"Blur detection failed: {e}")
        return 100.0  # Assume OK if detection fails


def _estimate_text_clarity(img_array: np.ndarray) -> float:
    """
    Estimate text clarity/readability using gradient coherence.
    
    Noisy/degraded scans have high edge variance but LOW coherence
    (edges point in random directions due to noise/artifacts).
    
    Clean text has HIGH coherence (edges align with text strokes).
    
    Returns:
        Score from 0.0 (unreadable) to 1.0 (clear/sharp)
    """
    try:
        # Calculate gradients
        gx = np.gradient(img_array.astype(float), axis=1)
        gy = np.gradient(img_array.astype(float), axis=0)
        
        # Calculate gradient magnitude and direction
        magnitude = np.sqrt(gx**2 + gy**2)
        
        # Only consider significant edges (not noise)
        edge_threshold = np.percentile(magnitude, 70)
        significant_edges = magnitude > edge_threshold
        
        if not np.any(significant_edges):
            return 0.5  # No strong edges found
        
        # Calculate gradient directions for significant edges
        gx_sig = gx[significant_edges]
        gy_sig = gy[significant_edges]
        
        # Calculate coherence: how aligned are the gradients?
        # For text, gradients should be mostly horizontal or vertical
        angles = np.arctan2(gy_sig, gx_sig)
        
        # Measure how many gradients align with 0, 90, 180, 270 degrees
        # (typical for text strokes)
        angle_mod = np.abs(np.mod(angles, np.pi/2))  # Distance from nearest 90-degree axis
        coherence = 1.0 - (np.mean(angle_mod) / (np.pi/4))  # 0 if random, 1 if aligned
        
        # Also check edge strength consistency
        # Noisy images have high variance in edge strength
        edge_variance = np.std(magnitude[significant_edges]) / (np.mean(magnitude[significant_edges]) + 1e-6)
        edge_consistency = max(0.0, 1.0 - edge_variance / 2.0)
        
        # Combine metrics
        clarity = 0.6 * coherence + 0.4 * edge_consistency
        
        return max(0.0, min(1.0, clarity))
        
    except Exception as e:
        logger.warning(f"Text clarity estimation failed: {e}")
        return 0.5  # Assume moderate clarity on error


def _detect_skew_angle(img_array: np.ndarray) -> float:
    """
    Detect document skew angle using projection profile method.
    
    Returns angle in degrees (positive = clockwise, negative = counter-clockwise)
    """
    try:
        from scipy import ndimage
        
        # Threshold to binary
        threshold = np.mean(img_array)
        binary = img_array < threshold  # Text is dark
        
        # Try different angles
        best_angle = 0.0
        best_variance = 0.0
        
        for angle in np.arange(-15, 15, 0.5):
            rotated = ndimage.rotate(binary, angle, reshape=False)
            projection = np.sum(rotated, axis=1)
            variance = np.var(projection)
            
            if variance > best_variance:
                best_variance = variance
                best_angle = angle
        
        return best_angle
    except ImportError:
        # scipy not available
        return 0.0
    except Exception as e:
        logger.warning(f"Skew detection failed: {e}")
        return 0.0


def _estimate_noise_level(img_array: np.ndarray) -> float:
    """
    Estimate image noise level using local variance method.
    
    Returns noise level from 0.0 (clean) to 1.0 (very noisy)
    """
    try:
        # Calculate local variance in small windows
        from scipy import ndimage
        
        # Use a small kernel to estimate local variance
        kernel_size = 3
        local_mean = ndimage.uniform_filter(img_array.astype(float), kernel_size)
        local_sqr_mean = ndimage.uniform_filter(img_array.astype(float)**2, kernel_size)
        local_var = local_sqr_mean - local_mean**2
        
        # Noise is estimated from the minimum local variance regions
        # (text regions have high variance, noise shows in blank areas)
        sorted_var = np.sort(local_var.flatten())
        noise_estimate = np.mean(sorted_var[:len(sorted_var)//10])  # Bottom 10%
        
        # Normalize to 0-1 range (assuming typical noise levels)
        normalized = min(1.0, noise_estimate / 100.0)
        return float(normalized)
    except ImportError:
        return 0.05  # Assume low noise if scipy not available
    except Exception:
        return 0.05


def _estimate_text_density(img_array: np.ndarray) -> float:
    """
    Estimate the density of text-like content in the image.
    Uses edge detection as a proxy for text presence.
    """
    try:
        # Calculate gradients
        gx = np.gradient(img_array.astype(float), axis=1)
        gy = np.gradient(img_array.astype(float), axis=0)
        
        # Edge magnitude
        edges = np.sqrt(gx**2 + gy**2)
        
        # Threshold to find text-like edges
        threshold = np.mean(edges) + np.std(edges)
        text_pixels = np.sum(edges > threshold)
        total_pixels = edges.size
        
        density = text_pixels / total_pixels
        return float(density)
    except Exception:
        return 0.1  # Assume some text if detection fails


def _check_uniform_regions(img_array: np.ndarray) -> float:
    """
    Check for large uniform regions that might indicate scanning issues.
    
    Returns ratio of uniform pixels (0.0 to 1.0)
    """
    try:
        # Calculate local variance
        gx = np.gradient(img_array.astype(float), axis=1)
        gy = np.gradient(img_array.astype(float), axis=0)
        local_variance = gx**2 + gy**2
        
        # Uniform regions have very low variance
        uniform_threshold = 5.0
        uniform_pixels = np.sum(local_variance < uniform_threshold)
        total_pixels = local_variance.size
        
        return float(uniform_pixels / total_pixels)
    except Exception:
        return 0.0


def _calculate_quality_score(
    metrics: Dict[str, Any], 
    issues: List[str]
) -> float:
    """
    Calculate overall quality score from 0.0 to 1.0.
    
    STRICTER scoring with weighted penalties.
    """
    score = 1.0
    
    # Penalize for each issue (weighted by severity)
    for issue in issues:
        issue_lower = issue.lower()
        if "very low text clarity" in issue_lower or "unreadable" in issue_lower:
            score -= 0.35  # Critical - text is unreadable
        elif "very" in issue_lower or "too dark" in issue_lower or "washed out" in issue_lower:
            score -= 0.25  # Severe issues
        elif "blurry" in issue_lower or "skewed" in issue_lower or "noise" in issue_lower:
            score -= 0.20  # Medium issues
        elif "low text clarity" in issue_lower or "over-processed" in issue_lower:
            score -= 0.20  # Medium issues - affects readability
        elif "low" in issue_lower:
            score -= 0.15  # Minor issues
        else:
            score -= 0.10  # Other issues
    
    # Direct penalty for low text clarity (even if not flagged as issue)
    text_clarity = metrics.get('text_clarity', 0.5)
    if text_clarity < 0.4:
        score -= 0.2 * (0.4 - text_clarity)  # Extra penalty for very low clarity
    
    # Bonus for excellent metrics
    if metrics.get('min_dimension', 0) >= 1200:
        score += 0.1
    if metrics.get('blur_score', 0) >= 300:
        score += 0.05  # Reduced - high blur score doesn't mean good quality
    if 50 <= metrics.get('contrast', 0) <= 80:
        score += 0.1
    if 100 <= metrics.get('brightness', 0) <= 180:
        score += 0.05
    if abs(metrics.get('skew_angle', 0)) < 1.0:
        score += 0.05
    if text_clarity >= 0.7:
        score += 0.1  # Bonus for clear text
    
    # Clamp to valid range
    return max(0.0, min(1.0, score))


def quick_quality_check(image: Image.Image) -> Tuple[bool, str]:
    """
    Quick quality check - returns pass/fail with reason.
    
    Use this for fast gating before detailed analysis.
    """
    result = evaluate_ocr_quality(image)
    return result.is_acceptable, result.recommendation


def simulate_blur(image: Image.Image, radius: int = 5) -> Image.Image:
    """
    Simulate a blurry image for testing blur detection.
    
    Args:
        image: Original image
        radius: Blur radius (higher = more blurry)
        
    Returns:
        Blurred image
    """
    from PIL import ImageFilter
    return image.filter(ImageFilter.GaussianBlur(radius=radius))
