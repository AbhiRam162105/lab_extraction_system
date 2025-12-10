# Call tree and file-by-file guide

This document explains how a request moves through the system and maps each repository file to the functions it exposes or triggers.

## Runtime call tree (happy-path)

- **Startup**
  - `start.sh` boots Redis/PostgreSQL (if running locally), then launches:
    - `backend/main.py` via `uvicorn backend.main:app`.
      - `on_startup()` → `create_db_and_tables()` (in `backend/core/database.py`) → `_init_test_definitions()` loads YAML from `config/test_mappings.yaml` into `StandardizedTestDefinition`.
    - `workers/extraction/main.py` via `rq worker` → waits for jobs named `process_document`.
    - `frontend_app/main.py` via `streamlit run` to serve the UI.
- **Upload & extraction path**
  - User clicks **Process Files** in `frontend_app/main.py` → `POST /api/v1/upload`.
  - `backend/api/documents.py::upload_files()`:
    - Saves uploads to storage, runs `backend/utils/image_optimizer.get_optimizer().optimize_and_store()`.
    - Persists `Document` rows via `get_session()` (from `backend/core/database.py`).
    - Enqueues `workers.extraction.main.process_document` through `get_queue()` (in `backend/core/queue.py`).
  - Background worker `workers/extraction/main.py::process_document()`:
    - Looks up the `Document`, marks stages, then calls `SingleVisionExtractor.extract()` (in `workers/extraction/single_vision_extractor.py`).
    - The extractor pipeline triggers:
      - `workers.extraction.preprocessing.preprocess_image()` for image cleanup.
      - OCR quality gating via `workers.extraction.ocr_quality.evaluate_ocr_quality()`.
      - Deterministic normalization with `StrictNormalizer.normalize()` (`workers/extraction/strict_normalizer.py`).
      - Panel completeness checks using `validate_panel_completeness()` (`workers/extraction/panel_validator.py`).
      - Summary generation via `generate_safe_summary()` (`workers/extraction/safe_summary.py`).
      - Quality verification via `verify_extraction_quality()` (`workers/extraction/quality_verifier.py`).
      - Adaptive throttling through `get_rate_limiter()` (`workers/extraction/rate_limiter.py`) and caching through `CacheManager` (`workers/extraction/cache_manager.py`).
    - Results are stored in `ExtractionResult` and normalized rows are saved through `_save_normalized_tests()` into `PatientTest`.
- **Dashboard & analytics paths**
  - `frontend_app/main.py` Dashboard tab uses:
    - `GET /api/v1/documents` → `backend/api/documents.get_documents()`.
    - `GET /api/v1/documents/flagged` → `backend/api/documents.get_flagged_documents()`.
    - `GET /api/v1/results/{id}` → `backend/api/documents.get_results()`.
  - `frontend_app/pages/1_Global_Tests.py` calls `backend/api/tests.py` endpoints:
    - `/tests/all`, `/tests/categories`, `/tests/stats` for listing and stats.
    - `/tests/export` to download CSV/Excel.
    - `/tests/pivot`, `/tests/patient/{patient_id}/history`, `/tests/trends/{test_name}` for aggregations.
  - `frontend_app/pages/2_Performance.py` monitors:
    - `/documents` and `/tests/stats` for counts.
    - `/tests/timing-stats` to plot per-pass timings.
  - `frontend_app/pages/3_Approach_Comparison.py` posts to `/compare-approaches` (deployment must provide the matching backend handler for this comparison workflow).
- **Storage & ops**
  - `backend/api/storage.py` exposes `/storage/stats`, `/storage/cleanup`, `/storage/cache-stats`, `/storage/rate-limit-stats`:
    - Calls `_count_files_by_type()`, interacts with `Document` records, and surfaces stats from `CacheManager.get_stats()` and `AdaptiveRateLimiter.get_stats()`.

## File-by-file explanations

### Root
- `README.md`: Product overview, pipeline description, and quick start.
- `README_TESTING.md`: Instructions for running the test suite.
- `.env.example`: Template environment variables consumed by `backend/core/config.py`.
- `.dockerignore`: Excludes build artifacts from Docker build context.
- `Dockerfile.backend`, `Dockerfile.frontend`, `Dockerfile.worker`: Container builds for FastAPI, Streamlit, and RQ worker respectively.
- `docker-compose.yaml`: Orchestrates Redis, Postgres, backend, frontend, and worker services.
- `requirements.txt`, `requirements-dev.txt`, `requirements-test.txt`: Python dependency sets for runtime, development, and testing.
- `pytest.ini`: Pytest defaults.
- `run_tests.sh`: Convenience wrapper running selected unit tests.
- `start.sh`: Local launcher wiring Redis/Postgres checks, then starting backend/worker/frontend processes; traps signals and cleans up.
- `wait_for_service.py`: Helper to block until a host:port is reachable; used by orchestration scripts.
- `scripts/test_pipeline.py`: CLI load-test helper that uploads many images, polls `/results/{id}`, and saves responses.
- `storage/`: Default local storage root for uploads and cache artifacts (created at runtime).

