# Configuration Reference

Complete reference for all settings, thresholds, and tunable parameters in the Lab Extraction System.

---

## Quick Start

1. Copy `.env.example` to `.env`
2. Set `GEMINI__API_KEY` (required)
3. Adjust other settings as needed

---

## Environment Variables (.env)

### Gemini API (Required)

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI__API_KEY` | *(required)* | Your Gemini API key from Google AI Studio |
| `GEMINI__MODEL` | `gemma-3-27b-it` | Model to use (`gemma-3-12b-it`, `gemini-2.5-flash`) |
| `GEMINI__RATE_LIMIT` | `15` | Max requests per minute |

---

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE__URL` | `sqlite:///./lab_extraction.db` | Database connection string |
| `DB_PASSWORD` | `labextract2024` | PostgreSQL password (Docker) |

**Connection String Examples:**
```bash
# SQLite (local development)
DATABASE__URL=sqlite:///./lab_extraction.db

# PostgreSQL (Docker/production)
DATABASE__URL=postgresql://postgres:password@postgres:5432/lab_extraction
```

---

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS__URL` | `redis://localhost:6379/0` | Redis connection URL |

---

### Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `PROCESSING__MAX_RETRIES` | `3` | Retry attempts on failure |
| `PROCESSING__TIMEOUT` | `300` | Timeout in seconds |
| `PROCESSING__BATCH_SIZE` | `15` | Documents per batch |
| `PROCESSING__MAX_CONCURRENT_WORKERS` | `32` | Max parallel workers |
| `PROCESSING__ENABLE_CACHING` | `true` | Enable result caching |
| `PROCESSING__CACHE_TTL_HOURS` | `24` | Cache expiry time |

---

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMITING__REQUESTS_PER_MINUTE` | `15` | Max Gemini API requests/min |
| `RATE_LIMITING__ADAPTIVE_BACKOFF` | `true` | Reduce rate on 429 errors |
| `RATE_LIMITING__BACKOFF_FACTOR` | `0.8` | Reduce to 80% on error |
| `RATE_LIMITING__RECOVERY_THRESHOLD` | `10` | Successes before recovery |

---

### Preprocessing

| Variable | Default | Description |
|----------|---------|-------------|
| `PREPROCESSING__PARALLEL_WORKERS` | `8` | Parallel image processors |
| `PREPROCESSING__QUALITY_THRESHOLD` | `100` | Min quality score to accept |
| `PREPROCESSING__MAX_DIMENSION` | `2048` | Max image width/height |
| `PREPROCESSING__JPEG_QUALITY` | `85` | JPEG compression quality (0-100) |

---

### Standardization

| Variable | Default | Description |
|----------|---------|-------------|
| `STANDARDIZATION__FUZZY_THRESHOLD` | `0.85` | Min similarity for fuzzy match (0-1) |
| `STANDARDIZATION__LLM_FALLBACK` | `true` | Use LLM if fuzzy match fails |

---

### Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE__BASE_PATH` | `storage` | Root storage directory |
| `STORAGE__BUCKET` | `lab-reports` | Subdirectory for reports |

---

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `API_URL` | `http://localhost:6000/api/v1` | Backend API URL |

---

## Code-Level Settings

### Image Optimization (`backend/utils/image_optimizer.py`)

```python
OptimizationConfig(
    jpeg_quality=85,                    # 0-100
    webp_quality=85,                    # 0-100
    use_webp=False,                     # Use WebP instead of JPEG
    max_dimension=2048,                 # Resize if larger
    min_dimension=500,                  # Don't resize below this
    delete_originals_after_days=10,     # Cleanup policy
    delete_processed_after_days=90,     # Final cleanup
    enable_deduplication=True           # Skip exact duplicates
)
```

---

### Image Preprocessing (`workers/extraction/preprocessing.py`)

```python
ImagePreprocessor(
    target_dpi=300,                     # Target resolution
    deskew_enabled=True,                # Auto-rotate tilted docs
    denoise_enabled=True,               # Reduce noise
    contrast_enhance_enabled=True,      # CLAHE enhancement
    binarize_enabled=False              # Convert to B&W (usually off)
)
```

---

### OCR Quality Gate (`workers/extraction/ocr_quality.py`)

```python
QUALITY_THRESHOLDS = {
    'min_resolution': 400,              # Min dimension in pixels
    'blur_score': 50,                   # Min blur score to accept
    'blur_score_critical': 25,          # Immediate reject below this
    'contrast_min': 35,                 # Min contrast value
    'contrast_max': 90,                 # Max before noise warning
    'brightness_min': 50,               # Reject if too dark
    'brightness_max': 220,              # Reject if washed out
    'text_density_min': 0.03,           # Min text-like content
    'skew_angle_max': 5.0,              # Max rotation in degrees
    'noise_threshold': 0.15             # Max noise level (0-1)
}
```

**Acceptance Logic:**
```python
ACCEPT if:
    score >= 0.3
    AND text_clarity >= 0.20
    AND blur_score >= 25
    AND NOT (contrast > 85 AND clarity < 0.45)  # Noisy scan pattern
```

---

### Rate Limiter (`workers/extraction/rate_limiter.py`)

```python
RateLimitConfig(
    requests_per_minute=15,             # Base limit
    window_seconds=60.0,                # Sliding window size
    adaptive_backoff=True,              # Auto-reduce on 429
    backoff_factor=0.8,                 # Reduce by 20% on error
    recovery_threshold=10,              # Successes before recovery
    min_requests_per_minute=5           # Never go below this
)
```

