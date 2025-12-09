"""
Test Whitelist and Validation Module.

Provides validation functions to detect and filter hallucinated data
from the extraction pipeline.
"""

from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)


# Common lab tests whitelist (Apollo Hospital / Indian lab reports)
VALID_TEST_NAMES = {
    # Blood Gas Analysis
    "ph", "pco2", "po2", "hco3", "spo2", "so2", "fio2", 
    "base excess", "be", "beb", "beecf",
    
    # Electrolytes
    "sodium", "na", "na+", "potassium", "k", "k+", 
    "chloride", "cl", "cl-", "calcium", "ca", "ca++", "ca2+",
    "magnesium", "mg", "phosphorus", "phosphate",
    
    # Metabolites
    "glucose", "glu", "lactate", "lac", "clac", "creatinine",
    "urea", "bun", "uric acid", "bilirubin",
    
    # Hematology - CBC
    "hemoglobin", "hb", "hgb", "hematocrit", "hct", "pcv",
    "rbc", "wbc", "platelet", "platelets", "plt",
    "mcv", "mch", "mchc", "rdw", "mpv", "pdw",
    
    # WBC Differential
    "neutrophils", "lymphocytes", "monocytes", "eosinophils", "basophils",
    "neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil",
    
    # Liver Function
    "alt", "sgpt", "ast", "sgot", "alp", "ggt", "ggtp",
    "albumin", "globulin", "total protein", "a/g ratio",
    
    # Kidney Function
    "egfr", "gfr", "creatinine clearance",
    
    # Lipid Panel
    "cholesterol", "triglycerides", "hdl", "ldl", "vldl",
    
    # Thyroid
    "tsh", "t3", "t4", "ft3", "ft4",
    
    # Diabetes
    "hba1c", "fasting glucose", "pp glucose", "random glucose",
    
    # Coagulation
    "pt", "inr", "aptt", "ptt", "fibrinogen",
    
    # Iron Studies
    "iron", "tibc", "ferritin", "transferrin",
    
    # Cardiac Markers
    "troponin", "ck-mb", "bnp", "nt-probnp",
    
    # Oxygen/CO
    "fco2hb", "fhhb", "fo2hb", "fmethb", "fcohb",
    "ctco2", "cthb", "fshunt",
}

# Tests that are CALCULATED and often hallucinated
CALCULATED_TESTS = {
    "anion gap", "a-a gradient", "alveolar-arterial gradient",
    "corrected calcium", "ldl calculated", "non-hdl cholesterol",
    "osmolality calculated", "osmolar gap"
}

# Physiological range validation
VALUE_RANGES = {
    "ph": (6.8, 8.0),
    "pco2": (10, 100),  # mmHg
    "po2": (20, 700),   # mmHg
    "hco3": (5, 50),    # mEq/L
    "hemoglobin": (3, 25),  # g/dL
    "hb": (3, 25),
    "hematocrit": (10, 70),  # %
    "sodium": (100, 180),    # mEq/L
    "na": (100, 180),
    "potassium": (1.5, 10),  # mEq/L
    "k": (1.5, 10),
    "glucose": (20, 1000),   # mg/dL
    "creatinine": (0.1, 30), # mg/dL
    "platelet": (10, 1500),  # x10^3/uL
    "wbc": (0.5, 100),       # x10^3/uL
}


@dataclass
class ValidationResult:
    """Result of validation check."""
    is_valid: bool
    issues: List[str]
    hallucinated_tests: List[str]
    suspicious_values: List[str]
    safe_matches: int


