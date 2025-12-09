"""
API Route modules.

This package contains modular route files:
- documents: Document upload, status, results
- tests: Test analytics, export, trends
- storage: Storage management
- batch: Batch processing
"""

from backend.api.documents import router as documents_router
from backend.api.tests import router as tests_router
from backend.api.storage import router as storage_router

__all__ = [
    'documents_router',
    'tests_router', 
    'storage_router',
]
