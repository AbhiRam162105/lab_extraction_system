"""
Panel Completeness Validator.

Validates extracted lab results against expected panel rules.
Flags missing tests that should typically appear together.
"""

import logging
from typing import Dict, List, Any, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of panel validation."""
    is_complete: bool
    missing_tests: List[str]
    panel_name: str
    found_tests: List[str]
    severity: str  # "info", "warning", "critical"


@dataclass
class PanelValidatorResult:
    """Complete validation result."""
    all_validations: List[ValidationResult]
    needs_review: bool
    review_reasons: List[str]
    completeness_score: float


# =============================================================================
# Panel Completeness Rules
# =============================================================================

PANEL_RULES = {
    "cbc_differential": {
        "name": "CBC Differential",
        "triggers": ["neutrophils", "lymphocytes", "monocytes", "eosinophils"],
        "expected_pairs": {
            "neutrophils": ["absolute neutrophil count", "anc", "neutrophils (abs)", "absolute neutrophils"],
            "lymphocytes": ["absolute lymphocyte count", "alc", "lymphocytes (abs)", "absolute lymphocytes"],
            "monocytes": ["absolute monocyte count", "amc", "monocytes (abs)", "absolute monocytes"],
            "eosinophils": ["absolute eosinophil count", "aec", "eosinophils (abs)", "absolute eosinophils"],
            "basophils": ["absolute basophil count", "abc", "basophils (abs)", "absolute basophils"],
        },
        "severity": "warning",
        "message": "CBC shows differential % but missing absolute counts"
    },
    
    "coagulation": {
        "name": "Coagulation Panel",
        "triggers": ["inr", "international normalized ratio"],
        "expected": ["prothrombin time", "pt"],
        "optional": ["aptt", "activated partial thromboplastin time", "ptt"],
        "severity": "warning",
        "message": "INR found but PT (Prothrombin Time) missing"
    },
    
    "coagulation_aptt": {
        "name": "Coagulation APTT",
        "triggers": ["aptt", "activated partial thromboplastin time"],
        "expected": ["prothrombin time", "pt", "inr"],
        "severity": "info",
        "message": "APTT found - PT/INR may also be present"
    },
    
    "liver_panel": {
        "name": "Liver Function",
        "triggers": ["alt", "sgpt", "alanine aminotransferase"],
        "expected": ["ast", "sgot", "aspartate aminotransferase"],
        "severity": "info",
        "message": "ALT found - AST usually accompanies it"
    },
    
    "kidney_panel": {
        "name": "Kidney Function",
        "triggers": ["creatinine"],
        "expected": ["blood urea nitrogen", "bun", "urea"],
        "optional": ["egfr", "gfr"],
        "severity": "info",
        "message": "Creatinine found - BUN may also be present"
    },
    
    "rbc_indices": {
        "name": "RBC Indices",
        "triggers": ["mcv", "mean corpuscular volume"],
        "expected": ["mch", "mchc"],
        "severity": "info",
        "message": "MCV found - MCH/MCHC usually accompany it"
    }
}


class PanelValidator:
    """
    Validates extracted lab results for panel completeness.
    
    Example:
        If INR is found but PT is missing, flag for review.
        If differential % found but absolute counts missing, flag for review.
    """
    
    def __init__(self, rules: Dict = None):
        self.rules = rules or PANEL_RULES
    
    def validate(self, lab_results: List[Dict[str, Any]]) -> PanelValidatorResult:
        """
        Validate extracted lab results against panel rules.
        
        Args:
            lab_results: List of extracted test dictionaries
            
        Returns:
            PanelValidatorResult with missing tests and review flags
        """
        # Extract all test names (normalized to lowercase)
        found_tests = self._get_test_names(lab_results)
        
        validations = []
        review_reasons = []
        
        # Check each panel rule
        for rule_id, rule in self.rules.items():
            validation = self._check_rule(rule_id, rule, found_tests)
            if validation:
                validations.append(validation)
                if not validation.is_complete:
                    review_reasons.append(
                        f"{validation.panel_name}: {validation.missing_tests}"
                    )
        
        # Calculate completeness score
        total_expected = sum(len(v.missing_tests) + len(v.found_tests) for v in validations)
        total_found = sum(len(v.found_tests) for v in validations)
        completeness_score = total_found / total_expected if total_expected > 0 else 1.0
        
        needs_review = any(
            v.severity in ("warning", "critical") and not v.is_complete 
            for v in validations
        )
        
        return PanelValidatorResult(
            all_validations=validations,
            needs_review=needs_review,
            review_reasons=review_reasons,
            completeness_score=completeness_score
        )
    
    def _get_test_names(self, lab_results: List[Dict[str, Any]]) -> Set[str]:
        """Extract normalized test names from results."""
        names = set()
        
        for result in lab_results:
            # Try different name fields
            for field in ['test_name', 'standardized_test_name', 'original_name']:
                name = result.get(field, '')
                if name:
                    names.add(name.lower().strip())
        
        return names
    
    def _check_rule(
        self, 
        rule_id: str, 
        rule: Dict, 
        found_tests: Set[str]
    ) -> ValidationResult:
        """Check a single panel rule."""
        triggers = rule.get("triggers", [])
        
        # Check if any trigger is present
        trigger_found = any(
            self._test_matches(found_tests, trigger) 
            for trigger in triggers
        )
        
        if not trigger_found:
            return None  # Rule doesn't apply
        
        # Handle paired tests (differential -> absolute)
        if "expected_pairs" in rule:
            return self._check_paired_rule(rule_id, rule, found_tests)
        
        # Handle simple expected tests
        expected = rule.get("expected", [])
        missing = []
        found = []
        
        for expected_test in expected:
            if self._test_matches(found_tests, expected_test):
                found.append(expected_test)
            else:
                missing.append(expected_test)
        
        # Also check optional tests (just for logging)
        optional = rule.get("optional", [])
        for opt_test in optional:
            if self._test_matches(found_tests, opt_test):
                found.append(opt_test)
        
        return ValidationResult(
            is_complete=len(missing) == 0,
            missing_tests=missing,
            panel_name=rule["name"],
            found_tests=found,
            severity=rule.get("severity", "info")
        )
    
    def _check_paired_rule(
        self, 
        rule_id: str, 
        rule: Dict, 
        found_tests: Set[str]
    ) -> ValidationResult:
        """Check paired test rules (e.g., differential -> absolute)."""
        expected_pairs = rule.get("expected_pairs", {})
        missing = []
        found = []
        
        for trigger, expected_list in expected_pairs.items():
            # Check if trigger is present
            if not self._test_matches(found_tests, trigger):
                continue
            
            found.append(trigger)
            
            # Check if any of the expected tests are present
            pair_found = any(
                self._test_matches(found_tests, exp) 
                for exp in expected_list
            )
            
            if pair_found:
                # Find which one was found
                for exp in expected_list:
                    if self._test_matches(found_tests, exp):
                        found.append(exp)
                        break
            else:
                # None of the expected pairs found
                missing.append(f"Absolute {trigger} count")
        
        return ValidationResult(
            is_complete=len(missing) == 0,
            missing_tests=missing,
            panel_name=rule["name"],
            found_tests=found,
            severity=rule.get("severity", "warning")
        )
    
    def _test_matches(self, found_tests: Set[str], pattern: str) -> bool:
        """Check if pattern matches any found test."""
        pattern_lower = pattern.lower().strip()
        
        for test in found_tests:
            # Exact match
            if test == pattern_lower:
                return True
            # Substring match (for variations)
            if pattern_lower in test or test in pattern_lower:
                return True
        
        return False


def validate_panel_completeness(lab_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenience function to validate panel completeness.
    
    Returns dict with:
    - needs_review: bool
    - missing_panels: list of incomplete panels
    - review_reasons: list of reason strings
    - completeness_score: 0.0-1.0
    """
    validator = PanelValidator()
    result = validator.validate(lab_results)
    
    return {
        "needs_review": result.needs_review,
        "missing_panels": [
            {
                "panel": v.panel_name,
                "missing": v.missing_tests,
                "found": v.found_tests,
                "severity": v.severity
            }
            for v in result.all_validations 
            if not v.is_complete
        ],
        "review_reasons": result.review_reasons,
        "completeness_score": result.completeness_score
    }
