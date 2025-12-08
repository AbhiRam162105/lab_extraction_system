"""
Test Name Standardization Module.

Provides 3-tier matching for lab test name standardization:
1. Exact alias matching
2. Fuzzy matching using RapidFuzz
3. LLM fallback for unknown tests

Each standardized result includes:
- Canonical test name
- LOINC code for interoperability
- Confidence score
- Match type
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from rapidfuzz import fuzz, process
import google.generativeai as genai

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class StandardizedTest:
    """Result of test name standardization."""
    original_name: str
    canonical_name: str
    loinc_code: Optional[str]
    category: Optional[str]
    unit: Optional[str]
    confidence: float
    match_type: str  # 'exact', 'fuzzy', 'llm', 'unknown'
    is_standardized: bool


class TestNameStandardizer:
    """
    Standardizes lab test names using a multi-tier matching approach.
    
    Tier 1: Exact alias matching (fastest, highest confidence)
    Tier 2: Fuzzy string matching with configurable threshold
    Tier 3: LLM-based standardization for unknown tests
    """
    
    def __init__(
        self,
        mappings_path: Optional[Path] = None,
        fuzzy_threshold: float = 0.85,
        use_llm_fallback: bool = True
    ):
        """
        Initialize the standardizer.
        
        Args:
            mappings_path: Path to test_mappings.yaml. Defaults to config/test_mappings.yaml
            fuzzy_threshold: Minimum score (0-1) for fuzzy matching
            use_llm_fallback: Whether to use Gemini for unknown tests
        """
        if mappings_path is None:
            mappings_path = Path(__file__).parent.parent.parent / "config" / "test_mappings.yaml"
        
        self.fuzzy_threshold = fuzzy_threshold
        self.use_llm_fallback = use_llm_fallback
        
        # Load mappings
        self.mappings: Dict[str, Dict] = {}
        self.alias_to_id: Dict[str, str] = {}
        self.canonical_names: List[str] = []
        
        self._load_mappings(mappings_path)
        
        # Cache for LLM results
        self._llm_cache: Dict[str, StandardizedTest] = {}
    
    def _load_mappings(self, path: Path) -> None:
        """Load test mappings from YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            
            self.mappings = data.get('mappings', {})
            
            # Build reverse lookup: alias -> test_id
            for test_id, test_data in self.mappings.items():
                canonical = test_data.get('canonical_name', test_id)
                self.canonical_names.append(canonical.lower())
                
                # Add canonical name as alias
                self.alias_to_id[canonical.lower()] = test_id
                
                # Add all aliases
                for alias in test_data.get('aliases', []):
                    self.alias_to_id[alias.lower().strip()] = test_id
            
            logger.info(f"Loaded {len(self.mappings)} test mappings with {len(self.alias_to_id)} aliases")
            
        except Exception as e:
            logger.error(f"Failed to load mappings from {path}: {e}")
            self.mappings = {}
            self.alias_to_id = {}
    
    def standardize(self, test_name: str) -> StandardizedTest:
        """
        Standardize a test name using the 3-tier approach.
        
        Args:
            test_name: Original test name from lab report
            
        Returns:
            StandardizedTest with canonical name and metadata
        """
        original = test_name.strip()
        name_lower = original.lower().strip()
        
        # Remove common suffixes/prefixes that might affect matching
        cleaned_name = self._clean_test_name(name_lower)
        
        # Tier 1: Exact match
        result = self._exact_match(original, cleaned_name)
        if result:
            return result
        
        # Tier 2: Fuzzy match
        result = self._fuzzy_match(original, cleaned_name)
        if result:
            return result
        
        # Tier 3: LLM fallback
        if self.use_llm_fallback:
            result = self._llm_match(original)
            if result:
                return result
        
        # No match found
        return StandardizedTest(
            original_name=original,
            canonical_name=original,  # Keep original
            loinc_code=None,
            category=None,
            unit=None,
            confidence=0.0,
            match_type='unknown',
            is_standardized=False
        )
    
    def _clean_test_name(self, name: str) -> str:
        """Clean test name for better matching."""
        # Remove common non-informative parts
        removals = [
            'serum', 'plasma', 'blood', 'level', 'levels',
            'test', 'assay', 'measurement', 'concentration',
            'total', 'random', 'automated', 'calculated'
        ]
        
        words = name.split()
        cleaned = [w for w in words if w.strip() not in removals]
        return ' '.join(cleaned)
    
    def _exact_match(
        self,
        original: str,
        cleaned: str
    ) -> Optional[StandardizedTest]:
        """Attempt exact alias matching."""
        # Try original name
        if original.lower() in self.alias_to_id:
            test_id = self.alias_to_id[original.lower()]
            return self._build_result(original, test_id, 1.0, 'exact')
        
        # Try cleaned name
        if cleaned != original.lower() and cleaned in self.alias_to_id:
            test_id = self.alias_to_id[cleaned]
            return self._build_result(original, test_id, 0.98, 'exact')
        
        return None
    
    def _fuzzy_match(
        self,
        original: str,
        cleaned: str
    ) -> Optional[StandardizedTest]:
        """Attempt fuzzy string matching."""
        if not self.alias_to_id:
            return None
        
        all_aliases = list(self.alias_to_id.keys())
        
        # Try matching against cleaned name first
        match = process.extractOne(
            cleaned,
            all_aliases,
            scorer=fuzz.ratio,
            score_cutoff=int(self.fuzzy_threshold * 100)
        )
        
        if match:
            matched_alias, score, _ = match
            test_id = self.alias_to_id[matched_alias]
            confidence = score / 100.0
            return self._build_result(original, test_id, confidence, 'fuzzy')
        
        # Try with token set ratio for reordered words
        match = process.extractOne(
            cleaned,
            all_aliases,
            scorer=fuzz.token_set_ratio,
            score_cutoff=int(self.fuzzy_threshold * 100)
        )
        
        if match:
            matched_alias, score, _ = match
            test_id = self.alias_to_id[matched_alias]
            # Slightly lower confidence for token matching
            confidence = (score / 100.0) * 0.95
            return self._build_result(original, test_id, confidence, 'fuzzy')
        
        return None
    
    def _llm_match(self, original: str) -> Optional[StandardizedTest]:
        """Use LLM to identify unknown test names."""
        # Check cache
        cache_key = original.lower().strip()
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]
        
        try:
            # Configure Gemini
            api_key = settings.gemini.api_key
            if not api_key:
                logger.warning("Gemini API key not set, skipping LLM fallback")
                return None
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(settings.gemini.model)
            
            # Sample of canonical names for context
            sample_names = list(self.canonical_names)[:50]
            names_str = ", ".join(sample_names)
            
            prompt = f"""
You are a medical laboratory terminology expert.

Given this lab test name from a report: "{original}"

What is the standard/canonical name for this test?

Here are some example standardized test names: {names_str}

RULES:
1. Return the most common standard name used in medical practice
2. If it's a well-known test, return its standard name
3. If you cannot determine the standard name, return "UNKNOWN"
4. Return ONLY the standardized name, nothing else

Standard name:"""

            response = model.generate_content(prompt)
            standardized_name = response.text.strip()
            
            if standardized_name and standardized_name.upper() != "UNKNOWN":
                # Check if the LLM response matches any known canonical name
                for test_id, test_data in self.mappings.items():
                    canonical = test_data.get('canonical_name', '')
                    if standardized_name.lower() == canonical.lower():
                        result = self._build_result(original, test_id, 0.7, 'llm')
                        self._llm_cache[cache_key] = result
                        return result
                
                # LLM gave a name but we don't have it mapped
                result = StandardizedTest(
                    original_name=original,
                    canonical_name=standardized_name,
                    loinc_code=None,
                    category=None,
                    unit=None,
                    confidence=0.6,
                    match_type='llm',
                    is_standardized=True
                )
                self._llm_cache[cache_key] = result
                return result
            
        except Exception as e:
            logger.warning(f"LLM standardization failed for '{original}': {e}")
        
        return None
    
    def _build_result(
        self,
        original: str,
        test_id: str,
        confidence: float,
        match_type: str
    ) -> StandardizedTest:
        """Build a StandardizedTest from a test_id."""
        test_data = self.mappings.get(test_id, {})
        
        return StandardizedTest(
            original_name=original,
            canonical_name=test_data.get('canonical_name', original),
            loinc_code=test_data.get('loinc_code'),
            category=test_data.get('category'),
            unit=test_data.get('unit'),
            confidence=confidence,
            match_type=match_type,
            is_standardized=True
        )
    
    def standardize_batch(
        self,
        test_names: List[str]
    ) -> List[StandardizedTest]:
        """
        Standardize multiple test names.
        
        Args:
            test_names: List of test names to standardize
            
        Returns:
            List of StandardizedTest objects
        """
        return [self.standardize(name) for name in test_names]
    
    def get_canonical_names(self) -> List[str]:
        """Get list of all canonical test names."""
        return [
            data.get('canonical_name', test_id)
            for test_id, data in self.mappings.items()
        ]
    
    def get_test_info(self, canonical_name: str) -> Optional[Dict[str, Any]]:
        """Get full test information by canonical name."""
        for test_id, data in self.mappings.items():
            if data.get('canonical_name', '').lower() == canonical_name.lower():
                return {
                    'test_id': test_id,
                    **data
                }
        return None


