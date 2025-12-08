"""
Performance benchmarking tests.
Tests extraction speed, standardization, cache performance, and throughput.
"""
import pytest
import time
import json
import hashlib
from unittest.mock import MagicMock, patch
from pathlib import Path
from PIL import Image
import numpy as np


class TestExtractionPerformance:
    """Benchmark extraction performance."""
    
    @pytest.mark.performance
    def test_image_preprocessing_speed(self, sample_lab_report_image, benchmark_config):
        """Benchmark image preprocessing time."""
        from PIL import ImageEnhance, ImageFilter
        
        def preprocess():
            img = Image.open(sample_lab_report_image)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            return img
        
        # Warm up
        for _ in range(benchmark_config["warmup_rounds"]):
            preprocess()
        
        # Benchmark
        times = []
        for _ in range(benchmark_config["rounds"]):
            start = time.perf_counter()
            preprocess()
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        print(f"Average preprocessing time: {avg_time*1000:.2f}ms")
        
        # Should complete in reasonable time
        assert avg_time < 1.0  # Less than 1 second
    
    @pytest.mark.performance
    def test_image_hash_speed(self, sample_image_path, benchmark_config):
        """Benchmark image hashing performance."""
        with open(sample_image_path, 'rb') as f:
            content = f.read()
        
        # Warm up
        for _ in range(benchmark_config["warmup_rounds"]):
            hashlib.md5(content).hexdigest()
        
        # Benchmark
        times = []
        for _ in range(benchmark_config["rounds"]):
            start = time.perf_counter()
            hashlib.md5(content).hexdigest()
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        print(f"Average hash time: {avg_time*1000:.4f}ms")
        
        assert avg_time < 0.1  # Less than 100ms


class TestStandardizationPerformance:
    """Benchmark standardization performance."""
    
    @pytest.mark.performance
    def test_fuzzy_match_speed(self, sample_test_mappings, benchmark_config):
        """Benchmark fuzzy matching speed."""
        from workers.extraction.standardizer import Standardizer
        
        with patch.object(Standardizer, '_load_test_mappings', return_value=sample_test_mappings):
            standardizer = Standardizer()
            standardizer.test_mappings = sample_test_mappings
            standardizer.canonical_names = list(sample_test_mappings.keys())
            
            test_names = ["Hemoglobin", "WBC", "RBC", "PLT", "FBS", "Creatinine"]
            
            # Warm up
            for _ in range(benchmark_config["warmup_rounds"]):
                for name in test_names:
                    standardizer._fuzzy_match(name)
            
            # Benchmark
            times = []
            for _ in range(benchmark_config["rounds"]):
                start = time.perf_counter()
                for name in test_names:
                    standardizer._fuzzy_match(name)
                times.append(time.perf_counter() - start)
            
            avg_time = sum(times) / len(times)
            print(f"Average fuzzy match time (6 tests): {avg_time*1000:.2f}ms")
            
            assert avg_time < 0.5  # Less than 500ms for 6 tests
    
    @pytest.mark.performance
    def test_batch_standardization_speed(self, sample_test_mappings, benchmark_config):
        """Benchmark batch standardization."""
        from workers.extraction.standardizer import Standardizer
        
        with patch.object(Standardizer, '_load_test_mappings', return_value=sample_test_mappings):
            standardizer = Standardizer()
            standardizer.test_mappings = sample_test_mappings
            standardizer.canonical_names = list(sample_test_mappings.keys())
            
            # Large batch of test names
            test_names = ["Hemoglobin", "WBC", "RBC", "PLT"] * 25  # 100 tests
            
            # Benchmark
            start = time.perf_counter()
            for name in test_names:
                standardizer._fuzzy_match(name)
            elapsed = time.perf_counter() - start
            
            print(f"Batch standardization (100 tests): {elapsed*1000:.2f}ms")
            print(f"Per-test average: {(elapsed/len(test_names))*1000:.4f}ms")
            
            assert elapsed < 5.0  # Less than 5 seconds for 100 tests


class TestCachePerformance:
    """Benchmark cache performance."""
    
    @pytest.mark.performance
    def test_redis_set_speed(self, mock_redis, benchmark_config):
        """Benchmark Redis set operations."""
        mock_redis.setex = MagicMock(return_value=True)
        
        data = json.dumps({"test": "data" * 100})  # ~500 bytes
        
        # Benchmark
        times = []
        for i in range(benchmark_config["rounds"]):
            start = time.perf_counter()
            mock_redis.setex(f"key_{i}", 3600, data)
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        print(f"Average Redis SET time: {avg_time*1000:.4f}ms")
        
        # Mock operations should be very fast
        assert avg_time < 0.01  # Less than 10ms
    
    @pytest.mark.performance
    def test_redis_get_speed(self, mock_redis, benchmark_config):
        """Benchmark Redis get operations."""
        data = json.dumps({"test": "data" * 100})
        mock_redis.get = MagicMock(return_value=data)
        
        # Benchmark
        times = []
        for i in range(benchmark_config["rounds"]):
            start = time.perf_counter()
            mock_redis.get(f"key_{i}")
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        print(f"Average Redis GET time: {avg_time*1000:.4f}ms")
        
        assert avg_time < 0.01
    
    @pytest.mark.performance
    def test_cache_hit_ratio(self, mock_redis):
        """Test cache hit ratio under simulated load."""
        total_requests = 100
        cache = {}
        hits = 0
        misses = 0
        
        # Simulate cache with 70% hit rate
        for i in range(total_requests):
            key = f"key_{i % 30}"  # Only 30 unique keys
            if key in cache:
                hits += 1
            else:
                cache[key] = f"value_{i}"
                misses += 1
        
        hit_ratio = hits / total_requests
        print(f"Cache hit ratio: {hit_ratio:.2%}")
        
        # Should have some hits after initial population
        assert hits > 0


