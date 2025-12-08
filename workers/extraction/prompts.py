"""
Multi-Prompt Strategy for Lab Report Extraction.

Provides multiple prompt variants for retry strategy when initial extraction
fails or returns low confidence results.
"""

from typing import List, Dict, Any

# Primary extraction prompt - comprehensive and structured
PRIMARY_VISION_PROMPT = """
Extract ALL text from this medical lab report image.

FOCUS ON:
1. Patient information (name, age, gender, patient ID, date)
2. Lab test results in tabular format
3. Test names, values, units, and reference ranges
4. Section/category headers (e.g., "Hematology", "Biochemistry")

PRESERVE:
- Table structure and alignment
- Headers and column names
- Hierarchical organization

Return the raw text representation maintaining the document structure.
"""

# Fallback 1: Focus on structured data extraction
FALLBACK_VISION_PROMPT_1 = """
This is a medical laboratory report. Please extract:

1. **Patient Details**: Name, ID, Age, Gender, Date
2. **Test Results Table**: Each row should have:
   - Test Name
   - Result Value
   - Unit of measurement
   - Normal/Reference Range

Focus on accuracy. If text is unclear, note it as [unclear].
Return structured text, preserving table alignment.
"""

# Fallback 2: Simplified approach for difficult documents
FALLBACK_VISION_PROMPT_2 = """
Read this lab report image carefully.

List all the medical tests and their results you can see.
Format each as: TEST_NAME: VALUE UNIT (Reference: RANGE)

Also extract patient name and any dates visible.
If something is hard to read, still try your best estimate.
"""

# Fallback 3: Minimal extraction for very poor quality
FALLBACK_VISION_PROMPT_3 = """
Extract whatever text you can read from this medical document.
Focus on numbers and test names.
List each piece of information on a new line.
"""

# All vision prompts in order of preference
VISION_PROMPTS = [
    PRIMARY_VISION_PROMPT,
    FALLBACK_VISION_PROMPT_1,
    FALLBACK_VISION_PROMPT_2,
    FALLBACK_VISION_PROMPT_3,
]


def get_refinement_prompt(raw_text: str, attempt: int = 0) -> str:
    """
    Get the refinement prompt for Pass 2 (Structure + Validate).
    
    Args:
        raw_text: The raw extracted text from Pass 1
        attempt: Retry attempt number (0 = first try)
        
    Returns:
        Refinement prompt string
    """
    
    # Base prompt - used for all attempts
    base_prompt = f"""
You are an expert medical data auditor.
Your task is to convert the following RAW OCR TEXT from a lab report into a standardized, structured JSON format.

RAW TEXT:
{raw_text}

INSTRUCTIONS:
1.  **Extract Data**: Populate the JSON schema below.
2.  **Filter**: Ignore irrelevant text like footers, disclaimers, or advertisement text.
3.  **Standardize Tables**: 
    - For tables with multiple value columns (e.g. "Result 1", "Result 2" or different dates), create separate entries for each.
    - Append column headers to `test_name` to disambiguate (e.g. "Platelet Count - Sample A").
4.  **Handle Ambiguity**:
    - If a value looks physically impossible (e.g. Hb = 500 g/dL), set "needs_review": true
    - If text is garbled or uncertain, set "needs_review": true
    - Provide "review_reason" explaining any issues
5.  **Confidence Score**: 
    - Rate your overall confidence from 0.0 to 1.0
    - 0.9-1.0: Clear, unambiguous extraction
    - 0.7-0.9: Minor uncertainties but results are reliable
    - 0.5-0.7: Some values may need verification
    - Below 0.5: Significant issues with extraction

STRICT JSON SCHEMA:
{{
    "lab_results": [
        {{
            "test_name": "Test Name (as written in report)",
            "value": "Value (number or string exactly as shown)",
            "value_type": "numeric/text/mixed (numeric if number, text if qualitative like 'Neutrophilia')",
            "unit": "Unit (or null if not specified)",
            "reference_range": "Reference Range (or null)",
            "category": "Category/Section Name (e.g. Hematology, Liver Panel)",
            "flag": "H/L/N/null (High/Low/Normal/Not specified)",
            "test_method": "Test method if mentioned (e.g. Immunoturbidimetric, Flow Cytometry, Photometry, or null)"
        }}
    ],
    "patient_info": {{
        "name": "Patient Name or null",
        "patient_id": "ID or null",
        "age": "Age or null",
        "gender": "M/F/null",
        "collection_date": "Date or null",
        "report_date": "Date or null"
    }},
    "metadata": {{
        "needs_review": true/false,
        "review_reason": "Explanation if review needed, else null",
        "confidence_score": 0.0 to 1.0,
        "total_tests_extracted": number,
        "extraction_notes": "Any relevant notes about the extraction"
    }}
}}

Return ONLY the raw JSON string, no markdown formatting.
"""
    
    # Enhanced prompt for retry attempts
    if attempt > 0:
        additional_instructions = """

ADDITIONAL GUIDANCE (Retry Mode):
- Be more lenient with OCR errors - try to interpret garbled text
- If a test name is partially readable, make your best guess
- Missing units are acceptable - leave as null
- Focus on extracting as many valid test results as possible
- Lower confidence thresholds are acceptable for difficult documents
"""
        return base_prompt + additional_instructions
    
    return base_prompt


