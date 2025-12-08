"""
Optimized Worker for Batch Document Processing.

Features:
- Batch processing of multiple documents
- Priority queues (high_priority, normal, batch)
- Progress tracking for bulk jobs
- Retry logic with exponential backoff
- Integration with async batch processor
"""

import time
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select

from backend.core.database import engine
from backend.core.config import get_settings
from backend.models.db import Document, ExtractionResult, PatientTest, StandardizedTestDefinition

from workers.extraction.gemini import extract_lab_report
from workers.extraction.batch_processor import BatchProcessor, BatchResult
from workers.extraction.cache_manager import get_cache_manager
from workers.extraction.rate_limiter import get_rate_limiter

import redis
from rq import Queue, get_current_job
import asyncio

logger = logging.getLogger(__name__)
settings = get_settings()


# =============================================================================
# Batch Job Tracking
# =============================================================================

class BatchJobTracker:
    """Track progress of batch processing jobs."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.prefix = "batch_job:"
    
    def create_job(self, job_id: str, total: int) -> None:
        """Create a new batch job tracker."""
        key = f"{self.prefix}{job_id}"
        self.redis.hset(key, mapping={
            "total": total,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "cached": 0,
            "status": "processing",
            "started_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        })
        self.redis.expire(key, 86400)  # 24 hour expiry
    
    def update_progress(
        self,
        job_id: str,
        processed: int = 0,
        successful: int = 0,
        failed: int = 0,
        cached: int = 0
    ) -> None:
        """Update job progress."""
        key = f"{self.prefix}{job_id}"
        self.redis.hincrby(key, "processed", processed)
        self.redis.hincrby(key, "successful", successful)
        self.redis.hincrby(key, "failed", failed)
        self.redis.hincrby(key, "cached", cached)
        self.redis.hset(key, "updated_at", datetime.utcnow().isoformat())
    
    def complete_job(self, job_id: str, status: str = "completed") -> None:
        """Mark job as completed."""
        key = f"{self.prefix}{job_id}"
        self.redis.hset(key, mapping={
            "status": status,
            "completed_at": datetime.utcnow().isoformat()
        })
    
    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status."""
        key = f"{self.prefix}{job_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None
        
        return {
            k.decode() if isinstance(k, bytes) else k: 
            v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }


# =============================================================================
# Optimized Worker Tasks
# =============================================================================

def process_document(document_id: str) -> Dict[str, Any]:
    """
    Process a single document with caching support.
    
    This is the standard single-document processing task,
    enhanced with caching and rate limiting.
    """
    cache_manager = get_cache_manager()
    rate_limiter = get_rate_limiter()
    
    # Rate limiting
    rate_limiter.acquire()
    
    logger.info(f"Processing document: {document_id}")
    
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if not doc:
            logger.error(f"Document not found: {document_id}")
            return {"error": "Document not found"}
        
        # Check cache
        image_hash = cache_manager.get_image_hash(doc.file_path)
        cached = cache_manager.get_cached_result(image_hash)
        
        if cached:
            logger.info(f"Cache hit for document {document_id}")
            result_data = cached.get("result", {})
            from_cache = True
        else:
            # Update status
            doc.status = "processing"
            session.add(doc)
            session.commit()
            
            try:
                # Run extraction
                extraction_result = extract_lab_report(doc.file_path)
                result_data = extraction_result.data
                from_cache = False
                
                # Cache result
                cache_manager.cache_result(image_hash, result_data)
                rate_limiter.report_success()
                
            except Exception as e:
                logger.error(f"Extraction failed: {e}")
                rate_limiter.report_rate_limit_error() if "429" in str(e) else None
                
                doc.status = "failed"
                session.add(doc)
                session.commit()
                return {"error": str(e)}
        
        # Save results
        confidence = result_data.get("metadata", {}).get("confidence_score", 0.0)
        needs_review = result_data.get("metadata", {}).get("needs_review", False)
        
        result = ExtractionResult(
            document_id=document_id,
            extracted_data=result_data,
            confidence_score=confidence,
            needs_review=needs_review
        )
        session.add(result)
        
        # Save patient tests
        _save_patient_tests(
            session=session,
            document_id=document_id,
            lab_results=result_data.get("lab_results", []),
            patient_info=result_data.get("patient_info", {})
        )
        
        doc.status = "completed"
        session.add(doc)
        session.commit()
        
        return {
            "document_id": document_id,
            "success": True,
            "from_cache": from_cache,
            "confidence": confidence
        }


