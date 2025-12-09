"""
Worker for processing lab report documents - PRODUCTION VERSION.

Uses Single Vision + Normalizer pipeline for extraction.
Saves NORMALIZED test names to PatientTest for global analytics.
"""

import json
import time
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlmodel import Session, select

from backend.core.database import engine
from backend.core.config import get_settings
from backend.models.db import (
    Document, 
    ExtractionResult, 
    PatientTest, 
    StandardizedTestDefinition,
    TestSynonym
)
from workers.extraction.single_vision_extractor import SingleVisionExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize extractor once
_extractor = None

def get_extractor() -> SingleVisionExtractor:
    """Get or create the production extractor."""
    global _extractor
    if _extractor is None:
        _extractor = SingleVisionExtractor()
    return _extractor


def process_document(document_id: str) -> None:
    """
    Process a single document through the production extraction pipeline.
    
    Pipeline:
    1. Single Vision extraction (Gemini)
    2. Deterministic normalization (YAML + Levenshtein)
    3. Safety validation
    4. Save to PatientTest with canonical names
    """
    # Rate Limiting
    if settings.gemini.rate_limit > 0:
        sleep_time = 60 / settings.gemini.rate_limit
        logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
        time.sleep(sleep_time)

    logger.info(f"Starting processing for document {document_id}")
    
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        # Helper to update processing stage
        def update_stage(stage: str):
            doc.processing_stage = stage
            session.add(doc)
            session.commit()
            logger.info(f"Document {document_id}: Stage -> {stage}")

        # Update status to processing
        doc.status = "processing"
        update_stage("queued")
        
        try:
            # Run production extraction pipeline
            update_stage("extracting")
            extractor = get_extractor()
            extraction_result = extractor.extract(doc.file_path)
            update_stage("normalizing")
            
            # Extract key fields
            data = extraction_result.data
            confidence = extraction_result.confidence
            success = extraction_result.success
            
            # Determine review status
            needs_review = not success
            review_reason = ""
            
            if extraction_result.issues:
                review_reason = "; ".join(extraction_result.issues[:3])
            
            # Log extraction summary
            lab_results = data.get('lab_results', []) if data else []
            metadata = data.get('metadata', {}) if data else {}
            
            if success:
                logger.info(
                    f"Document {document_id}: Extracted {len(lab_results)} tests, "
                    f"confidence={confidence:.2f}, "
                    f"unknown={len(metadata.get('unknown_tests', []))}"
                )
            else:
                logger.warning(f"Document {document_id}: Extraction failed - {review_reason}")
                needs_review = True

            # Create extraction result record
            summary = extraction_result.summary or {}
            result = ExtractionResult(
                document_id=document_id,
                extracted_data=data,
                confidence_score=confidence,
                needs_review=needs_review,
                review_reason=review_reason,
                preprocessing_time=0.0,  # Combined in extraction_time
                pass1_time=extraction_result.extraction_time,
                pass2_time=extraction_result.normalization_time,
                pass3_time=extraction_result.validation_time,
                pass4_time=0.0,
                total_time=extraction_result.total_time,
                # Summary fields
                report_type=summary.get('report_type'),
                report_purpose=summary.get('report_purpose'),
                abnormal_findings=summary.get('abnormal_findings', []),
                manual_review_items=summary.get('manual_review_items', []),
                priority_level=summary.get('priority_level')
            )
            session.add(result)
            
            update_stage("saving")
            
            # Save NORMALIZED tests to PatientTest table
            if success and lab_results:
                saved = _save_normalized_tests(
                    session=session,
                    document_id=document_id,
                    lab_results=lab_results,
                    patient_info=data.get('patient_info', {}),
                    source_filename=doc.filename
                )
                logger.info(f"Document {document_id}: Saved {saved} tests to PatientTest")
            
            # Update document status
            doc.status = "completed" if success else "failed"
            update_stage("completed" if success else "failed")
            
            logger.info(f"Successfully processed document {document_id} (status: {doc.status})")
            
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
            
            # Save error result
            error_result = ExtractionResult(
                document_id=document_id,
                extracted_data={'error': str(e)},
                confidence_score=0.0,
                needs_review=True,
                review_reason=f"Processing error: {str(e)}"
            )
            session.add(error_result)
            
            doc.status = "failed"
            session.add(doc)
            session.commit()


