# streaming/performance_manager.py
# Proposed file that can be utilized more in integrating modularity of realtime streaming
"""
Centralized performance monitoring and dynamic adjustment system
Used by both windowed and headless processors
"""
import time
import numpy as np
from typing import Dict, List, Tuple, Any

class PerformanceManager:
    def __init__(self, config: Dict):
        self.config = config
        
        # Performance tracking
        self.performance_history = []
        self.consecutive_poor_detections = 0
        self.consecutive_good_detections = 0
        self.adjustment_cooldown = 0

        # Resolution adjustment parameters
        self.min_processing_scale = config.get('min_processing_scale', 0.5)
        self.max_processing_scale = config.get('max_processing_scale', 3.0)
        self.current_processing_scale = config.get('current_processing_scale', 1.0)
        self.scale_adjustment_step = config.get('scale_adjustment_step', 0.1)
        
        # Performance thresholds
        self.target_detection_rate = config.get('target_detection_rate', 0.7)
        self.target_face_size = config.get('target_face_size', 60)
        self.min_face_size = config.get('min_face_size', 40)
        
        # Dynamic adjustment system
        self.dynamic_adjustment_enabled = config.get('dynamic_adjustment_enabled', True)
        self.adaptive_check_interval = config.get('adaptive_check_interval', 30)
        self.max_history_size = config.get('max_history_size', 50)
        
        print("🎯 PerformanceManager initialized with dynamic adjustment")

    def analyze_detection_performance(self, results: List[Dict], original_frame_shape: Tuple[int, int]) -> Dict:
        """Comprehensive analysis of detection performance for dynamic adjustment"""
        performance = {
            'detection_count': len(results),
            'face_sizes': [],
            'detection_confidences': [],
            'recognition_rates': [],
            'avg_face_size': 0,
            'detection_quality': 0,
            'needs_adjustment': False,
            'adjustment_direction': 0
        }
        
        if not results:
            performance['detection_quality'] = 0
            performance['needs_adjustment'] = True
            performance['adjustment_direction'] = 1
            return performance
        
        # Analyze each detection using ORIGINAL frame coordinates
        orig_h, orig_w = original_frame_shape
        frame_diagonal = np.sqrt(orig_h**2 + orig_w**2)
        
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            face_width = x2 - x1
            face_height = y2 - y1
            face_size = min(face_width, face_height)
            
            # Normalize face size relative to frame size
            normalized_face_size = face_size / frame_diagonal * 1000  # Scale factor
            
            performance['face_sizes'].append(normalized_face_size)
            performance['detection_confidences'].append(result['detection_confidence'])
            
            if result['identity']:
                performance['recognition_rates'].append(result['recognition_confidence'])
        
        # Calculate metrics
        if performance['face_sizes']:
            performance['avg_face_size'] = np.mean(performance['face_sizes'])
            performance['detection_quality'] = self.calculate_detection_quality(performance)
            performance['needs_adjustment'] = self.should_adjust_resolution(performance)
            performance['adjustment_direction'] = self.get_adjustment_direction(performance)
        
        return performance  

    def calculate_detection_quality(self, performance: Dict) -> float:
        """Calculate overall detection quality score (0-1)"""
        quality_factors = []
        
        # Face size factor (normalized to target)
        if performance['avg_face_size'] > 0:
            size_factor = min(performance['avg_face_size'] / self.target_face_size, 1.0)
            quality_factors.append(size_factor * 0.6)  # 60% weight
        
        # Detection confidence factor
        if performance['detection_confidences']:
            conf_factor = np.mean(performance['detection_confidences'])
            quality_factors.append(conf_factor * 0.7)  # 70% weight
        
        # Recognition rate factor (if applicable)
        if performance['recognition_rates']:
            recog_factor = np.mean(performance['recognition_rates'])
            quality_factors.append(recog_factor * 0.5)  # 50% weight
        else:
            # If no recognitions but detections exist, use medium weight
            quality_factors.append(0.15)
        
        return min(1.0, sum(quality_factors))

    def should_adjust_resolution(self, performance: Dict) -> bool:
        """Determine if resolution adjustment is needed"""
        # Always adjust if no detections
        if performance['detection_count'] == 0:
            return True
        
        # Check face size thresholds
        if performance['avg_face_size'] < self.min_face_size:
            return True
        
        # Check detection quality
        if performance['detection_quality'] < self.target_detection_rate:
            return True
        
        # Check if we're in cooldown period
        if self.adjustment_cooldown > 0:
            return False
        
        return False

    def get_adjustment_direction(self, performance: Dict) -> int:
        """Determine which direction to adjust resolution"""
        if performance['detection_count'] == 0:
            return 1  # Increase resolution if no detections
        
        if performance['avg_face_size'] < self.min_face_size:
            return 1  # Increase resolution for small faces
        
        if performance['detection_quality'] < self.target_detection_rate:
            return 1  # Increase resolution for poor quality
        
        # If quality is good and faces are large, consider decreasing resolution
        if (performance['detection_quality'] > self.target_detection_rate + 0.2 and 
            performance['avg_face_size'] > self.target_face_size + 20):
            return -1  # Decrease resolution
        
        return 0  # Maintain current resolution
    
    def apply_dynamic_adjustment(self, performance: Dict):
        """Apply resolution adjustment based on performance analysis"""
        if not self.dynamic_adjustment_enabled or self.adjustment_cooldown > 0:
            return
        
        direction = performance['adjustment_direction']
        
        if direction == 0:
            self.consecutive_good_detections += 1
            self.consecutive_poor_detections = 0
            return
        
        # Track consecutive adjustments
        if direction == 1:  # Need to increase resolution
            self.consecutive_poor_detections += 1
            self.consecutive_good_detections = 0
        else:  # Need to decrease resolution
            self.consecutive_good_detections += 1
            self.consecutive_poor_detections = 0
        
        # Calculate new scale with momentum
        momentum = self.calculate_adjustment_momentum()
        new_scale = self.current_processing_scale + (direction * self.scale_adjustment_step * momentum)
        
        # Apply bounds
        new_scale = max(self.min_processing_scale, min(self.max_processing_scale, new_scale))
        
        # Only adjust if change is significant
        if abs(new_scale - self.current_processing_scale) >= self.scale_adjustment_step * 0.5:
            old_scale = self.current_processing_scale
            self.current_processing_scale = new_scale
            self.adjustment_cooldown = 10  # Cooldown period
            
            # Log the adjustment
            direction_symbol = "🔼" if direction > 0 else "🔽"
            reason = self.get_adjustment_reason(performance, direction)
            print(f"{direction_symbol} Dynamic adjustment: {old_scale:.2f} → {new_scale:.2f} | {reason}")

    def calculate_adjustment_momentum(self) -> float:
        """Calculate adjustment momentum based on consecutive performance"""
        if self.consecutive_poor_detections > 3:
            return 2.0  # Double step size for persistent issues
        elif self.consecutive_poor_detections > 1:
            return 1.5  # 50% larger step
        elif self.consecutive_good_detections > 5:
            return 0.5  # Smaller step when optimizing from good state
        else:
            return 1.0  # Normal step

    def get_adjustment_reason(self, performance: Dict, direction: int) -> str:
        """Generate human-readable reason for adjustment"""
        if performance['detection_count'] == 0:
            return "No faces detected"
        elif performance['avg_face_size'] < self.min_face_size:
            return f"Faces too small ({performance['avg_face_size']:.0f}px < {self.min_face_size}px)"
        elif performance['detection_quality'] < self.target_detection_rate:
            return f"Poor detection quality ({performance['detection_quality']:.2f})"
        else:
            return f"Optimizing performance ({performance['detection_quality']:.2f})"
    
    def update_dynamic_system(self):
        """Update dynamic adjustment system state"""
        if self.adjustment_cooldown > 0:
            self.adjustment_cooldown -= 1
        
        # Trim performance history
        if len(self.performance_history) > self.max_history_size:
            self.performance_history.pop(0)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        return {
            'current_scale': self.current_processing_scale,
            'performance_history_size': len(self.performance_history),
            'consecutive_good_detections': self.consecutive_good_detections,
            'consecutive_poor_detections': self.consecutive_poor_detections,
            'adjustment_cooldown': self.adjustment_cooldown,
            'dynamic_adjustment_enabled': self.dynamic_adjustment_enabled
        }
    
    def toggle_dynamic_adjustment(self):
        """Toggle dynamic adjustment on/off"""
        self.dynamic_adjustment_enabled = not self.dynamic_adjustment_enabled
        status = "ENABLED" if self.dynamic_adjustment_enabled else "DISABLED"
        print(f"🎯 Dynamic adjustment: {status}")
    
    def reset_dynamic_scaling(self):
        """Reset dynamic scaling to default values"""
        old_scale = self.current_processing_scale
        self.current_processing_scale = 1.0
        self.performance_history = []
        self.consecutive_poor_detections = 0
        self.consecutive_good_detections = 0
        self.adjustment_cooldown = 0
        print(f"🔄 Dynamic scaling reset: {old_scale:.2f} → 1.00")
    
    def enable_small_face_mode(self):
        """Enable optimized settings for small face detection"""
        self.current_processing_scale = 1.5
        self.target_face_size = 60
        self.min_face_size = 20
        print("🔍 Small face detection mode ENABLED in PerformanceManager")      
        
        