def process_document_batch(document_ids: List[str], job_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Process multiple documents as a batch.
    
    Args:
        document_ids: List of document IDs to process
        job_id: Optional job ID for tracking (generated if not provided)
        
    Returns:
        Batch processing results with statistics
    """
    job_id = job_id or str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(f"Starting batch job {job_id} with {len(document_ids)} documents")
    
    # Get Redis for tracking
    try:
        redis_client = redis.from_url(settings.redis.url)
        tracker = BatchJobTracker(redis_client)
        tracker.create_job(job_id, len(document_ids))
    except Exception as e:
        logger.warning(f"Job tracking unavailable: {e}")
        tracker = None
    
    results = {
        "job_id": job_id,
        "total": len(document_ids),
        "successful": 0,
        "failed": 0,
        "cached": 0,
        "errors": [],
        "documents": []
    }
    
    # Get image paths for batch processing
    with Session(engine) as session:
        docs = []
        for doc_id in document_ids:
            doc = session.get(Document, doc_id)
            if doc:
                docs.append(doc)
                doc.status = "processing"
                session.add(doc)
        session.commit()
    
    if not docs:
        logger.error("No valid documents found")
        return {"error": "No valid documents found", "job_id": job_id}
    
    # Use async batch processor
    api_key = settings.gemini.api_key
    if not api_key:
        return {"error": "Gemini API key not configured", "job_id": job_id}
    
    processor = BatchProcessor(
        api_key=api_key,
        max_workers=min(15, len(docs)),
        batch_delay_seconds=5.0
    )
    
    # Run batch processing
    image_paths = [doc.file_path for doc in docs]
    batch_result = asyncio.run(processor.process_images_async(image_paths))
    
    # Map results back to documents
    path_to_doc = {doc.file_path: doc for doc in docs}
    
    with Session(engine) as session:
        for result in batch_result.results:
            path = result["image_path"]
            doc = path_to_doc.get(path)
            
            if doc:
                data = result["data"]
                confidence = data.get("metadata", {}).get("confidence_score", 0.0)
                
                # Save extraction result
                extraction = ExtractionResult(
                    document_id=doc.id,
                    extracted_data=data,
                    confidence_score=confidence,
                    needs_review=data.get("metadata", {}).get("needs_review", False)
                )
                session.add(extraction)
                
                # Save patient tests
                _save_patient_tests(
                    session=session,
                    document_id=doc.id,
                    lab_results=data.get("lab_results", []),
                    patient_info=data.get("patient_info", {})
                )
                
                # Update document status
                doc_refresh = session.get(Document, doc.id)
                doc_refresh.status = "completed"
                session.add(doc_refresh)
                
                results["successful"] += 1
                if result["from_cache"]:
                    results["cached"] += 1
                
                results["documents"].append({
                    "document_id": doc.id,
                    "success": True,
                    "from_cache": result["from_cache"]
                })
        
        # Handle errors
        for error in batch_result.errors:
            results["failed"] += 1
            results["errors"].append(error)
            
            # Update failed document statuses
            if "image_path" in error:
                doc = path_to_doc.get(error["image_path"])
                if doc:
                    doc_refresh = session.get(Document, doc.id)
                    doc_refresh.status = "failed"
                    session.add(doc_refresh)
        
        session.commit()
    
    # Update tracker
    if tracker:
        tracker.update_progress(
            job_id,
            processed=results["total"],
            successful=results["successful"],
            failed=results["failed"],
            cached=results["cached"]
        )
        tracker.complete_job(job_id)
    
    results["processing_time"] = time.time() - start_time
    results["success_rate"] = results["successful"] / results["total"] if results["total"] > 0 else 0
    
    logger.info(
        f"Batch job {job_id} complete: {results['successful']}/{results['total']} successful, "
        f"{results['cached']} cached, {results['processing_time']:.1f}s"
    )
    
    return results


def submit_bulk_job(document_ids: List[str], batch_size: int = 50) -> Dict[str, Any]:
    """
    Submit a bulk job that splits documents into optimal batches.
    
    Args:
        document_ids: List of all document IDs to process
        batch_size: Documents per batch task
        
    Returns:
        Job submission info with batch IDs
    """
    job_id = str(uuid.uuid4())
    batches = [
        document_ids[i:i + batch_size]
        for i in range(0, len(document_ids), batch_size)
    ]
    
    logger.info(f"Submitting bulk job {job_id}: {len(document_ids)} documents in {len(batches)} batches")
    
    # Get queue
    try:
        redis_client = redis.from_url(settings.redis.url)
        queue = Queue("batch", connection=redis_client)
        
        batch_jobs = []
        for batch_idx, batch in enumerate(batches):
            batch_job_id = f"{job_id}_batch_{batch_idx}"
            job = queue.enqueue(
                process_document_batch,
                batch,
                batch_job_id,
                job_id=batch_job_id
            )
            batch_jobs.append({
                "batch_id": batch_job_id,
                "document_count": len(batch)
            })
        
        return {
            "job_id": job_id,
            "total_documents": len(document_ids),
            "batch_count": len(batches),
            "batch_size": batch_size,
            "batches": batch_jobs
        }
        
    except Exception as e:
        logger.error(f"Failed to submit bulk job: {e}")
        return {"error": str(e)}


# =============================================================================
# Helper Functions
# =============================================================================

def _save_patient_tests(
    session: Session,
    document_id: str,
    lab_results: List[Dict[str, Any]],
    patient_info: Dict[str, Any]
) -> int:
    """Save extracted lab results to PatientTest table."""
    saved_count = 0
    patient_name = patient_info.get('name')
    patient_id = patient_info.get('patient_id')
    
    for result in lab_results:
        try:
            original_name = result.get('test_name', result.get('original_name', ''))
            if not original_name:
                continue
            
            std_info = result.get('standardization', {})
            is_standardized = std_info.get('is_standardized', False)
            
            # Find test definition
            test_definition_id = None
            if is_standardized:
                canonical = result.get('test_name')
                if canonical:
                    defn = session.exec(
                        select(StandardizedTestDefinition)
                        .where(StandardizedTestDefinition.canonical_name == canonical)
                    ).first()
                    if defn:
                        test_definition_id = defn.id
            
            patient_test = PatientTest(
                document_id=document_id,
                test_definition_id=test_definition_id,
                patient_name=patient_name,
                patient_id=patient_id,
                original_test_name=result.get('original_name', original_name),
                standardized_test_name=result.get('test_name') if is_standardized else None,
                value=str(result.get('value', '')),
                unit=result.get('unit'),
                reference_range=result.get('reference_range'),
                flag=result.get('flag'),
                category=result.get('category'),
                loinc_code=result.get('loinc_code'),
                standardization_confidence=std_info.get('confidence', 0.0),
                match_type=std_info.get('match_type')
            )
            session.add(patient_test)
            saved_count += 1
            
        except Exception as e:
            logger.warning(f"Failed to save test: {e}")
    
    return saved_count


def get_batch_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get status of a batch job."""
    try:
        redis_client = redis.from_url(settings.redis.url)
        tracker = BatchJobTracker(redis_client)
        return tracker.get_status(job_id)
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        return None
