import shutil
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, func
from rq import Queue
from rq.job import Job
import io

from backend.core.config import get_settings
from backend.core.database import create_db_and_tables, get_session
from backend.core.queue import get_queue
from backend.models.db import (
    Document, 
    ExtractionResult, 
    PatientTest, 
    StandardizedTestDefinition,
    TestSynonym
)

settings = get_settings()

app = FastAPI(
    title="Lab Report Extraction System",
    description="Enterprise-grade document processing platform with global test analytics",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
import os

storage_path = Path(settings.storage.base_path) / settings.storage.bucket
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(storage_path)), name="static")


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    # Initialize standardized test definitions from YAML
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
        
        from backend.core.database import engine
        with Session(engine) as session:
            for test_key, test_data in mappings.items():
                # Check if already exists
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


router = APIRouter()


# =============================================================================
# Document Upload & Status
# =============================================================================

@router.post("/upload", response_model=List[Document])
def upload_files(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    queue: Queue = Depends(get_queue)
):
    uploaded_docs = []
    storage_path = Path(settings.storage.base_path) / settings.storage.bucket
    storage_path.mkdir(parents=True, exist_ok=True)

    for file in files:
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename}"
        file_location = storage_path / safe_filename
        
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
            
        doc = Document(
            id=file_id,
            filename=file.filename,
            file_path=str(file_location),
            content_type=file.content_type or "application/octet-stream",
            status="queued"
        )
        session.add(doc)
        uploaded_docs.append(doc)
        
        # Enqueue task
        queue.enqueue('workers.extraction.main.process_document', file_id, job_id=file_id)

    session.commit()
    for doc in uploaded_docs:
        session.refresh(doc)
    return uploaded_docs


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str, queue: Queue = Depends(get_queue)):
    try:
        job = Job.fetch(task_id, connection=queue.connection)
    except Exception:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return {
        "task_id": task_id,
        "status": job.get_status(),
        "result": job.result,
        "meta": job.meta
    }


@router.get("/documents", response_model=List[Document])
def get_documents(session: Session = Depends(get_session)):
    docs = session.exec(select(Document).order_by(Document.upload_date.desc())).all()
    return docs


@router.get("/results/{document_id}")
def get_results(document_id: str, session: Session = Depends(get_session)):
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    result = session.exec(
        select(ExtractionResult).where(ExtractionResult.document_id == document_id)
    ).first()
    return {
        "document": doc,
        "extraction": result
    }


# =============================================================================
# Global Test Analytics
# =============================================================================

@router.get("/tests/all")
def get_all_tests(
    session: Session = Depends(get_session),
    category: Optional[str] = Query(None, description="Filter by test category"),
    patient_name: Optional[str] = Query(None, description="Filter by patient name"),
    standardized_only: bool = Query(False, description="Show only standardized tests"),
    limit: int = Query(1000, le=5000),
    offset: int = Query(0)
):
    """Get all patient tests across all documents."""
    query = select(PatientTest)
    
    if category:
        query = query.where(PatientTest.category == category)
    if patient_name:
        query = query.where(PatientTest.patient_name.ilike(f"%{patient_name}%"))
    if standardized_only:
        query = query.where(PatientTest.test_definition_id.isnot(None))
    
    query = query.order_by(PatientTest.created_at.desc()).offset(offset).limit(limit)
    
    tests = session.exec(query).all()
    
    return {
        "tests": [
            {
                "id": t.id,
                "document_id": t.document_id,
                "patient_name": t.patient_name,
                "patient_id": t.patient_id,
                "original_test_name": t.original_test_name,
                "standardized_test_name": t.standardized_test_name,
                "value": t.value,
                "unit": t.unit,
                "reference_range": t.reference_range,
                "flag": t.flag,
                "category": t.category,
                "loinc_code": t.loinc_code,
                "match_type": t.match_type,
                "confidence": t.standardization_confidence,
                "test_date": t.test_date,
                "created_at": t.created_at
            }
            for t in tests
        ],
        "total": len(tests),
        "offset": offset,
        "limit": limit
    }


