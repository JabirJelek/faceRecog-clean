#!/usr/bin/env python3
"""
Comprehensive testing workflow for VoyagerFaceRecognitionSystem
Measures performance, accuracy, robustness, and scalability
"""

import unittest
import tempfile
import json
import time
import numpy as np
import torch
from pathlib import Path
import logging
import gc
from typing import Dict, List, Tuple
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recognition.voyager_system import VoyagerFaceRecognitionSystem, VoyagerPerformanceMonitor


class TestVoyagerFaceRecognitionSystem(unittest.TestCase):
    """Main test class for VoyagerFaceRecognitionSystem"""
    
    @classmethod
    def setUpClass(cls):
        """Setup test environment once for all tests"""
        cls.test_dir = tempfile.mkdtemp(prefix="voyager_test_")
        cls.embedding_dim = 512  # Default dimension for ArcFace
        cls.num_test_identities = 10
        cls.num_test_embeddings_per_identity = 5
        
        # Configure logging for tests
        logging.basicConfig(
            level=logging.WARNING,  # Reduce noise during tests
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        cls.logger = logging.getLogger(__name__)
        
        # Generate test data
        cls.test_data = cls._generate_test_data()
        
        cls.logger.info(f"Test directory: {cls.test_dir}")
        cls.logger.info(f"Generated {cls.num_test_identities} test identities")
    
    @classmethod
    def _generate_test_data(cls):
        """Generate synthetic test data with realistic patterns"""
        np.random.seed(42)  # For reproducibility
        torch.manual_seed(42)
        
        data = {}
        
        # Generate base embeddings for each identity
        for i in range(cls.num_test_identities):
            identity_name = f"TestPerson_{i+1}"
            base_embedding = np.random.randn(cls.embedding_dim).astype(np.float32)
            base_embedding = base_embedding / np.linalg.norm(base_embedding)
            
            # Generate variations around the base embedding (simulating same person)
            embeddings = []
            for j in range(cls.num_test_embeddings_per_identity):
                # Add small Gaussian noise to create variations
                variation = base_embedding + np.random.normal(0, 0.1, cls.embedding_dim)
                variation = variation / np.linalg.norm(variation)
                embeddings.append(variation.tolist())
            
            data[identity_name] = {
                "base_embedding": base_embedding.tolist(),
                "variations": embeddings,
                "embeddings": [{"vector": emb, "source": f"test_{j}"} 
                              for j, emb in enumerate(embeddings)]
            }
        
        # Generate some completely random embeddings for unknown identities
        unknown_embeddings = []
        for i in range(5):
            random_emb = np.random.randn(cls.embedding_dim).astype(np.float32)
            random_emb = random_emb / np.linalg.norm(random_emb)
            unknown_embeddings.append(random_emb)
        
        data["unknown_embeddings"] = unknown_embeddings
        
        return data
    
    def setUp(self):
        """Setup for each test"""
        # Create test database file
        self.db_path = Path(self.test_dir) / "test_embeddings.json"
        self._create_test_database()
        
        # Default configuration for tests
        self.config = {
            'embeddings_db_path': str(self.db_path),
            'recognition_threshold': 0.6,
            'embedding_model': 'ArcFace',
            'use_voyager': True,
            'verbose_voyager': False,
            'device': 'cuda' if torch.cuda.is_available() else 'cpu'
        }
        
        # Clean up any previous GPU memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
    def _create_test_database(self):
        """Create a test JSON database"""
        db_structure = {
            "persons": {},
            "metadata": {
                "embedding_model": "ArcFace",
                "embedding_length": self.embedding_dim,
                "creation_time": time.time()
            }
        }
        
        # Add test identities to database
        for i, (identity_name, data) in enumerate(self.test_data.items()):
            if identity_name == "unknown_embeddings":
                continue
                
            db_structure["persons"][f"person_{i}"] = {
                "display_name": identity_name,
                "person_id": f"person_{i}",
                "embeddings": data["embeddings"],
                "centroid_embedding": data["base_embedding"],
                "embedding_count": len(data["embeddings"])
            }
        
        # Save to file
        with open(self.db_path, 'w') as f:
            json.dump(db_structure, f, indent=2)
    
    def tearDown(self):
        """Cleanup after each test"""
        # Force garbage collection
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    # ===== CORE FUNCTIONALITY TESTS =====
    
    def test_01_initialization(self):
        """Test system initialization"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        # Check basic initialization
        self.assertIsNotNone(system)
        self.assertIsNotNone(system.voyager_index)
        self.assertEqual(len(system.voyager_id_to_identity), self.num_test_identities)
        
        # Check GPU tensor initialization
        if torch.cuda.is_available():
            self.assertIsNotNone(system.identity_centroids_tensor)
            self.assertEqual(len(system.identity_names_list), self.num_test_identities)
        
        system.print_voyager_status()
    
    def test_02_recognition_accuracy(self):
        """Test recognition accuracy with known identities"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        correct_matches = 0
        total_tests = 0
        
        # Test each identity with their variations
        for identity_name, data in self.test_data.items():
            if identity_name == "unknown_embeddings":
                continue
            
            for variation in data["variations"]:
                identity, similarity = system.recognize_face(np.array(variation))
                
                total_tests += 1
                if identity == identity_name and similarity >= self.config['recognition_threshold']:
                    correct_matches += 1
                else:
                    self.logger.debug(f"Failed match: Expected {identity_name}, got {identity}, sim={similarity:.3f}")
        
        accuracy = correct_matches / total_tests
        self.logger.info(f"Recognition Accuracy: {accuracy:.2%} ({correct_matches}/{total_tests})")
        
        # Should have high accuracy (> 90% for synthetic data)
        self.assertGreater(accuracy, 0.9, "Accuracy too low")
    
    def test_03_unknown_identity_rejection(self):
        """Test that unknown identities are correctly rejected"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        false_positives = 0
        total_unknown = len(self.test_data["unknown_embeddings"])
        
        for unknown_emb in self.test_data["unknown_embeddings"]:
            identity, similarity = system.recognize_face(unknown_emb)
            
            if identity is not None:
                false_positives += 1
                self.logger.debug(f"False positive: {identity} with similarity {similarity:.3f}")
        
        false_positive_rate = false_positives / total_unknown
        self.logger.info(f"False Positive Rate: {false_positive_rate:.2%} ({false_positives}/{total_unknown})")
        
        # Should have low false positive rate
        self.assertLess(false_positive_rate, 0.2, "False positive rate too high")
    
    def test_04_performance_benchmark(self):
        """Benchmark recognition performance"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        # Warm up
        test_embedding = self.test_data["TestPerson_1"]["variations"][0]
        for _ in range(10):
            system.recognize_face(test_embedding)
        
        # Performance test
        num_iterations = 100
        start_time = time.time()
        
        for i in range(num_iterations):
            # Cycle through different embeddings
            identity_idx = i % self.num_test_identities
            identity_name = f"TestPerson_{identity_idx + 1}"
            variation_idx = i % len(self.test_data[identity_name]["variations"])
            embedding = self.test_data[identity_name]["variations"][variation_idx]
            
            system.recognize_face(embedding)
        
        total_time = time.time() - start_time
        avg_time_per_query = (total_time / num_iterations) * 1000  # Convert to ms
        
        self.logger.info(f"Performance Benchmark:")
        self.logger.info(f"  Total queries: {num_iterations}")
        self.logger.info(f"  Total time: {total_time:.3f}s")
        self.logger.info(f"  Average time per query: {avg_time_per_query:.2f}ms")
        self.logger.info(f"  Queries per second: {num_iterations / total_time:.1f}")
        
        # Performance requirements (adjust based on your needs)
        if torch.cuda.is_available():
            self.assertLess(avg_time_per_query, 50.0, "GPU performance too slow")
        else:
            self.assertLess(avg_time_per_query, 100.0, "CPU performance too slow")
    
    def test_05_gpu_vs_cpu_performance(self):
        """Compare GPU vs CPU performance if GPU available"""
        if not torch.cuda.is_available():
            self.skipTest("GPU not available for comparison")
        
        # Test GPU performance
        gpu_config = self.config.copy()
        gpu_config['device'] = 'cuda'
        gpu_system = VoyagerFaceRecognitionSystem(gpu_config)
        
        # Test CPU performance (force CPU)
        cpu_config = self.config.copy()
        cpu_config['device'] = 'cpu'
        cpu_system = VoyagerFaceRecognitionSystem(cpu_config)
        
        test_embedding = self.test_data["TestPerson_1"]["variations"][0]
        
        # GPU performance
        gpu_times = []
        for _ in range(50):
            start = time.time()
            gpu_system.recognize_face(test_embedding)
            gpu_times.append((time.time() - start) * 1000)
        
        # CPU performance
        cpu_times = []
        for _ in range(50):
            start = time.time()
            cpu_system.recognize_face(test_embedding)
            cpu_times.append((time.time() - start) * 1000)
        
        avg_gpu_time = np.mean(gpu_times)
        avg_cpu_time = np.mean(cpu_times)
        speedup = avg_cpu_time / avg_gpu_time
        
        self.logger.info(f"GPU vs CPU Performance:")
        self.logger.info(f"  GPU Average: {avg_gpu_time:.2f}ms")
        self.logger.info(f"  CPU Average: {avg_cpu_time:.2f}ms")
        self.logger.info(f"  Speedup: {speedup:.2f}x")
        
        # GPU should be faster
        self.assertGreater(speedup, 1.0, "GPU should be faster than CPU")
    
    def test_06_memory_usage(self):
        """Test memory usage and leaks"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create multiple systems and perform operations
        systems = []
        for i in range(5):
            system = VoyagerFaceRecognitionSystem(self.config)
            systems.append(system)
            
            # Perform some recognition
            for _ in range(10):
                identity_name = f"TestPerson_{(i % self.num_test_identities) + 1}"
                embedding = self.test_data[identity_name]["variations"][0]
                system.recognize_face(embedding)
        
        # Clear systems
        del systems
        gc.collect()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gpu_memory = torch.cuda.memory_allocated() / 1024 / 1024
            self.logger.info(f"GPU Memory after cleanup: {gpu_memory:.1f} MB")
            self.assertLess(gpu_memory, 100, "GPU memory leak detected")
        
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory
        
        self.logger.info(f"Memory Usage Test:")
        self.logger.info(f"  Initial: {initial_memory:.1f} MB")
        self.logger.info(f"  Final: {final_memory:.1f} MB")
        self.logger.info(f"  Increase: {memory_increase:.1f} MB")
        
        # Memory increase should be reasonable
        self.assertLess(memory_increase, 50, "Memory leak detected")
    
    def test_07_index_management(self):
        """Test index save/load and management"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        # Save index
        index_path = Path(self.test_dir) / "test_index.bin"
        save_success = system.save_voyager_index(str(index_path))
        self.assertTrue(save_success, "Failed to save index")
        self.assertTrue(index_path.exists(), "Index file not created")
        
        # Create new system and load index
        new_system = VoyagerFaceRecognitionSystem({
            'embeddings_db_path': str(self.db_path),
            'recognition_threshold': 0.6,
            'embedding_model': 'ArcFace',
            'use_voyager': True
        })
        
        # Clear current index
        new_system.voyager_index = None
        
        # Load saved index
        load_success = new_system.load_voyager_index(str(index_path))
        self.assertTrue(load_success, "Failed to load index")
        
        # Verify loaded index works
        test_embedding = self.test_data["TestPerson_1"]["variations"][0]
        identity, similarity = new_system.recognize_face(test_embedding)
        
        self.assertIsNotNone(identity, "Loaded index not working")
        self.assertGreaterEqual(similarity, self.config['recognition_threshold'])
    
    def test_08_add_identity_dynamically(self):
        """Test adding new identities at runtime"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        initial_count = len(system.voyager_id_to_identity)
        
        # Add new identity
        new_identity = "NewTestPerson"
        new_embedding = np.random.randn(self.embedding_dim).astype(np.float32)
        new_embedding = new_embedding / np.linalg.norm(new_embedding)
        
        system.add_identity_to_voyager(new_identity, new_embedding)
        
        # Verify addition
        self.assertEqual(len(system.voyager_id_to_identity), initial_count + 1)
        self.assertIn(new_identity, system.identity_to_voyager_id)
        
        # Test recognition of new identity
        identity, similarity = system.recognize_face(new_embedding)
        self.assertEqual(identity, new_identity)
        self.assertGreaterEqual(similarity, 0.99)  # Should match exactly
    
    def test_09_error_handling(self):
        """Test error handling and robustness"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        # Test with invalid embeddings
        invalid_cases = [
            None,
            np.array([]),
            np.array([np.nan] * self.embedding_dim),
            np.array([np.inf] * self.embedding_dim),
            np.random.randn(256).astype(np.float32),  # Wrong dimension
        ]
        
        for invalid_emb in invalid_cases:
            identity, similarity = system.recognize_face(invalid_emb)
            self.assertIsNone(identity, f"Should handle invalid embedding: {type(invalid_emb)}")
            self.assertEqual(similarity, 0.0)
    
    def test_10_concurrent_access(self):
        """Test thread safety with concurrent access"""
        import threading
        import queue
        
        system = VoyagerFaceRecognitionSystem(self.config)
        results_queue = queue.Queue()
        errors = []
        
        def recognition_worker(worker_id, num_requests):
            try:
                for i in range(num_requests):
                    identity_idx = (worker_id + i) % self.num_test_identities
                    identity_name = f"TestPerson_{identity_idx + 1}"
                    embedding = self.test_data[identity_name]["variations"][0]
                    
                    identity, similarity = system.recognize_face(embedding)
                    
                    if identity is not None:
                        results_queue.put((worker_id, i, identity, similarity))
            except Exception as e:
                errors.append((worker_id, str(e)))
        
        # Start multiple worker threads
        num_workers = 4
        requests_per_worker = 25
        threads = []
        
        for i in range(num_workers):
            thread = threading.Thread(
                target=recognition_worker,
                args=(i, requests_per_worker)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        total_results = results_queue.qsize()
        expected_results = num_workers * requests_per_worker
        
        self.logger.info(f"Concurrent Test Results:")
        self.logger.info(f"  Expected results: {expected_results}")
        self.logger.info(f"  Actual results: {total_results}")
        self.logger.info(f"  Errors: {len(errors)}")
        
        if errors:
            for error in errors:
                self.logger.error(f"Worker {error[0]} error: {error[1]}")
        
        self.assertEqual(len(errors), 0, "Threading errors occurred")
        self.assertGreater(total_results, 0, "No results from concurrent access")
    
    def test_11_scalability(self):
        """Test scalability with large number of identities"""
        # Create larger test dataset
        large_num_identities = 1000
        embeddings_per_identity = 3
        
        # Generate synthetic data quickly
        np.random.seed(123)
        large_embeddings = []
        identity_names = []
        
        for i in range(large_num_identities):
            identity_name = f"ScaledPerson_{i}"
            base_embedding = np.random.randn(self.embedding_dim).astype(np.float32)
            base_embedding = base_embedding / np.linalg.norm(base_embedding)
            
            large_embeddings.append(base_embedding)
            identity_names.append(identity_name)
        
        # Create a new system with empty database
        empty_db_path = Path(self.test_dir) / "empty_db.json"
        with open(empty_db_path, 'w') as f:
            json.dump({"persons": {}, "metadata": {}}, f)
        
        scalability_config = self.config.copy()
        scalability_config['embeddings_db_path'] = str(empty_db_path)
        
        system = VoyagerFaceRecognitionSystem(scalability_config)
        
        # Measure time to add identities
        start_time = time.time()
        
        for i, (identity_name, embedding) in enumerate(zip(identity_names, large_embeddings)):
            system.add_identity_to_voyager(identity_name, embedding)
            
            # Log progress
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                self.logger.info(f"Added {i + 1}/{large_num_identities} identities, "
                               f"rate: {rate:.1f} identites/sec")
        
        add_time = time.time() - start_time
        
        # Measure query performance with large index
        query_times = []
        num_test_queries = 100
        
        for i in range(num_test_queries):
            query_idx = i % len(large_embeddings)
            start = time.time()
            system.recognize_face(large_embeddings[query_idx])
            query_times.append((time.time() - start) * 1000)
        
        avg_query_time = np.mean(query_times)
        
        self.logger.info(f"\nScalability Results:")
        self.logger.info(f"  Identities added: {large_num_identities}")
        self.logger.info(f"  Time to add: {add_time:.2f}s")
        self.logger.info(f"  Add rate: {large_num_identities / add_time:.1f} identities/sec")
        self.logger.info(f"  Average query time: {avg_query_time:.2f}ms")
        self.logger.info(f"  Index size: {system._get_voyager_item_count()}")
        
        # Verify all identities are searchable
        test_indices = np.random.choice(len(identity_names), min(10, len(identity_names)), replace=False)
        for idx in test_indices:
            identity, similarity = system.recognize_face(large_embeddings[idx])
            self.assertEqual(identity, identity_names[idx])
            self.assertGreaterEqual(similarity, 0.99)
    
    def test_12_performance_monitor(self):
        """Test performance monitoring metrics"""
        system = VoyagerFaceRecognitionSystem(self.config)
        
        # Perform multiple recognition operations
        test_embeddings = []
        for i in range(20):
            identity_name = f"TestPerson_{(i % self.num_test_identities) + 1}"
            test_embeddings.append(self.test_data[identity_name]["variations"][0])
        
        for embedding in test_embeddings:
            system.recognize_face(embedding)
        
        # Get stats
        stats = system.get_voyager_stats()
        
        self.assertIn('total_queries', stats)
        self.assertIn('avg_query_time', stats)
        self.assertIn('recall_rate', stats)
        self.assertIn('fallback_count', stats)
        
        self.logger.info(f"Performance Monitor Stats:")
        for key, value in stats.items():
            self.logger.info(f"  {key}: {value}")
        
        # Verify stats are reasonable
        self.assertGreater(stats['total_queries'], 0)
        self.assertGreater(stats['avg_query_time'], 0)
        self.assertLessEqual(stats['fallback_count'], stats['total_queries'])


# ===== PERFORMANCE TEST SUITE =====

class PerformanceTestSuite:
    """Comprehensive performance testing suite"""
    
    def __init__(self, test_dir: str):
        self.test_dir = Path(test_dir)
        self.results = {}
    
    def run_comprehensive_benchmark(self, config: Dict):
        """Run all performance benchmarks"""
        print("\n" + "="*60)
        print("VOYAGER SYSTEM COMPREHENSIVE BENCHMARK")
        print("="*60)
        
        benchmarks = [
            self.benchmark_initialization,
            self.benchmark_recognition_throughput,
            self.benchmark_memory_efficiency,
            self.benchmark_index_scalability,
            self.benchmark_error_recovery
        ]
        
        for benchmark in benchmarks:
            try:
                result = benchmark(config)
                self.results[benchmark.__name__] = result
            except Exception as e:
                print(f"Benchmark {benchmark.__name__} failed: {e}")
        
        self._generate_report()
    
    def benchmark_initialization(self, config: Dict) -> Dict:
        """Benchmark system initialization time"""
        print("\n[1] Initialization Benchmark")
        
        times = []
        memory_usages = []
        
        for i in range(5):  # Multiple runs for consistency
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            start_time = time.time()
            system = VoyagerFaceRecognitionSystem(config)
            init_time = time.time() - start_time
            
            times.append(init_time)
            
            # Get memory usage
            stats = system.get_voyager_stats()
            if 'gpu_memory_allocated' in stats:
                memory_usages.append(stats['gpu_memory_allocated'])
            
            del system
        
        return {
            'avg_init_time': np.mean(times),
            'std_init_time': np.std(times),
            'avg_memory_mb': np.mean(memory_usages) if memory_usages else 0,
            'num_identities': len(system.voyager_id_to_identity) if 'system' in locals() else 0
        }
    
    def benchmark_recognition_throughput(self, config: Dict) -> Dict:
        """Benchmark recognition throughput under load"""
        print("\n[2] Recognition Throughput Benchmark")
        
        system = VoyagerFaceRecognitionSystem(config)
        
        # Generate test queries
        num_queries = 1000
        test_queries = []
        
        for i in range(num_queries):
            identity_idx = i % 10  # Use first 10 identities
            identity_name = f"TestPerson_{identity_idx + 1}"
            # Get test data from global test_data
            test_queries.append(np.random.randn(config.get('embedding_dim', 512)).astype(np.float32))
        
        # Warm up
        for i in range(10):
            system.recognize_face(test_queries[i])
        
        # Benchmark
        start_time = time.time()
        
        for query in test_queries:
            system.recognize_face(query)
        
        total_time = time.time() - start_time
        throughput = num_queries / total_time
        
        stats = system.get_voyager_stats()
        
        return {
            'total_queries': num_queries,
            'total_time_seconds': total_time,
            'queries_per_second': throughput,
            'avg_query_time_ms': stats.get('avg_query_time', 0),
            'success_rate': stats.get('recall_rate', 0) * 100
        }
    
    def benchmark_memory_efficiency(self, config: Dict) -> Dict:
        """Benchmark memory usage efficiency"""
        print("\n[3] Memory Efficiency Benchmark")
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Track memory over operations
        memory_samples = []
        
        system = VoyagerFaceRecognitionSystem(config)
        memory_samples.append(process.memory_info().rss / 1024 / 1024)
        
        # Add identities incrementally
        for i in range(100):
            identity_name = f"MemTestPerson_{i}"
            embedding = np.random.randn(512).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            
            system.add_identity_to_voyager(identity_name, embedding)
            
            if i % 20 == 0:
                memory_samples.append(process.memory_info().rss / 1024 / 1024)
        
        # Check GPU memory if available
        gpu_memory = 0
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.memory_allocated() / 1024 / 1024
        
        return {
            'initial_memory_mb': memory_samples[0],
            'final_memory_mb': memory_samples[-1],
            'memory_growth_mb': memory_samples[-1] - memory_samples[0],
            'gpu_memory_mb': gpu_memory,
            'identities_per_gb': 100 / (memory_samples[-1] / 1024) if memory_samples[-1] > 0 else 0
        }
    
    def benchmark_index_scalability(self, config: Dict) -> Dict:
        """Benchmark index performance at different scales"""
        print("\n[4] Index Scalability Benchmark")
        
        scales = [10, 100, 500, 1000]
        results = {}
        
        for scale in scales:
            print(f"  Testing scale: {scale} identities")
            
            # Create system with scale identities
            scale_config = config.copy()
            scale_db = self._create_scale_database(scale)
            
            scale_config['embeddings_db_path'] = str(scale_db)
            system = VoyagerFaceRecognitionSystem(scale_config)
            
            # Benchmark queries
            query_times = []
            for _ in range(100):
                query = np.random.randn(512).astype(np.float32)
                query = query / np.linalg.norm(query)
                
                start = time.time()
                system.recognize_face(query)
                query_times.append((time.time() - start) * 1000)
            
            results[scale] = {
                'avg_query_time_ms': np.mean(query_times),
                'std_query_time_ms': np.std(query_times),
                'index_size': system._get_voyager_item_count()
            }
            
            del system
            gc.collect()
        
        return results
    
    def benchmark_error_recovery(self, config: Dict) -> Dict:
        """Benchmark error recovery capabilities"""
        print("\n[5] Error Recovery Benchmark")
        
        system = VoyagerFaceRecognitionSystem(config)
        
        error_cases = [
            ('null', None),
            ('empty', np.array([])),
            ('nan', np.array([np.nan] * 512)),
            ('inf', np.array([np.inf] * 512)),
            ('wrong_dim', np.random.randn(256)),
        ]
        
        recovery_times = []
        success_count = 0
        
        for case_name, invalid_input in error_cases:
            try:
                start = time.time()
                identity, similarity = system.recognize_face(invalid_input)
                recovery_time = (time.time() - start) * 1000
                
                recovery_times.append(recovery_time)
                
                # Should safely return None, 0.0
                if identity is None and similarity == 0.0:
                    success_count += 1
                    
            except Exception as e:
                print(f"    Error case '{case_name}' caused exception: {e}")
        
        return {
            'error_cases_tested': len(error_cases),
            'successful_recoveries': success_count,
            'avg_recovery_time_ms': np.mean(recovery_times) if recovery_times else 0,
            'recovery_rate': success_count / len(error_cases) * 100
        }
    
    def _create_scale_database(self, num_identities: int) -> Path:
        """Create a database with specified number of identities"""
        db_path = self.test_dir / f"scale_db_{num_identities}.json"
        
        db_structure = {
            "persons": {},
            "metadata": {"embedding_model": "ArcFace"}
        }
        
        for i in range(num_identities):
            embedding = np.random.randn(512).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            
            db_structure["persons"][f"person_{i}"] = {
                "display_name": f"ScalePerson_{i}",
                "centroid_embedding": embedding.tolist(),
                "embeddings": [{"vector": embedding.tolist()}]
            }
        
        with open(db_path, 'w') as f:
            json.dump(db_structure, f)
        
        return db_path
    
    def _generate_report(self):
        """Generate comprehensive benchmark report"""
        print("\n" + "="*60)
        print("BENCHMARK REPORT SUMMARY")
        print("="*60)
        
        for test_name, result in self.results.items():
            print(f"\n{test_name.replace('_', ' ').title()}:")
            
            if isinstance(result, dict):
                for key, value in result.items():
                    if isinstance(value, float):
                        print(f"  {key}: {value:.2f}")
                    else:
                        print(f"  {key}: {value}")
            else:
                print(f"  Result: {result}")
        
        # Generate pass/fail recommendations
        self._generate_recommendations()
    
    def _generate_recommendations(self):
        """Generate performance recommendations based on benchmarks"""
        print("\n" + "="*60)
        print("PERFORMANCE RECOMMENDATIONS")
        print("="*60)
        
        recs = []
        
        # Check initialization time
        if 'benchmark_initialization' in self.results:
            init_result = self.results['benchmark_initialization']
            if init_result['avg_init_time'] > 5.0:
                recs.append("High initialization time (>5s). Consider lazy loading.")
        
        # Check query performance
        if 'benchmark_recognition_throughput' in self.results:
            throughput_result = self.results['benchmark_recognition_throughput']
            if throughput_result['queries_per_second'] < 10:
                recs.append("Low throughput (<10 qps). Consider GPU optimization or index tuning.")
        
        # Check memory efficiency
        if 'benchmark_memory_efficiency' in self.results:
            memory_result = self.results['benchmark_memory_efficiency']
            if memory_result['memory_growth_mb'] > 500:
                recs.append("High memory growth. Consider memory-efficient data structures.")
        
        # Check scalability
        if 'benchmark_index_scalability' in self.results:
            scale_result = self.results['benchmark_index_scalability']
            for scale, data in scale_result.items():
                if data['avg_query_time_ms'] > 100:
                    recs.append(f"Query time >100ms at {scale} identities. Consider index optimization.")
        
        if recs:
            print("\nRecommendations:")
            for i, rec in enumerate(recs, 1):
                print(f"  {i}. {rec}")
        else:
            print("\nAll benchmarks meet performance targets!")


# ===== MAIN EXECUTION =====

def run_all_tests():
    """Run all tests and benchmarks"""
    # Create test runner
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestVoyagerFaceRecognitionSystem)
    
    # Run unit tests
    print("\n" + "="*60)
    print("RUNNING UNIT TESTS")
    print("="*60)
    
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)
    
    # Run performance benchmarks if unit tests pass
    if test_result.wasSuccessful():
        print("\n" + "="*60)
        print("RUNNING PERFORMANCE BENCHMARKS")
        print("="*60)
        
        # Create performance test suite
        perf_suite = PerformanceTestSuite(tempfile.mkdtemp(prefix="perf_test_"))
        
        # Configuration for benchmarks
        benchmark_config = {
            'embeddings_db_path': TestVoyagerFaceRecognitionSystem.db_path,
            'recognition_threshold': 0.6,
            'embedding_model': 'ArcFace',
            'use_voyager': True,
            'embedding_dim': 512
        }
        
        perf_suite.run_comprehensive_benchmark(benchmark_config)
    
    return test_result.wasSuccessful()