# Global standardizer instance (lazy initialization)
_standardizer: Optional[TestNameStandardizer] = None


def get_standardizer() -> TestNameStandardizer:
    """Get or create the global standardizer instance."""
    global _standardizer
    if _standardizer is None:
        _standardizer = TestNameStandardizer(
            fuzzy_threshold=settings.standardization.fuzzy_threshold,
            use_llm_fallback=settings.standardization.llm_fallback
        )
    return _standardizer


def standardize_test_name(test_name: str) -> StandardizedTest:
    """
    Convenience function to standardize a single test name.
    
    Args:
        test_name: Original test name from lab report
        
    Returns:
        StandardizedTest with canonical name and metadata
    """
    return get_standardizer().standardize(test_name)


def standardize_lab_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Standardize test names in a list of lab results.
    
    Args:
        results: List of lab result dictionaries with 'test_name' key
        
    Returns:
        List of results with added standardization fields
    """
    standardizer = get_standardizer()
    standardized_results = []
    
    for result in results:
        test_name = result.get('test_name', '')
        if not test_name:
            standardized_results.append(result)
            continue
        
        std = standardizer.standardize(test_name)
        
        # Add standardization fields to result
        enhanced_result = {
            **result,
            'original_name': std.original_name,
            'test_name': std.canonical_name,  # Replace with canonical
            'loinc_code': std.loinc_code,
            'standardization': {
                'is_standardized': std.is_standardized,
                'confidence': std.confidence,
                'match_type': std.match_type
            }
        }
        
        # Add category from mapping if not already present
        if std.category and not result.get('category'):
            enhanced_result['category'] = std.category
        
        # Add unit from mapping if not already present (fallback for missing units)
        if std.unit and not result.get('unit'):
            enhanced_result['unit'] = std.unit
        
        standardized_results.append(enhanced_result)
    
    return standardized_results
