"""
Test Analytics Routes - All test-related endpoints.
"""

import io
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, func

from backend.core.database import get_session
from backend.models.db import PatientTest, ExtractionResult, StandardizedTestDefinition

router = APIRouter(tags=["Tests"])


@router.get("/tests/all")
def get_all_tests(
    session: Session = Depends(get_session),
    category: Optional[str] = Query(None, description="Filter by test category"),
    patient_name: Optional[str] = Query(None, description="Filter by patient name"),
    source_file: Optional[str] = Query(None, description="Filter by source filename"),
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
    if source_file:
        query = query.where(PatientTest.source_filename.ilike(f"%{source_file}%"))
    if standardized_only:
        query = query.where(PatientTest.test_definition_id.isnot(None))
    
    query = query.order_by(PatientTest.source_filename, PatientTest.standardized_test_name).offset(offset).limit(limit)
    
    tests = session.exec(query).all()
    
    return {
        "tests": [
            {
                "id": t.id,
                "source_filename": t.source_filename,
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
    """Get tests in pivot table format: patients × standardized tests."""
    query = select(PatientTest).where(PatientTest.standardized_test_name.isnot(None))
    
    if category:
        query = query.where(PatientTest.category == category)
    
    tests = session.exec(query).all()
    
    # Build pivot data
    patients = {}
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
        
        patients[patient_key]["tests"][test_name] = {
            "value": t.value,
            "unit": t.unit,
            "flag": t.flag,
            "date": t.test_date.isoformat() if t.test_date else None
        }
        all_tests.add(test_name)
    
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


@router.get("/tests/trends/{test_name}")
def get_test_trends(
    test_name: str,
    session: Session = Depends(get_session),
    patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
    limit: int = Query(100, le=500)
):
    """Get time-series data for a test across all reports."""
    query = select(PatientTest).where(
        PatientTest.standardized_test_name == test_name
    )
    
    if patient_id:
        query = query.where(PatientTest.patient_id == patient_id)
    
    query = query.order_by(PatientTest.test_date.desc()).limit(limit)
    
    results = session.exec(query).all()
    
    return {
        "test_name": test_name,
        "total_records": len(results),
        "trends": [
            {
                "date": r.test_date.isoformat() if r.test_date else None,
                "value": r.numeric_value or r.value,
                "unit": r.unit,
                "flag": r.flag,
                "original_name": r.original_test_name,
                "patient_id": r.patient_id,
                "patient_name": r.patient_name,
                "document_id": r.document_id
            }
            for r in results
        ]
    }


@router.get("/tests/patient/{patient_id}/history")
def get_patient_history(
    patient_id: str,
    session: Session = Depends(get_session)
):
    """Get all tests for a patient, grouped by canonical name."""
    query = select(PatientTest).where(
        PatientTest.patient_id == patient_id
    ).order_by(PatientTest.test_date.desc())
    
    results = session.exec(query).all()
    
    grouped = {}
    for r in results:
        name = r.standardized_test_name or r.original_test_name
        if name not in grouped:
            grouped[name] = []
        grouped[name].append({
            "date": r.test_date.isoformat() if r.test_date else None,
            "value": r.numeric_value or r.value,
            "unit": r.unit,
            "flag": r.flag,
            "original_name": r.original_test_name,
            "document_id": r.document_id,
            "loinc_code": r.loinc_code
        })
    
    return {
        "patient_id": patient_id,
        "total_tests": len(results),
        "unique_test_types": len(grouped),
        "tests": grouped
    }


@router.get("/tests/canonical-names")
def get_canonical_names(session: Session = Depends(get_session)):
    """Get list of all canonical test names."""
    results = session.exec(
        select(PatientTest.standardized_test_name, func.count(PatientTest.id))
        .where(PatientTest.standardized_test_name.isnot(None))
        .group_by(PatientTest.standardized_test_name)
        .order_by(func.count(PatientTest.id).desc())
    ).all()
    
    return {
        "total_types": len(results),
        "canonical_names": [
            {"name": name, "count": count}
            for name, count in results
        ]
    }


@router.get("/tests/timing-stats")
def get_timing_stats(session: Session = Depends(get_session)):
    """Get processing timing statistics."""
    results = session.exec(
        select(ExtractionResult)
        .where(ExtractionResult.total_time.isnot(None))
    ).all()
    
    if not results:
        return {
            "total_processed": 0,
            "avg_preprocessing": None,
            "avg_pass1": None,
            "avg_pass2": None,
            "avg_pass3": None,
            "avg_total": None,
            "recent_timings": []
        }
    
    preprocessing_times = [r.preprocessing_time for r in results if r.preprocessing_time]
    pass1_times = [r.pass1_time for r in results if r.pass1_time]
    pass2_times = [r.pass2_time for r in results if r.pass2_time]
    pass3_times = [r.pass3_time for r in results if r.pass3_time]
    total_times = [r.total_time for r in results if r.total_time]
    
    recent = results[:20]
    recent_timings = [
        {
            "document_id": r.document_id,
            "preprocessing": round(r.preprocessing_time or 0, 2),
            "pass1_vision": round(r.pass1_time or 0, 2),
            "pass2_structure": round(r.pass2_time or 0, 2),
            "pass3_standardize": round(r.pass3_time or 0, 2),
            "total": round(r.total_time or 0, 2),
            "confidence": r.confidence_score
        }
        for r in recent
    ]
    
    return {
        "total_processed": len(results),
        "avg_preprocessing": round(sum(preprocessing_times) / len(preprocessing_times), 3) if preprocessing_times else None,
        "avg_pass1": round(sum(pass1_times) / len(pass1_times), 3) if pass1_times else None,
        "avg_pass2": round(sum(pass2_times) / len(pass2_times), 3) if pass2_times else None,
        "avg_pass3": round(sum(pass3_times) / len(pass3_times), 3) if pass3_times else None,
        "avg_total": round(sum(total_times) / len(total_times), 3) if total_times else None,
        "recent_timings": recent_timings
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
    
    data = [
        {
            "Patient Name": t.patient_name,
            "Patient ID": t.patient_id,
            "Original Test Name": t.original_test_name,
            "Standardized Test Name": t.standardized_test_name,
            "Value": t.value,
            "Numeric Value": t.numeric_value,
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
    definitions = session.exec(select(StandardizedTestDefinition)).all()
    
    return {
        "total": len(definitions),
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
        ]
    }
