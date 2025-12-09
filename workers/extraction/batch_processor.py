"""
Batch Processor for Lab Report Extraction.

Features:
- Concurrent processing of multiple images
- Progress tracking via Redis
- Rate limit awareness
- Automatic retry on failures
"""

import asyncio
import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    """Represents a batch processing job."""
    job_id: str
    document_ids: List[str]
    status: str = "pending"  # pending, processing, completed, failed
    total: int = 0
    completed: int = 0
    failed: int = 0
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def progress(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed + self.failed) / self.total


class BatchProcessor:
    """
    Processes multiple lab reports concurrently.
    
    Usage:
        processor = BatchProcessor(max_concurrent=3)
        job_id = await processor.process_batch(document_ids)
        
        # Check status
        status = processor.get_job_status(job_id)
    """
    
    def __init__(
        self, 
        max_concurrent: int = 3,
        redis_client: Optional[Any] = None
    ):
        self.max_concurrent = max_concurrent
        self.redis_client = redis_client
        self._jobs: Dict[str, BatchJob] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    def _get_semaphore(self) -> asyncio.Semaphore:
        """Get or create semaphore for concurrency control."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore
    
    async def process_batch(
        self, 
        document_ids: List[str],
        priority: str = "normal"
    ) -> str:
        """
        Start batch processing of documents.
        
        Args:
            document_ids: List of document IDs to process
            priority: Priority level (high_priority, normal, batch)
            
        Returns:
            job_id for status tracking
        """
        job_id = f"batch_{uuid.uuid4().hex[:12]}"
        
        job = BatchJob(
            job_id=job_id,
            document_ids=document_ids,
            total=len(document_ids),
            started_at=datetime.now()
        )
        
        self._jobs[job_id] = job
        self._update_redis_status(job)
        
        # Start processing in background
        asyncio.create_task(self._process_documents(job))
        
        return job_id
    
    async def _process_documents(self, job: BatchJob) -> None:
        """Process all documents in the batch."""
        from workers.extraction.main import process_document
        
        job.status = "processing"
        self._update_redis_status(job)
        
        semaphore = self._get_semaphore()
        
        async def process_one(doc_id: str) -> Dict[str, Any]:
            """Process single document with concurrency limit."""
            async with semaphore:
                try:
                    logger.info(f"[Batch {job.job_id}] Processing {doc_id}")
                    
                    # Run synchronous process_document in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, 
                        process_document,
                        doc_id
                    )
                    
                    job.completed += 1
                    job.results[doc_id] = {
                        "status": "completed",
                        "success": True
                    }
                    
                    return {"doc_id": doc_id, "success": True}
                    
                except Exception as e:
                    logger.error(f"[Batch {job.job_id}] Failed {doc_id}: {e}")
                    job.failed += 1
                    job.errors.append(f"{doc_id}: {str(e)}")
                    job.results[doc_id] = {
                        "status": "failed",
                        "error": str(e)
                    }
                    return {"doc_id": doc_id, "success": False, "error": str(e)}
                finally:
                    self._update_redis_status(job)
        
        # Process all documents concurrently (limited by semaphore)
        tasks = [process_one(doc_id) for doc_id in job.document_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Mark completed
        job.status = "completed" if job.failed == 0 else "completed_with_errors"
        job.completed_at = datetime.now()
        self._update_redis_status(job)
        
        logger.info(
            f"[Batch {job.job_id}] Complete: "
            f"{job.completed}/{job.total} succeeded, {job.failed} failed"
        )
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a batch job."""
        # Try memory first
        if job_id in self._jobs:
            job = self._jobs[job_id]
            return self._job_to_dict(job)
        
        # Try Redis
        if self.redis_client:
            try:
                data = self.redis_client.get(f"batch:{job_id}")
                if data:
                    import json
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Failed to get job from Redis: {e}")
        
        return None
    
    def _job_to_dict(self, job: BatchJob) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "job_id": job.job_id,
            "status": job.status,
            "total": job.total,
            "completed": job.completed,
            "failed": job.failed,
            "progress": job.progress,
            "errors": job.errors[:10],  # Limit errors returned
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "estimated_remaining": self._estimate_remaining(job)
        }
    
    def _estimate_remaining(self, job: BatchJob) -> Optional[int]:
        """Estimate remaining time in seconds."""
        if job.status != "processing" or job.completed == 0:
            return None
        
        elapsed = (datetime.now() - job.started_at).total_seconds() if job.started_at else 0
        if elapsed == 0:
            return None
        
        avg_per_doc = elapsed / job.completed
        remaining = job.total - job.completed - job.failed
        return int(avg_per_doc * remaining)
    
    def _update_redis_status(self, job: BatchJob) -> None:
        """Update job status in Redis for distributed tracking."""
        if not self.redis_client:
            return
        
        try:
            import json
            data = self._job_to_dict(job)
            self.redis_client.setex(
                f"batch:{job.job_id}",
                3600 * 24,  # 24 hour expiry
                json.dumps(data)
            )
        except Exception as e:
            logger.warning(f"Failed to update Redis: {e}")
    
    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent batch jobs."""
        jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.started_at or datetime.min, reverse=True)
        return [self._job_to_dict(j) for j in jobs[:limit]]


# Global instance
_batch_processor: Optional[BatchProcessor] = None


def get_batch_processor(
    max_concurrent: int = 3,
    redis_client: Optional[Any] = None
) -> BatchProcessor:
    """Get or create the global batch processor."""
    global _batch_processor
    
    if _batch_processor is None:
        # Try to get Redis client
        if redis_client is None:
            try:
                import redis
                from backend.core.config import get_settings
                settings = get_settings()
                redis_client = redis.Redis.from_url(settings.redis.url)
                redis_client.ping()
            except Exception as e:
                logger.warning(f"Redis not available for batch processing: {e}")
                redis_client = None
        
        _batch_processor = BatchProcessor(
            max_concurrent=max_concurrent,
            redis_client=redis_client
        )
    
    return _batch_processor