def quick_test():
    """Quick smoke test for development"""
    print("Running quick smoke test...")
    
    # Minimal configuration
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_db.json"
        
        # Create minimal test database
        test_db = {
            "persons": {
                "person_1": {
                    "display_name": "Test Person",
                    "centroid_embedding": [0.1] * 512,
                    "embeddings": [{"vector": [0.1] * 512}]
                }
            },
            "metadata": {"embedding_model": "ArcFace"}
        }
        
        with open(db_path, 'w') as f:
            json.dump(test_db, f)
        
        config = {
            'embeddings_db_path': str(db_path),
            'recognition_threshold': 0.6,
            'embedding_model': 'ArcFace',
            'use_voyager': True
        }
        
        try:
            system = VoyagerFaceRecognitionSystem(config)
            print("✓ System initialized successfully")
            
            # Test recognition
            test_embedding = np.array([0.1] * 512, dtype=np.float32)
            identity, similarity = system.recognize_face(test_embedding)
            
            if identity == "Test Person" and similarity > 0.9:
                print("✓ Recognition working correctly")
            else:
                print(f"✗ Recognition issue: {identity}, {similarity}")
            
            # Print stats
            stats = system.get_voyager_stats()
            print(f"✓ System stats collected: {stats.get('total_identities', 0)} identities")
            
            return True
            
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Voyager Face Recognition System")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke test")
    parser.add_argument("--benchmark", action="store_true", help="Run only benchmarks")
    parser.add_argument("--test", type=str, help="Run specific test (e.g., test_01_initialization)")
    
    args = parser.parse_args()
    
    if args.quick:
        success = quick_test()
        sys.exit(0 if success else 1)
    
    elif args.benchmark:
        # Run only benchmarks
        perf_suite = PerformanceTestSuite(tempfile.mkdtemp())
        config = {
            'embeddings_db_path': 'test_db.json',  # Will be created by benchmark
            'recognition_threshold': 0.6,
            'embedding_model': 'ArcFace',
            'use_voyager': True
        }
        perf_suite.run_comprehensive_benchmark(config)
    
    elif args.test:
        # Run specific test
        suite = unittest.TestSuite()
        suite.addTest(TestVoyagerFaceRecognitionSystem(args.test))
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
    
    else:
        # Run all tests
        success = run_all_tests()
        sys.exit(0 if success else 1)