@router.get("/tests/pivot")
def get_tests_pivot(
    session: Session = Depends(get_session),
    category: Optional[str] = Query(None)
):
    """
    Get tests in pivot table format: patients × standardized tests.
    
    Returns a matrix where:
    - Rows = unique patients
    - Columns = unique standardized test names
    - Values = test results
    """
    query = select(PatientTest).where(PatientTest.standardized_test_name.isnot(None))
    
    if category:
        query = query.where(PatientTest.category == category)
    
    tests = session.exec(query).all()
    
    # Build pivot data
    patients = {}  # patient_key -> {test_name -> value}
    all_tests = set()
    
    for t in tests:
        patient_key = t.patient_name or t.patient_id or f"doc_{t.document_id}"
        test_name = t.standardized_test_name
        
        if patient_key not in patients:
            patients[patient_key] = {
                "patient_name": t.patient_name,
                "patient_id": t.patient_id,
                "tests": {}
            }
        
        # Store test value (if multiple, keep latest)
        patients[patient_key]["tests"][test_name] = {
            "value": t.value,
            "unit": t.unit,
            "flag": t.flag,
            "date": t.test_date.isoformat() if t.test_date else None
        }
        all_tests.add(test_name)
    
    # Sort tests alphabetically
    sorted_tests = sorted(all_tests)
    
    return {
        "columns": ["Patient"] + sorted_tests,
        "rows": [
            {
                "patient": key,
                "patient_name": data["patient_name"],
                "patient_id": data["patient_id"],
                **{
                    test: data["tests"].get(test, {}).get("value", "")
                    for test in sorted_tests
                }
            }
            for key, data in patients.items()
        ],
        "test_count": len(sorted_tests),
        "patient_count": len(patients)
    }


@router.get("/tests/categories")
def get_test_categories(session: Session = Depends(get_session)):
    """Get all unique test categories with counts."""
    results = session.exec(
        select(PatientTest.category, func.count(PatientTest.id))
        .where(PatientTest.category.isnot(None))
        .group_by(PatientTest.category)
    ).all()
    
    return {
        "categories": [
            {"name": cat, "count": count}
            for cat, count in results
        ]
    }


@router.get("/tests/stats")
def get_test_stats(session: Session = Depends(get_session)):
    """Get global test statistics."""
    total_tests = session.exec(select(func.count(PatientTest.id))).one()
    
    standardized_count = session.exec(
        select(func.count(PatientTest.id))
        .where(PatientTest.test_definition_id.isnot(None))
    ).one()
    
    unique_patients = session.exec(
        select(func.count(func.distinct(PatientTest.patient_name)))
        .where(PatientTest.patient_name.isnot(None))
    ).one()
    
    unique_tests = session.exec(
        select(func.count(func.distinct(PatientTest.standardized_test_name)))
        .where(PatientTest.standardized_test_name.isnot(None))
    ).one()
    
    match_type_stats = session.exec(
        select(PatientTest.match_type, func.count(PatientTest.id))
        .where(PatientTest.match_type.isnot(None))
        .group_by(PatientTest.match_type)
    ).all()
    
    return {
        "total_tests": total_tests,
        "standardized_count": standardized_count,
        "standardization_rate": standardized_count / total_tests if total_tests > 0 else 0,
        "unique_patients": unique_patients,
        "unique_test_types": unique_tests,
        "match_type_distribution": {
            match_type: count for match_type, count in match_type_stats
        }
    }


@router.get("/tests/export")
def export_tests(
    session: Session = Depends(get_session),
    format: str = Query("csv", regex="^(csv|excel)$"),
    category: Optional[str] = Query(None)
):
    """Export all tests as CSV or Excel."""
    import pandas as pd
    
    query = select(PatientTest)
    if category:
        query = query.where(PatientTest.category == category)
    
    tests = session.exec(query).all()
    
    # Convert to DataFrame
    data = [
        {
            "Patient Name": t.patient_name,
            "Patient ID": t.patient_id,
            "Original Test Name": t.original_test_name,
            "Standardized Test Name": t.standardized_test_name,
            "Value": t.value,
            "Unit": t.unit,
            "Reference Range": t.reference_range,
            "Flag": t.flag,
            "Category": t.category,
            "LOINC Code": t.loinc_code,
            "Match Type": t.match_type,
            "Confidence": t.standardization_confidence,
            "Test Date": t.test_date,
            "Document ID": t.document_id
        }
        for t in tests
    ]
    
    df = pd.DataFrame(data)
    
    if format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=lab_tests_export.csv"}
        )
    else:
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=lab_tests_export.xlsx"}
        )