def _save_normalized_tests(
    session: Session,
    document_id: str,
    lab_results: List[Dict[str, Any]],
    patient_info: Dict[str, Any],
    source_filename: Optional[str] = None
) -> int:
    """
    Save normalized lab results to PatientTest table.
    
    Uses CANONICAL test names for global analytics and time-series tracking.
    Different lab formats (RBC, Erythrocytes, etc.) all map to same canonical name.
    """
    saved_count = 0
    patient_name = patient_info.get('name')
    patient_id = patient_info.get('patient_id')
    
    # Parse test date
    test_date = _parse_date(patient_info.get('collection_date') or patient_info.get('report_date'))
    
    for result in lab_results:
        try:
            # Get both original and canonical names
            original_name = result.get('original_name', '')
            canonical_name = result.get('test_name', '')
            
            # Skip if no test name
            if not canonical_name and not original_name:
                continue
            
            # Skip UNKNOWN tests for global analytics
            if canonical_name == "UNKNOWN":
                logger.debug(f"Skipping UNKNOWN test: {original_name}")
                continue
            
            # Parse value
            value_str = str(result.get('value', ''))
            numeric_value, value_type = _parse_value(value_str)
            
            # Look up test definition by canonical name
            test_definition_id = None
            if canonical_name:
                definition = session.exec(
                    select(StandardizedTestDefinition)
                    .where(StandardizedTestDefinition.canonical_name == canonical_name)
                ).first()
                if definition:
                    test_definition_id = definition.id
            
            # Determine standardization confidence
            mapping_method = result.get('mapping_method', 'unknown')
            std_confidence = {
                'exact': 1.0,
                'alias': 0.95,
                'fuzzy': 0.8,
                'llm': 0.7,
                'unknown': 0.0
            }.get(mapping_method, 0.5)
            
            # Create PatientTest record with CANONICAL name
            patient_test = PatientTest(
                document_id=document_id,
                source_filename=source_filename,
                test_definition_id=test_definition_id,
                patient_name=patient_name,
                patient_id=patient_id,
                original_test_name=original_name,
                standardized_test_name=canonical_name,  # CANONICAL NAME FOR GLOBAL ANALYTICS
                value=value_str,
                numeric_value=numeric_value,
                text_value=value_str if value_type == 'text' else None,
                value_type=value_type,
                unit=result.get('unit'),
                reference_range=result.get('reference_range'),
                flag=result.get('flag'),
                category=result.get('category'),
                loinc_code=result.get('loinc_code'),
                standardization_confidence=std_confidence,
                match_type=mapping_method,
                test_date=test_date,
                needs_review=result.get('needs_review', False)
            )
            session.add(patient_test)
            saved_count += 1
            
        except Exception as e:
            logger.warning(f"Error saving test {result.get('test_name')}: {e}")
            continue
    
    session.commit()
    return saved_count


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string in common formats."""
    if not date_str:
        return None
    
    formats = [
        '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y',
        '%Y/%m/%d', '%d %b %Y', '%d %B %Y', '%B %d, %Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    return None


def _parse_value(value_str: str) -> tuple:
    """
    Parse value string to numeric and determine type.
    
    Returns:
        (numeric_value, value_type)
    """
    if not value_str:
        return None, 'unknown'
    
    # Clean value
    clean_val = value_str.strip()
    clean_val = re.sub(r'\s*\[.*?\]\s*$', '', clean_val)  # Remove [H], [L]
    clean_val = re.sub(r'[↑↓HLhl\*]$', '', clean_val)     # Remove flags
    clean_val = clean_val.replace(',', '').strip()
    
    try:
        numeric = float(clean_val)
        return numeric, 'numeric'
    except ValueError:
        # Check for mixed (contains digits)
        if any(c.isdigit() for c in value_str):
            return None, 'mixed'
        return None, 'text'


def get_global_test_trends(
    session: Session,
    canonical_test_name: str,
    patient_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get time-series data for a test across all reports.
    
    Uses CANONICAL test name to unify different lab formats.
    
    Example: get_global_test_trends(session, "Hemoglobin", patient_id="P123")
    Returns all Hemoglobin values even if labs called it "Hb", "HGB", or "Haemoglobin"
    """
    query = select(PatientTest).where(
        PatientTest.standardized_test_name == canonical_test_name
    )
    
    if patient_id:
        query = query.where(PatientTest.patient_id == patient_id)
    
    query = query.order_by(PatientTest.test_date.desc()).limit(limit)
    
    results = session.exec(query).all()
    
    return [
        {
            'date': r.test_date,
            'value': r.numeric_value or r.value,
            'unit': r.unit,
            'flag': r.flag,
            'lab_name': r.original_test_name,  # What the lab called it
            'document_id': r.document_id
        }
        for r in results
    ]


def get_patient_all_tests(
    session: Session,
    patient_id: str
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all tests for a patient, grouped by CANONICAL name.
    
    Returns: {
        "Hemoglobin": [values from different reports...],
        "Red Blood Cell Count": [values...],
        ...
    }
    """
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
            'date': r.test_date,
            'value': r.numeric_value or r.value,
            'unit': r.unit,
            'flag': r.flag,
            'original_name': r.original_test_name,
            'document_id': r.document_id
        })
    
    return grouped
