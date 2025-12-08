"""
Worker for processing lab report documents.

Handles the document processing queue, extracts lab data using the 3-pass pipeline,
and saves normalized test results to the PatientTest table for global analytics.
"""

import json
import time
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
from workers.extraction.gemini import extract_lab_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


def process_document(document_id: str) -> None:
    """
    Process a single document through the extraction pipeline.
    
    Args:
        document_id: UUID of the document to process
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

        # Helper to update processing stage in real-time
        def update_stage(stage: str):
            doc.processing_stage = stage
            session.add(doc)
            session.commit()
            logger.info(f"Document {document_id}: Stage -> {stage}")

        # Update status to processing
        doc.status = "processing"
        update_stage("queued")
        
        try:
            # Run extraction pipeline with stage callbacks
            update_stage("preprocessing")
            extraction_result = extract_lab_report(doc.file_path)
            update_stage("saving")
            
            # Extract key fields from result
            data = extraction_result.data
            confidence = extraction_result.confidence
            needs_review = extraction_result.needs_review
            review_reason = extraction_result.review_reason
            
            # Log extraction summary
            lab_results = data.get('lab_results', [])
            if extraction_result.success:
                standardization = data.get('metadata', {}).get('standardization', {})
                logger.info(
                    f"Document {document_id}: Extracted {len(lab_results)} tests, "
                    f"confidence={confidence:.2f}, "
                    f"standardized={standardization.get('standardized_count', 0)}/{standardization.get('total_tests', 0)}"
                )
            else:
                logger.warning(f"Document {document_id}: Extraction failed - {review_reason}")
            
            # Check for errors in data
            if 'error' in data and not extraction_result.success:
                needs_review = True
                if not review_reason:
                    review_reason = data.get('error', 'Unknown error')

            # Create extraction result record with timing
            result = ExtractionResult(
                document_id=document_id,
                extracted_data=data,
                confidence_score=confidence,
                needs_review=needs_review,
                review_reason=review_reason,
                preprocessing_time=extraction_result.preprocessing_time,
                pass1_time=extraction_result.pass1_time,
                pass2_time=extraction_result.pass2_time,
                pass3_time=extraction_result.pass3_time,
                total_time=extraction_result.total_time
            )
            session.add(result)
            
            # Save normalized tests to PatientTest table
            if extraction_result.success and lab_results:
                _save_patient_tests(
                    session=session,
                    document_id=document_id,
                    lab_results=lab_results,
                    patient_info=data.get('patient_info', {})
                )
            
            # Update document status
            doc.status = "completed" if extraction_result.success else "failed"
            update_stage("completed" if extraction_result.success else "failed")
            
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


def _save_patient_tests(
    session: Session,
    document_id: str,
    lab_results: List[Dict[str, Any]],
    patient_info: Dict[str, Any]
) -> int:
    """
    Save extracted lab results to the PatientTest table for global analytics.
    
    Args:
        session: Database session
        document_id: Source document ID
        lab_results: List of extracted lab results
        patient_info: Patient information from extraction
        
    Returns:
        Number of tests saved
    """
    saved_count = 0
    patient_name = patient_info.get('name')
    patient_id = patient_info.get('patient_id')
    
    # Parse test date if available
    test_date = None
    date_str = patient_info.get('collection_date') or patient_info.get('report_date')
    if date_str:
        try:
            # Try common date formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    test_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
        except:
            pass
    
    for result in lab_results:
        try:
            original_name = result.get('test_name', result.get('original_name', ''))
            if not original_name:
                continue
            
            # Get standardization info
            std_info = result.get('standardization', {})
            is_standardized = std_info.get('is_standardized', False)
            
            # Find test definition if standardized
            test_definition_id = None
            if is_standardized:
                canonical_name = result.get('test_name')
                if canonical_name:
                    definition = session.exec(
                        select(StandardizedTestDefinition)
                        .where(StandardizedTestDefinition.canonical_name == canonical_name)
                    ).first()
                    if definition:
                        test_definition_id = definition.id
            
            # Parse value to determine type
            value_str = str(result.get('value', ''))
            value_type = result.get('value_type', 'unknown')
            numeric_value = None
            text_value = None
            
            # Try to parse as numeric
            try:
                # Handle common number formats
                clean_val = value_str.replace(',', '').replace(' ', '').strip()
                # Remove common suffixes like [H], [L], etc.
                import re
                clean_val = re.sub(r'\s*\[.*?\]\s*$', '', clean_val)
                numeric_value = float(clean_val)
                if value_type == 'unknown':
                    value_type = 'numeric'
            except (ValueError, TypeError):
                # Not a pure number - check if it's text or mixed
                if value_type == 'unknown':
                    # Check if contains any digits
                    if any(c.isdigit() for c in value_str):
                        value_type = 'mixed'
                    else:
                        value_type = 'text'
                text_value = value_str
            
            # Create PatientTest record
            patient_test = PatientTest(
                document_id=document_id,
                test_definition_id=test_definition_id,
                patient_name=patient_name,
                patient_id=patient_id,
                original_test_name=result.get('original_name', original_name),
                standardized_test_name=result.get('test_name') if is_standardized else None,
                value=value_str,
                numeric_value=numeric_value,
                text_value=text_value,
                value_type=value_type,
                unit=result.get('unit'),
                reference_range=result.get('reference_range'),
                flag=result.get('flag'),
                category=result.get('category'),
                loinc_code=result.get('loinc_code'),
                method=result.get('test_method'),
                standardization_confidence=std_info.get('confidence', 0.0),
                match_type=std_info.get('match_type'),
                test_date=test_date
            )
            
            session.add(patient_test)
            saved_count += 1
            
            # Save learned synonym if LLM matched
            if std_info.get('match_type') == 'llm' and is_standardized:
                _save_learned_synonym(
                    session=session,
                    original_term=result.get('original_name', original_name),
                    canonical_name=result.get('test_name'),
                    test_definition_id=test_definition_id,
                    confidence=std_info.get('confidence', 0.8)
                )
            
        except Exception as e:
            logger.warning(f"Failed to save test result: {e}")
            continue
    
    logger.info(f"Saved {saved_count} patient tests for document {document_id}")
    return saved_count


def _save_learned_synonym(
    session: Session,
    original_term: str,
    canonical_name: str,
    test_definition_id: Optional[int],
    confidence: float
) -> None:
    """
    Save a learned synonym for future faster lookups.
    
    When the LLM successfully maps an unknown term, we store it so
    future occurrences can be matched with exact lookup.
    """
    try:
        # Check if already exists
        existing = session.exec(
            select(TestSynonym)
            .where(TestSynonym.original_term == original_term.lower())
        ).first()
        
        if not existing:
            synonym = TestSynonym(
                original_term=original_term.lower(),
                canonical_name=canonical_name,
                test_definition_id=test_definition_id,
                confidence=confidence,
                source='llm'
            )
            session.add(synonym)
            logger.info(f"Learned new synonym: '{original_term}' -> '{canonical_name}'")
            
    except Exception as e:
        logger.debug(f"Could not save synonym: {e}")