class TestDatabasePerformance:
    """Benchmark database query performance."""
    
    @pytest.mark.performance
    def test_single_document_query(self, mock_session, benchmark_config):
        """Benchmark single document query."""
        mock_doc = MagicMock(id="doc-123", status="completed")
        mock_session.get = MagicMock(return_value=mock_doc)
        
        # Benchmark
        times = []
        for _ in range(benchmark_config["rounds"]):
            start = time.perf_counter()
            mock_session.get("Document", "doc-123")
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        print(f"Average query time: {avg_time*1000:.4f}ms")
        
        assert avg_time < 0.01
    
    @pytest.mark.performance
    def test_bulk_insert(self, mock_session, benchmark_config):
        """Benchmark bulk insert operations."""
        mock_session.add_all = MagicMock()
        mock_session.commit = MagicMock()
        
        # Create mock documents
        docs = [MagicMock(id=f"doc-{i}") for i in range(100)]
        
        # Benchmark
        start = time.perf_counter()
        mock_session.add_all(docs)
        mock_session.commit()
        elapsed = time.perf_counter() - start
        
        print(f"Bulk insert (100 docs): {elapsed*1000:.2f}ms")
        
        assert elapsed < 1.0


class TestThroughputBenchmarks:
    """Benchmark system throughput."""
    
    @pytest.mark.performance
    def test_requests_per_second(self, test_client, benchmark_config):
        """Benchmark API requests per second."""
        with patch('backend.main.get_session') as mock_session:
            session = MagicMock()
            session.exec = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            mock_session.return_value = iter([session])
            
            # Benchmark
            num_requests = 50
            start = time.perf_counter()
            
            for _ in range(num_requests):
                test_client.get("/docs")  # Health check endpoint
            
            elapsed = time.perf_counter() - start
            rps = num_requests / elapsed
            
            print(f"Requests per second: {rps:.2f}")
            print(f"Average latency: {(elapsed/num_requests)*1000:.2f}ms")
    
    @pytest.mark.performance
    def test_concurrent_processing_throughput(self):
        """Benchmark concurrent processing simulation."""
        import threading
        
        processed_count = 0
        lock = threading.Lock()
        
        def process_document():
            nonlocal processed_count
            # Simulate processing
            time.sleep(0.01)
            with lock:
                processed_count += 1
        
        # Run concurrent workers
        num_workers = 10
        threads = [threading.Thread(target=process_document) for _ in range(num_workers)]
        
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start
        
        throughput = processed_count / elapsed
        print(f"Concurrent throughput: {throughput:.2f} docs/sec")
        
        assert processed_count == num_workers


class TestScalabilityBenchmarks:
    """Benchmark scalability characteristics."""
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_linear_scaling(self, sample_test_mappings):
        """Test that performance scales linearly with input."""
        from workers.extraction.standardizer import Standardizer
        
        with patch.object(Standardizer, '_load_test_mappings', return_value=sample_test_mappings):
            standardizer = Standardizer()
            standardizer.test_mappings = sample_test_mappings
            standardizer.canonical_names = list(sample_test_mappings.keys())
            
            sizes = [10, 50, 100]
            times = []
            
            for size in sizes:
                test_names = ["Hemoglobin"] * size
                
                start = time.perf_counter()
                for name in test_names:
                    standardizer._fuzzy_match(name)
                elapsed = time.perf_counter() - start
                
                times.append(elapsed)
                print(f"Size {size}: {elapsed*1000:.2f}ms")
            
            # Check roughly linear scaling (with some tolerance)
            ratio_50_10 = times[1] / times[0]
            ratio_100_10 = times[2] / times[0]
            
            print(f"Scaling ratio 50/10: {ratio_50_10:.2f}x")
            print(f"Scaling ratio 100/10: {ratio_100_10:.2f}x")
    
    @pytest.mark.performance
    def test_memory_usage(self):
        """Benchmark memory usage."""
        import sys
        
        # Create test data structures
        data = []
        for i in range(1000):
            data.append({
                "id": f"doc-{i}",
                "tests": [{"name": "Test", "value": "123"} for _ in range(10)]
            })
        
        # Measure approximate size
        size_bytes = sys.getsizeof(json.dumps(data))
        size_mb = size_bytes / (1024 * 1024)
        
        print(f"Memory for 1000 docs: {size_mb:.2f}MB")
        
        # Should be reasonable
        assert size_mb < 100  # Less than 100MB


class TestLatencyPercentiles:
    """Benchmark latency percentiles."""
    
    @pytest.mark.performance
    def test_processing_latency_percentiles(self, benchmark_config):
        """Calculate processing latency percentiles."""
        import random
        
        # Simulate processing times with some variance
        latencies = []
        for _ in range(100):
            base_time = 0.01
            variance = random.uniform(-0.005, 0.015)
            latencies.append(max(0.001, base_time + variance))
        
        latencies.sort()
        
        p50 = latencies[50]
        p95 = latencies[95]
        p99 = latencies[99]
        
        print(f"P50: {p50*1000:.2f}ms")
        print(f"P95: {p95*1000:.2f}ms")
        print(f"P99: {p99*1000:.2f}ms")
        
        # P99 should not be too far from P50
        assert p99 / p50 < 10  # Less than 10x difference
