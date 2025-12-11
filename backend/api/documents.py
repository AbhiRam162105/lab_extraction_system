"""
Document Routes - Upload, status, and results endpoints.
"""

import shutil
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlmodel import Session, select
from rq import Queue
from rq.job import Job

from backend.core.config import get_settings
from backend.core.database import get_session
from backend.core.queue import get_queue
from backend.models.db import Document, ExtractionResult
from backend.utils.image_optimizer import get_optimizer

settings = get_settings()
router = APIRouter(tags=["Documents"])


@router.post("/upload")
def upload_files(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    queue: Queue = Depends(get_queue)
):
    """
    Upload lab report files for processing.
    
    Returns info about:
    - new_files: Files that were uploaded and queued for processing
    - duplicates: Files that were already uploaded previously (skipped)
    """
    
    
    uploaded_docs = []
    duplicate_info = []  # Track duplicates to inform user
    new_files = []       # Track actually new files
    storage_path = Path(settings.storage.base_path) / settings.storage.bucket
    storage_path.mkdir(parents=True, exist_ok=True)
    optimizer = get_optimizer()

    for file in files:
        file_id = str(uuid.uuid4())
        
        # Save uploaded file to temp location first
        temp_filename = f"temp_{file_id}_{file.filename}"
        temp_location = storage_path / temp_filename
        
        with open(temp_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        
        # Optimize image (compress, resize, deduplicate)
        try:
            optimized_path, is_duplicate, stats = optimizer.optimize_and_store(
                input_path=str(temp_location),
                output_dir=str(storage_path),
                original_filename=file.filename
            )
            
            # Remove temp file
            if temp_location.exists():
                temp_location.unlink()
            
            # If duplicate, find existing document and inform user
            if is_duplicate:
                existing_doc = session.exec(
                    select(Document).where(Document.file_path == optimized_path)
                ).first()
                if existing_doc:
                    duplicate_info.append({
                        "uploaded_filename": file.filename,
                        "existing_filename": existing_doc.filename,
                        "existing_id": existing_doc.id,
                        "upload_date": existing_doc.upload_date.isoformat() if existing_doc.upload_date else None,
                        "status": existing_doc.status,
                        "message": f"'{file.filename}' is a duplicate of '{existing_doc.filename}' (uploaded previously)"
                    })
                    uploaded_docs.append(existing_doc)
                    continue
            
            # Create new document record
            doc = Document(
                id=file_id,
                filename=file.filename,
                file_path=optimized_path,
                content_type=file.content_type or "application/octet-stream",
                status="queued",
                phash=stats.get('phash') if stats else None
            )
            session.add(doc)
            uploaded_docs.append(doc)
            new_files.append({
                "id": file_id,
                "filename": file.filename,
                "status": "queued"
            })
            
            # Enqueue task with 600s timeout
            queue.enqueue('workers.extraction.main.process_document', file_id, job_id=file_id, job_timeout=600)
            
        except Exception as e:
            import logging
            logging.warning(f"Image optimization failed, using original: {e}")
            
            # Move temp to permanent location
            safe_filename = f"{file_id}_{file.filename}"
            file_location = storage_path / safe_filename
            temp_location.rename(file_location)
            
            doc = Document(
                id=file_id,
                filename=file.filename,
                file_path=str(file_location),
                content_type=file.content_type or "application/octet-stream",
                status="queued"
            )
            session.add(doc)
            uploaded_docs.append(doc)
            new_files.append({
                "id": file_id,
                "filename": file.filename,
                "status": "queued"
            })
            queue.enqueue('workers.extraction.main.process_document', file_id, job_id=file_id, job_timeout=600)

    session.commit()
    for doc in uploaded_docs:
        session.refresh(doc)
    
    # Return detailed response with duplicate info
    return {
        "total_uploaded": len(files),
        "new_files_count": len(new_files),
        "duplicates_count": len(duplicate_info),
        "new_files": new_files,
        "duplicates": duplicate_info,
        "documents": uploaded_docs,
        "message": _generate_upload_message(len(new_files), len(duplicate_info))
    }


def _generate_upload_message(new_count: int, dup_count: int) -> str:
    """Generate user-friendly message about upload results."""
    if dup_count == 0:
        return f"Successfully queued {new_count} file(s) for processing."
    elif new_count == 0:
        return f"All {dup_count} file(s) were already uploaded previously. No new processing needed."
    else:
        return f"Queued {new_count} new file(s). {dup_count} file(s) were duplicates (already uploaded)."


@router.get("/documents", response_model=List[Document])
def get_documents(session: Session = Depends(get_session)):
    """Get all documents."""
    docs = session.exec(select(Document).order_by(Document.upload_date.desc())).all()
    return docs


@router.get("/documents/flagged")
def get_flagged_documents(session: Session = Depends(get_session)):
    """Get documents flagged for review due to low quality images."""
    flagged = session.exec(
        select(Document, ExtractionResult)
        .join(ExtractionResult, Document.id == ExtractionResult.document_id)
        .where(ExtractionResult.needs_review == True)
        .order_by(Document.upload_date.desc())
    ).all()
    
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "upload_date": doc.upload_date.isoformat(),
            "status": doc.status,
            "review_reason": result.review_reason,
            "confidence_score": result.confidence_score
        }
        for doc, result in flagged
    ]


