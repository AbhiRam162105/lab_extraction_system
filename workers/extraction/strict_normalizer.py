"""
Strict Normalizer Module - PRODUCTION VERSION.

Single Vision → Deterministic Normalizer → Safety Validation

CRITICAL FIXES:
1. NO substring matching (caused RBC→RDW bug)
2. Levenshtein distance with strict threshold
3. Panel-aware whitelists
4. Reference range parsing for validation
5. Unknown tests preserved
"""

import logging
import re
import yaml
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from pathlib import Path

import google.generativeai as genai
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class NormalizedResult:
    """A single normalized lab result."""
    test_name: str           # Canonical name from YAML
    original_name: str       # Raw OCR text
    value: str               # Parsed numeric value
    value_numeric: Optional[float] = None
    unit: str = ""
    reference_range: str = ""
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    flag: str = ""           # H/L/N
    loinc_code: str = ""
    category: str = ""
    needs_review: bool = False
    review_reason: str = ""
    mapping_method: str = "" # "exact", "alias", "fuzzy", "llm", "unknown"


@dataclass
class NormalizerResult:
    """Result of normalization."""
    success: bool
    results: List[NormalizedResult]
    unknown_tests: List[str]
    issues: List[str]


# Panel definitions - which tests belong to which panel (MUST MATCH YAML KEYS)
PANEL_DEFINITIONS = {
    "cbc": [
        "hemoglobin", "red_blood_cells", "white_blood_cells", "platelets", 
        "hematocrit", "mcv", "mch", "mchc", "rdw", "mpv"
    ],
    "differential": [
        "neutrophils", "lymphocytes", "monocytes", "eosinophils", "basophils", "esr"
    ],
    "abg": [
        "ph", "pco2", "po2", "hco3_abg", "base_excess", "oxygen_saturation", "lactate", "ionized_calcium"
    ],
    "electrolytes": [
        "sodium", "potassium", "chloride", "bicarbonate", "calcium", "phosphorus", "magnesium"
    ],
    "liver": [
        "alt", "ast", "alp", "ggt", "total_bilirubin", "direct_bilirubin", "indirect_bilirubin",
        "total_protein", "albumin", "globulin", "ag_ratio"
    ],
    "kidney": [
        "creatinine", "blood_urea_nitrogen", "uric_acid", "egfr"
    ],
    "lipid": [
        "total_cholesterol", "ldl_cholesterol", "hdl_cholesterol", "triglycerides", "vldl"
    ],
    "thyroid": [
        "tsh", "free_t3", "free_t4", "total_t3", "total_t4"
    ],
    "diabetes": [
        "fasting_glucose", "random_glucose", "postprandial_glucose", "hba1c"
    ],
}

# Keywords to detect panel
PANEL_KEYWORDS = {
    "cbc": ["hemoglobin", "hb", "rbc", "wbc", "platelet", "plt", "pcv", "hct", "mcv", "mch", "mchc", "rdw", "haemoglobin"],
    "differential": ["neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil", "neut", "lymph", "mono", "eos", "baso", "differential"],
    "abg": ["pco2", "po2", "hco3", "base excess", "sao2", "blood gas", "abg"],  # Removed 'ph' to avoid false matches
    "electrolytes": ["sodium", "potassium", "chloride", "calcium", "magnesium", "na+", "k+", "cl-"],
    "liver": ["alt", "ast", "sgpt", "sgot", "bilirubin", "alp", "ggt", "albumin"],
    "kidney": ["creatinine", "urea", "bun", "egfr", "uric acid"],
    "lipid": ["cholesterol", "triglyceride", "hdl", "ldl", "vldl"],
    "thyroid": ["tsh", "t3", "t4", "thyroid"],
    "diabetes": ["glucose", "hba1c", "sugar", "fasting", "random"],
}


