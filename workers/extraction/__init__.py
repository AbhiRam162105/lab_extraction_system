"""
Lab Report Extraction Workers Package.

This package contains the extraction pipeline components:
- preprocessing: Enhanced image preprocessing with deskewing, denoising, etc.
- prompts: Multi-prompt strategy for robust extraction
- standardizer: Test name standardization with LOINC codes
- gemini: 3-pass extraction pipeline using Gemini Vision API
- main: Document processing worker
"""

from workers.extraction.gemini import extract_lab_report, two_pass_extraction, GeminiExtractor
from workers.extraction.standardizer import (
    standardize_test_name,
    standardize_lab_results,
    TestNameStandardizer,
    get_standardizer
)
from workers.extraction.preprocessing import preprocess_image, ImagePreprocessor
from workers.extraction.prompts import (
    VISION_PROMPTS,
    get_refinement_prompt,
    should_retry,
    get_validation_status
)

__all__ = [
    # Main extraction
    'extract_lab_report',
    'two_pass_extraction',
    'GeminiExtractor',
    
    # Standardization
    'standardize_test_name',
    'standardize_lab_results',
    'TestNameStandardizer',
    'get_standardizer',
    
    # Preprocessing
    'preprocess_image',
    'ImagePreprocessor',
    
    # Prompts
    'VISION_PROMPTS',
    'get_refinement_prompt',
    'should_retry',
    'get_validation_status',
]
