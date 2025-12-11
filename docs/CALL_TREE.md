# System Architecture & Call Tree

This document explains how requests flow through the Lab Extraction System with visual diagrams and file-by-file mapping.

---

## High-Level Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        UI["Streamlit UI<br/>frontend_app/main.py"]
    end
    
    subgraph APILayer["API Layer"]
        API["FastAPI<br/>backend/main.py"]
        DOCS["/api/v1/documents"]
        TESTS["/api/v1/tests"]
        STORAGE["/api/v1/storage"]
    end
    
    subgraph WorkerLayer["Worker Layer"]
        QUEUE["Redis Queue"]
        WORKER["RQ Worker<br/>workers/extraction/main.py"]
    end
    
    subgraph DataLayer["Data Layer"]
        DB[("PostgreSQL")]
        CACHE[("Redis Cache")]
        FILES[("File Storage")]
    end
    
    subgraph External["External Services"]
        GEMINI["Gemini Vision API"]
    end
    
    UI --> API
    API --> DOCS
    API --> TESTS
    API --> STORAGE
    DOCS --> QUEUE
    QUEUE --> WORKER
    WORKER --> GEMINI
    WORKER --> DB
    API --> DB
    WORKER --> CACHE
    WORKER --> FILES
```

---

## Request Flow Diagrams

### 1. System Startup Flow

```mermaid
sequenceDiagram
    participant S as start.sh
    participant R as Redis
    participant P as PostgreSQL
    participant B as Backend
    participant W as Worker
    participant F as Frontend

    S->>R: Check/Start Redis
    S->>P: Check/Start PostgreSQL
    S->>B: uvicorn backend.main:app
    B->>B: on_startup
    B->>P: create_db_and_tables
    B->>B: _init_test_definitions
    Note over B: Load config/test_mappings.yaml
    S->>W: rq worker extraction
    Note over W: Waiting for jobs...
    S->>F: streamlit run frontend_app/main.py
```

---

### 2. Document Upload and Extraction Pipeline

```mermaid
flowchart TD
    subgraph UserAction["User Action"]
        A["User Uploads File"]
    end
    
    subgraph FE["Frontend"]
        B["frontend_app/main.py<br/>Process Files button"]
    end
    
    subgraph BackendAPI["Backend API"]
        C["POST /api/v1/upload<br/>backend/api/documents.py"]
        D["ImageOptimizer.optimize_and_store"]
        E["Save Document to DB"]
        F["Enqueue process_document"]
    end
    
    subgraph RedisQ["Redis Queue"]
        G["Job Queue"]
    end
    
    subgraph WorkerProc["Worker Process"]
        H["process_document<br/>workers/extraction/main.py"]
        I["SingleVisionExtractor.extract"]
    end
    
    subgraph Pipeline["Extraction Pipeline"]
        J["1. preprocess_image"]
        K["2. evaluate_ocr_quality"]
        L["3. Gemini Vision API Call"]
        M["4. StrictNormalizer.normalize"]
        N["5. validate_panel_completeness"]
        O["6. verify_extraction_quality"]
        P["7. generate_safe_summary"]
    end
    
    subgraph DataStore["Data Storage"]
        Q["Save ExtractionResult"]
        R["Save PatientTest rows"]
    end
    
    A --> B --> C --> D --> E --> F --> G --> H --> I
    I --> J --> K
    K -->|Quality OK| L
    K -->|Quality Fail| REJECT["Reject Document"]
    L --> M --> N --> O --> P --> Q --> R