def get_standardization_prompt(test_name: str, known_tests: List[str]) -> str:
    """
    Get prompt for LLM-based test name standardization.
    
    Args:
        test_name: The original test name to standardize
        known_tests: List of known canonical test names for reference
        
    Returns:
        Standardization prompt string
    """
    
    # Limit the known tests list to avoid token limits
    sample_tests = known_tests[:50] if len(known_tests) > 50 else known_tests
    tests_str = "\n".join(f"- {t}" for t in sample_tests)
    
    return f"""
You are a medical terminology expert.

Given this lab test name from a report: "{test_name}"

What is the standard/canonical name for this test?

Here are some common standardized test names for reference:
{tests_str}

RULES:
1. If the test name matches or is clearly an alias of a known test, return the standard name
2. If it's a common test not in the list, return a reasonable standard name
3. If you cannot determine the standard name, return "UNKNOWN"
4. Return ONLY the standardized name, nothing else

Standard name:
"""


# Validation thresholds
CONFIDENCE_THRESHOLDS = {
    "auto_accept": 0.9,      # Automatically accept without review
    "acceptable": 0.7,       # Acceptable but may benefit from review
    "retry": 0.5,            # Trigger retry with fallback prompt
    "manual_review": 0.3,    # Flag for mandatory manual review
}


def should_retry(confidence: float, attempt: int, max_attempts: int = 3) -> bool:
    """
    Determine if extraction should be retried based on confidence.
    
    Args:
        confidence: Current extraction confidence score
        attempt: Current attempt number (0-indexed)
        max_attempts: Maximum number of retry attempts
        
    Returns:
        True if should retry, False otherwise
    """
    if attempt >= max_attempts:
        return False
    
    return confidence < CONFIDENCE_THRESHOLDS["acceptable"]


def get_validation_status(confidence: float) -> Dict[str, Any]:
    """
    Get validation status and recommendations based on confidence.
    
    Args:
        confidence: Extraction confidence score
        
    Returns:
        Dictionary with status and recommendations
    """
    if confidence >= CONFIDENCE_THRESHOLDS["auto_accept"]:
        return {
            "status": "accepted",
            "needs_review": False,
            "recommendation": "High confidence extraction, safe to use"
        }
    elif confidence >= CONFIDENCE_THRESHOLDS["acceptable"]:
        return {
            "status": "acceptable",
            "needs_review": False,
            "recommendation": "Good extraction quality, review recommended for critical use"
        }
    elif confidence >= CONFIDENCE_THRESHOLDS["retry"]:
        return {
            "status": "low_confidence",
            "needs_review": True,
            "recommendation": "Some values may be incorrect, manual review suggested"
        }
    else:
        return {
            "status": "unreliable",
            "needs_review": True,
            "recommendation": "Extraction quality is poor, manual verification required"
        }
