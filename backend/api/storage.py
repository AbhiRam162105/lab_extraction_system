"""
Storage Routes - Storage management and cleanup.
"""

from pathlib import Path
from typing import List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from backend.core.config import get_settings
from backend.core.database import get_session
from backend.models.db import Document

settings = get_settings()
router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/stats")
def get_storage_stats():
    """Get storage statistics."""
    storage_path = Path(settings.storage.base_path) / settings.storage.bucket
    
    if not storage_path.exists():
        return {
            "total_files": 0,
            "total_size_mb": 0,
            "storage_path": str(storage_path)
        }
    
    files = list(storage_path.glob("*"))
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    
    return {
        "total_files": len([f for f in files if f.is_file()]),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "storage_path": str(storage_path),
        "files_by_type": _count_files_by_type(files)
    }


def _count_files_by_type(files: List[Path]) -> dict:
    """Count files by extension."""
    from collections import Counter
    extensions = [f.suffix.lower() for f in files if f.is_file()]
    return dict(Counter(extensions))


@router.post("/cleanup")
def cleanup_storage(
    dry_run: bool = Query(True, description="Preview cleanup without deleting"),
    session: Session = Depends(get_session)
):
    """Clean up old files based on retention policy."""
    storage_path = Path(settings.storage.base_path) / settings.storage.bucket
    
    if not storage_path.exists():
        return {"deleted": 0, "message": "Storage path does not exist"}
    
    # Find documents older than retention period (default 30 days)
    retention_days = 30
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    old_docs = session.exec(
        select(Document).where(Document.upload_date < cutoff_date)
    ).all()
    
    files_to_delete = []
    for doc in old_docs:
        file_path = Path(doc.file_path)
        if file_path.exists():
            files_to_delete.append({
                "document_id": doc.id,
                "filename": doc.filename,
                "path": str(file_path),
                "size_kb": round(file_path.stat().st_size / 1024, 2)
            })
    
    if dry_run:
        return {
            "dry_run": True,
            "would_delete": len(files_to_delete),
            "files": files_to_delete
        }
    
    # Actually delete files
    deleted_count = 0
    for file_info in files_to_delete:
        try:
            Path(file_info["path"]).unlink()
            deleted_count += 1
        except Exception as e:
            import logging
            logging.error(f"Failed to delete {file_info['path']}: {e}")
    
    return {
        "dry_run": False,
        "deleted": deleted_count,
        "total_attempted": len(files_to_delete)
    }


@router.get("/cache-stats")
def get_cache_stats():
    """Get cache statistics."""
    try:
        from workers.extraction.cache_manager import get_cache_manager
        cache = get_cache_manager()
        stats = cache.get_stats()
        
        return {
            "caching_enabled": True,
            **stats
        }
        
    except Exception as e:
        return {
            "caching_enabled": False,
            "error": str(e)
        }


@router.get("/rate-limit-stats")
def get_rate_limit_stats():
    """Get rate limiting statistics."""
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
