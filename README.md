# 🧬 Enterprise Lab Report Extraction System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade AI-powered system for extracting, standardizing, and managing lab report data from medical documents using Google's Gemini Vision API. Built for scale with async processing, intelligent caching, and PostgreSQL for production deployments.

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Deployment](#-deployment)
- [Development](#-development)
- [License](#-license)

---

## ✨ Features

### 🔍 3-Pass Extraction Pipeline
| Pass | Function | Technology |
|------|----------|------------|
| **Pass 1** | Vision extraction with multi-prompt retry | Gemini Vision API |
| **Pass 2** | Structured JSON conversion with validation | Schema validation |
| **Pass 3** | Test name standardization with LOINC codes | Fuzzy matching + LLM |

### 🎯 Intelligent Processing
- **Multi-prompt retry strategy** for difficult documents
- **Confidence-based validation** with automatic flagging for review
- **Enhanced image preprocessing** (deskewing, denoising, contrast enhancement)
- **Adaptive rate limiting** to prevent API throttling

### 📊 Test Name Standardization
- **100+ pre-mapped** common lab tests with LOINC codes
- **Fuzzy matching** (RapidFuzz) for alias recognition
- **Semantic matching** using sentence transformers
- **LLM fallback** for unknown tests

### ⚡ Performance Optimizations
- **Async batch processing** for high throughput
- **Two-tier caching** (Redis + disk) to reduce API calls
- **Connection pooling** for PostgreSQL
- **Horizontal scaling** with multiple workers

### 🐳 Production-Ready
- **Docker Compose** orchestration
- **PostgreSQL** for concurrent multi-writer safety
- **Redis** for job queuing and caching
- **Health checks** on all services
- **Graceful shutdown** handling

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Streamlit Frontend                               │
│                        (http://localhost:8501)                          │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Backend                                 │
│                        (http://localhost:6000)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────────┐ │
│  │   Upload     │  │   Results    │  │        Queue Jobs              │ │
│  │   Endpoint   │  │   Endpoint   │  │     (Redis Queue)              │ │
│  └──────────────┘  └──────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  RQ Worker 1    │    │  RQ Worker 2    │    │  RQ Worker 3    │
│  (lab_reports)  │    │    (batch)      │    │ (high_priority) │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │           3-Pass Extraction Pipeline          │
         │  ┌────────────┐ ┌────────────┐ ┌───────────┐ │
         │  │ Preprocess │→│  Gemini    │→│ Standardize│ │
         │  │   Image    │ │  Vision    │ │   Tests   │ │
         │  └────────────┘ └────────────┘ └───────────┘ │
         └──────────────────────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
┌─────────────────────┐                 ┌─────────────────────┐
│     PostgreSQL      │                 │       Redis         │
│   (lab_extraction)  │                 │  (Cache + Queue)    │
│    Port: 5432       │                 │    Port: 6379       │
└─────────────────────┘                 └─────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker** and **Docker Compose** (recommended)
- **Python 3.11+** (for local development)
- **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/apikey)

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone <repository-url>
cd lab_extraction_system

# 2. Configure environment
cp .env.example .env
# Edit .env and add your GEMINI__API_KEY

# 3. Start all services
docker-compose up --build

# 4. Access the application
# Frontend: http://localhost:8501
# API Docs: http://localhost:6000/docs
```

### Option 2: Production Deployment

```bash
# Use the optimized compose file with multiple workers
docker-compose -f docker-compose.optimized.yaml up --build
```

### Option 3: Local Development

```bash
# 1. Setup virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine

# 4. Configure environment
cp .env.example .env
# Edit .env and add your GEMINI__API_KEY

# 5. Run the application
chmod +x start.sh
./start.sh
```

---

## 📁 Project Structure

```
lab_extraction_system/
│
├── 📂 backend/                    # FastAPI Backend Application
│   ├── 📂 api/                    # API route handlers
│   ├── 📂 core/                   # Core configuration
│   │   ├── config.py              # Settings management (Pydantic)
│   │   ├── database.py            # SQLAlchemy/SQLModel setup
│   │   └── queue.py               # Redis queue connection
│   ├── 📂 models/                 # Database models
│   │   └── document.py            # Document & Extraction models
│   ├── 📂 services/               # Business logic services
│   └── main.py                    # FastAPI application entry point
│
├── 📂 workers/                    # Background Processing Workers
│   ├── 📂 extraction/             # Extraction pipeline
│   │   ├── __init__.py            # Package exports
│   │   ├── main.py                # Document processor entry
│   │   ├── gemini.py              # 3-pass Gemini extraction pipeline
│   │   ├── preprocessing.py       # Image preprocessing (deskew, denoise)
│   │   ├── fast_preprocessing.py  # Optimized parallel preprocessing
│   │   ├── prompts.py             # Multi-prompt extraction strategies
│   │   ├── standardizer.py        # Test name standardization
│   │   ├── semantic_matcher.py    # Sentence transformer matching
│   │   ├── batch_processor.py     # Async batch processing
│   │   ├── cache_manager.py       # Two-tier caching (Redis + disk)
│   │   ├── rate_limiter.py        # Adaptive rate limiting
│   │   └── optimized_worker.py    # Enhanced RQ worker
│   ├── 📂 queue/                  # Queue management
│   └── 📂 tasks/                  # Task definitions
│
├── 📂 frontend_app/               # Streamlit Frontend
│   ├── main.py                    # Main dashboard UI
│   └── 📂 pages/                  # Multi-page app
│       └── 1_📊_Global_Tests.py   # Global test analysis page
│
├── 📂 config/                     # Configuration Files
│   ├── settings.yaml              # Application settings
│   └── test_mappings.yaml         # Lab test → LOINC mappings (100+)
│
├── 📂 storage/                    # File Storage
│   └── 📂 lab-reports/            # Uploaded lab report images
│
├── 📂 scripts/                    # Utility scripts
│
├── 🐳 Docker Files
│   ├── docker-compose.yaml        # Standard deployment
│   ├── docker-compose.optimized.yaml  # Production with 3 workers
│   ├── Dockerfile.backend         # Backend image
│   ├── Dockerfile.worker          # Worker image
│   └── Dockerfile.frontend        # Frontend image
│
├── 📄 Configuration
│   ├── .env.example               # Environment template
│   ├── .env                       # Local environment (gitignored)
│   ├── requirements.txt           # Python dependencies
│   └── .gitignore                 # Git ignore rules
│
├── 📄 Documentation
│   └── README.md                  # This file
│
└── 🔧 Scripts
    ├── start.sh                   # Local development startup
    └── wait_for_service.py        # Service readiness checker
```

---

## ⚙️ Configuration

### Environment Variables

All configuration is managed via environment variables. Copy `.env.example` to `.env` and configure:

#### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `GEMINI__API_KEY` | Your Gemini API key | `AIza...` |

#### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI__MODEL` | Gemini model to use | `gemini-2.5-flash-lite` |
| `GEMINI__RATE_LIMIT` | Requests per minute | `15` |
| `DATABASE__URL` | Database connection string | PostgreSQL for Docker |
| `REDIS__URL` | Redis connection string | `redis://redis:6379/0` |

#### Processing Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PROCESSING__BATCH_SIZE` | Images per batch | `15` |
| `PROCESSING__MAX_RETRIES` | Retry attempts | `3` |
| `PROCESSING__ENABLE_CACHING` | Enable result caching | `true` |
| `PROCESSING__CACHE_TTL_HOURS` | Cache duration | `24` |

#### Standardization Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `STANDARDIZATION__FUZZY_THRESHOLD` | Minimum fuzzy match score | `0.85` |
| `STANDARDIZATION__LLM_FALLBACK` | Use LLM for unknown tests | `true` |

---

## 📡 API Reference

### Base URL
- **Development**: `http://localhost:6000/api/v1`
- **Docker**: `http://backend:6000/api/v1`

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload documents for processing |
| `GET` | `/documents` | List all documents |
| `GET` | `/results/{id}` | Get extraction results |
| `GET` | `/tasks/{id}` | Check task status |
| `GET` | `/cache/stats` | Get cache statistics |
| `POST` | `/batch/upload` | Batch upload multiple files |

### Example: Upload Document

```bash
curl -X POST "http://localhost:6000/api/v1/upload" \
  -F "files=@lab_report.pdf"
```

### Example: Get Results

```bash
curl "http://localhost:6000/api/v1/results/{document_id}"
```

### Response Schema

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
    "total_tests_extracted": 15,
    "standardization": {
      "standardized_count": 14,
      "standardization_rate": 0.93
    }
  }
}
```

---

## 🐳 Deployment

### Standard Deployment

```bash
docker-compose up --build -d
```

### Production Deployment (Multiple Workers)

```bash
docker-compose -f docker-compose.optimized.yaml up --build -d
```

### Service Health Check

```bash
# Check all services
docker-compose ps

# View logs
docker-compose logs -f

# Check specific service
docker-compose logs backend
```

### Scaling Workers

```bash
# Scale workers for higher throughput
docker-compose up --scale worker=3 -d
```

---

## 🔧 Development

### Adding New Test Mappings

Edit `config/test_mappings.yaml`:

```yaml
mappings:
  hemoglobin:
    canonical_name: "Hemoglobin"
    loinc_code: "718-7"
    category: "Hematology"
    unit: "g/dL"
    reference_range: "12.0-16.0"
    aliases:
      - "hb"
      - "hgb"
      - "haemoglobin"
```

### Running Tests

```bash
# Run backend tests
pytest backend/tests/

# Run with coverage
pytest --cov=backend --cov=workers
```

### Code Style

```bash
# Format code
black backend/ workers/ frontend_app/

# Lint
flake8 backend/ workers/
```

---

## 📊 Monitoring

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:8501 | Streamlit Dashboard |
| API Docs | http://localhost:6000/docs | Swagger UI |
| ReDoc | http://localhost:6000/redoc | Alternative API docs |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache & Queue |

### Docker Health Status

All services include health checks:
- **PostgreSQL**: `pg_isready`
- **Redis**: `redis-cli ping`
- **Backend**: `curl /docs`
- **Frontend**: `curl /_stcore/health`
- **Workers**: Redis connectivity check

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Google Gemini](https://deepmind.google/technologies/gemini/) for Vision AI
- [FastAPI](https://fastapi.tiangolo.com/) for the backend framework
- [Streamlit](https://streamlit.io/) for the frontend
- [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) for fuzzy matching
- [LOINC](https://loinc.org/) for medical test standardization

---

<p align="center">
  Made with ❤️ for healthcare data interoperability
</p>