@router.get("/tests/definitions")
def get_test_definitions(session: Session = Depends(get_session)):
    """Get all standardized test definitions."""
    definitions = session.exec(
        select(StandardizedTestDefinition)
        .order_by(StandardizedTestDefinition.category, StandardizedTestDefinition.canonical_name)
    ).all()
    
    return {
        "definitions": [
            {
                "id": d.id,
                "test_key": d.test_key,
                "canonical_name": d.canonical_name,
                "loinc_code": d.loinc_code,
                "category": d.category,
                "unit": d.unit,
                "aliases": d.aliases
            }
            for d in definitions
        ],
        "total": len(definitions)
    }


# =============================================================================
# Batch Processing & Performance
# =============================================================================

@router.post("/batch-upload")
async def batch_upload(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    queue: Queue = Depends(get_queue),
    priority: str = Query("normal", regex="^(high_priority|normal|batch)$")
):
    """
    Upload and process multiple files as a batch.
    
    Returns a job_id that can be used to track progress.
    """
    import redis as redis_lib
    
    uploaded_docs = []
    storage_path = Path(settings.storage.base_path) / settings.storage.bucket
    storage_path.mkdir(parents=True, exist_ok=True)
    
    # Save all files
    for file in files:
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename}"
        file_location = storage_path / safe_filename
        
        content = await file.read()
        with open(file_location, "wb") as f:
            f.write(content)
        
        doc = Document(
            id=file_id,
            filename=file.filename,
            file_path=str(file_location),
            content_type=file.content_type or "application/octet-stream",
            status="queued"
        )
        session.add(doc)
        uploaded_docs.append(doc)
    
    session.commit()
    
    # Get document IDs
    document_ids = [doc.id for doc in uploaded_docs]
    
    # Create batch job
    job_id = str(uuid.uuid4())
    
    # Enqueue batch processing task
    try:
        redis_client = redis_lib.from_url(settings.redis.url)
        batch_queue = Queue(priority, connection=redis_client)
        
        batch_queue.enqueue(
            'workers.extraction.optimized_worker.process_document_batch',
            document_ids,
            job_id,
            job_id=job_id
        )
    except Exception as e:
        # Fallback to individual processing
        for doc in uploaded_docs:
            queue.enqueue(
                'workers.extraction.main.process_document',
                doc.id,
                job_id=doc.id
            )
        job_id = None
    
    return {
        "job_id": job_id,
        "documents": [
            {"id": doc.id, "filename": doc.filename}
            for doc in uploaded_docs
        ],
        "total": len(uploaded_docs),
        "priority": priority,
        "status": "queued"
    }


@router.get("/batch-status/{job_id}")
def get_batch_status(job_id: str):
    """
    Get status of a batch processing job.
    
    Returns progress: processed/total, success/failed, cached.
    """
    try:
        from workers.extraction.optimized_worker import get_batch_job_status
        status = get_batch_job_status(job_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Batch job not found")
        
        # Calculate progress percentage
        total = int(status.get("total", 0))
        processed = int(status.get("processed", 0))
        progress = processed / total if total > 0 else 0
        
        return {
            "job_id": job_id,
            "status": status.get("status", "unknown"),
            "total": total,
            "processed": processed,
            "successful": int(status.get("successful", 0)),
            "failed": int(status.get("failed", 0)),
            "cached": int(status.get("cached", 0)),
            "progress": f"{progress:.1%}",
            "started_at": status.get("started_at"),
            "completed_at": status.get("completed_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache-stats")
def get_cache_stats():
    """
    Get cache statistics.
    
    Returns hit rate, size, and performance metrics.
    """
    try:
        from workers.extraction.cache_manager import get_cache_manager
        cache = get_cache_manager()
        stats = cache.get_stats()
        
        return {
            "cache_enabled": True,
            "redis_available": cache.redis is not None,
            **stats
        }
        
    except Exception as e:
        return {
            "cache_enabled": False,
            "error": str(e)
        }


@router.get("/rate-limit-stats")
def get_rate_limit_stats():
    """
    Get rate limiter statistics.
    
    Returns current request count and throttling status.
    """
    try:
        from workers.extraction.rate_limiter import get_rate_limiter
        limiter = get_rate_limiter()
        stats = limiter.get_stats()
        
        return {
            "rate_limiting_enabled": True,
            **stats
        }
        
    except Exception as e:
        return {
            "rate_limiting_enabled": False,
            "error": str(e)
        }


app.include_router(router, prefix="/api/v1")

