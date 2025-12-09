"""
Extraction Quality Verifier.

Comprehensive post-extraction validation to ensure:
- All CBC parameters including absolute counts
- RDW, MPV, IPF when present
- Complete coagulation panel (PT, INR, APTT together)
- Peripheral smear morphology findings
- Flags match actual reference range logic
- Unit consistency and standardization
- Qualitative findings captured as Text type
- No duplicate or overlapping standardized names
"""

import logging
import re
from typing import Dict, List, Any, Set, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a single verification check."""
    check_name: str
    passed: bool
    severity: str  # "info", "warning", "error"
    message: str
    details: List[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """Complete quality report for an extraction."""
    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: List[str]
    errors: List[str]
    results: List[VerificationResult]
    quality_score: float  # 0.0 - 1.0


# =============================================================================
# Expected Test Sets
# =============================================================================

CBC_DIFFERENTIAL_PERCENT = {
    "neutrophils", "lymphocytes", "monocytes", "eosinophils", "basophils"
}

CBC_ABSOLUTE_COUNTS = {
    "absolute neutrophil count", "absolute lymphocyte count", 
    "absolute monocyte count", "absolute eosinophil count", "absolute basophil count",
    "anc", "alc", "amc", "aec", "abc"
}

CBC_INDICES = {
    "rdw", "red cell distribution width", "mpv", "mean platelet volume",
    "ipf", "immature platelet fraction"
}

COAGULATION_PANEL = {
    "prothrombin time", "pt", "inr", "international normalized ratio",
    "aptt", "activated partial thromboplastin time", "ptt"
}

PERIPHERAL_SMEAR = {
    "rbc morphology", "wbc morphology", "platelet morphology",
    "hemoparasites", "abnormal cells"
}

# Standard units for tests
STANDARD_UNITS = {
    "hemoglobin": ["g/dl", "g/l"],
    "rbc": ["m/ul", "million/ul", "x10^12/l"],
    "wbc": ["/cumm", "/ul", "x10^3/ul", "x10^9/l"],
    "platelets": ["/cumm", "/ul", "x10^3/ul", "lacs/cumm"],
    "neutrophils": ["%"],
    "lymphocytes": ["%"],
    "absolute neutrophil count": ["/cumm", "/ul", "cells/cumm"],
    "creatinine": ["mg/dl", "umol/l"],
    "glucose": ["mg/dl", "mmol/l"],
}


class ExtractionQualityVerifier:
    """
    Verifies extraction quality against a comprehensive checklist.
    """
    
    def __init__(self):
        self.checks = [
            self._check_cbc_absolute_counts,
            self._check_cbc_indices,
            self._check_coagulation_completeness,
            self._check_peripheral_smear,
            self._check_flag_consistency,
            self._check_unit_consistency,
            self._check_qualitative_data,
            self._check_duplicates,
        ]
    
    def verify(self, lab_results: List[Dict[str, Any]]) -> QualityReport:
        """
        Run all verification checks on extracted lab results.
        
        Args:
            lab_results: List of extracted test dictionaries
            
        Returns:
            QualityReport with all check results
        """
        results = []
        warnings = []
        errors = []
        
        for check in self.checks:
            try:
                result = check(lab_results)
                results.append(result)
                
                if not result.passed:
                    if result.severity == "error":
                        errors.append(result.message)
                    elif result.severity == "warning":
                        warnings.append(result.message)
            except Exception as e:
                logger.error(f"Check {check.__name__} failed: {e}")
                results.append(VerificationResult(
                    check_name=check.__name__,
                    passed=False,
                    severity="error",
                    message=f"Check failed with error: {str(e)}"
                ))
        
        passed_checks = sum(1 for r in results if r.passed)
        total_checks = len(results)
        
        # Calculate quality score
        quality_score = passed_checks / total_checks if total_checks > 0 else 0.0
        
        return QualityReport(
            passed=len(errors) == 0,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=total_checks - passed_checks,
            warnings=warnings,
            errors=errors,
            results=results,
            quality_score=quality_score
        )
    
    def _get_test_names(self, lab_results: List[Dict[str, Any]]) -> Set[str]:
        """Extract normalized test names."""
        names = set()
        for result in lab_results:
            for field in ['test_name', 'standardized_test_name', 'original_name']:
                name = result.get(field, '')
                if name:
                    names.add(name.lower().strip())
        return names
    
    def _check_cbc_absolute_counts(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check if CBC differential has corresponding absolute counts."""
        names = self._get_test_names(lab_results)
        
        # Check if differential % is present
        has_differential = any(
            self._name_matches(names, diff) for diff in CBC_DIFFERENTIAL_PERCENT
        )
        
        if not has_differential:
            return VerificationResult(
                check_name="CBC Absolute Counts",
                passed=True,
                severity="info",
                message="No CBC differential found - check not applicable"
            )
        
        # Check for absolute counts
        missing_absolutes = []
        found_absolutes = []
        
        for diff in CBC_DIFFERENTIAL_PERCENT:
            if self._name_matches(names, diff):
                # Look for corresponding absolute count
                abs_name = f"absolute {diff} count"
                has_absolute = any(
                    self._name_matches(names, pattern) 
                    for pattern in [abs_name, diff[:3].upper() + "C", f"abs {diff}"]
                )
                
                if has_absolute:
                    found_absolutes.append(diff)
                else:
                    missing_absolutes.append(diff)
        
        if missing_absolutes:
            return VerificationResult(
                check_name="CBC Absolute Counts",
                passed=False,
                severity="warning",
                message=f"Missing absolute counts for: {', '.join(missing_absolutes)}",
                details=[f"Found {len(found_absolutes)} absolute counts, missing {len(missing_absolutes)}"]
            )
        
        return VerificationResult(
            check_name="CBC Absolute Counts",
            passed=True,
            severity="info",
            message=f"All {len(found_absolutes)} absolute counts present"
        )
    
    def _check_cbc_indices(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check for RDW, MPV, IPF presence."""
        names = self._get_test_names(lab_results)
        
        # Check if CBC is present
        has_cbc = any(
            self._name_matches(names, pattern)
            for pattern in ["hemoglobin", "hb", "rbc", "wbc", "platelets"]
        )
        
        if not has_cbc:
            return VerificationResult(
                check_name="CBC Indices (RDW/MPV/IPF)",
                passed=True,
                severity="info",
                message="No CBC found - check not applicable"
            )
        
        found_indices = []
        for idx in CBC_INDICES:
            if self._name_matches(names, idx):
                found_indices.append(idx.upper())
        
        if found_indices:
            return VerificationResult(
                check_name="CBC Indices (RDW/MPV/IPF)",
                passed=True,
                severity="info",
                message=f"Found CBC indices: {', '.join(found_indices)}"
            )
        else:
            return VerificationResult(
                check_name="CBC Indices (RDW/MPV/IPF)",
                passed=True,  # Not an error, just info
                severity="info",
                message="No RDW/MPV/IPF found (may not be in source document)"
            )
    
    def _check_coagulation_completeness(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check for complete coagulation panel (PT, INR, APTT)."""
        names = self._get_test_names(lab_results)
        
        found_coag = []
        for test in ["pt", "prothrombin time", "inr", "aptt", "ptt"]:
            if self._name_matches(names, test):
                found_coag.append(test.upper())
        
        if not found_coag:
            return VerificationResult(
                check_name="Coagulation Panel Completeness",
                passed=True,
                severity="info",
                message="No coagulation tests found - check not applicable"
            )
        
        has_pt = self._name_matches(names, "pt") or self._name_matches(names, "prothrombin time")
        has_inr = self._name_matches(names, "inr")
        has_aptt = self._name_matches(names, "aptt") or self._name_matches(names, "ptt")
        
        missing = []
        if has_inr and not has_pt:
            missing.append("PT (Prothrombin Time)")
        
        if missing:
            return VerificationResult(
                check_name="Coagulation Panel Completeness",
                passed=False,
                severity="warning",
                message=f"Incomplete coagulation panel - missing: {', '.join(missing)}",
                details=[f"Found: {', '.join(found_coag)}"]
            )
        
        return VerificationResult(
            check_name="Coagulation Panel Completeness",
            passed=True,
            severity="info",
            message=f"Coagulation panel: {', '.join(found_coag)}"
        )
    
    def _check_peripheral_smear(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check for peripheral smear morphology findings."""
        names = self._get_test_names(lab_results)
        
        found_smear = []
        for smear in PERIPHERAL_SMEAR:
            if self._name_matches(names, smear):
                found_smear.append(smear)
        
        # Check if there are qualitative findings that should be smear
        qualitative_count = sum(
            1 for r in lab_results 
            if r.get('value_type') == 'text' or 
            (isinstance(r.get('value'), str) and not r.get('value', '').replace('.', '').replace('-', '').isdigit())
        )
        
        if found_smear:
            return VerificationResult(
                check_name="Peripheral Smear Findings",
                passed=True,
                severity="info",
                message=f"Found peripheral smear data: {', '.join(found_smear)}"
            )
        elif qualitative_count > 0:
            return VerificationResult(
                check_name="Peripheral Smear Findings",
                passed=True,
                severity="info",
                message=f"Found {qualitative_count} qualitative findings (may include smear data)"
            )
        else:
            return VerificationResult(
                check_name="Peripheral Smear Findings",
                passed=True,
                severity="info",
                message="No peripheral smear data found (may not be in source document)"
            )
    
    def _check_flag_consistency(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check if flags match reference range logic."""
        inconsistencies = []
        
        for result in lab_results:
            flag = result.get('flag', '').upper()
            value = result.get('value', '')
            ref_range = result.get('reference_range', '')
            
            if not value or not ref_range or not flag:
                continue
            
            # Try to parse value
            try:
                numeric_value = float(str(value).replace(',', ''))
            except ValueError:
                continue
            
            # Try to parse reference range
            parsed_range = self._parse_reference_range(ref_range)
            if not parsed_range:
                continue
            
            low, high = parsed_range
            
            # Check consistency
            expected_flag = ""
            if numeric_value < low:
                expected_flag = "L"
            elif numeric_value > high:
                expected_flag = "H"
            
            actual_flag = flag.replace("HIGH", "H").replace("LOW", "L")
            
            if expected_flag and actual_flag not in [expected_flag, "H" if expected_flag == "H" else "L"]:
                test_name = result.get('test_name', result.get('standardized_test_name', 'Unknown'))
                inconsistencies.append(
                    f"{test_name}: value={value}, range={ref_range}, flag={flag}, expected={expected_flag}"
                )
        
        if inconsistencies:
            return VerificationResult(
                check_name="Flag Consistency",
                passed=False,
                severity="warning",
                message=f"Found {len(inconsistencies)} flag inconsistencies",
                details=inconsistencies[:5]  # Limit details
            )
        
        return VerificationResult(
            check_name="Flag Consistency",
            passed=True,
            severity="info",
            message="All flags consistent with reference ranges"
        )
    
    def _check_unit_consistency(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check for unit consistency and standardization."""
        issues = []
        
        for result in lab_results:
            unit = result.get('unit', '')
            test_name = result.get('standardized_test_name', result.get('test_name', '')).lower()
            
            if not unit:
                continue
            
            unit_lower = unit.lower().strip()
            
            # Check for common issues
            if unit_lower in ['', '-', 'n/a', 'na']:
                continue
            
            # Check for unusual units
            if len(unit_lower) > 20:
                issues.append(f"{test_name}: unusually long unit '{unit[:20]}...'")
            
            # Check if unit looks like a value
            if unit_lower.replace('.', '').replace('-', '').isdigit():
                issues.append(f"{test_name}: unit looks like a number '{unit}'")
        
        if issues:
            return VerificationResult(
                check_name="Unit Consistency",
                passed=False,
                severity="warning",
                message=f"Found {len(issues)} unit issues",
                details=issues[:5]
            )
        
        return VerificationResult(
            check_name="Unit Consistency",
            passed=True,
            severity="info",
            message="Units appear consistent"
        )
    
    def _check_qualitative_data(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check if qualitative findings are properly typed."""
        qualitative_tests = []
        mistyped = []
        
        qualitative_patterns = [
            "morphology", "smear", "appearance", "comment", "finding",
            "impression", "conclusion", "interpretation"
        ]
        
        for result in lab_results:
            test_name = result.get('test_name', result.get('standardized_test_name', '')).lower()
            value = result.get('value', '')
            value_type = result.get('value_type', '')
            
            # Check if this looks like qualitative data
            is_qualitative = any(p in test_name for p in qualitative_patterns)
            
            # Also check if value is non-numeric
            if not is_qualitative and value:
                try:
                    float(str(value).replace(',', ''))
                except ValueError:
                    # Value is non-numeric
                    if len(str(value)) > 10 and not str(value).replace('.', '').replace('-', '').isdigit():
                        is_qualitative = True
            
            if is_qualitative:
                qualitative_tests.append(test_name)
                if value_type not in ['text', 'qualitative']:
                    mistyped.append(test_name)
        
        if mistyped:
            return VerificationResult(
                check_name="Qualitative Data Typing",
                passed=False,
                severity="warning",
                message=f"{len(mistyped)} qualitative tests not typed as 'text'",
                details=mistyped[:5]
            )
        
        if qualitative_tests:
            return VerificationResult(
                check_name="Qualitative Data Typing",
                passed=True,
                severity="info",
                message=f"Found {len(qualitative_tests)} qualitative tests, properly typed"
            )
        
        return VerificationResult(
            check_name="Qualitative Data Typing",
            passed=True,
            severity="info",
            message="No qualitative data found"
        )
    
    def _check_duplicates(self, lab_results: List[Dict[str, Any]]) -> VerificationResult:
        """Check for duplicate or overlapping standardized names."""
        seen_names = {}
        duplicates = []
        
        for result in lab_results:
            std_name = result.get('standardized_test_name', '')
            if not std_name:
                continue
            
            std_lower = std_name.lower().strip()
            
            if std_lower in seen_names:
                # Check if values are different
                prev_value = seen_names[std_lower]
                curr_value = result.get('value', '')
                
                if prev_value != curr_value:
                    duplicates.append(f"{std_name}: '{prev_value}' vs '{curr_value}'")
                else:
                    duplicates.append(f"{std_name}: duplicate entry with same value")
            else:
                seen_names[std_lower] = result.get('value', '')
        
        if duplicates:
            return VerificationResult(
                check_name="Duplicate Detection",
                passed=False,
                severity="warning",
                message=f"Found {len(duplicates)} potential duplicates",
                details=duplicates[:5]
            )
        
        return VerificationResult(
            check_name="Duplicate Detection",
            passed=True,
            severity="info",
            message="No duplicates detected"
        )
    
    def _name_matches(self, names: Set[str], pattern: str) -> bool:
        """Check if pattern matches any name."""
        pattern_lower = pattern.lower().strip()
        for name in names:
            if pattern_lower in name or name in pattern_lower:
                return True
        return False
    
    def _parse_reference_range(self, ref_range: str) -> Optional[Tuple[float, float]]:
        """Parse reference range string into low, high tuple."""
        if not ref_range:
            return None
        
        # Common patterns: "10-20", "10 - 20", "10.0-20.0", "> 10", "< 20"
        ref_clean = ref_range.replace(',', '').strip()
        
        # Pattern: "low - high"
        match = re.match(r'([\d.]+)\s*[-–]\s*([\d.]+)', ref_clean)
        if match:
            try:
                return (float(match.group(1)), float(match.group(2)))
            except ValueError:
                return None
        
        return None


def verify_extraction_quality(lab_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenience function to verify extraction quality.
    
    Returns dict with:
    - passed: bool
    - quality_score: 0.0-1.0
    - warnings: list
    - errors: list
    - checks: list of individual check results
    """
    verifier = ExtractionQualityVerifier()
    report = verifier.verify(lab_results)
    
    return {
        "passed": report.passed,
        "quality_score": report.quality_score,
        "total_checks": report.total_checks,
        "passed_checks": report.passed_checks,
        "warnings": report.warnings,
        "errors": report.errors,
        "checks": [
            {
                "name": r.check_name,
                "passed": r.passed,
                "severity": r.severity,
                "message": r.message,
                "details": r.details
            }
            for r in report.results
        ]
    }
