"""
Single Vision Extractor - Production Pipeline.

ONE Gemini Vision call → Deterministic Normalizer → Safety Validation

This replaces the multi-pass three-tier approach with a clean,
hallucination-free single-pass extraction.
"""

import logging
import time
import json
import uuid
from collections import deque
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from PIL import Image

import google.generativeai as genai
from backend.core.config import get_settings
from workers.extraction.preprocessing import preprocess_image
from workers.extraction.ocr_quality import evaluate_ocr_quality
from workers.extraction.strict_normalizer import StrictNormalizer, NormalizerResult
from workers.extraction.safe_summary import generate_safe_summary
from workers.extraction.panel_validator import validate_panel_completeness
from workers.extraction.quality_verifier import verify_extraction_quality
from workers.extraction.rate_limiter import get_rate_limiter
from workers.extraction.cache_manager import CacheManager, CacheConfig

logger = logging.getLogger(__name__)
settings = get_settings()


# Patient memory - stores last 20 documents for patient matching
_patient_memory: deque = deque(maxlen=20)


@dataclass
class PatientMemoryEntry:
    """Entry in patient memory for matching."""
    document_id: str
    patient_name: Optional[str]
    patient_id: str  # Always has a value (generated if not found)
    age: Optional[str]
    gender: Optional[str]
    timestamp: float


@dataclass
class VisionExtractionResult:
    """Result from single-vision extraction pipeline."""
    success: bool
    data: Dict[str, Any]
    confidence: float
    extraction_time: float
    normalization_time: float
    validation_time: float
    total_time: float
    issues: List[str]
    summary: Optional[Dict[str, Any]] = None


