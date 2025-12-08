# Lab Extraction System - Testing Guide

## 📋 Overview

This testing suite provides comprehensive coverage for the lab extraction system, including unit tests, integration tests, end-to-end tests, and performance benchmarks.

## 🚀 Quick Start

### Install Dependencies

```bash
pip install -r requirements-test.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# E2E tests
pytest tests/e2e/ -v

# Performance benchmarks
pytest tests/performance/ -v -m performance
```

## 📂 Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests
│   ├── test_standardizer.py # Test name standardization
│   ├── test_cache_manager.py# Caching functionality
│   ├── test_preprocessing.py# Image preprocessing
│   └── test_rate_limiter.py # Rate limiting
├── integration/             # Integration tests
│   └── test_api_endpoints.py# API endpoint tests
├── e2e/                     # End-to-end tests
│   └── test_extraction_pipeline.py
├── performance/             # Performance tests
│   ├── benchmark_tests.py   # Benchmarks
│   └── locustfile.py        # Load testing
└── fixtures/                # Test data
    └── sample_lab_reports.py
```

## 🏷️ Test Markers

Use markers to run specific test types:

```bash
# Run only unit tests
pytest -m unit

# Run slow tests
pytest -m slow

# Skip Redis-dependent tests
pytest -m "not redis"

# Run performance tests
pytest -m performance
```

## 🔧 Configuration

### pytest.ini Settings

- Test discovery: `tests/` directory
- Markers: `unit`, `integration`, `e2e`, `performance`, `slow`, `redis`, `database`
- Async mode: Auto

### Environment Variables

```bash
export TESTING=true
export REDIS__URL=redis://localhost:6379/15
export DATABASE__URL=sqlite:///./test.db
```

## 📊 Performance Testing

### Benchmarks

```bash
pytest tests/performance/benchmark_tests.py -v --benchmark-autosave
```

### Load Testing with Locust

```bash
# Start Locust web UI
locust -f tests/performance/locustfile.py --host=http://localhost:6000

# Headless mode
locust -f tests/performance/locustfile.py --host=http://localhost:6000 \
  --users 50 --spawn-rate 5 --run-time 60s --headless
```

## 🧪 Writing Tests

### Unit Test Example

```python
def test_fuzzy_match(sample_test_mappings):
    from workers.extraction.standardizer import Standardizer
    
    standardizer = Standardizer()
    result = standardizer._fuzzy_match("Hemoglobin")
    
    assert result is not None
    assert result[0] == "Hemoglobin"
```

### Using Fixtures

```python
def test_with_mock_redis(mock_redis):
    mock_redis.get.return_value = '{"cached": true}'
    result = mock_redis.get("key")
    assert result is not None
```

### Mocking Gemini API

All tests mock the Gemini API to avoid actual API calls:

```python
def test_extraction(mock_gemini_extractor):
    # Gemini is mocked, no API calls made
    result = mock_gemini_extractor.extract("image.png")
    assert "tests" in result
```

## 📈 Coverage

Generate coverage report:

```bash
pytest --cov=workers --cov=backend --cov-report=html

# View report
open htmlcov/index.html
```

## 🐳 Docker Testing

Run tests in Docker:

```bash
docker-compose -f docker-compose.test.yaml up --build
```

## ⚡ CI/CD Integration

The test suite integrates with GitHub Actions. See `.github/workflows/tests.yml` for the pipeline configuration.

## 🔍 Debugging Tips

1. **Verbose output**: `pytest -v -s`
2. **Stop on first failure**: `pytest -x`
3. **Run specific test**: `pytest tests/unit/test_standardizer.py::TestFuzzyMatching::test_exact_match`
4. **Show print statements**: `pytest -s`
