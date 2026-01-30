# streaming/performance_manager.py
# Updated to strictly enforce historical performance-based scaling with cooldown

"""
Centralized performance monitoring and dynamic adjustment system
Used by both windowed and headless processors
"""
import time
import numpy as np
from typing import Dict, List, Tuple, Any
from queue import deque


class PerformanceManager:
    def __init__(self, config: Dict):
        self.config = config
        
        # Performance tracking with enhanced history for momentum
        self.performance_history = []
        self.scale_adjustment_history = deque(maxlen=20)  # Track recent adjustments
        self.consecutive_poor_detections = 0
        self.consecutive_good_detections = 0
        self.adjustment_cooldown = 0
        self.last_adjustment_time = time.time()

        # Resolution adjustment parameters
        self.min_processing_scale = config.get('min_processing_scale', 0.5)
        self.max_processing_scale = config.get('max_processing_scale', 3.0)
        self.current_processing_scale = config.get('current_processing_scale', 1.0)
        self.scale_adjustment_step = config.get('scale_adjustment_step', 0.1)
        
        # Momentum-based adjustment parameters
        self.momentum_window = config.get('momentum_window', 5)
        self.max_momentum_factor = config.get('max_momentum_factor', 2.0)
        self.min_cooldown_seconds = config.get('min_cooldown_seconds', 2.0)
        self.max_cooldown_seconds = config.get('max_cooldown_seconds', 10.0)
        
        # Performance thresholds
        self.target_detection_rate = config.get('target_detection_rate', 0.7)
        self.target_face_size = config.get('target_face_size', 60)
        self.min_face_size = config.get('min_face_size', 40)
        
        # Dynamic adjustment system
        self.dynamic_adjustment_enabled = config.get('dynamic_adjustment_enabled', True)
        self.adaptive_check_interval = config.get('adaptive_check_interval', 30)
        self.max_history_size = config.get('max_history_size', 50)
        
        print("🎯 PerformanceManager initialized with momentum-based historical scaling")
        print(f"   - Scale range: {self.min_processing_scale:.2f} to {self.max_processing_scale:.2f}")
        print(f"   - Cooldown range: {self.min_cooldown_seconds}s to {self.max_cooldown_seconds}s")

    def analyze_detection_performance(self, results: List[Dict], original_frame_shape: Tuple[int, int]) -> Dict:
        """Comprehensive analysis of detection performance with historical context"""
        performance = {
            'detection_count': len(results),
            'face_sizes': [],
            'detection_confidences': [],
            'recognition_rates': [],
            'avg_face_size': 0,
            'detection_quality': 0,
            'needs_adjustment': False,
            'adjustment_direction': 0,
            'historical_trend': 0,  # -1 declining, 0 stable, +1 improving
            'momentum_factor': 1.0
        }
        
        if not results:
            performance['detection_quality'] = 0
            performance['needs_adjustment'] = True
            performance['adjustment_direction'] = 1
            
            # Check historical trend
            if len(self.performance_history) >= 3:
                recent_quality = [p.get('detection_quality', 0) for p in self.performance_history[-3:]]
                if all(q == 0 for q in recent_quality):
                    performance['momentum_factor'] = self.max_momentum_factor
                    performance['historical_trend'] = -1
            
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
            
            # Calculate historical trend and momentum
            performance['historical_trend'] = self.calculate_historical_trend(performance)
            performance['momentum_factor'] = self.calculate_momentum_factor(performance)
        
        return performance

    def calculate_historical_trend(self, current_performance: Dict) -> int:
        """Calculate performance trend based on history (-1 declining, 0 stable, +1 improving)"""
        if len(self.performance_history) < 3:
            return 0
        
        # Get recent performance metrics
        recent_performances = self.performance_history[-3:]
        recent_qualities = [p.get('detection_quality', 0) for p in recent_performances]
        
        if len(recent_qualities) < 2:
            return 0
        
        # Calculate trend
        current_quality = current_performance['detection_quality']
        avg_recent_quality = np.mean(recent_qualities)
        
        if current_quality > avg_recent_quality + 0.1:
            return 1  # Improving
        elif current_quality < avg_recent_quality - 0.1:
            return -1  # Declining
        else:
            return 0  # Stable

    def calculate_momentum_factor(self, performance: Dict) -> float:
        """Calculate momentum factor based on historical performance trends"""
        momentum = 1.0
        
        # Increase momentum for persistent issues
        if self.consecutive_poor_detections >= 3:
            momentum += 0.5 * min(self.consecutive_poor_detections / 10, 1.0)
        
        # Increase momentum for strong historical decline
        if performance['historical_trend'] == -1:
            momentum += 0.3
        
        # Decrease momentum for good performance
        if self.consecutive_good_detections >= 5:
            momentum = max(0.5, momentum - 0.1)
        
        return min(self.max_momentum_factor, max(0.5, momentum))

    def should_adjust_resolution(self, performance: Dict) -> bool:
        """Determine if resolution adjustment is needed with cooldown consideration"""
        # Always adjust if no detections and cooldown expired
        if performance['detection_count'] == 0:
            return self.adjustment_cooldown == 0
        
        # Check if we're in cooldown period
        if self.adjustment_cooldown > 0:
            return False
        
        # Check face size thresholds
        if performance['avg_face_size'] < self.min_face_size:
            return True
        
        # Check detection quality
        if performance['detection_quality'] < self.target_detection_rate:
            return True
        
        # Check for sustained poor performance
        if (self.consecutive_poor_detections >= 3 and 
            performance['detection_quality'] < self.target_detection_rate + 0.1):
            return True
        
        return False

    def get_adjustment_direction(self, performance: Dict) -> int:
        """Determine which direction to adjust resolution with historical context"""
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
        """Apply momentum-based resolution adjustment with enforced cooldown"""
        if not self.dynamic_adjustment_enabled:
            return
        
        # Check cooldown
        current_time = time.time()
        if self.adjustment_cooldown > 0:
            self.adjustment_cooldown -= 1
            return
        
        # Check minimum time between adjustments
        time_since_last = current_time - self.last_adjustment_time
        if time_since_last < self.min_cooldown_seconds:
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
        
        # Calculate new scale with momentum and historical context
        momentum = performance.get('momentum_factor', 1.0)
        new_scale = self.current_processing_scale + (direction * self.scale_adjustment_step * momentum)
        
        # Apply bounds
        new_scale = max(self.min_processing_scale, min(self.max_processing_scale, new_scale))
        
        # Only adjust if change is significant
        scale_change = abs(new_scale - self.current_processing_scale)
        if scale_change >= self.scale_adjustment_step * 0.3:
            old_scale = self.current_processing_scale
            self.current_processing_scale = new_scale
            
            # Set cooldown based on adjustment magnitude
            cooldown_factor = min(scale_change / self.scale_adjustment_step, 2.0)
            self.adjustment_cooldown = int(self.min_cooldown_seconds * cooldown_factor)
            self.last_adjustment_time = current_time
            
            # Record adjustment in history
            adjustment_record = {
                'timestamp': current_time,
                'old_scale': old_scale,
                'new_scale': new_scale,
                'direction': direction,
                'momentum': momentum,
                'performance': performance
            }
            self.scale_adjustment_history.append(adjustment_record)
            
            # Log the adjustment
            direction_symbol = "🔼" if direction > 0 else "🔽"
            reason = self.get_adjustment_reason(performance, direction)
            print(f"{direction_symbol} Dynamic adjustment: {old_scale:.2f} → {new_scale:.2f}")
            print(f"   📈 Momentum: {momentum:.2f}x | Cooldown: {self.adjustment_cooldown}s")
            print(f"   📊 Reason: {reason}")

    def calculate_detection_quality(self, performance: Dict) -> float:
        """Calculate overall detection quality score (0-1) with historical weighting"""
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
        
        # Apply historical smoothing if we have history
        if len(self.performance_history) >= 2:
            recent_qualities = [p.get('detection_quality', 0.5) for p in self.performance_history[-2:]]
            historical_factor = np.mean(recent_qualities) * 0.3
            quality_factors.append(historical_factor)
        
        return min(1.0, sum(quality_factors) / len(quality_factors))

    def get_adjustment_reason(self, performance: Dict, direction: int) -> str:
        """Generate human-readable reason for adjustment"""
        if performance['detection_count'] == 0:
            return f"No faces detected ({self.consecutive_poor_detections} consecutive)"
        elif performance['avg_face_size'] < self.min_face_size:
            return f"Faces too small ({performance['avg_face_size']:.0f}px < {self.min_face_size}px)"
        elif performance['detection_quality'] < self.target_detection_rate:
            return f"Poor detection quality ({performance['detection_quality']:.2f})"
        elif direction == -1:
            return f"Optimizing performance ({performance['detection_quality']:.2f})"
        else:
            return f"Historical trend: {['declining', 'stable', 'improving'][performance['historical_trend'] + 1]}"
    
    def update_dynamic_system(self):
        """Update dynamic adjustment system state"""
        # Trim performance history
        if len(self.performance_history) > self.max_history_size:
            self.performance_history.pop(0)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics including historical data"""
        recent_adjustments = list(self.scale_adjustment_history)
        
        return {
            'current_scale': self.current_processing_scale,
            'performance_history_size': len(self.performance_history),
            'adjustment_history_size': len(recent_adjustments),
            'consecutive_good_detections': self.consecutive_good_detections,
            'consecutive_poor_detections': self.consecutive_poor_detections,
            'adjustment_cooldown': self.adjustment_cooldown,
            'dynamic_adjustment_enabled': self.dynamic_adjustment_enabled,
            'min_scale': self.min_processing_scale,
            'max_scale': self.max_processing_scale,
            'recent_adjustments': [
                {'old': adj.get('old_scale'), 'new': adj.get('new_scale')} 
                for adj in recent_adjustments[-3:]
            ] if recent_adjustments else []
        }
    
    def toggle_dynamic_adjustment(self):
        """Toggle dynamic adjustment on/off"""
        self.dynamic_adjustment_enabled = not self.dynamic_adjustment_enabled
        status = "ENABLED" if self.dynamic_adjustment_enabled else "DISABLED"
        print(f"🎯 Dynamic adjustment: {status}")
    
    def reset_dynamic_scaling(self):
        """Reset dynamic scaling to default values with cooldown"""
        old_scale = self.current_processing_scale
        self.current_processing_scale = 1.0
        self.performance_history = []
        self.scale_adjustment_history.clear()
        self.consecutive_poor_detections = 0
        self.consecutive_good_detections = 0
        self.adjustment_cooldown = 5  # Reset cooldown
        self.last_adjustment_time = time.time()
        print(f"🔄 Dynamic scaling reset: {old_scale:.2f} → 1.00")
        print(f"   ⏰ Cooldown set: {self.adjustment_cooldown}s")
    
    def enable_small_face_mode(self):
        """Enable optimized settings for small face detection"""
        self.current_processing_scale = 1.5
        self.target_face_size = 60
        self.min_face_size = 20
        self.adjustment_cooldown = 3  # Short cooldown for initial adjustment
        print("🔍 Small face detection mode ENABLED in PerformanceManager")
        print(f"   📐 Scale set to: {self.current_processing_scale:.2f}")
        