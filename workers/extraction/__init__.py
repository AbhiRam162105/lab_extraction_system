"""
Lab Report Extraction Workers Package.

Production Pipeline:
- single_vision_extractor: Main extraction using Gemini Vision
- strict_normalizer: YAML-based test name standardization
- panel_validator: Panel completeness validation
- quality_verifier: Extraction quality verification
- safe_summary: Read-only summary generation
- rate_limiter: API rate limiting
- cache_manager: Redis/disk caching
- batch_processor: Batch processing
"""

from workers.extraction.single_vision_extractor import (
    SingleVisionExtractor,
    VisionExtractionResult,
    extract_single_vision
)
from workers.extraction.strict_normalizer import (
    StrictNormalizer,
    NormalizerResult,
    NormalizedResult
)
from workers.extraction.preprocessing import preprocess_image, ImagePreprocessor
from workers.extraction.panel_validator import validate_panel_completeness
from workers.extraction.quality_verifier import verify_extraction_quality
from workers.extraction.safe_summary import generate_safe_summary
from workers.extraction.rate_limiter import get_rate_limiter, AdaptiveRateLimiter
from workers.extraction.cache_manager import CacheManager, get_cache_manager
from workers.extraction.batch_processor import BatchProcessor, get_batch_processor

__all__ = [
    # Main extraction
    'SingleVisionExtractor',
    'VisionExtractionResult',
    'extract_single_vision',
    
    # Normalization
    'StrictNormalizer',
    'NormalizerResult',
    'NormalizedResult',
    
    # Preprocessing
    'preprocess_image',
    'ImagePreprocessor',
    
    # Validation
    'validate_panel_completeness',
    'verify_extraction_quality',
    
    # Summary
    'generate_safe_summary',
    
    # Rate limiting
    'get_rate_limiter',
    'AdaptiveRateLimiter',
    
    # Caching
    'CacheManager',
    'get_cache_manager',
    
    # Batch processing
    'BatchProcessor',
    'get_batch_processor',
]
