"""
Semantic Similarity Matcher for Lab Test Names.

Uses lightweight sentence embeddings to find similar test names,
then optionally falls back to LLM for final categorization with context.

This approach is more robust than pure fuzzy matching because it understands
semantic meaning (e.g., "Blood Sugar" is similar to "Glucose" even though
they share few characters).
"""

import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
import numpy as np

# Try to import sentence-transformers, fall back gracefully if not available
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

import google.generativeai as genai
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SemanticMatch:
    """Result of semantic similarity matching."""
    original_name: str
    canonical_name: str
    loinc_code: Optional[str]
    category: Optional[str]
    similarity_score: float
    confidence: float
    match_type: str  # exact, semantic, llm, unknown
    similar_terms: List[Tuple[str, float]]  # Top similar terms for context


class SemanticMatcher:
    """
    Matches lab test names using semantic similarity.
    
    Flow:
    1. Exact match against known aliases
    2. Compute embedding similarity against all known tests
    3. If high confidence match (>0.85), use it directly
    4. Otherwise, use LLM with top-5 similar terms as context
    """
    
    # Lightweight model for embeddings (~90MB)
    MODEL_NAME = "all-MiniLM-L6-v2"
    
    def __init__(
        self,
        test_definitions: Dict[str, Dict[str, Any]],
        similarity_threshold: float = 0.85,
        use_llm_fallback: bool = True
    ):
        """
        Initialize the semantic matcher.
        
        Args:
            test_definitions: Dict of test_key -> {canonical_name, loinc_code, aliases, ...}
            similarity_threshold: Minimum similarity for auto-matching
            use_llm_fallback: Whether to use LLM for uncertain matches
        """
        self.test_definitions = test_definitions
        self.similarity_threshold = similarity_threshold
        self.use_llm_fallback = use_llm_fallback
        
        # Build lookup structures
        self.canonical_names: List[str] = []
        self.test_keys: List[str] = []
        self.alias_to_key: Dict[str, str] = {}
        
        for test_key, data in test_definitions.items():
            canonical = data.get('canonical_name', test_key)
            self.canonical_names.append(canonical)
            self.test_keys.append(test_key)
            
            # Index aliases
            self.alias_to_key[canonical.lower()] = test_key
            for alias in data.get('aliases', []):
                self.alias_to_key[alias.lower().strip()] = test_key
        
        # Initialize embedding model (lazy load)
        self._model = None
        self._embeddings = None
        
        logger.info(
            f"SemanticMatcher initialized with {len(self.test_definitions)} tests, "
            f"embeddings_available={EMBEDDINGS_AVAILABLE}"
        )
    
    def _load_model(self) -> bool:
        """Lazy load the embedding model and compute test embeddings."""
        if not EMBEDDINGS_AVAILABLE:
            logger.warning("sentence-transformers not available, semantic matching disabled")
            return False
        
        if self._model is not None:
            return True
        
        try:
            logger.info(f"Loading embedding model: {self.MODEL_NAME}")
            self._model = SentenceTransformer(self.MODEL_NAME)
            
            # Pre-compute embeddings for all canonical names
            self._embeddings = self._model.encode(
                self.canonical_names,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            
            logger.info(f"Computed embeddings for {len(self.canonical_names)} tests")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._model = None
            return False
    
    def match(self, test_name: str) -> SemanticMatch:
        """
        Find the best matching standardized test for the given name.
        
        Args:
            test_name: Original test name from lab report
            
        Returns:
            SemanticMatch with best match and confidence
        """
        original = test_name.strip()
        name_lower = original.lower().strip()
        
        # Step 1: Exact alias match
        if name_lower in self.alias_to_key:
            test_key = self.alias_to_key[name_lower]
            data = self.test_definitions[test_key]
            return SemanticMatch(
                original_name=original,
                canonical_name=data.get('canonical_name', test_key),
                loinc_code=data.get('loinc_code'),
                category=data.get('category'),
                similarity_score=1.0,
                confidence=1.0,
                match_type='exact',
                similar_terms=[]
            )
        
        # Step 2: Semantic similarity
        similar_terms = self._find_similar(original)
        
        if similar_terms:
            top_match, top_score = similar_terms[0]
            
            # High confidence semantic match
            if top_score >= self.similarity_threshold:
                test_key = self._get_key_for_canonical(top_match)
                data = self.test_definitions.get(test_key, {})
                return SemanticMatch(
                    original_name=original,
                    canonical_name=top_match,
                    loinc_code=data.get('loinc_code'),
                    category=data.get('category'),
                    similarity_score=top_score,
                    confidence=top_score,
                    match_type='semantic',
                    similar_terms=similar_terms[:5]
                )
        
        # Step 3: LLM fallback with context
        if self.use_llm_fallback and similar_terms:
            return self._llm_match_with_context(original, similar_terms[:5])
        
        # No match found
        return SemanticMatch(
            original_name=original,
            canonical_name=original,
            loinc_code=None,
            category=None,
            similarity_score=0.0,
            confidence=0.0,
            match_type='unknown',
            similar_terms=similar_terms[:5] if similar_terms else []
        )
    
    def _find_similar(self, text: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        Find the most similar canonical test names using embeddings.
        
        Args:
            text: Text to match
            top_k: Number of top matches to return
            
        Returns:
            List of (canonical_name, similarity_score) tuples
        """
        if not self._load_model():
            return []
        
        try:
            # Encode query
            query_embedding = self._model.encode(
                [text],
                convert_to_numpy=True,
                normalize_embeddings=True
            )[0]
            
            # Compute cosine similarity (embeddings are normalized)
            similarities = np.dot(self._embeddings, query_embedding)
            
            # Get top-k indices
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                score = float(similarities[idx])
                if score > 0.3:  # Minimum threshold
                    results.append((self.canonical_names[idx], score))
            
            return results
            
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []
    
    def _get_key_for_canonical(self, canonical_name: str) -> Optional[str]:
        """Get test key for a canonical name."""
        for test_key, data in self.test_definitions.items():
            if data.get('canonical_name') == canonical_name:
                return test_key
        return None
    
    def _llm_match_with_context(
        self,
        original: str,
        similar_terms: List[Tuple[str, float]]
    ) -> SemanticMatch:
        """
        Use LLM to categorize the test with similar terms as context.
        
        Args:
            original: Original test name
            similar_terms: List of (canonical_name, score) for context
            
        Returns:
            SemanticMatch from LLM decision
        """
        try:
            api_key = settings.gemini.api_key
            if not api_key:
                return self._unknown_match(original, similar_terms)
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(settings.gemini.model)
            
            # Build context with similar terms
            context_lines = []
            for name, score in similar_terms:
                context_lines.append(f"- {name} (similarity: {score:.2f})")
            context = "\n".join(context_lines)
            
            prompt = f"""You are a medical laboratory terminology expert.

Given this lab test name from a report: "{original}"

Here are the most similar standardized test names (with similarity scores):
{context}

TASK: Determine which standardized test (if any) this refers to.

RULES:
1. If the original clearly matches one of the similar tests, return that test name
2. If it's a common test but not in the list, return a reasonable standard name
3. If you cannot determine what test this is, return "UNKNOWN"

Return ONLY a JSON object with this format:
{{"canonical_name": "...", "confidence": 0.0-1.0, "reasoning": "..."}}
"""

            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Parse JSON response
            import json
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            canonical = result.get('canonical_name', 'UNKNOWN')
            confidence = float(result.get('confidence', 0.5))
            
            if canonical == 'UNKNOWN' or not canonical:
                return self._unknown_match(original, similar_terms)
            
            # Find matching test definition
            test_key = self._get_key_for_canonical(canonical)
            data = self.test_definitions.get(test_key, {}) if test_key else {}
            
            return SemanticMatch(
                original_name=original,
                canonical_name=canonical,
                loinc_code=data.get('loinc_code'),
                category=data.get('category'),
                similarity_score=similar_terms[0][1] if similar_terms else 0.0,
                confidence=confidence,
                match_type='llm',
                similar_terms=similar_terms
            )
            
        except Exception as e:
            logger.warning(f"LLM matching failed for '{original}': {e}")
            return self._unknown_match(original, similar_terms)
    
    def _unknown_match(
        self,
        original: str,
        similar_terms: List[Tuple[str, float]]
    ) -> SemanticMatch:
        """Return unknown match result."""
        return SemanticMatch(
            original_name=original,
            canonical_name=original,
            loinc_code=None,
            category=None,
            similarity_score=similar_terms[0][1] if similar_terms else 0.0,
            confidence=0.0,
            match_type='unknown',
            similar_terms=similar_terms
        )
    
    def batch_match(self, test_names: List[str]) -> List[SemanticMatch]:
        """Match multiple test names."""
        return [self.match(name) for name in test_names]


# Global instance (lazy initialization)
_semantic_matcher: Optional[SemanticMatcher] = None


def get_semantic_matcher() -> SemanticMatcher:
    """Get or create the global semantic matcher."""
    global _semantic_matcher
    
    if _semantic_matcher is None:
        import yaml
        from pathlib import Path
        
        # Load test definitions
        mappings_path = Path(__file__).parent.parent.parent / "config" / "test_mappings.yaml"
        
        try:
            with open(mappings_path) as f:
                data = yaml.safe_load(f)
            test_definitions = data.get('mappings', {})
        except Exception as e:
            logger.error(f"Failed to load test mappings: {e}")
            test_definitions = {}
        
        _semantic_matcher = SemanticMatcher(
            test_definitions=test_definitions,
            similarity_threshold=settings.standardization.fuzzy_threshold,
            use_llm_fallback=settings.standardization.llm_fallback
        )
    
    return _semantic_matcher


def match_test_semantic(test_name: str) -> SemanticMatch:
    """Convenience function for semantic matching."""
    return get_semantic_matcher().match(test_name)