@router.get("/results/{document_id}")
def get_results(document_id: str, session: Session = Depends(get_session)):
    """Get extraction results for a document."""
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


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str, queue: Queue = Depends(get_queue)):
    """Get task processing status."""
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


# =============================================================================
# Batch Processing
# =============================================================================

@router.post("/batch/upload")
async def batch_upload(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    queue: Queue = Depends(get_queue)
):
    """
    Upload and process multiple files as a batch.
    
    Returns a job_id that can be used to track progress.
    """
    from backend.utils.image_optimizer import get_optimizer
    import asyncio
    
    storage_path = Path(settings.storage.base_path) / settings.storage.bucket
    storage_path.mkdir(parents=True, exist_ok=True)
    optimizer = get_optimizer()
    
    document_ids = []
    
    for file in files:
        file_id = str(uuid.uuid4())
        
        # Save file
        temp_filename = f"temp_{file_id}_{file.filename}"
        temp_location = storage_path / temp_filename
        
        content = await file.read()
        with open(temp_location, "wb") as f:
            f.write(content)
        
        try:
            optimized_path, is_duplicate, stats = optimizer.optimize_and_store(
                input_path=str(temp_location),
                output_dir=str(storage_path),
                original_filename=file.filename
            )
            
            if temp_location.exists():
                temp_location.unlink()
            
            if is_duplicate:
                existing_doc = session.exec(
                    select(Document).where(Document.file_path == optimized_path)
                ).first()
                if existing_doc:
                    document_ids.append(existing_doc.id)
                    continue
            
            doc = Document(
                id=file_id,
                filename=file.filename,
                file_path=optimized_path,
                content_type=file.content_type or "application/octet-stream",
                status="queued",
                phash=stats.get('phash') if stats else None
            )
            session.add(doc)
            document_ids.append(file_id)
            
        except Exception as e:
            import logging
            logging.warning(f"Failed to process {file.filename}: {e}")
    
    session.commit()
    
    # Enqueue all documents for processing
    for doc_id in document_ids:
        queue.enqueue(
            'workers.extraction.main.process_document', 
            doc_id, 
            job_id=doc_id, 
            job_timeout=600
        )
    
    # Create batch job for tracking
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    
    # Store batch info in Redis for tracking
    try:
        import redis
        import json
        redis_client = redis.Redis.from_url(settings.redis.url)
        batch_data = {
            "batch_id": batch_id,
            "document_ids": document_ids,
            "total": len(document_ids),
            "status": "processing"
        }
        redis_client.setex(f"batch:{batch_id}", 3600 * 24, json.dumps(batch_data))
    except Exception:
        pass
    
    return {
        "batch_id": batch_id,
        "document_ids": document_ids,
        "total_files": len(document_ids),
        "status": "processing"
    }


@router.get("/batch/{batch_id}/status")
def get_batch_status(batch_id: str, session: Session = Depends(get_session)):
    """Get status of a batch processing job."""
    import json
    
    # Try to get batch info from Redis
    try:
        import redis
        redis_client = redis.Redis.from_url(settings.redis.url)
        batch_data = redis_client.get(f"batch:{batch_id}")
        
        if batch_data:
            batch_info = json.loads(batch_data)
            document_ids = batch_info.get("document_ids", [])
            
            # Check status of each document
            completed = 0
            failed = 0
            processing = 0
            
            for doc_id in document_ids:
                doc = session.get(Document, doc_id)
                if doc:
                    if doc.status == "completed":
                        completed += 1
                    elif doc.status == "failed":
                        failed += 1
                    else:
                        processing += 1
            
            total = len(document_ids)
            progress = (completed + failed) / total if total > 0 else 0
            
            status = "completed" if processing == 0 else "processing"
            if failed > 0 and processing == 0:
                status = "completed_with_errors"
            
            return {
                "batch_id": batch_id,
                "status": status,
                "total": total,
                "completed": completed,
                "failed": failed,
                "processing": processing,
                "progress": progress
            }
    except Exception as e:
        import logging
        logging.warning(f"Failed to get batch status: {e}")
    
    raise HTTPException(status_code=404, detail="Batch job not found")
