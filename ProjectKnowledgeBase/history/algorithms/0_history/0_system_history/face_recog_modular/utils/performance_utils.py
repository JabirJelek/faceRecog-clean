# utils/performance_utils.py
"""
Performance monitoring utilities.
"""

import time
from collections import deque
from typing import Deque, Dict, Any
import numpy as np

class PerformanceMonitor:
    """Monitor and track system performance metrics."""
    
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.metrics_history: Dict[str, Deque] = {}
        self.start_time = time.time()
    
    def record_metric(self, name: str, value: float):
        """Record a performance metric."""
        if name not in self.metrics_history:
            self.metrics_history[name] = deque(maxlen=self.max_history)
        self.metrics_history[name].append(value)
    
    def get_statistics(self, name: str) -> Dict[str, float]:
        """Get statistics for a metric."""
        if name not in self.metrics_history or not self.metrics_history[name]:
            return {}
        
        values = list(self.metrics_history[name])
        return {
            'mean': np.mean(values),
            'std': np.std(values),
            'min': np.min(values),
            'max': np.max(values),
            'p95': np.percentile(values, 95),
            'count': len(values)
        }
    
    def get_all_statistics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all metrics."""
        return {name: self.get_statistics(name) for name in self.metrics_history}

def calculate_fps(frame_count: int, start_time: float) -> float:
    """Calculate frames per second."""
    elapsed = time.time() - start_time
    return frame_count / elapsed if elapsed > 0 else 0.0

def measure_performance(func):
    """Decorator to measure function execution time."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        return result, execution_time
    return wrapper