def normalize_test_name(name: str) -> str:
    """Normalize test name for comparison."""
    if not name:
        return ""
    # Lowercase, remove special chars, collapse spaces
    normalized = re.sub(r'[^a-z0-9\s+\-]', '', name.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def is_test_in_whitelist(test_name: str) -> bool:
    """Check if test name is in the whitelist."""
    normalized = normalize_test_name(test_name)
    
    # Direct match
    if normalized in VALID_TEST_NAMES:
        return True
    
    # Check if any whitelist term is contained in the test name
    for valid_test in VALID_TEST_NAMES:
        if valid_test in normalized or normalized in valid_test:
            return True
    
    return False


def is_calculated_test(test_name: str) -> bool:
    """Check if test is a calculated/derived value."""
    normalized = normalize_test_name(test_name)
    
    for calc_test in CALCULATED_TESTS:
        if calc_test in normalized:
            return True
    
    return False


def validate_value_range(test_name: str, value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate if a test value is within physiological range.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    normalized = normalize_test_name(test_name)
    
    # Try to parse numeric value
    try:
        if isinstance(value, str):
            # Extract first number from string
            match = re.search(r'[-+]?\d*\.?\d+', value)
            if match:
                numeric_value = float(match.group())
            else:
                return True, None  # Non-numeric, can't validate
        else:
            numeric_value = float(value)
    except (ValueError, TypeError):
        return True, None  # Can't parse, skip validation
    
    # Check against range
    for test_key, (min_val, max_val) in VALUE_RANGES.items():
        if test_key in normalized:
            if numeric_value < min_val or numeric_value > max_val:
                return False, f"{test_name}: {value} outside range ({min_val}-{max_val})"
            break
    
    return True, None


def validate_extraction_results(
    lab_results: List[Dict[str, Any]],
    raw_text: Optional[str] = None
) -> ValidationResult:
    """
    Validate extracted lab results for hallucinations and errors.
    
    Args:
        lab_results: List of extracted lab results
        raw_text: Original OCR text for cross-validation
        
    Returns:
        ValidationResult with issues found
    """
    issues = []
    hallucinated = []
    suspicious = []
    safe_count = 0
    
    seen_tests = set()
    
    for result in lab_results:
        test_name = result.get("test_name", "")
        value = result.get("value", "")
        normalized = normalize_test_name(test_name)
        
        # Check for duplicates
        if normalized in seen_tests:
            issues.append(f"Duplicate test: {test_name}")
            suspicious.append(test_name)
            continue
        seen_tests.add(normalized)
        
        # Check if test is calculated (often hallucinated)
        if is_calculated_test(test_name):
            hallucinated.append(f"{test_name} (calculated value)")
            issues.append(f"Calculated test detected: {test_name}")
            continue
        
        # Check value range
        range_valid, range_error = validate_value_range(test_name, value)
        if not range_valid:
            suspicious.append(f"{test_name}: {value}")
            issues.append(range_error)
            continue
        
        # Cross-validate with raw text if available
        if raw_text:
            # Check if test name or value appears in raw text
            if test_name.lower() not in raw_text.lower():
                # Try partial match
                words = test_name.split()
                if not any(word.lower() in raw_text.lower() for word in words if len(word) > 2):
                    hallucinated.append(f"{test_name} (not in raw text)")
                    issues.append(f"Test not found in raw text: {test_name}")
                    continue
        
        # Passed all checks
        safe_count += 1
    
    return ValidationResult(
        is_valid=len(hallucinated) == 0 and len(suspicious) == 0,
        issues=issues,
        hallucinated_tests=hallucinated,
        suspicious_values=suspicious,
        safe_matches=safe_count
    )


def compare_extractions(
    vision_only: Dict[str, Any],
    three_tier: Dict[str, Any],
    tolerance: float = 0.1
) -> Dict[str, Any]:
    """
    Compare two extraction results and categorize differences.
    
    Args:
        vision_only: Results from vision-only extraction
        three_tier: Results from three-tier extraction
        tolerance: Numeric tolerance for "safe match" (10% default)
        
    Returns:
        Comparison results with categorized differences
    """
    vision_results = vision_only.get("lab_results", [])
    tier_results = three_tier.get("lab_results", [])
    
    # Build lookup by normalized test name
    vision_lookup = {}
    for r in vision_results:
        key = normalize_test_name(r.get("test_name", ""))
        if key:
            vision_lookup[key] = r
    
    tier_lookup = {}
    for r in tier_results:
        key = normalize_test_name(r.get("test_name", ""))
        if key:
            tier_lookup[key] = r
    
    # Categorize
    safe_matches = []      # 🟢 Values match
    suspicious = []        # 🟡 Values differ significantly  
    hallucinated = []      # 🔴 Only in three-tier
    missing_in_tier = []   # Tests in vision-only but not in three-tier
    
    # Check three-tier against vision-only
    for key, tier_result in tier_lookup.items():
        if key not in vision_lookup:
            # Test only in three-tier = potentially hallucinated
            hallucinated.append({
                "test_name": tier_result.get("test_name"),
                "value": tier_result.get("value"),
                "reason": "Not found in vision-only extraction"
            })
        else:
            # Both have it - compare values
            vision_result = vision_lookup[key]
            tier_value = tier_result.get("value", "")
            vision_value = vision_result.get("value", "")
            
            match_status = _compare_values(vision_value, tier_value, tolerance)
            
            if match_status == "safe":
                safe_matches.append({
                    "test_name": tier_result.get("test_name"),
                    "vision_value": vision_value,
                    "tier_value": tier_value
                })
            else:
                suspicious.append({
                    "test_name": tier_result.get("test_name"),
                    "vision_value": vision_value,
                    "tier_value": tier_value,
                    "reason": match_status
                })
    
    # Check what's in vision-only but not in three-tier
    for key, vision_result in vision_lookup.items():
        if key not in tier_lookup:
            missing_in_tier.append({
                "test_name": vision_result.get("test_name"),
                "value": vision_result.get("value")
            })
    
    return {
        "safe_matches": safe_matches,
        "suspicious": suspicious,
        "hallucinated": hallucinated,
        "missing_in_tier": missing_in_tier,
        "summary": {
            "safe_count": len(safe_matches),
            "suspicious_count": len(suspicious),
            "hallucinated_count": len(hallucinated),
            "missing_count": len(missing_in_tier)
        }
    }


def _compare_values(value1: Any, value2: Any, tolerance: float = 0.1) -> str:
    """
    Compare two values and return match status.
    
    Returns:
        "safe" - values match or within tolerance
        "unit_mismatch" - values similar but units may differ
        "value_mismatch" - significant value difference
    """
    # String comparison first
    str1 = str(value1).strip().lower()
    str2 = str(value2).strip().lower()
    
    if str1 == str2:
        return "safe"
    
    # Try numeric comparison
    try:
        # Extract numbers
        num1_match = re.search(r'[-+]?\d*\.?\d+', str1)
        num2_match = re.search(r'[-+]?\d*\.?\d+', str2)
        
        if num1_match and num2_match:
            num1 = float(num1_match.group())
            num2 = float(num2_match.group())
            
            # Check if within tolerance
            if num1 == 0 and num2 == 0:
                return "safe"
            
            max_val = max(abs(num1), abs(num2), 1)
            diff_ratio = abs(num1 - num2) / max_val
            
            if diff_ratio <= tolerance:
                return "safe"
            elif diff_ratio <= 0.5:
                return "unit_mismatch"  # Might be unit conversion issue
            else:
                return "value_mismatch"
    except (ValueError, ZeroDivisionError):
        pass
    
    # String values differ
    return "value_mismatch"
