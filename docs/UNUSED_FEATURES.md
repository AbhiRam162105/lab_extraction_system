# Unused Features Analysis

**Generated:** 2025-12-12  
**Purpose:** Document coded features that are not currently used in production, with recommendations for keeping or removing.

---

## Summary

| Feature | Location | Status | Recommendation |
|---------|----------|--------|----------------|
| `get_global_test_trends()` | `main.py` | Never called | ✅ **KEEP** |
| `get_patient_all_tests()` | `main.py` | Never called | ✅ **KEEP** |
| `BatchProcessor` | `batch_processor.py` | Exported but unused | ✅ **KEEP** |
| `compare_extractions()` | `validation.py` | Never called | ❌ **REMOVE** |
| `validate_extraction_results()` | `validation.py` | Never called | ⚠️ **REVIEW** |
| `quick_quality_check()` | `ocr_quality.py` | Tests only | ✅ **KEEP** |
| `simulate_blur()` | `ocr_quality.py` | Tests only | ✅ **KEEP** |
| `acquire_async()` | `rate_limiter.py` | Commented out | ❌ **REMOVE** |
| `find_similar_by_phash()` | `cache_manager.py` | Never called | ✅ **KEEP** |
| `cache_partial_result()` | `cache_manager.py` | Tests only | ✅ **KEEP** |
| `get_perceptual_hash()` | `cache_manager.py` | Never called | ✅ **KEEP** |
| `_llm_validate()` | `single_vision_extractor.py` | Defined but not always used | ⚠️ **REVIEW** |
| `_llm_panel_match()` | `strict_normalizer.py` | Fallback path | ✅ **KEEP** |
| `phash` DB field | `backend/models/db.py` | Stored but never queried | ⚠️ **REVIEW** |

---

## Features to KEEP (Future Value)

### 1. Analytics Functions (`main.py`)

```python
# Lines 313-384
get_global_test_trends(session, canonical_test_name, patient_id, limit)
get_patient_all_tests(session, patient_id)
```

**Why Keep:**
- Essential for patient health tracking over time
- Enables trend analysis (e.g., "Show Hemoglobin trend for last 6 months")
- Uses canonical test names for cross-lab compatibility
- Ready for API integration when analytics dashboard is built

**Action Required:** Create API endpoints in `backend/api/` to expose these functions.

---

### 2. Batch Processor (`batch_processor.py`)

```python
class BatchProcessor:
    async def process_batch(document_ids, priority="normal")
    def get_job_status(job_id)
    def list_jobs(limit=20)
```

**Why Keep:**
- Enables bulk document processing with concurrency control
- Built-in progress tracking via Redis
- Essential for processing large document uploads
- Rate limit aware - prevents API throttling

**Action Required:** Create batch processing API endpoint or CLI command.

---

### 3. Similar Document Detection (`cache_manager.py`)

```python
def find_similar_by_phash(phash, all_phashes) -> List[Tuple[doc_id, distance]]
def get_perceptual_hash(image_path) -> str
```

**Why Keep:**
- Detects duplicate/near-duplicate lab reports
- Prevents processing the same document twice
- Can flag potential data quality issues

**Action Required:** Wire into document upload flow to warn about duplicates.

---

### 4. Partial Result Caching (`cache_manager.py`)

```python
def cache_partial_result(image_hash, stage, result)
def get_partial_result(image_hash, stage) -> Any
```

**Why Keep:**
- Enables resume from failure (e.g., if pass 2 fails, restart from pass 1 results)
- Reduces API costs on retries
- Useful for debugging extraction pipeline

**Action Required:** Integrate into extraction pipeline for fault tolerance.

---

### 5. Testing Utilities (`ocr_quality.py`)

```python
def quick_quality_check(image) -> Tuple[bool, reason]
def simulate_blur(image, radius) -> Image
```

**Why Keep:**
- `quick_quality_check`: Fast pre-filter before expensive extraction
- `simulate_blur`: Essential for testing blur detection thresholds
- Both are used in unit tests

**Status:** Currently used correctly as testing/utility functions.

---

## Features to REMOVE (Dead Code)

### 1. `compare_extractions()` in `validation.py`

```python
# Lines 246-334
def compare_extractions(vision_only, three_tier, tolerance=0.1)
```

**Why Remove:**
- Was designed to compare "vision-only" vs "three-tier" extraction
- Three-tier extraction has been replaced by single-vision pipeline
- No longer relevant to current architecture

**Safe to Delete:** Yes

---

### 2. `acquire_async()` in `rate_limiter.py`

