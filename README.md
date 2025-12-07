# 🧬 Enterprise Lab Report Extraction System

An AI-powered system for extracting and standardizing lab report data from images using Google's Gemini Vision API.

## Features

- **🔍 3-Pass Extraction Pipeline**
  - Pass 1: Vision extraction with multi-prompt retry strategy
  - Pass 2: Structured JSON conversion with validation
  - Pass 3: Test name standardization with LOINC codes

- **🎯 Robust Extraction**
  - Multi-prompt retry strategy for difficult documents
  - Confidence-based validation
  - Enhanced image preprocessing (deskewing, denoising, contrast enhancement)

- **📊 Test Name Standardization**
  - 100+ pre-mapped common lab tests
  - Fuzzy matching (RapidFuzz) for alias recognition
  - LLM fallback for unknown tests
  - LOINC codes for interoperability

- **🐳 Docker Deployment**
  - Full Docker Compose orchestration
  - Redis for job queuing
  - Scalable worker architecture

## Quick Start

### Option 1: Local Development

1. **Clone and setup environment:**
   ```bash
   cd lab_extraction_system
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

2. **Start Redis:**
   ```bash
   # Using Docker
   docker run -d -p 6379:6379 redis:7-alpine
   
   # Or install locally
   brew install redis && redis-server
   ```

3. **Run the application:**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

4. **Access the application:**
   - Frontend: http://localhost:8501
   - API Docs: http://localhost:6000/docs

### Option 2: Docker Compose (Recommended for Production)

1. **Setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

2. **Start all services:**
   ```bash
   docker-compose up --build
   ```

3. **Access the application:**
   - Frontend: http://localhost:8501
   - API: http://localhost:6000
   - API Docs: http://localhost:6000/docs

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Image Upload                              │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Enhanced Preprocessing                          │
│  • Deskewing  • Denoising  • Contrast Enhancement           │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        Pass 1: Vision Extraction (Multi-Prompt Retry)        │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        Pass 2: Structure + Validate (Confidence Check)       │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        Pass 3: Standardize (Fuzzy Match + LLM Fallback)      │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Standardized Output                        │
│  • Canonical test names  • LOINC codes  • Confidence scores │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

All configuration is done via environment variables. See `.env.example` for all options.

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI__API_KEY` | Your Gemini API key | Required |
| `GEMINI__MODEL` | Gemini model to use | `gemini-2.5-flash-lite` |
| `STANDARDIZATION__FUZZY_THRESHOLD` | Minimum fuzzy match score | `0.85` |
| `STANDARDIZATION__LLM_FALLBACK` | Use LLM for unknown tests | `true` |
| `PROCESSING__MAX_RETRIES` | Max retry attempts | `3` |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/upload` | POST | Upload documents for processing |
| `/api/v1/documents` | GET | List all documents |
| `/api/v1/results/{id}` | GET | Get extraction results |
| `/api/v1/tasks/{id}` | GET | Check task status |

## Output Schema

```json
{
  "lab_results": [
    {
      "test_name": "Hemoglobin",
      "original_name": "Hb",
      "value": "14.5",
      "unit": "g/dL",
      "reference_range": "12.0-16.0",
      "category": "Hematology",
      "loinc_code": "718-7",
      "standardization": {
        "is_standardized": true,
        "confidence": 1.0,
        "match_type": "exact"
      }
    }
  ],
  "patient_info": {
    "name": "John Doe",
    "patient_id": "12345",
    "age": "45",
    "gender": "M"
  },
  "metadata": {
    "confidence_score": 0.92,
    "needs_review": false,
    "standardization": {
      "total_tests": 15,
      "standardized_count": 14,
      "standardization_rate": 0.93
    }
  }
}
```

## Adding New Test Mappings

Edit `config/test_mappings.yaml` to add new tests:

```yaml
mappings:
  my_new_test:
    canonical_name: "My New Test"
    loinc_code: "12345-6"
    category: "My Category"
    unit: "mg/dL"
    aliases:
      - "mnt"
      - "my new test"
      - "new test"
```

## Project Structure

```
lab_extraction_system/
├── backend/
│   ├── core/           # Configuration, database, queue
│   ├── models/         # Database models
│   └── main.py         # FastAPI application
├── workers/
│   └── extraction/
│       ├── gemini.py       # 3-pass extraction pipeline
│       ├── preprocessing.py # Image preprocessing
│       ├── prompts.py      # Multi-prompt strategy
│       ├── standardizer.py # Test name standardization
│       └── main.py         # Document processor
├── frontend_app/
│   └── main.py         # Streamlit UI
├── config/
│   ├── settings.yaml   # App settings
│   └── test_mappings.yaml  # Test name mappings
├── docker-compose.yaml
├── Dockerfile.backend
├── Dockerfile.worker
├── Dockerfile.frontend
└── start.sh            # Local development script
```

## License

MIT License