class StrictNormalizer:
    """
    Production-grade normalizer using Levenshtein distance.
    
    NO substring matching. Panel-aware. Reference range validation.
    """
    
    def __init__(self, yaml_path: Optional[str] = None):
        self.yaml_path = yaml_path or self._get_default_yaml_path()
        self.mappings = self._load_mappings()
        self.whitelist = self._build_whitelist()
        self.panel_whitelists = self._build_panel_whitelists()
        self._configure_gemini()
        self.model = genai.GenerativeModel(settings.gemini.model)
    
    def _get_default_yaml_path(self) -> str:
        base_path = Path(__file__).parent.parent.parent
        return str(base_path / "config" / "test_mappings.yaml")
    
    def _load_mappings(self) -> Dict[str, Any]:
        try:
            with open(self.yaml_path, 'r') as f:
                data = yaml.safe_load(f)
                return data.get('mappings', {})
        except Exception as e:
            logger.error(f"Failed to load mappings: {e}")
            return {}
    
    def _build_whitelist(self) -> Dict[str, str]:
        """Build whitelist: lowercase alias -> canonical key"""
        whitelist = {}
        
        for key, mapping in self.mappings.items():
            canonical = mapping.get('canonical_name', key)
            
            whitelist[key.lower()] = key
            whitelist[canonical.lower()] = key
            
            for alias in mapping.get('aliases', []):
                whitelist[alias.lower()] = key
        
        return whitelist
    
    def _build_panel_whitelists(self) -> Dict[str, Set[str]]:
        """Build panel-specific whitelists."""
        panel_whitelists = {}
        
        for panel_name, test_keys in PANEL_DEFINITIONS.items():
            allowed_keys = set()
            for key in test_keys:
                if key in self.mappings:
                    allowed_keys.add(key)
            panel_whitelists[panel_name] = allowed_keys
        
        return panel_whitelists
    
    def _configure_gemini(self) -> None:
        api_key = settings.gemini.api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
    
    def _levenshtein(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _parse_reference_range(self, ref: str) -> Tuple[Optional[float], Optional[float]]:
        """Parse reference range string into (low, high) floats."""
        if not ref:
            return None, None
        
        # Find all numbers in the string
        matches = re.findall(r'[-+]?\d*\.?\d+', ref)
        
        if len(matches) >= 2:
            try:
                return float(matches[0]), float(matches[1])
            except ValueError:
                return None, None
        elif len(matches) == 1:
            # Single value - could be max or min
            try:
                val = float(matches[0])
                if '<' in ref:
                    return None, val
                elif '>' in ref:
                    return val, None
                return None, None
            except ValueError:
                return None, None
        
        return None, None
    
    def normalize(self, raw_rows: List[Dict[str, str]]) -> NormalizerResult:
        """Normalize raw table rows."""
        results = []
        unknown = []
        issues = []
        
        for row in raw_rows:
            test_raw = row.get('test_name', row.get('test_raw', '')).strip()
            
            if not test_raw:
                continue
            
            # Skip obvious non-test text
            if self._is_non_test_text(test_raw):
                continue
            
            # Detect panel
            detected_panel = self._detect_panel(test_raw)
            
            # Map test name
            mapped_key, method = self._map_test_name(test_raw, detected_panel)
            
            # Parse value
            value_raw = row.get('value', row.get('value_raw', ''))
            value, value_numeric = self._parse_value(value_raw)
            
            # Parse reference range
            ref_raw = row.get('reference_range', row.get('ref_raw', ''))
            ref_low, ref_high = self._parse_reference_range(ref_raw)
            
            # Get flag
            flag = row.get('flag', row.get('flag_raw', ''))
            flag = self._normalize_flag(flag, value_raw)
            
            if mapped_key is None:
                # Preserve unknown tests
                unknown.append(test_raw)
                logger.warning(f"Unknown test: {test_raw}")
                
                results.append(NormalizedResult(
                    test_name="UNKNOWN",
                    original_name=test_raw,
                    value=value,
                    value_numeric=value_numeric,
                    unit=row.get('unit', row.get('unit_raw', '')),
                    reference_range=ref_raw,
                    ref_low=ref_low,
                    ref_high=ref_high,
                    flag=flag,
                    needs_review=True,
                    review_reason=f"Unmapped: {test_raw}",
                    mapping_method="unknown"
                ))
                continue
            
            mapping = self.mappings.get(mapped_key, {})
            
            # Validate against reference range
            needs_review = False
            review_reason = ""
            
            if method == 'llm':
                needs_review = True
                review_reason = "Mapped via LLM"
            elif method == 'fuzzy':
                needs_review = True
                review_reason = "Fuzzy match - verify"
            
            # Check if value is outside reference range from report
            if value_numeric is not None and ref_low is not None and ref_high is not None:
                if value_numeric < ref_low or value_numeric > ref_high:
                    if not needs_review:
                        needs_review = True
                        review_reason = "Value outside reference range"
            
            results.append(NormalizedResult(
                test_name=mapping.get('canonical_name', mapped_key),
                original_name=test_raw,
                value=value,
                value_numeric=value_numeric,
                unit=row.get('unit', row.get('unit_raw', '')) or mapping.get('unit', ''),
                reference_range=ref_raw,
                ref_low=ref_low,
                ref_high=ref_high,
                flag=flag,
                loinc_code=mapping.get('loinc_code', ''),
                category=mapping.get('category', ''),
                needs_review=needs_review,
                review_reason=review_reason,
                mapping_method=method
            ))
        
        return NormalizerResult(
            success=len(results) > 0,
            results=results,
            unknown_tests=unknown,
            issues=issues
        )
    
    def _is_non_test_text(self, text: str) -> bool:
        """Check if text is not a test name."""
        text_lower = text.lower()
        
        skip_patterns = [
            'hospital', 'laboratory', 'report', 'date', 'time', 'sample',
            'patient', 'doctor', 'method', 'instrument', 
            'normal range', 'reference', 'investigation', 'parameter',
            'result', 'printed', 'page', 'test name', 'lab no', 'uhid'
        ]
        
        for pattern in skip_patterns:
            if pattern in text_lower:
                return True
        
        if len(text) < 2:
            return True
        
        return False
    
    def _detect_panel(self, raw_name: str) -> Optional[str]:
        """Detect which panel this test belongs to."""
        name_lower = raw_name.lower()
        
        for panel, keywords in PANEL_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return panel
        
        return None
    
    def _map_test_name(
        self, 
        raw_name: str, 
        detected_panel: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """
        Map raw test name to canonical key.
        
        PRODUCTION VERSION:
        1. Exact match only
        2. Direct alias match (identical string)
        3. Levenshtein distance (threshold ≤ 2)
        4. Panel-scoped LLM fallback
        
        NO SUBSTRING MATCHING!
        """
        normalized = raw_name.lower().strip()
        
        # Clean common suffixes
        normalized_clean = re.sub(r'\s*[%$#]\s*$', '', normalized)
        normalized_clean = re.sub(r'\s+count\s*$', '', normalized_clean)
        normalized_clean = re.sub(r'\s+\(.*\)\s*$', '', normalized_clean)
        
        # Get allowed keys for this panel
        allowed_keys = None
        if detected_panel and detected_panel in self.panel_whitelists:
            allowed_keys = self.panel_whitelists[detected_panel]
        
        # 1. EXACT match
        if normalized in self.whitelist:
            key = self.whitelist[normalized]
            if allowed_keys is None or key in allowed_keys:
                return key, "exact"
        
        if normalized_clean in self.whitelist:
            key = self.whitelist[normalized_clean]
            if allowed_keys is None or key in allowed_keys:
                return key, "exact"
        
        # 2. Direct alias match (identical strings only, NO substring!)
        for alias, key in self.whitelist.items():
            if allowed_keys and key not in allowed_keys:
                continue
            if normalized == alias or normalized_clean == alias:
                return key, "alias"
        
        # 3. Levenshtein distance matching (threshold ≤ 2)
        best_key = None
        best_score = 999
        
        for alias, key in self.whitelist.items():
            # Skip if panel-scoped and key not allowed
            if allowed_keys and key not in allowed_keys:
                continue
            
            # Skip very short aliases
            if len(alias) < 3:
                continue
            
            # Calculate Levenshtein distance
            dist = self._levenshtein(normalized_clean, alias)
            
            # Prefer shorter distances
            if dist < best_score:
                best_score = dist
                best_key = key
        
        # Require strong similarity (distance ≤ 2 for short names, ≤ 3 for longer)
        max_dist = 2 if len(normalized_clean) < 6 else 3
        if best_key and best_score <= max_dist:
            return best_key, "fuzzy"
        
        # 4. Panel-scoped LLM match (last resort)
        if detected_panel:
            llm_pick = self._llm_panel_match(raw_name, detected_panel)
            if llm_pick:
                return llm_pick, "llm"
        
        return None, "unknown"
    
    def _llm_panel_match(self, raw_name: str, panel: str) -> Optional[str]:
        """LLM match RESTRICTED to panel subset."""
        try:
            allowed_keys = list(self.panel_whitelists.get(panel, set()))
            
            if not allowed_keys:
                return None
            
            candidate_names = [
                self.mappings.get(k, {}).get('canonical_name', k) 
                for k in allowed_keys
            ]
            
            prompt = f"""You are a medical lab test name matcher.

OCR text: "{raw_name}"
Panel: {panel.upper()}

Valid tests for this panel:
{', '.join(candidate_names)}

Pick EXACTLY ONE test that matches, or respond "NONE".
Response (just the canonical name):"""

            response = self.model.generate_content(prompt)
            pick = response.text.strip().lower()
            
            if pick == "none" or not pick:
                return None
            
            for key in allowed_keys:
                canonical = self.mappings.get(key, {}).get('canonical_name', key).lower()
                if pick == key or pick == canonical:
                    return key
            
            return None
            
        except Exception as e:
            logger.warning(f"LLM panel match failed: {e}")
            return None
    
    def _parse_value(self, raw_value: str) -> Tuple[str, Optional[float]]:
        """Parse raw value string."""
        if not raw_value:
            return "", None
        
        cleaned = str(raw_value).strip()
        cleaned = re.sub(r'[↑↓HLhl\*]$', '', cleaned).strip()
        
        match = re.search(r'[-+]?\d*\.?\d+', cleaned)
        if match:
            try:
                numeric = float(match.group())
                return cleaned, numeric
            except ValueError:
                pass
        
        return cleaned, None
    
    def _normalize_flag(self, flag_raw: str, value_raw: str) -> str:
        """Normalize flag to H/L/N."""
        if not flag_raw:
            if value_raw:
                value_str = str(value_raw)
                if '↑' in value_str or value_str.upper().endswith('H'):
                    return 'H'
                elif '↓' in value_str or value_str.upper().endswith('L'):
                    return 'L'
            return ''
        
        flag = str(flag_raw).upper().strip()
        
        if flag in ['H', 'HIGH', '↑']:
            return 'H'
        elif flag in ['L', 'LOW', '↓']:
            return 'L'
        elif flag in ['N', 'NORMAL']:
            return 'N'
        
        return flag[:1] if flag else ''


def normalize_results(raw_rows: List[Dict[str, str]]) -> NormalizerResult:
    """Convenience function for normalization."""
    normalizer = StrictNormalizer()
    return normalizer.normalize(raw_rows)