```python
# Lines 83-92 (commented out)
# async def acquire_async(self) -> None:
#     """Async version of acquire."""
#     ...
```

**Why Remove:**
- Completely commented out
- Tests reference it but the method doesn't exist
- Current pipeline uses synchronous `acquire()`

**Action:** Delete commented code and fix/remove related tests.

---

## Features to REVIEW

### `validate_extraction_results()` in `validation.py`

```python
# Lines 177-243
def validate_extraction_results(lab_results, raw_text=None)
```

**Status:** Defined but never called.

**Potential Value:**
- Validates against whitelist of known tests
- Checks for hallucinated tests
- Validates physiological ranges

**Decision Needed:**
- If duplicate of `_validate_results()` in `single_vision_extractor.py` → **REMOVE**
- If provides additional validation → **INTEGRATE**

---

## Implementation Priority

If you decide to wire up the unused features:

1. **High Priority:** Analytics functions (`get_global_test_trends`, `get_patient_all_tests`)
   - Immediate user value for trend tracking

2. **Medium Priority:** Batch processing
   - Needed for bulk uploads

3. **Low Priority:** Duplicate detection
   - Nice-to-have, not blocking

---

## Quick Cleanup Commands

To remove dead code:

```bash
# Remove compare_extractions function (lines 246-334 in validation.py)
# Remove commented acquire_async (lines 83-92 in rate_limiter.py)
```

To verify removal is safe:

```bash
# Search for any references before deleting
grep -r "compare_extractions" --include="*.py" .
grep -r "acquire_async" --include="*.py" .
```

---

## Additional Underutilized Features

### 6. Perceptual Hashing System

**Components:**

| Component | Location | Status |
|-----------|----------|--------|
| `get_perceptual_hash()` | `cache_manager.py:149` | Defined, never called from extraction |
| `find_similar_by_phash()` | `cache_manager.py:174` | Defined, never called |
| `phash` field | `backend/models/db.py:15` | Stored on upload, never queried |
| `PHASH_AVAILABLE` | `cache_manager.py:32` | Conditional import for imagehash |

**Current State:**
- `phash` is calculated and stored in DB during document upload (`backend/api/documents.py:92`)
- But **no code ever queries** the phash to find duplicates
- `find_similar_by_phash()` exists but is never called

**Why Keep:**
- Infrastructure is in place
- Just needs API endpoint to expose duplicate detection
- Valuable for preventing duplicate processing

**Integration Needed:**
```python
# In backend/api/documents.py - add duplicate check before processing
phash = optimizer.get_perceptual_hash(file_path)
similar_docs = cache.find_similar_by_phash(phash, existing_phashes)
if similar_docs:
    return {"warning": "Similar document already exists", "similar_ids": similar_docs}
```

---

### 7. LLM Validation Pass (`_llm_validate`)

**Location:** `single_vision_extractor.py:567-635`

```python
def _llm_validate(self, results: List[Dict[str, Any]], image) -> List[Dict[str, Any]]:
    """LLM Validation Pass (API Call 2)."""
```

**Current State:**
- Called at line 206 in the extraction pipeline
- Uses a **second Gemini API call** to validate extracted results
- Runs AFTER initial extraction

**Issue:** 
- This is an expensive operation (extra API call per document)
- Currently always runs, consuming API quota
- May not provide significant value vs rule-based validation

**Recommendation:** ⚠️ **REVIEW**
- Consider making LLM validation **optional** (config flag)
- Or replace with cheaper rule-based validation from `quality_verifier.py`
- Keep for high-stakes documents, skip for routine processing

---

### 8. LLM Panel Match (`_llm_panel_match`)

**Location:** `strict_normalizer.py:422-461`

```python
def _llm_panel_match(self, raw_name: str, panel: str) -> Optional[str]:
    """LLM match RESTRICTED to panel subset."""
```

**Current State:**
- Called as **fallback** at line 416 when Levenshtein matching fails
- Uses Gemini to match unknown test names to canonical names
- Panel-scoped to prevent hallucination

**Status:** ✅ **KEEP** - This is working as intended (fallback for edge cases)

---

## Summary of New Findings

| Feature | Status | Cost Impact | Action |
|---------|--------|-------------|--------|
| Perceptual hashing | ❌ Not wired | None (stored but unused) | Wire into upload flow |
| `_llm_validate()` | ⚠️ Always runs | Extra API call/doc | Make optional |
| `_llm_panel_match()` | ✅ Working | Only on fallback | Keep as-is |
| `phash` DB field | ⚠️ Never queried | Wastes storage | Use it or remove |

