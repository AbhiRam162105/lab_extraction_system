"""
Safe Summary Generator.

LLM-based summary that operates in READ-ONLY mode.
It can ONLY describe abnormalities in the provided data - never invent tests.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import google.generativeai as genai
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SafeSummary:
    """Safe summary of lab results."""
    report_type: str
    report_purpose: str
    abnormal_findings: List[str]
    manual_review_items: List[str]
    priority_level: str  # normal, attention, urgent
    clinical_notes: str


def generate_safe_summary(
    lab_results: List[Dict[str, Any]],
    patient_info: Optional[Dict[str, str]] = None
) -> SafeSummary:
    """
    Generate a safe summary from validated lab results.
    
    The LLM operates in READ-ONLY mode:
    - It can ONLY summarize data already in lab_results
    - It CANNOT add new tests or values
    - It CANNOT modify existing values
    
    Args:
        lab_results: List of normalized/filtered lab results
        patient_info: Optional patient information
        
    Returns:
        SafeSummary with clinical insights
    """
    if not lab_results:
        return SafeSummary(
            report_type="Unknown",
            report_purpose="Unable to determine - no results",
            abnormal_findings=[],
            manual_review_items=["No valid lab results extracted"],
            priority_level="attention",
            clinical_notes=""
        )
    
    try:
        # Configure Gemini
        api_key = settings.gemini.api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(settings.gemini.model)
        
        # Build prompt with strict READ-ONLY rules
        prompt = _build_safe_prompt(lab_results, patient_info)
        
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        # Parse response
        return _parse_summary_response(result_text, lab_results)
        
    except Exception as e:
        logger.error(f"Safe summary generation failed: {e}")
        return _generate_fallback_summary(lab_results)


def _build_safe_prompt(
    lab_results: List[Dict[str, Any]],
    patient_info: Optional[Dict[str, str]]
) -> str:
    """Build the READ-ONLY summary prompt."""
    
    # Format results for prompt
    results_text = json.dumps(lab_results, indent=2)
    
    patient_text = ""
    if patient_info:
        patient_text = f"\nPatient Info: {json.dumps(patient_info)}"
    
    return f"""You are a clinical laboratory assistant creating a summary of lab results.

CRITICAL RULES - YOU MUST FOLLOW:
1. You are in READ-ONLY mode
2. You can ONLY describe findings that exist in the provided data
3. You CANNOT add, invent, or calculate new test results
4. You CANNOT modify any values
5. If you mention a test, it MUST be in the data below

LAB RESULTS DATA:
{results_text}
{patient_text}

Generate a JSON summary with this structure:
{{
    "report_type": "Type of lab panel (e.g., Complete Blood Count, ABG)",
    "report_purpose": "Brief clinical purpose of these tests",
    "abnormal_findings": ["List ONLY tests marked with H or L flag, with clinical significance"],
    "manual_review_items": ["Any items needing human verification"],
    "priority_level": "normal|attention|urgent",
    "clinical_notes": "Brief clinical interpretation"
}}

PRIORITY RULES:
- "urgent": Any critical value (e.g., pH < 7.2, K+ > 6.5)
- "attention": Multiple abnormal values or borderline criticals
- "normal": All values in range or minor deviations

Remember: You can ONLY reference tests that exist in the data above.
Return ONLY valid JSON, no other text."""


def _parse_summary_response(
    response: str,
    lab_results: List[Dict[str, Any]]
) -> SafeSummary:
    """Parse LLM response into SafeSummary."""
    try:
        # Clean JSON
        if response.startswith('```json'):
            response = response[7:]
        elif response.startswith('```'):
            response = response[3:]
        if response.endswith('```'):
            response = response[:-3]
        
        data = json.loads(response.strip())
        
        # Validate abnormal findings reference actual tests
        valid_tests = {r.get('test_name', '').lower() for r in lab_results}
        valid_tests.update({r.get('original_name', '').lower() for r in lab_results})
        
        validated_abnormal = []
        for finding in data.get('abnormal_findings', []):
            # Check if finding references a real test
            finding_lower = finding.lower()
            if any(test in finding_lower for test in valid_tests if test):
                validated_abnormal.append(finding)
            else:
                logger.warning(f"Filtered hallucinated finding: {finding}")
        
        return SafeSummary(
            report_type=data.get('report_type', 'Unknown'),
            report_purpose=data.get('report_purpose', ''),
            abnormal_findings=validated_abnormal,
            manual_review_items=data.get('manual_review_items', []),
            priority_level=data.get('priority_level', 'normal'),
            clinical_notes=data.get('clinical_notes', '')
        )
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse summary JSON: {e}")
        return _generate_fallback_summary(lab_results)


def _generate_fallback_summary(lab_results: List[Dict[str, Any]]) -> SafeSummary:
    """Generate basic fallback summary without LLM."""
    
    # Detect report type from categories
    categories = set()
    for r in lab_results:
        cat = r.get('category', '')
        if cat:
            categories.add(cat)
    
    report_type = ", ".join(categories) if categories else "Laboratory Report"
    
    # Find abnormal values
    abnormal = []
    for r in lab_results:
        flag = r.get('flag', '')
        if flag in ['H', 'L']:
            name = r.get('test_name', r.get('original_name', 'Unknown'))
            value = r.get('value', '')
            abnormal.append(f"{name}: {value} ({flag})")
    
    # Determine priority
    priority = 'normal'
    if len(abnormal) > 3:
        priority = 'attention'
    
    return SafeSummary(
        report_type=report_type,
        report_purpose="Medical laboratory analysis",
        abnormal_findings=abnormal,
        manual_review_items=[],
        priority_level=priority,
        clinical_notes="Generated from validated extraction results"
    )