---

### Cache Manager (`workers/extraction/cache_manager.py`)

```python
CacheConfig(
    redis_enabled=True,                 # Use Redis (Tier 1)
    disk_enabled=True,                  # Use disk (Tier 2)
    compression_enabled=True,           # zstd compression
    redis_ttl_hours=24,                 # Redis expiry
    disk_cache_dir="storage/cache",     # Disk cache location
    max_disk_cache_size_mb=5000,        # 5GB limit
    hash_algorithm="sha256",            # Hash for cache keys
    phash_similarity_threshold=5        # Max Hamming distance
)
```

---

### Normalizer (`workers/extraction/strict_normalizer.py`)

```python
NormalizerConfig = {
    'fuzzy_threshold': 0.85,            # Levenshtein similarity
    'llm_panel_restricted': True,       # Limit LLM to detected panel
    'max_llm_calls_per_doc': 10,        # Limit LLM usage
    'canonical_mappings': 'config/test_mappings.yaml'
}
```

---

## Test Mappings (`config/test_mappings.yaml`)

Defines canonical test names, aliases, and reference ranges:

```yaml
tests:
  - canonical_name: "Hemoglobin"
    aliases:
      - "Hb"
      - "HGB"
      - "Haemoglobin"
    category: "Hematology"
    loinc_code: "718-7"
    unit: "g/dL"
    reference_ranges:
      male: [13.5, 17.5]
      female: [12.0, 16.0]
```

---

## Docker Settings (`docker-compose.yaml`)

| Service | Port | Environment |
|---------|------|-------------|
| Backend | 6000 | Uses `.env` |
| Frontend | 8501 | Uses `API_URL` |
| Worker | - | Uses `.env` |
| Redis | 6379 | Default |
| PostgreSQL | 5432 | Uses `DB_PASSWORD` |

---

## Performance Tuning Guide

### Low Resources (Free Tier)

```bash
GEMINI__RATE_LIMIT=5
PROCESSING__MAX_CONCURRENT_WORKERS=4
PREPROCESSING__PARALLEL_WORKERS=2
```

### High Throughput (Paid API)

```bash
GEMINI__RATE_LIMIT=60
PROCESSING__MAX_CONCURRENT_WORKERS=32
PREPROCESSING__PARALLEL_WORKERS=8
PROCESSING__BATCH_SIZE=50
```

### Memory Constrained

```bash
PREPROCESSING__MAX_DIMENSION=1024
PROCESSING__BATCH_SIZE=5
```

---

## Quality Tuning

### Stricter Quality (Fewer Errors)

```python
QUALITY_THRESHOLDS = {
    'blur_score': 100,            # Higher = stricter
    'text_clarity_min': 0.4,      # Higher = stricter
    'contrast_min': 45,           # Higher = stricter
}
```

### Lenient Quality (More Throughput)

```python
QUALITY_THRESHOLDS = {
    'blur_score': 30,             # Lower = more lenient
    'text_clarity_min': 0.15,     # Lower = more lenient
    'contrast_min': 25,           # Lower = more lenient
}
```

---

## Standardization Tuning

### Higher Match Accuracy

```bash
STANDARDIZATION__FUZZY_THRESHOLD=0.90  # Stricter matching
STANDARDIZATION__LLM_FALLBACK=true     # Use LLM for unknowns
```

### Faster Processing

```bash
STANDARDIZATION__FUZZY_THRESHOLD=0.80  # More lenient matching
STANDARDIZATION__LLM_FALLBACK=false    # Skip LLM calls
```

---

## All Environment Variables Summary

```bash
# === REQUIRED ===
GEMINI__API_KEY=your_key_here

# === API ===
GEMINI__MODEL=gemma-3-27b-it
GEMINI__RATE_LIMIT=15

# === Database ===
DATABASE__URL=postgresql://postgres:password@postgres:5432/lab_extraction
DB_PASSWORD=labextract2024

# === Redis ===
REDIS__URL=redis://localhost:6379/0

# === Processing ===
PROCESSING__MAX_RETRIES=3
PROCESSING__TIMEOUT=300
PROCESSING__BATCH_SIZE=15
PROCESSING__MAX_CONCURRENT_WORKERS=32
PROCESSING__ENABLE_CACHING=true
PROCESSING__CACHE_TTL_HOURS=24

# === Rate Limiting ===
RATE_LIMITING__REQUESTS_PER_MINUTE=15
RATE_LIMITING__ADAPTIVE_BACKOFF=true
RATE_LIMITING__BACKOFF_FACTOR=0.8
RATE_LIMITING__RECOVERY_THRESHOLD=10

# === Preprocessing ===
PREPROCESSING__PARALLEL_WORKERS=8
PREPROCESSING__QUALITY_THRESHOLD=100
PREPROCESSING__MAX_DIMENSION=2048
PREPROCESSING__JPEG_QUALITY=85

# === Standardization ===
STANDARDIZATION__FUZZY_THRESHOLD=0.85
STANDARDIZATION__LLM_FALLBACK=true

# === Storage ===
STORAGE__BASE_PATH=storage
STORAGE__BUCKET=lab-reports

# === Frontend ===
API_URL=http://localhost:6000/api/v1
```