```

---

### 3. Detailed Extraction Pipeline

```mermaid
flowchart LR
    subgraph Input["Input"]
        IMG["Lab Report Image"]
    end
    
    subgraph Preprocessing["Preprocessing"]
        PP["ImagePreprocessor"]
        PP1["_deskew"]
        PP2["_denoise"]
        PP3["_enhance_contrast"]
        PP4["_enhance_sharpness"]
    end
    
    subgraph QualityGate["Quality Gate"]
        QG["evaluate_ocr_quality"]
        QG1["Blur Score"]
        QG2["Contrast Check"]
        QG3["Resolution Check"]
        QG4["Skew Detection"]
    end
    
    subgraph VisionExtract["Vision Extraction"]
        VE["Gemini Vision"]
        VE1["Extract Patient Info"]
        VE2["Extract Lab Values"]
        VE3["Extract Reference Ranges"]
    end
    
    subgraph Normalization["Normalization"]
        NM["StrictNormalizer"]
        NM1["YAML Lookup"]
        NM2["Levenshtein Match"]
        NM3["LLM Fallback"]
    end
    
    subgraph Validation["Validation"]
        VL["Multi-Layer Validation"]
        VL1["Panel Completeness"]
        VL2["Quality Verification"]
        VL3["Physiological Range Check"]
    end
    
    subgraph Output["Output"]
        OUT["Structured Results"]
        SUM["Clinical Summary"]
    end
    
    IMG --> PP
    PP --> PP1
    PP --> PP2
    PP --> PP3
    PP --> PP4
    PP4 --> QG
    QG --> QG1
    QG --> QG2
    QG --> QG3
    QG --> QG4
    QG4 --> VE
    VE --> VE1
    VE --> VE2
    VE --> VE3
    VE3 --> NM
    NM --> NM1
    NM1 -->|Not Found| NM2
    NM2 -->|Not Found| NM3
    NM3 --> VL
    NM1 -->|Found| VL
    NM2 -->|Found| VL
    VL --> VL1
    VL --> VL2
    VL --> VL3
    VL3 --> OUT
    VL3 --> SUM
```

---

### 4. Rate Limiting and Caching Flow

```mermaid
flowchart TD
    subgraph Request["Request"]
        REQ["API Call Request"]
    end
    
    subgraph CacheLayer["Cache Layer"]
        CACHE_CHECK{"Cache Hit?"}
        CACHE_HIT["Return Cached Result"]
        CACHE_MISS["Continue to API"]
    end
    
    subgraph RateLimiter["Rate Limiter"]
        RL_CHECK{"Under Limit?"}
        RL_WAIT["Wait for Rate Reset"]
        RL_OK["Proceed"]
    end
    
    subgraph GeminiAPI["Gemini API"]
        API_CALL["Make API Call"]
        API_SUCCESS["Success"]
        API_429["429 Error"]
    end
    
    subgraph AdaptiveBackoff["Adaptive Backoff"]
        BACKOFF["Reduce RPM by 20%"]
        RECOVERY["Increase RPM after 10 successes"]
    end
    
    subgraph Response["Response"]
        SAVE_CACHE["Save to Cache"]
        RETURN["Return Result"]
    end
    
    REQ --> CACHE_CHECK
    CACHE_CHECK -->|Yes| CACHE_HIT --> RETURN
    CACHE_CHECK -->|No| CACHE_MISS --> RL_CHECK
    RL_CHECK -->|No| RL_WAIT --> RL_CHECK
    RL_CHECK -->|Yes| RL_OK --> API_CALL
    API_CALL --> API_SUCCESS
    API_CALL --> API_429
    API_SUCCESS --> RECOVERY --> SAVE_CACHE --> RETURN
    API_429 --> BACKOFF --> RL_WAIT
```

---

### 5. Dashboard and Analytics Flow

```mermaid
flowchart LR
    subgraph FrontendPages["Frontend Pages"]
        DASH["Dashboard<br/>main.py"]
        GLOBAL["Global Tests<br/>1_Global_Tests.py"]
        PERF["Performance<br/>2_Performance.py"]
    end
    
    subgraph Endpoints["API Endpoints"]
        E1["/documents"]
        E2["/documents/flagged"]
        E3["/results/id"]
        E4["/tests/all"]
        E5["/tests/categories"]
        E6["/tests/stats"]
        E7["/tests/export"]
        E8["/tests/trends/name"]
        E9["/tests/timing-stats"]
    end
    
    subgraph Database["Database"]
        T1["Document"]
        T2["ExtractionResult"]
        T3["PatientTest"]
    end
    
    DASH --> E1
    DASH --> E2
    DASH --> E3
    GLOBAL --> E4
    GLOBAL --> E5
    GLOBAL --> E6
    GLOBAL --> E7
    GLOBAL --> E8
    PERF --> E1
    PERF --> E6
    PERF --> E9
    E1 --> T1
    E2 --> T1
    E3 --> T2
    E4 --> T3
    E5 --> T3
    E6 --> T3
    E7 --> T3
    E8 --> T3
