#!/bin/bash
# Run pytest for lab extraction system tests

cd "$(dirname "$0")"

echo "Running Lab Extraction System Tests..."
echo "========================================"

# Run working tests
pytest tests/unit/test_rate_limiter.py tests/unit/test_cache_manager.py -v --tb=short

# Uncomment below to run all tests (after fixing pydantic version):
# pytest tests/ -v --tb=short --cov=workers --cov=backend --cov-report=term-missing
