"""
Enhanced Lab Report Extraction Pipeline using Gemini Vision API.

Three-pass architecture:
1. Pass 1: Vision Extraction - Extract raw text from image
2. Pass 2: Structure + Validate - Convert to structured JSON with validation
3. Pass 3: Standardize - Apply test name standardization with LOINC codes

Features:
- Multi-prompt retry strategy for robust extraction
- Confidence-based validation and retry logic
- Enhanced image preprocessing
- Test name standardization with fuzzy matching
"""

import json
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, asdict

import google.generativeai as genai
from PIL import Image

from backend.core.config import get_settings
from workers.extraction.preprocessing import preprocess_image
from workers.extraction.prompts import (
    VISION_PROMPTS,
    get_refinement_prompt,
    should_retry,
    get_validation_status,
    CONFIDENCE_THRESHOLDS
)
from workers.extraction.standardizer import standardize_lab_results

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class ExtractionResult:
    """Result of the extraction pipeline."""
    success: bool
    data: Dict[str, Any]
    confidence: float
    needs_review: bool
    review_reason: Optional[str]
    extraction_metadata: Dict[str, Any]
    # Timing information (in seconds)
    preprocessing_time: float = 0.0
    pass1_time: float = 0.0
    pass2_time: float = 0.0
    pass3_time: float = 0.0
    total_time: float = 0.0