```

---

## File-by-File Reference

### Core Components

| File | Purpose | Key Functions |
|------|---------|---------------|
| `backend/main.py` | FastAPI application entry | `on_startup()`, router registration |
| `backend/core/config.py` | Configuration management | `get_settings()` |
| `backend/core/database.py` | Database connection | `create_db_and_tables()`, `get_session()` |
| `backend/core/queue.py` | Redis queue setup | `get_queue()` |

---

### API Layer

| File | Endpoints | Description |
|------|-----------|-------------|
| `backend/api/documents.py` | `/upload`, `/documents`, `/results/{id}` | Document upload, status, results |
| `backend/api/tests.py` | `/tests/*` | Analytics, trends, exports |
| `backend/api/storage.py` | `/storage/*` | Storage stats, cleanup, diagnostics |

---

### Worker Layer

| File | Functions | Description |
|------|-----------|-------------|
| `workers/extraction/main.py` | `process_document()` | RQ job handler, saves results |
| `single_vision_extractor.py` | `SingleVisionExtractor.extract()` | Main extraction pipeline |
| `preprocessing.py` | `preprocess_image()`, `ImagePreprocessor` | Image enhancement |
| `ocr_quality.py` | `evaluate_ocr_quality()` | Quality gating |
| `strict_normalizer.py` | `StrictNormalizer.normalize()` | Test name standardization |
| `panel_validator.py` | `validate_panel_completeness()` | Panel completeness checks |
| `quality_verifier.py` | `verify_extraction_quality()` | Result quality verification |
| `safe_summary.py` | `generate_safe_summary()` | Clinical summary generation |
| `rate_limiter.py` | `get_rate_limiter()` | Adaptive API throttling |
| `cache_manager.py` | `CacheManager` | Two-tier caching Redis plus disk |
| `batch_processor.py` | `BatchProcessor` | Bulk document processing |

---

### Data Models

```mermaid
erDiagram
    Document ||--o{ ExtractionResult : has
    Document {
        uuid id PK
        string filename
        string status
        datetime uploaded_at
        string phash
    }
    
    ExtractionResult {
        uuid id PK
        uuid document_id FK
        json raw_results
        json normalized_results
        float confidence
        datetime created_at
    }
    
    PatientTest {
        uuid id PK
        uuid document_id FK
        string patient_id
        string canonical_test_name
        float value_numeric
        string unit
        string flag
        datetime test_date
    }
    
    StandardizedTestDefinition {
        uuid id PK
        string canonical_name
        string category
        json aliases
        string loinc_code
    }
    
    Document ||--o{ PatientTest : contains
    PatientTest }o--|| StandardizedTestDefinition : maps_to
```

---

### Frontend Pages

| Page | File | API Calls |
|------|------|-----------|
| Home/Upload | `frontend_app/main.py` | `/upload`, `/documents`, `/results/{id}` |
| Global Tests | `pages/1_Global_Tests.py` | `/tests/all`, `/tests/export`, `/tests/trends/*` |
| Performance | `pages/2_Performance.py` | `/documents`, `/tests/stats`, `/tests/timing-stats` |
| Comparison | `pages/3_Approach_Comparison.py` | `/compare-approaches` (not implemented) |

---

### Configuration Files

| File | Purpose |
|------|---------|
| `config/settings.yaml` | Application configuration |
| `config/test_mappings.yaml` | Canonical test definitions and aliases |
| `.env` / `.env.example` | Environment variables |
| `docker-compose.yaml` | Container orchestration |

---

### Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── test_rate_limiter.py
│   ├── test_cache_manager.py
│   ├── test_preprocessing.py
│   ├── test_ocr_quality.py
│   └── test_normalizer.py
├── integration/             # API integration tests
│   └── test_api_endpoints.py
├── e2e/                     # End-to-end tests
│   └── test_extraction_pipeline.py
├── fixtures/                # Test data
└── conftest.py              # Shared fixtures
```

---

## Quick Reference: Key Function Chains

### Upload to Extraction to Results

```mermaid
flowchart TD
    subgraph Frontend["Frontend Layer"]
        A["frontend_app/main.py<br/>Upload Button Click"]
    end

    subgraph API["API Layer"]
        B["POST /api/v1/upload"]
        C["documents.py::upload_files"]
        D["ImageOptimizer.optimize_and_store"]
        E["Document.save to DB"]
        F["queue.enqueue process_document"]
    end

    subgraph Queue["Redis Queue"]
        G["Job: process_document"]
    end

    subgraph Worker["Worker Layer"]
        H["main.py::process_document"]
        I["SingleVisionExtractor.extract"]
    end

    subgraph Extraction["Extraction Pipeline"]
        J["preprocess_image"]
        K["evaluate_ocr_quality"]
        L["Gemini Vision API"]
        M["StrictNormalizer.normalize"]
        N["validate_panel_completeness"]
        O["verify_extraction_quality"]
        P["generate_safe_summary"]
    end

    subgraph Save["Save Results"]
        Q["_save_normalized_tests"]
        R["PatientTest.save"]
        S["ExtractionResult.save"]
    end

    A --> B --> C
    C --> D --> E --> F --> G --> H --> I
    I --> J --> K --> L --> M --> N --> O --> P
    P --> Q --> R
    Q --> S

    style A fill:#e1f5fe
    style L fill:#fff3e0
    style R fill:#e8f5e9
    style S fill:#e8f5e9
```

---

### Analytics Query Flow

```mermaid
flowchart LR
    subgraph Frontend["Frontend"]
        A["1_Global_Tests.py<br/>Trends Chart"]
    end

    subgraph API["API Layer"]
        B["GET /tests/trends/test_name"]
        C["tests.py::get_trends"]
    end

    subgraph Database["Database"]
        D["SELECT FROM PatientTest<br/>WHERE canonical_test_name = ?"]
        E["Return Time Series Data"]
    end

    subgraph Response["Response"]
        F["JSON: dates, values, flags"]
        G["Render Chart"]
    end

    A --> B --> C --> D --> E --> F --> G

    style A fill:#e1f5fe
    style D fill:#fff9c4
    style G fill:#e8f5e9
```

---

### Document Status Check Flow

```mermaid
flowchart LR
    subgraph Frontend["Frontend"]
        A["Dashboard<br/>Poll Status"]
    end

    subgraph API["API Layer"]
        B["GET /documents"]
        C["GET /results/doc_id"]
    end

    subgraph Database["Database"]
        D["Document Table"]
        E["ExtractionResult Table"]
    end

    subgraph Display["Display"]
        F["Status: processing/completed/failed"]
        G["Show Extracted Results"]
    end

    A --> B --> D --> F
    A --> C --> E --> G

    style A fill:#e1f5fe
    style F fill:#fff3e0
    style G fill:#e8f5e9
```

---

### Complete System Interaction

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Streamlit Frontend
    participant API as FastAPI Backend
    participant Q as Redis Queue
    participant W as RQ Worker
    participant G as Gemini API
    participant DB as PostgreSQL

    U->>FE: Upload Lab Report
    FE->>API: POST /upload
    API->>API: Optimize Image
    API->>DB: Save Document
    API->>Q: Enqueue Job
    API-->>FE: Return doc_id
    
    Q->>W: process_document job
    W->>W: Preprocess Image
    W->>W: Quality Check
    W->>G: Extract with Vision
    G-->>W: Raw Results
    W->>W: Normalize Results
    W->>W: Validate Panel
    W->>W: Generate Summary
    W->>DB: Save ExtractionResult
    W->>DB: Save PatientTests
    
    FE->>API: GET /results/doc_id
    API->>DB: Query Results
    DB-->>API: Return Data
    API-->>FE: JSON Response
    FE-->>U: Display Results
```
