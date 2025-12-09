"""
Lab Report Extraction System - Main FastAPI Application.

Routes are organized in modular files under backend/api/:
- documents.py: Document upload, status, results
- tests.py: Test analytics, export, trends
- storage.py: Storage management
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from backend.core.config import get_settings
from backend.core.database import create_db_and_tables, engine
from backend.models.db import StandardizedTestDefinition

# Import routers
from backend.api.documents import router as documents_router
from backend.api.tests import router as tests_router
from backend.api.storage import router as storage_router

settings = get_settings()

app = FastAPI(
    title="Lab Report Extraction System",
    description="Enterprise-grade document processing platform with global test analytics",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploaded documents
storage_path = Path(settings.storage.base_path) / settings.storage.bucket
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(storage_path)), name="static")


@app.on_event("startup")
def on_startup():
    """Initialize database and load test definitions."""
    create_db_and_tables()
    _init_test_definitions()


def _init_test_definitions():
    """Load test definitions from YAML into database."""
    import yaml
    
    mappings_path = Path(__file__).parent.parent / "config" / "test_mappings.yaml"
    if not mappings_path.exists():
        return
    
    try:
        with open(mappings_path) as f:
            data = yaml.safe_load(f)
        
        mappings = data.get('mappings', {})
        
        with Session(engine) as session:
            for test_key, test_data in mappings.items():
                existing = session.exec(
                    select(StandardizedTestDefinition)
                    .where(StandardizedTestDefinition.test_key == test_key)
                ).first()
                
                if not existing:
                    defn = StandardizedTestDefinition(
                        test_key=test_key,
                        canonical_name=test_data.get('canonical_name', test_key),
                        loinc_code=test_data.get('loinc_code'),
                        category=test_data.get('category'),
                        unit=test_data.get('unit'),
                        aliases=test_data.get('aliases', [])
                    )
                    session.add(defn)
            
            session.commit()
    except Exception as e:
        print(f"Warning: Failed to initialize test definitions: {e}")


# =============================================================================
# Include Routers
# =============================================================================

# All routes are prefixed with /api/v1
app.include_router(documents_router, prefix="/api/v1")
app.include_router(tests_router, prefix="/api/v1")
app.include_router(storage_router, prefix="/api/v1")


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0"}


@app.get("/api/v1/health")
def api_health_check():
    """API health check."""
    return {"status": "healthy", "api_version": "v1"}