class GeminiExtractor:
    """
    Handles the complete extraction pipeline using Gemini Vision API.
    """
    
    def __init__(self):
        """Initialize the extractor with Gemini configuration."""
        self._configure_gemini()
        self.model = genai.GenerativeModel(settings.gemini.model)
        self.max_retries = settings.processing.max_retries
    
    def _configure_gemini(self) -> None:
        """Configure Gemini API with API key from settings."""
        api_key = settings.gemini.api_key
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Please set the GEMINI__API_KEY environment variable "
                "or add it to your .env file."
            )
        genai.configure(api_key=api_key)
    
    def extract(self, image_path: str) -> ExtractionResult:
        """
        Run the complete 3-pass extraction pipeline.
        
        Args:
            image_path: Path to the lab report image
            
        Returns:
            ExtractionResult with extracted data and metadata
        """
        extraction_metadata = {
            'image_path': image_path,
            'passes_completed': 0,
            'retry_attempts': 0,
            'preprocessing_applied': True,
            'standardization_applied': False
        }
        
        # Timing tracking
        total_start = time.time()
        preprocessing_time = 0.0
        pass1_time = 0.0
        pass2_time = 0.0
        pass3_time = 0.0
        
        try:
            # Preprocess image
            logger.info(f"Preprocessing image: {image_path}")
            preprocess_start = time.time()
            preprocessed_image = preprocess_image(image_path)
            preprocessing_time = time.time() - preprocess_start
            
            # Pass 1: Vision Extraction with retry
            pass1_start = time.time()
            raw_text, pass1_confidence = self._pass1_vision_extraction(preprocessed_image)
            pass1_time = time.time() - pass1_start
            
            if not raw_text:
                total_time = time.time() - total_start
                return ExtractionResult(
                    success=False,
                    data={'error': 'Vision extraction failed'},
                    confidence=0.0,
                    needs_review=True,
                    review_reason='Failed to extract text from image',
                    extraction_metadata=extraction_metadata,
                    preprocessing_time=preprocessing_time,
                    pass1_time=pass1_time,
                    total_time=total_time
                )
            extraction_metadata['passes_completed'] = 1
            extraction_metadata['pass1_text_length'] = len(raw_text)
            
            # Pass 2: Structure + Validate with retry
            pass2_start = time.time()
            structured_data, pass2_confidence, attempt = self._pass2_structure_validate(raw_text)
            pass2_time = time.time() - pass2_start
            extraction_metadata['passes_completed'] = 2
            extraction_metadata['retry_attempts'] = attempt
            
            if 'error' in structured_data:
                total_time = time.time() - total_start
                return ExtractionResult(
                    success=False,
                    data=structured_data,
                    confidence=pass2_confidence,
                    needs_review=True,
                    review_reason=structured_data.get('error', 'Structuring failed'),
                    extraction_metadata=extraction_metadata,
                    preprocessing_time=preprocessing_time,
                    pass1_time=pass1_time,
                    pass2_time=pass2_time,
                    total_time=total_time
                )
            
            # Pass 3: Standardize test names
            pass3_start = time.time()
            standardized_data = self._pass3_standardize(structured_data)
            pass3_time = time.time() - pass3_start
            extraction_metadata['passes_completed'] = 3
            extraction_metadata['standardization_applied'] = True
            
            # Calculate total time
            total_time = time.time() - total_start
            
            # Get final confidence and validation status
            final_confidence = standardized_data.get('metadata', {}).get('confidence_score', pass2_confidence)
            validation = get_validation_status(final_confidence)
            
            # Add timing to extraction metadata
            extraction_metadata['timing'] = {
                'preprocessing': round(preprocessing_time, 3),
                'pass1_vision': round(pass1_time, 3),
                'pass2_structure': round(pass2_time, 3),
                'pass3_standardize': round(pass3_time, 3),
                'total': round(total_time, 3)
            }
            standardized_data['extraction_metadata'] = extraction_metadata
            
            return ExtractionResult(
                success=True,
                data=standardized_data,
                confidence=final_confidence,
                needs_review=validation['needs_review'],
                review_reason=validation['recommendation'] if validation['needs_review'] else None,
                extraction_metadata=extraction_metadata,
                preprocessing_time=preprocessing_time,
                pass1_time=pass1_time,
                pass2_time=pass2_time,
                pass3_time=pass3_time,
                total_time=total_time
            )
            
        except Exception as e:
            total_time = time.time() - total_start
            logger.error(f"Extraction pipeline failed: {e}", exc_info=True)
            return ExtractionResult(
                success=False,
                data={'error': str(e)},
                confidence=0.0,
                needs_review=True,
                review_reason=f'Pipeline error: {str(e)}',
                extraction_metadata=extraction_metadata,
                preprocessing_time=preprocessing_time,
                pass1_time=pass1_time,
                pass2_time=pass2_time,
                pass3_time=pass3_time,
                total_time=total_time
            )
    
    def _pass1_vision_extraction(
        self,
        image: Image.Image
    ) -> Tuple[Optional[str], float]:
        """
        Pass 1: Extract raw text from image using Vision API.
        
        Uses multi-prompt retry strategy for robust extraction.
        
        Args:
            image: Preprocessed PIL Image
            
        Returns:
            Tuple of (extracted_text, confidence)
        """
        best_result = None
        best_score = 0.0
        
        for attempt, prompt in enumerate(VISION_PROMPTS):
            try:
                logger.info(f"Pass 1, attempt {attempt + 1}/{len(VISION_PROMPTS)}")
                
                response = self.model.generate_content([prompt, image])
                extracted_text = response.text
                
                if not extracted_text or len(extracted_text) < 50:
                    logger.warning(f"Attempt {attempt + 1}: Insufficient text extracted")
                    continue
                
                # Simple heuristic: longer extraction with numbers is better
                score = self._score_extraction(extracted_text)
                
                if score > best_score:
                    best_score = score
                    best_result = extracted_text
                
                # If we got good results, no need for more attempts
                if score > 0.8:
                    break
                
                # Rate limiting between attempts
                if attempt < len(VISION_PROMPTS) - 1:
                    time.sleep(1)
                    
            except Exception as e:
                logger.warning(f"Pass 1 attempt {attempt + 1} failed: {e}")
                continue
        
        return best_result, best_score
    
    def _score_extraction(self, text: str) -> float:
        """
        Score the quality of extracted text.
        
        Args:
            text: Extracted text
            
        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0
        
        # Length check (expect at least some content)
        if len(text) > 100:
            score += 0.2
        if len(text) > 500:
            score += 0.1
        
        # Contains numbers (lab values)
        import re
        numbers = re.findall(r'\d+\.?\d*', text)
        if len(numbers) > 5:
            score += 0.3
        
        # Contains common lab test indicators
        lab_keywords = [
            'hemoglobin', 'hb', 'wbc', 'rbc', 'glucose', 'creatinine',
            'cholesterol', 'platelet', 'mcv', 'hematocrit', 'normal',
            'high', 'low', 'reference', 'range', 'mg/dl', 'g/dl',
            '%', 'cells', 'count', 'result', 'test'
        ]
        text_lower = text.lower()
        matches = sum(1 for kw in lab_keywords if kw in text_lower)
        if matches > 3:
            score += 0.2
        if matches > 7:
            score += 0.2
        
        return min(score, 1.0)
    
    def _pass2_structure_validate(
        self,
        raw_text: str
    ) -> Tuple[Dict[str, Any], float, int]:
        """
        Pass 2: Convert raw text to structured JSON with validation.
        
        Uses retry logic based on confidence scores.
        
        Args:
            raw_text: Raw extracted text from Pass 1
            
        Returns:
            Tuple of (structured_data, confidence, attempts)
        """
        best_result = None
        best_confidence = 0.0
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Pass 2, attempt {attempt + 1}/{self.max_retries}")
                
                prompt = get_refinement_prompt(raw_text, attempt)
                response = self.model.generate_content(prompt)
                
                # Parse JSON response
                result_text = response.text.strip()
                result_text = self._clean_json_response(result_text)
                
                data = json.loads(result_text)
                
                # Extract confidence
                confidence = float(data.get('metadata', {}).get('confidence_score', 0.5))
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_result = data
                
                # Check if we should retry
                if not should_retry(confidence, attempt, self.max_retries):
                    return data, confidence, attempt + 1
                
                logger.info(f"Confidence {confidence:.2f} below threshold, retrying...")
                time.sleep(1)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Pass 2 attempt {attempt + 1}: JSON parse error: {e}")
                best_result = {
                    'error': 'JSON parsing failed',
                    'raw_output': result_text if 'result_text' in locals() else None
                }
                best_confidence = 0.2
                
            except Exception as e:
                logger.warning(f"Pass 2 attempt {attempt + 1} failed: {e}")
                continue
        
        if best_result is None:
            best_result = {'error': 'All structuring attempts failed'}
            best_confidence = 0.0
        
        return best_result, best_confidence, self.max_retries
    
    def _clean_json_response(self, text: str) -> str:
        """Remove markdown formatting from JSON response."""
        # Remove markdown code block markers
        if text.startswith('```json'):
            text = text[7:]
        elif text.startswith('```'):
            text = text[3:]
        
        if text.endswith('```'):
            text = text[:-3]
        
        return text.strip()
    
    def _pass3_standardize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pass 3: Standardize test names with LOINC codes.
        
        Args:
            data: Structured data from Pass 2
            
        Returns:
            Data with standardized test names
        """
        try:
            lab_results = data.get('lab_results', [])
            
            if not lab_results:
                logger.info("No lab results to standardize")
                return data
            
            # Apply standardization
            standardized_results = standardize_lab_results(lab_results)
            
            # Update data with standardized results
            data['lab_results'] = standardized_results
            
            # Add standardization summary to metadata
            total = len(standardized_results)
            standardized_count = sum(
                1 for r in standardized_results
                if r.get('standardization', {}).get('is_standardized', False)
            )
            
            if 'metadata' not in data:
                data['metadata'] = {}
            
            data['metadata']['standardization'] = {
                'total_tests': total,
                'standardized_count': standardized_count,
                'standardization_rate': standardized_count / total if total > 0 else 0
            }
            
            logger.info(f"Standardized {standardized_count}/{total} test names")
            return data
            
        except Exception as e:
            logger.error(f"Pass 3 standardization failed: {e}")
            # Return original data if standardization fails
            return data


# Convenience function for backward compatibility
def two_pass_extraction(image_path: str) -> str:
    """
    Legacy interface for extraction.
    
    Now uses the enhanced 3-pass pipeline.
    
    Args:
        image_path: Path to lab report image
        
    Returns:
        JSON string with extracted data
    """
    extractor = GeminiExtractor()
    result = extractor.extract(image_path)
    
    # Build output compatible with legacy format
    output = result.data
    
    # Ensure metadata exists with required fields
    if 'metadata' not in output:
        output['metadata'] = {}
    
    output['metadata']['confidence_score'] = result.confidence
    output['metadata']['needs_review'] = result.needs_review
    output['metadata']['review_reason'] = result.review_reason
    
    return json.dumps(output)


def extract_lab_report(image_path: str) -> ExtractionResult:
    """
    Extract lab report data using the full pipeline.
    
    Args:
        image_path: Path to lab report image
        
    Returns:
        ExtractionResult with full metadata
    """
    extractor = GeminiExtractor()
    return extractor.extract(image_path)