class SingleVisionExtractor:
    """
    Production-grade single-pass vision extractor.
    
    Pipeline:
    1. Image Quality Check
    2. Single Gemini Vision Call (extract everything)
    3. Deterministic Normalization (YAML + Levenshtein)
    4. Safety Validation (reference range, physiological checks)
    5. Patient Memory Match (detect same patient across docs)
    6. Read-only Summary
    """
    
    def __init__(self):
        self._configure_gemini()
        self.model = genai.GenerativeModel(settings.gemini.model)
        self.normalizer = StrictNormalizer()
        self.rate_limiter = get_rate_limiter()
        
        # Initialize cache with Redis if available
        try:
            import redis
            redis_client = redis.Redis.from_url(settings.redis.url)
            redis_client.ping()  # Test connection
            self.cache = CacheManager(redis_client=redis_client)
            logger.info("Cache initialized with Redis")
        except Exception as e:
            logger.warning(f"Redis not available, using disk cache only: {e}")
            self.cache = CacheManager(redis_client=None)
    
    def _configure_gemini(self) -> None:
        api_key = settings.gemini.api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
    
    def extract(self, image_path: str) -> VisionExtractionResult:
        """Run the complete single-vision extraction pipeline."""
        issues = []
        total_start = time.time()
        
        try:
            # Check cache first
            image_hash = self.cache.get_image_hash(image_path)
            cached_result = self.cache.get_cached_result(image_hash)
            if cached_result:
                logger.info(f"[CACHE HIT] Returning cached result for {image_hash[:8]}")
                cached_data = cached_result.get('data', {})
                return VisionExtractionResult(
                    success=cached_data.get('success', True),
                    data=cached_data,
                    confidence=cached_data.get('confidence', 0.9),
                    extraction_time=0.0,
                    normalization_time=0.0,
                    validation_time=0.0,
                    total_time=0.01,  # Almost instant
                    issues=cached_data.get('issues', []),
                    summary=cached_data.get('summary')
                )
            
            # Load and preprocess image
            logger.info(f"[Step 1] Loading image: {image_path}")
            image = preprocess_image(image_path)
            
            # Quality check
            quality = evaluate_ocr_quality(image)
            if not quality.is_acceptable:
                logger.warning(f"Quality check failed: {quality.recommendation}")
                return VisionExtractionResult(
                    success=False,
                    data={'error': 'Image quality too poor', 'issues': quality.issues},
                    confidence=0.0,
                    extraction_time=0.0,
                    normalization_time=0.0,
                    validation_time=0.0,
                    total_time=time.time() - total_start,
                    issues=quality.issues
                )
            
            # STEP 2a: Verify this is a medical report (quick check)
            logger.info("[Step 2a] Verifying document is a medical report")
            is_medical, doc_type = self._verify_medical_report(image)
            
            if not is_medical:
                logger.warning(f"Document is not a medical report: {doc_type}")
                return VisionExtractionResult(
                    success=False,
                    data={'error': f'Not a medical lab report: {doc_type}', 'document_type': doc_type},
                    confidence=0.0,
                    extraction_time=0.0,
                    normalization_time=0.0,
                    validation_time=0.0,
                    total_time=time.time() - total_start,
                    issues=[f'Document appears to be: {doc_type}, not a medical lab report']
                )
            
            # STEP 2b: Single Vision Extraction (API Call 2)
            logger.info("[Step 2b] Running Gemini Vision extraction")
            extraction_start = time.time()
            
            raw_results = self._vision_extract(image)
            extraction_time = time.time() - extraction_start
            
            if not raw_results:
                logger.warning("Vision extraction returned no results")
                return VisionExtractionResult(
                    success=False,
                    data={'error': 'No data extracted from image'},
                    confidence=0.0,
                    extraction_time=extraction_time,
                    normalization_time=0.0,
                    validation_time=0.0,
                    total_time=time.time() - total_start,
                    issues=['Vision extraction returned empty results']
                )
            
            patient_info = raw_results.get('patient_info', {})
            
            # Flatten sections into lab_results with heading context
            raw_tests = self._flatten_sections(raw_results)
            
            logger.info(f"[Step 2] Extracted {len(raw_tests)} raw tests from sections")
            
            # STEP 3: Deterministic Normalization
            logger.info("[Step 3] Running deterministic normalization")
            norm_start = time.time()
            
            norm_result = self.normalizer.normalize(raw_tests)
            normalization_time = time.time() - norm_start
            
            logger.info(f"[Step 3] Normalized {len(norm_result.results)} tests, {len(norm_result.unknown_tests)} unknown")
            issues.extend(norm_result.issues)
            
            # STEP 4: LLM Validation (API Call 2)
            logger.info("[Step 4] Running LLM validation")
            validation_start = time.time()
            
            validated_results = self._validate_results(norm_result.results)
            
            # Convert to output format before LLM validation
            lab_results = [self._to_output_dict(r) for r in validated_results]
            
            # Run LLM validation pass (second API call)
            lab_results = self._llm_validate(lab_results, image)
            
            validation_time = time.time() - validation_start
            
            # STEP 5: Panel Completeness Validation
            logger.info("[Step 5] Running panel completeness validation")
            panel_validation = validate_panel_completeness(lab_results)
            
            if panel_validation.get("needs_review"):
                logger.warning(f"Panel validation: Missing tests detected - {panel_validation.get('review_reasons')}")
                issues.append(f"Missing panel tests: {', '.join(panel_validation.get('review_reasons', []))}")
            
            # Add validation metadata to results
            for lab_result in lab_results:
                if panel_validation.get("needs_review") and not lab_result.get("needs_review"):
                    # Check if this test's panel has missing items
                    for missing_panel in panel_validation.get("missing_panels", []):
                        if missing_panel.get("severity") in ("warning", "critical"):
                            lab_result["panel_incomplete"] = True
            
            # STEP 6: Patient Memory - match to existing patient or generate ID
            logger.info("[Step 6] Processing patient identity")
            patient_info = self._process_patient_identity(patient_info, image_path)
            
            # STEP 7: Safe Summary
            logger.info("[Step 7] Generating summary")
            summary = generate_safe_summary(lab_results, patient_info)
            
            # STEP 8: Quality Verification
            logger.info("[Step 8] Running quality verification")
            quality_report = verify_extraction_quality(lab_results)
            
            if quality_report.get("warnings"):
                for warning in quality_report["warnings"][:3]:
                    issues.append(f"Quality: {warning}")
                logger.warning(f"Quality warnings: {quality_report['warnings']}")
            
            if quality_report.get("errors"):
                for error in quality_report["errors"][:3]:
                    issues.append(f"Quality Error: {error}")
                logger.error(f"Quality errors: {quality_report['errors']}")
            
            # Calculate confidence
            confidence = self._calculate_confidence(norm_result, validated_results)
            
            # Adjust confidence based on quality score
            quality_score = quality_report.get("quality_score", 1.0)
            adjusted_confidence = confidence * (0.5 + 0.5 * quality_score)
            
            total_time = time.time() - total_start
            
            logger.info(
                f"Extraction complete: {len(lab_results)} tests, "
                f"confidence={adjusted_confidence:.2f}, quality={quality_score:.2f}, time={total_time:.1f}s"
            )
            
            result = VisionExtractionResult(
                success=True,
                data={
                    'lab_results': lab_results,
                    'patient_info': patient_info,
                    'metadata': {
                        'total_extracted': len(lab_results),
                        'unknown_tests': norm_result.unknown_tests,
                        'confidence_score': adjusted_confidence,
                        'quality_score': quality_score,
                        'quality_checks': quality_report.get("checks", []),
                        'quality_warnings': quality_report.get("warnings", [])
                    }
                },
                confidence=confidence,
                extraction_time=extraction_time,
                normalization_time=normalization_time,
                validation_time=validation_time,
                total_time=total_time,
                issues=issues,
                summary=asdict(summary)
            )
            
            # Cache successful result
            try:
                cache_data = {
                    'success': True,
                    'data': result.data,
                    'confidence': result.confidence,
                    'summary': result.summary,
                    'issues': result.issues
                }
                self.cache.cache_result(image_hash, cache_data, metadata={
                    'extracted_tests': len(lab_results),
                    'quality_score': quality_score
                })
                logger.info(f"[CACHE] Saved result for {image_hash[:8]}")
            except Exception as cache_err:
                logger.warning(f"Failed to cache result: {cache_err}")
            
            return result
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}", exc_info=True)
            return VisionExtractionResult(
                success=False,
                data={'error': str(e)},
                confidence=0.0,
                extraction_time=0.0,
                normalization_time=0.0,
                validation_time=0.0,
                total_time=time.time() - total_start,
                issues=[str(e)]
            )
    
    def _verify_medical_report(self, image: Image.Image) -> tuple:
        """
        Quick verification that the document is a medical lab report.
        
        Returns:
            (is_medical_report: bool, document_type: str)
        """
        verification_prompt = """Look at this document and answer with ONLY a JSON response:

{
  "is_medical_lab_report": true/false,
  "document_type": "brief description of what this document is",
  "confidence": 0.0 to 1.0
}

A medical lab report typically contains:
- Patient information (name, ID, date)
- Laboratory test names (CBC, hemoglobin, glucose, etc.)
- Test values with units and reference ranges
- Hospital/lab name

If this is NOT a medical lab report (e.g., invoice, prescription, X-ray, random image), set is_medical_lab_report to false.

Return ONLY the JSON, no other text."""

        try:
            # Rate limiting
            self.rate_limiter.acquire()
            
            response = self.model.generate_content([verification_prompt, image])
            result_text = self._clean_json(response.text.strip())
            
            self.rate_limiter.report_success()
            
            result = json.loads(result_text)
            
            is_medical = result.get('is_medical_lab_report', False)
            doc_type = result.get('document_type', 'Unknown document')
            confidence = result.get('confidence', 0.5)
            # if not extracted assume 50-50
            
            logger.info(f"Document verification: is_medical={is_medical}, type='{doc_type}', confidence={confidence}")
            
            # Only accept if confident it's a medical report
            if is_medical and confidence >= 0.7:
                return True, doc_type
            else:
                return False, doc_type
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse verification response: {e}")
            # If we can't parse, assume it might be a medical report (fail open)
            return True, "Verification inconclusive"
        except Exception as e:
            if '429' in str(e) or 'rate' in str(e).lower():
                self.rate_limiter.report_rate_limit_error()
            logger.warning(f"Document verification failed: {e}")
            # Fail open - attempt extraction
            return True, "Verification failed"
    
    def _vision_extract(self, image: Image.Image) -> Dict[str, Any]:
        """Single Gemini Vision call to extract everything."""
        prompt = self._get_vision_prompt()
        
        try:
            # Rate limiting - wait if needed
            self.rate_limiter.acquire()
            
            response = self.model.generate_content([prompt, image])
            result_text = response.text.strip()
            
            # Report success for adaptive rate limiting
            self.rate_limiter.report_success()
            
            # Clean JSON
            result_text = self._clean_json(result_text)
            # Removes markdown code block formatting that Gemini often adds
    
            return json.loads(result_text)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Raw response: {result_text[:500]}")
            return {}
        except Exception as e:
            # Check if rate limited
            if '429' in str(e) or 'rate' in str(e).lower():
                self.rate_limiter.report_rate_limit_error()
            logger.error(f"Vision extraction error: {e}")
            return {}
    
    def _get_vision_prompt(self) -> str:
        """Aggressive extraction prompt that explicitly lists mandatory tests."""
        return """You are a medical lab report extractor. You MUST extract EVERY test visible in the document.

# MANDATORY TESTS - YOU MUST LOOK FOR AND EXTRACT ALL OF THESE:

## 1. CBC ABSOLUTE COUNTS (CRITICAL - DO NOT MISS THESE)
Look for a section called "Absolute Differential Count" or "Absolute Count" or "(abs)":

MANDATORY - Extract these if visible:
- "Absolute Neutrophils Count" or "Neutrophils (abs)" or "ANC" → value like 6072, 8976
- "Absolute Lymphocytes Count" or "Lymphocytes (abs)" or "ALC" → value like 2208, 3264
- "Absolute Monocytes Count" or "Monocytes (abs)" or "AMC" → value like 552, 816  
- "Absolute Eosinophils Count" or "Eosinophils (abs)" or "AEC" → value like 368, 544
- "Absolute Basophils Count" or "Basophils (abs)" or "ABC" → value like 9, 36

These have units like "/cumm", "/uL", "cells/cumm" and reference ranges like "2000-7000".

## 2. DIFFERENTIAL PERCENTAGES (%)
- Neutrophils % (like 66%, 72%)
- Lymphocytes % (like 24%, 20%)
- Monocytes % (like 6%, 8%)
- Eosinophils % (like 4%, 2%)
- Basophils % (like 0%, 1%)

## 3. COAGULATION PANEL - ALL TOGETHER
If you see INR, you MUST also look for PT and APTT nearby:
- "PROTHROMBIN TIME" or "PT" → value like 11.1, 12.5 seconds
- "INR" → value like 0.92, 1.02
- "APTT" or "Activated Partial Thromboplastin Time" → value like 33.8, 28.5 seconds

## 4. PERIPHERAL SMEAR / MORPHOLOGY
Look for sections called "Peripheral Smear" or "Blood Smear":
- "RBC MORPHOLOGY" or "RBC's" → text like "Normocytic Normochromic", "Mild Anisocytosis"
- "WBC MORPHOLOGY" or "WBC's" → text like "Neutrophilia", "No immature cells"  
- "PLATELET MORPHOLOGY" or "Platelets" → text like "Adequate", "Normal"
- "HEMOPARASITES" → text like "Nil", "Not seen"
- "ABNORMAL CELLS" → text like "Nil", "None"

## 5. RATIO TESTS (NOT percentages)
- "NEUTROPHIL LYMPHOCYTE RATIO" or "NLR" → value like 15.9, 3.2 (NO unit, it's a ratio)
- "PLATELET LYMPHOCYTE RATIO" or "PLR" → value like 150, 200

## 6. ADVANCED CBC
- "RDW" or "Red Cell Distribution Width" → value like 16.5%
- "MPV" or "Mean Platelet Volume" → value like 9.4 fL
- "IPF" or "Immature Platelet Fraction" → value like 2.9%

---

# EXTRACTION RULES:

1. **Scan the ENTIRE document** - do not stop early
2. **Sub-sections have tests** - "Absolute Differential Count:" is a heading, the tests below it must be extracted
3. **Morphology values are TEXT** - capture descriptive text, not numbers

# OUTPUT FORMAT:

{
  "patient_info": {
    "name": "patient name or null",
    "patient_id": "UHID/ID or null",
    "age": "age or null",
    "gender": "M/F or null",
    "collection_date": "date or null"
  },
  "sections": [
    {
      "heading": "COMPLETE BLOOD COUNT",
      "tests": [
        {"test_name": "HEMOGLOBIN", "value": "14.5", "unit": "g/dL", "reference_range": "13-17", "flag": ""},
        {"test_name": "NEUTROPHILS", "value": "66", "unit": "%", "reference_range": "50-70", "flag": ""},
        {"test_name": "ABSOLUTE NEUTROPHILS COUNT", "value": "6072", "unit": "/cumm", "reference_range": "2000-7000", "flag": ""},
        {"test_name": "ABSOLUTE LYMPHOCYTES COUNT", "value": "2208", "unit": "/cumm", "reference_range": "1000-3000", "flag": ""},
        {"test_name": "ABSOLUTE MONOCYTES COUNT", "value": "552", "unit": "/cumm", "reference_range": "200-1000", "flag": ""},
        {"test_name": "ABSOLUTE EOSINOPHILS COUNT", "value": "368", "unit": "/cumm", "reference_range": "20-500", "flag": ""},
        {"test_name": "RDW", "value": "16.5", "unit": "%", "reference_range": "11.6-14.6", "flag": "H"}
      ]
    },
    {
      "heading": "COAGULATION",
      "tests": [
        {"test_name": "PROTHROMBIN TIME", "value": "11.1", "unit": "Seconds", "reference_range": "10.8-13.3", "flag": ""},
        {"test_name": "INR", "value": "0.92", "unit": "", "reference_range": "0.9-1.1", "flag": ""},
        {"test_name": "APTT", "value": "33.8", "unit": "Seconds", "reference_range": "26.8-36.1", "flag": ""}
      ]
    },
    {
      "heading": "PERIPHERAL SMEAR",
      "tests": [
        {"test_name": "RBC MORPHOLOGY", "value": "Normocytic Normochromic", "unit": "", "value_type": "text"},
        {"test_name": "WBC MORPHOLOGY", "value": "No immature cells", "unit": "", "value_type": "text"},
        {"test_name": "PLATELET MORPHOLOGY", "value": "Adequate", "unit": "", "value_type": "text"}
      ]
    }
  ],
  "comments": []
}

# CHECKLIST BEFORE RETURNING:
- Did I extract absolute counts (values like 6072, 8976, /cumm)?
- Did I extract PT AND APTT if INR is present?
- Did I extract morphology descriptions as text?
- Did I extract RDW, MPV if visible?

Return ONLY valid JSON, no markdown."""
    
    def _flatten_sections(self, raw_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Flatten section-based extraction into flat lab_results.
        
        Uses section heading to contextualize test names:
        - "ERYTHROPOIETIN" under "ERYTHROPOIETIN, SERUM (1160-SRL)" 
          → section_heading = "ERYTHROPOIETIN, SERUM"
        """
        lab_results = []
        
        # Handle old format (direct lab_results array)
        if 'lab_results' in raw_results:
            return raw_results['lab_results']
        
        # Handle new sections format
        sections = raw_results.get('sections', [])
        
        for section in sections:
            heading = section.get('heading', '')
            tests = section.get('tests', [])
            
            # Clean heading - extract meaningful part
            clean_heading = self._extract_heading_context(heading)
            
            for test in tests:
                # Add section context to test
                test['section_heading'] = clean_heading
                
                # If test name is generic but heading gives context, enhance the name
                test_name = test.get('test_name', '')
                if test_name and clean_heading:
                    test['contextualized_name'] = f"{test_name} ({clean_heading})"
                
                lab_results.append(test)
        
        return lab_results
    
    def _extract_heading_context(self, heading: str) -> str:
        """Extract meaningful context from section heading."""
        if not heading:
            return ''
        
        # Remove lab codes like "(1160-SRL)", "(1568HD-SRL)"
        import re
        cleaned = re.sub(r'\s*\([^)]*-SRL\)', '', heading)
        cleaned = re.sub(r'\s*\([^)]*SRL[^)]*\)', '', cleaned)
        
        # Remove excessive whitespace
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    def _llm_validate(self, results: List[Dict[str, Any]], image) -> List[Dict[str, Any]]:
        """
        LLM Validation Pass (API Call 2).
        
        Light validation to flag suspicious values or extraction errors.
        """
        if not results:
            return results
        
        # Build summary for validation
        test_summary = []
        for r in results[:20]:  # Limit to first 20 tests
            test_summary.append({
                'name': r.get('test_name', r.get('original_name', 'Unknown')),
                'value': r.get('value', ''),
                'unit': r.get('unit', ''),
                'flag': r.get('flag', '')
            })
        
        validation_prompt = f"""Review these extracted lab test results for any obvious errors or suspicious values:

{json.dumps(test_summary, indent=2)}

For each issue found, respond with JSON:
{{
  "issues": [
    {{"test_name": "...", "issue": "description of problem", "severity": "low/medium/high"}}
  ]
}}

Common issues to check:
1. Values that seem impossible (e.g., Hemoglobin = 500)
2. Test names that look like comments or headings (not actual tests)
3. Missing required fields
4. Mismatched units and values

If no issues found, respond: {{"issues": []}}
Return ONLY valid JSON."""

        try:
            # Rate limiting for second API call
            self.rate_limiter.acquire()
            
            response = self.model.generate_content(validation_prompt)
            result_text = self._clean_json(response.text.strip())
            validation_result = json.loads(result_text)
            
            self.rate_limiter.report_success()
            
            issues = validation_result.get('issues', [])
            
            # Apply flags to results
            issue_map = {i.get('test_name', '').lower(): i for i in issues}
            
            for r in results:
                test_name = r.get('test_name', r.get('original_name', '')).lower()
                if test_name in issue_map:
                    issue = issue_map[test_name]
                    r['needs_review'] = True
                    r['review_reason'] = issue.get('issue', 'Flagged by validation')
                    r['validation_severity'] = issue.get('severity', 'medium')
            
            return results
            
        except Exception as e:
            if '429' in str(e) or 'rate' in str(e).lower():
                self.rate_limiter.report_rate_limit_error()
            logger.warning(f"LLM validation failed: {e}")
            return results
    
    def _clean_json(self, text: str) -> str:
        """Remove markdown formatting from JSON response."""
        if text.startswith('```json'):
            text = text[7:]
        elif text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        return text.strip()
    
    def _validate_results(self, results: List) -> List:
        """Apply safety validation to normalized results."""
        validated = []
        seen_tests = set()
        
        for r in results:
            # Skip duplicates
            test_key = r.test_name.lower() if r.test_name != "UNKNOWN" else r.original_name.lower()
            if test_key in seen_tests:
                continue
            seen_tests.add(test_key)
            
            # Physiological sanity check (only for mapped tests)
            if r.test_name != "UNKNOWN" and r.value_numeric is not None:
                if not self._is_physiologically_valid(r):
                    r.needs_review = True
                    if r.review_reason:
                        r.review_reason += "; physiological_outlier"
                    else:
                        r.review_reason = "physiological_outlier"
            
            validated.append(r)
        
        return validated
    
    def _is_physiologically_valid(self, result) -> bool:
        """Check if value is physiologically plausible."""
        if result.value_numeric is None:
            return True
        
        val = result.value_numeric
        name = result.test_name.lower()
        
        # Wide physiological limits (for outlier detection only)
        limits = {
            'hemoglobin': (3, 25),
            'rbc': (1, 10),
            'wbc': (0.5, 100),
            'platelet': (10, 2000),
            'sodium': (100, 180),
            'potassium': (1.5, 10),
            'glucose': (20, 1000),
            'creatinine': (0.1, 30),
        }
        
        for test_pattern, (min_val, max_val) in limits.items():
            if test_pattern in name:
                if val < min_val or val > max_val:
                    return False
                return True
        
        return True
    
    def _to_output_dict(self, result) -> Dict[str, Any]:
        """Convert normalized result to output dict."""
        return {
            'test_name': result.test_name,
            'original_name': result.original_name,
            'value': result.value,
            'unit': result.unit,
            'reference_range': result.reference_range,
            'flag': result.flag,
            'loinc_code': result.loinc_code,
            'category': result.category,
            'needs_review': result.needs_review,
            'review_reason': result.review_reason
        }
    
    def _calculate_confidence(self, norm_result, validated: List) -> float:
        """Calculate confidence score."""
        if not validated:
            return 0.0
        
        score = 0.7  # Base score for successful extraction
        
        # Bonus for high mapping success rate
        total = len(norm_result.results)
        mapped = sum(1 for r in validated if r.test_name != "UNKNOWN")
        if total > 0:
            mapping_rate = mapped / total
            score += mapping_rate * 0.2
        
        # Penalty for needing review
        review_count = sum(1 for r in validated if r.needs_review)
        review_rate = review_count / len(validated) if validated else 0
        score -= review_rate * 0.1
        
        return min(1.0, max(0.0, score))
    
    def _process_patient_identity(
        self, 
        patient_info: Dict[str, Any],
        document_id: str
    ) -> Dict[str, Any]:
        """
        Process patient identity with memory matching.
        
        1. If patient_id exists, use it
        2. If patient_name matches a recent document, reuse that patient_id
        3. Otherwise, generate a new patient_id
        """
        global _patient_memory
        
        patient_name = patient_info.get('name')
        patient_id = patient_info.get('patient_id')
        age = patient_info.get('age')
        gender = patient_info.get('gender')
        
        # If we have a patient_id from the document, use it
        if patient_id:
            # Store in memory
            self._add_to_patient_memory(document_id, patient_name, patient_id, age, gender)
            return patient_info
        
        # Try to match with recent documents
        matched_id = self._match_patient_from_memory(patient_name, age, gender)
        
        if matched_id:
            logger.info(f"Matched patient to existing ID: {matched_id}")
            patient_info['patient_id'] = matched_id
            patient_info['matched_from_memory'] = True
        else:
            # Generate new patient ID
            new_id = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
            logger.info(f"Generated new patient ID: {new_id}")
            patient_info['patient_id'] = new_id
            patient_info['auto_generated_id'] = True
        
        # Store in memory for future matching
        self._add_to_patient_memory(
            document_id, 
            patient_name, 
            patient_info['patient_id'], 
            age, 
            gender
        )
        
        return patient_info
    
    def _add_to_patient_memory(
        self,
        document_id: str,
        patient_name: Optional[str],
        patient_id: str,
        age: Optional[str],
        gender: Optional[str]
    ) -> None:
        """Add patient entry to memory."""
        global _patient_memory
        
        entry = PatientMemoryEntry(
            document_id=document_id,
            patient_name=patient_name,
            patient_id=patient_id,
            age=age,
            gender=gender,
            timestamp=time.time()
        )
        _patient_memory.append(entry)
    
    def _match_patient_from_memory(
        self,
        patient_name: Optional[str],
        age: Optional[str],
        gender: Optional[str]
    ) -> Optional[str]:
        """
        Try to match patient with recent documents.
        
        Matching logic:
        1. If patient_name matches exactly, return that patient_id
        2. If patient_name is similar AND age/gender match, return that patient_id
        """
        global _patient_memory
        
        if not patient_name:
            return None
        
        name_lower = patient_name.lower().strip()
        
        for entry in reversed(_patient_memory):  # Check most recent first
            if not entry.patient_name:
                continue
            
            entry_name = entry.patient_name.lower().strip()
            
            # Exact name match
            if name_lower == entry_name:
                return entry.patient_id
            
            # Similar name with same demographics
            if self._names_similar(name_lower, entry_name):
                # Check if age/gender also match
                age_match = (not age or not entry.age or 
                            age.split()[0] == entry.age.split()[0] if age and entry.age else True)
                gender_match = (not gender or not entry.gender or 
                               gender[0].upper() == entry.gender[0].upper() if gender and entry.gender else True)
                
                if age_match and gender_match:
                    return entry.patient_id
        
        return None
    
    def _names_similar(self, name1: str, name2: str) -> bool:
        """Check if two names are similar (simple check)."""
        # Split into words
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        # If they share at least 2 words, consider similar
        common = words1 & words2
        return len(common) >= 2 or (len(common) >= 1 and max(len(words1), len(words2)) <= 2)


def extract_single_vision(image_path: str) -> Dict[str, Any]:
    """Convenience function for single-vision extraction."""
    extractor = SingleVisionExtractor()
    result = extractor.extract(image_path)
    return asdict(result)