### `backend/` (FastAPI app)
- `backend/main.py`: Builds the FastAPI app, configures CORS/static mounts, seeds test definitions on startup, and registers routers; exposes `/health` endpoints.
- `backend/core/config.py`: Loads `config/settings.yaml` with environment substitution and builds typed `Settings` objects.
- `backend/core/database.py`: Creates the SQLModel engine, `create_db_and_tables()`, and the `get_session()` dependency.
- `backend/core/queue.py`: Configures the Redis-backed RQ queue and `get_queue()` dependency.
- `backend/api/documents.py`: Upload/status/result endpoints; orchestrates image optimization, duplicate detection, DB writes, and enqueues `process_document`.
- `backend/api/tests.py`: Analytics endpoints for test listings, pivots, trends, categories, timing, exports, and standardized definitions.
- `backend/api/storage.py`: Storage statistics and cleanup plus cache/rate-limit diagnostics.
- `backend/models/db.py`: SQLModel tables `Document`, `ExtractionResult`, `StandardizedTestDefinition`, `PatientTest`, and `TestSynonym`.
- `backend/utils/image_optimizer.py`: `ImageOptimizer` with compression/resizing/deduplication (`optimize_and_store`, `cleanup_old_files`) and `get_optimizer()` singleton.

### `workers/extraction/` (RQ worker and helpers)
- `main.py`: RQ job handler `process_document()` and `_save_normalized_tests()`, plus helpers for parsing dates/values and trend utilities.
- `single_vision_extractor.py`: Production extraction pipeline (`SingleVisionExtractor.extract`) coordinating preprocessing, Gemini calls, normalization, panel checks, summaries, caching, and rate limiting.
- `preprocessing.py`: `ImagePreprocessor.process()` and helpers (`_deskew`, `_denoise`, `_enhance_contrast`, etc.) used before OCR.
- `ocr_quality.py`: Scores OCR suitability and flags low-quality images.
- `strict_normalizer.py`: Loads YAML mappings, normalizes test names/values via `StrictNormalizer.normalize`, and outputs `NormalizerResult`.
- `panel_validator.py`: `validate_panel_completeness()` to flag missing panel members.
- `quality_verifier.py`: `verify_extraction_quality()` producing `QualityReport` and warnings/errors.
- `safe_summary.py`: `generate_safe_summary()` builds human-friendly summaries from standardized results.
- `rate_limiter.py`: Adaptive rate limiter (`get_rate_limiter`, `AdaptiveRateLimiter`) guarding Gemini calls.
- `cache_manager.py`: Two-tier cache (`CacheManager`, `CacheConfig`) plus hashing utilities for duplicate detection.
- `batch_processor.py`: Batch orchestration helpers for grouped document processing.
- `validation.py`: Extra validation helpers for value sanity checks.

### `frontend_app/` (Streamlit UI)
- `main.py`: Landing page with upload workflow and dashboard cards; calls `/upload`, `/documents`, `/documents/flagged`, and `/results/{id}`.
- `pages/1_Global_Tests.py`: Global table and exports backed by `/tests/*` endpoints.
- `pages/2_Performance.py`: Performance monitor hitting `/documents`, `/tests/stats`, and `/tests/timing-stats`.
- `pages/3_Approach_Comparison.py`: UI to compare extraction approaches; posts to `/compare-approaches`.

### `config/`
- `settings.yaml`: Default configuration consumed by `get_settings()`.
- `test_mappings.yaml`: Canonical test definitions loaded into `StandardizedTestDefinition` and used by `StrictNormalizer`.

### `tests/`
- `tests/unit/*.py`: Unit suites for rate limiting, caching, preprocessing, OCR quality, and normalization logic.
- `tests/integration/test_api_endpoints.py`: API-level checks across FastAPI routes.
- `tests/e2e/test_extraction_pipeline.py`: End-to-end flow of upload → worker → results.
- `tests/fixtures/*`: Sample lab report payloads reused by tests.
- `tests/conftest.py`: Shared pytest fixtures.

### `docs/`
- `docs/home.png`: Dashboard screenshot referenced in the README.
