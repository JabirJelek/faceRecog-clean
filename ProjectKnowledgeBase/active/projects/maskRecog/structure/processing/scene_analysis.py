# processing/scene_analysis.py
import cv2
import numpy as np
from collections import deque
from typing import Dict, List
import time
import logging



class SceneContextAnalyzer:
    """Advanced scene context analysis for intelligent scaling decisions"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.previous_frame = None
        self.motion_history = deque(maxlen=30)
        self.context_history = deque(maxlen=50)
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        # Context thresholds
        self.thresholds = {
            'high_face_density': 0.05,  # faces per 1000 pixels
            'low_face_density': 0.005,
            'high_complexity': 0.6,
            'low_complexity': 0.2,
            'dark_lighting': 0.3,
            'bright_lighting': 0.7,
            'high_motion': 0.4,
            'low_motion': 0.1
        }
        
        self.logger.info("Scene Context Analyzer initialized")
        
    def analyze_scene_context(self, frame: np.ndarray, detection_results: List[Dict]) -> Dict[str, float]:
        """Comprehensive scene context analysis"""
        if frame is None or frame.size == 0:
            return self._get_default_context()
        
        try:
            # Convert to grayscale for analysis
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame
            
            h, w = gray.shape
            
            context = {
                'face_density': self._calculate_face_density(detection_results, w, h),
                'scene_complexity': self._calculate_scene_complexity(gray),
                'lighting_conditions': self._assess_lighting_conditions(gray),
                'motion_level': self._estimate_motion_level(gray),
                'texture_density': self._calculate_texture_density(gray),
                'edge_concentration': self._calculate_edge_concentration(gray),
                'color_variance': self._calculate_color_variance(frame),
                'focus_quality': self._assess_focus_quality(gray)
            }
            
            # Store context for trend analysis
            self.context_history.append(context)
            
            return context
            
        except Exception as e:
            self.logger.error(f"Scene context analysis error: {e}")
            return self._get_default_context()
               
    def _calculate_face_density(self, results: List[Dict], frame_width: int, frame_height: int) -> float:
        """Calculate face density in the scene"""
        if not results:
            return 0.0
        
        total_face_area = 0
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            face_area = (x2 - x1) * (y2 - y1)
            total_face_area += face_area
        
        frame_area = frame_width * frame_height
        density = total_face_area / frame_area if frame_area > 0 else 0.0
        
        return min(1.0, density * 10)  # Normalize to 0-1 range

    def _calculate_scene_complexity(self, gray_frame: np.ndarray) -> float:
        """Calculate scene complexity using edge density and variance"""
        try:
            # Edge detection
            edges = cv2.Canny(gray_frame, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Texture analysis using variance
            laplacian_var = cv2.Laplacian(gray_frame, cv2.CV_64F).var()
            texture_complexity = min(1.0, laplacian_var / 1000.0)
            
            # Combined complexity score
            complexity = 0.6 * edge_density + 0.4 * texture_complexity
            return min(1.0, complexity)
            
        except:
            return 0.5

    def _assess_lighting_conditions(self, gray_frame: np.ndarray) -> float:
        """Assess lighting conditions (0=dark, 1=bright)"""
        try:
            brightness = np.mean(gray_frame) / 255.0
            
            # Calculate contrast
            contrast = np.std(gray_frame) / 128.0  # Normalized
            
            # Combined lighting score (prioritize adequate lighting)
            if 0.3 <= brightness <= 0.7:
                lighting_score = 0.8 + (0.2 * contrast)  # Good lighting
            else:
                lighting_score = brightness * contrast  # Poor lighting
            
            return min(1.0, lighting_score)
            
        except:
            return 0.5

    def _estimate_motion_level(self, current_gray: np.ndarray) -> float:
        """Estimate motion level between consecutive frames"""
        try:
            if self.previous_frame is None:
                self.previous_frame = current_gray
                return 0.0
            
            # Calculate frame difference
            frame_diff = cv2.absdiff(self.previous_frame, current_gray)
            motion_level = np.mean(frame_diff) / 255.0
            
            # Update previous frame
            self.previous_frame = current_gray
            
            # Store in history for smoothing
            self.motion_history.append(motion_level)
            
            # Use moving average for stability
            if len(self.motion_history) > 0:
                smoothed_motion = np.mean(list(self.motion_history))
                return min(1.0, smoothed_motion * 3)  # Amplify for better sensitivity
            
            return motion_level
            
        except:
            return 0.0

    def _calculate_texture_density(self, gray_frame: np.ndarray) -> float:
        """Calculate texture density using local binary patterns (simplified)"""
        try:
            # Use variance of Gaussian blur differences as texture indicator
            blur1 = cv2.GaussianBlur(gray_frame, (5, 5), 0)
            blur2 = cv2.GaussianBlur(gray_frame, (9, 9), 0)
            texture_map = cv2.absdiff(blur1, blur2)
            texture_density = np.mean(texture_map) / 255.0
            return min(1.0, texture_density * 2)
        except:
            return 0.5

    def _calculate_edge_concentration(self, gray_frame: np.ndarray) -> float:
        """Calculate edge concentration in different regions"""
        try:
            edges = cv2.Canny(gray_frame, 50, 150)
            h, w = edges.shape
            
            # Divide frame into 3x3 grid and analyze edge distribution
            grid_h, grid_w = h // 3, w // 3
            edge_concentrations = []
            
            for i in range(3):
                for j in range(3):
                    roi = edges[i*grid_h:(i+1)*grid_h, j*grid_w:(j+1)*grid_w]
                    concentration = np.sum(roi > 0) / roi.size
                    edge_concentrations.append(concentration)
            
            # Use standard deviation of concentrations as measure of focus
            concentration_variance = np.std(edge_concentrations)
            return min(1.0, concentration_variance * 5)
        except:
            return 0.5

    def _calculate_color_variance(self, color_frame: np.ndarray) -> float:
        """Calculate color variance in the scene"""
        try:
            if len(color_frame.shape) != 3:
                return 0.5
                
            hsv = cv2.cvtColor(color_frame, cv2.COLOR_BGR2HSV)
            saturation = hsv[:, :, 1]
            color_variance = np.std(saturation) / 255.0
            return min(1.0, color_variance * 2)
        except:
            return 0.5

    def _assess_focus_quality(self, gray_frame: np.ndarray) -> float:
        """Assess image focus quality using frequency analysis"""
        try:
            # Use FFT to assess focus (blurry images have less high frequency content)
            fft = np.fft.fft2(gray_frame)
            fft_shift = np.fft.fftshift(fft)
            magnitude = np.log(np.abs(fft_shift) + 1)
            
            # High frequency content (edges)
            h, w = magnitude.shape
            center_h, center_w = h // 2, w // 2
            high_freq_region = magnitude[center_h-20:center_h+20, center_w-20:center_w+20]
            high_freq_content = np.mean(high_freq_region)
            
            focus_quality = min(1.0, high_freq_content / 8.0)  # Normalize
            return focus_quality
        except:
            return 0.5

    def get_context_recommendations(self, context: Dict[str, float]) -> Dict[str, any]:
        """Get scaling recommendations based on scene context"""
        recommendations = {
            'suggested_scale_adjustment': 1.0,
            'reasoning': [],
            'priority_factors': {}
        }
        
        # Face density recommendations
        if context['face_density'] > self.thresholds['high_face_density']:
            recommendations['suggested_scale_adjustment'] *= 1.3
            recommendations['reasoning'].append("High face density - increase resolution")
            recommendations['priority_factors']['face_density'] = 'high'
        elif context['face_density'] < self.thresholds['low_face_density']:
            recommendations['suggested_scale_adjustment'] *= 0.8
            recommendations['reasoning'].append("Low face density - can reduce resolution")
            recommendations['priority_factors']['face_density'] = 'low'
        else:
            recommendations['priority_factors']['face_density'] = 'medium'

        # Scene complexity recommendations
        if context['scene_complexity'] > self.thresholds['high_complexity']:
            recommendations['suggested_scale_adjustment'] *= 0.7
            recommendations['reasoning'].append("Complex scene - reduce resolution for performance")
            recommendations['priority_factors']['complexity'] = 'high'
        elif context['scene_complexity'] < self.thresholds['low_complexity']:
            recommendations['suggested_scale_adjustment'] *= 1.2
            recommendations['reasoning'].append("Simple scene - can increase resolution")
            recommendations['priority_factors']['complexity'] = 'low'
        else:
            recommendations['priority_factors']['complexity'] = 'medium'

        # Lighting condition recommendations
        if context['lighting_conditions'] < self.thresholds['dark_lighting']:
            recommendations['suggested_scale_adjustment'] *= 1.4
            recommendations['reasoning'].append("Poor lighting - increase resolution for detail")
            recommendations['priority_factors']['lighting'] = 'poor'
        elif context['lighting_conditions'] > self.thresholds['bright_lighting']:
            recommendations['suggested_scale_adjustment'] *= 1.1
            recommendations['reasoning'].append("Bright lighting - slight increase for overexposure compensation")
            recommendations['priority_factors']['lighting'] = 'bright'
        else:
            recommendations['priority_factors']['lighting'] = 'good'

        # Motion level recommendations
        if context['motion_level'] > self.thresholds['high_motion']:
            recommendations['suggested_scale_adjustment'] *= 0.6
            recommendations['reasoning'].append("High motion - reduce resolution for stability")
            recommendations['priority_factors']['motion'] = 'high'
        elif context['motion_level'] < self.thresholds['low_motion']:
            recommendations['suggested_scale_adjustment'] *= 1.1
            recommendations['reasoning'].append("Low motion - can increase resolution")
            recommendations['priority_factors']['motion'] = 'low'
        else:
            recommendations['priority_factors']['motion'] = 'medium'

        # Focus quality recommendations
        if context['focus_quality'] < 0.3:
            recommendations['suggested_scale_adjustment'] *= 0.8
            recommendations['reasoning'].append("Poor focus - reducing resolution won't help")
            recommendations['priority_factors']['focus'] = 'poor'
        elif context['focus_quality'] > 0.7:
            recommendations['suggested_scale_adjustment'] *= 1.2
            recommendations['reasoning'].append("Good focus - increase resolution for detail")
            recommendations['priority_factors']['focus'] = 'good'
        else:
            recommendations['priority_factors']['focus'] = 'medium'

        return recommendations

    def _get_default_context(self) -> Dict[str, float]:
        """Return default context when analysis fails"""
        return {
            'face_density': 0.0,
            'scene_complexity': 0.5,
            'lighting_conditions': 0.5,
            'motion_level': 0.0,
            'texture_density': 0.5,
            'edge_concentration': 0.5,
            'color_variance': 0.5,
            'focus_quality': 0.5
        }

    def get_context_statistics(self) -> Dict[str, any]:
        """Get statistics about historical context analysis"""
        if not self.context_history:
            return {}
        
        contexts = list(self.context_history)
        stats = {}
        
        for key in contexts[0].keys():
            values = [ctx[key] for ctx in contexts]
            stats[key] = {
                'mean': np.mean(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values),
                'trend': 'increasing' if values[-1] > values[0] else 'decreasing'
            }
        
        return stats
class ContextAwareDynamicScaling:
    """Dynamic scaling enhanced with scene context awareness and PerformanceManager integration"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.scene_analyzer = SceneContextAnalyzer(config)
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        # Scaling parameters
        self.scaling_params = {
            'min_scale': config.get('min_processing_scale', 0.5),
            'max_scale': config.get('max_processing_scale', 3.0),
            'base_step': config.get('scale_adjustment_step', 0.15),
            'context_weight': config.get('context_weight', 0.4),  # Lower weight for context
            'performance_weight': config.get('performance_weight', 0.8)  # Higher weight for performance
        }
        
        # Historical data
        self.scaling_decisions = deque(maxlen=100)
        self.performance_history = deque(maxlen=50)
        self.context_recommendations_history = deque(maxlen=50)
        
        self.current_scale = 1.0
        self.adjustment_cooldown = 0
        self.last_adjustment_time = time.time()
        
        # Performance Manager reference (will be set by BaseProcessor)
        self.performance_manager = None
        
        self.logger.info("Context-Aware Dynamic Scaling initialized")
        self.logger.info(f"Performance weight: {self.scaling_params['performance_weight']:.1f}")
        self.logger.info(f"Context weight: {self.scaling_params['context_weight']:.1f}")
        
    def set_performance_manager(self, performance_manager):
            """Set reference to PerformanceManager for coordinated scaling"""
            self.performance_manager = performance_manager
            self.logger.info("Linked ContextAwareDynamicScaling with PerformanceManager")

    def compute_optimal_scale(self, frame: np.ndarray, detection_results: List[Dict], 
                            performance_metrics: Dict) -> float:
        """Compute optimal scale using both performance metrics and context"""
        
        if self.performance_manager is None:
            self.logger.warning("PerformanceManager not linked, using context-only scaling")
            return self._compute_context_only_scale(frame, detection_results)
        
        # Analyze scene context
        scene_context = self.scene_analyzer.analyze_scene_context(frame, detection_results)
        context_recommendations = self.scene_analyzer.get_context_recommendations(scene_context)
        
        # Store for analysis
        self.context_recommendations_history.append({
            'context': scene_context,
            'recommendations': context_recommendations,
            'timestamp': time.time()
        })
        
        # Get performance manager's current scale (respecting its cooldown)
        performance_scale = self.performance_manager.current_processing_scale
        
        # Get context-based scale adjustment
        context_scale_factor = context_recommendations.get('suggested_scale_adjustment', 1.0)
        
        # Combine with weights, prioritizing performance manager
        performance_weight = self.scaling_params['performance_weight']
        context_weight = self.scaling_params['context_weight']
        
        optimal_scale = (
            performance_scale * performance_weight +
            (performance_scale * context_scale_factor) * context_weight
        ) / (performance_weight + context_weight)
        
        # Apply predictive adjustments based on historical patterns
        optimal_scale = self._apply_predictive_adjustments(optimal_scale, scene_context, performance_metrics)
        
        # Ensure we respect performance manager's bounds
        optimal_scale = max(self.performance_manager.min_processing_scale, 
                           min(self.performance_manager.max_processing_scale, optimal_scale))
        
        # Record decision
        decision = {
            'timestamp': time.time(),
            'performance_scale': performance_scale,
            'context_scale_factor': context_scale_factor,
            'optimal_scale': optimal_scale,
            'previous_scale': self.current_scale,
            'context': scene_context,
            'performance': performance_metrics,
            'recommendations': context_recommendations,
            'respecting_cooldown': self.performance_manager.adjustment_cooldown > 0
        }
        self.scaling_decisions.append(decision)
        self.performance_history.append(performance_metrics)
        
        return optimal_scale
    
    def _compute_context_only_scale(self, frame: np.ndarray, detection_results: List[Dict]) -> float:
        """Fallback method when PerformanceManager is not available"""
        scene_context = self.scene_analyzer.analyze_scene_context(frame, detection_results)
        context_recommendations = self.scene_analyzer.get_context_recommendations(scene_context)
        
        context_scale = context_recommendations.get('suggested_scale_adjustment', 1.0)
        
        # Apply bounds
        context_scale = max(self.scaling_params['min_scale'], 
                           min(self.scaling_params['max_scale'], context_scale))
        
        return context_scale

    def _apply_predictive_adjustments(self, current_scale: float, context: Dict, 
                                    performance_metrics: Dict) -> float:
        """Apply predictive adjustments based on historical patterns and current performance"""
        
        # Check if performance manager is in cooldown - if so, limit changes
        if (self.performance_manager and 
            self.performance_manager.adjustment_cooldown > 0 and
            len(self.scaling_decisions) > 0):
            
            # During cooldown, only allow small adjustments
            last_scale = self.scaling_decisions[-1]['optimal_scale']
            max_change = self.scaling_params['base_step'] * 0.3
            bounded_scale = last_scale + np.clip(current_scale - last_scale, -max_change, max_change)
            return bounded_scale
        
        # Analyze historical success with similar contexts
        if len(self.scaling_decisions) >= 5:
            similar_contexts = []
            for decision in self.scaling_decisions:
                context_similarity = self._calculate_context_similarity(context, decision['context'])
                if context_similarity > 0.7:  # Similar context
                    performance_improvement = self._calculate_performance_improvement(decision)
                    similar_contexts.append((decision['optimal_scale'], performance_improvement))
            
            if similar_contexts:
                # Find the scale that gave best performance in similar contexts
                best_scale, best_improvement = max(similar_contexts, key=lambda x: x[1])
                
                if best_improvement > 0.1:  # Significant improvement
                    # Blend with historical best (20% weight during non-cooldown)
                    adjusted_scale = current_scale * 0.8 + best_scale * 0.2
                    return adjusted_scale
        
        return current_scale

    def _calculate_context_similarity(self, ctx1: Dict, ctx2: Dict) -> float:
        """Calculate similarity between two context profiles"""
        similarity = 0.0
        weights = {
            'face_density': 0.3,
            'scene_complexity': 0.2,
            'lighting_conditions': 0.2,
            'motion_level': 0.15,
            'focus_quality': 0.15
        }
        
        for key, weight in weights.items():
            if key in ctx1 and key in ctx2:
                diff = abs(ctx1[key] - ctx2[key])
                similarity += weight * (1.0 - diff)
        
        return similarity

    def _calculate_performance_improvement(self, decision: Dict) -> float:
        """Calculate performance improvement from a scaling decision"""
        if 'performance' not in decision:
            return 0.0
        
        perf = decision['performance']
        # Simple improvement metric based on detection quality and count
        improvement = perf.get('detection_quality', 0) * 0.7 + \
                     min(1.0, perf.get('detection_count', 0) / 10) * 0.3
        return improvement

    def apply_scale_adjustment(self, new_scale: float) -> bool:
        """Apply scale adjustment with cooldown and performance manager coordination"""
        
        # Check minimum time between adjustments
        current_time = time.time()
        time_since_last = current_time - self.last_adjustment_time
        
        # Respect performance manager's cooldown
        if (self.performance_manager and 
            self.performance_manager.adjustment_cooldown > 0 and
            time_since_last < 1.0):  # Minimal cooldown even if PM has longer
            return False
        
        # Apply cooldown after adjustments
        if self.adjustment_cooldown > 0:
            self.adjustment_cooldown -= 1
            return False
        
        scale_change = abs(new_scale - self.current_scale)
        
        # Only apply significant changes, respecting performance manager's step size
        min_change = getattr(self.performance_manager, 'scale_adjustment_step', 
                           self.scaling_params['base_step']) * 0.4
        
        if scale_change >= min_change:
            old_scale = self.current_scale
            self.current_scale = new_scale
            self.adjustment_cooldown = 2  # Short cooldown for context adjustments
            self.last_adjustment_time = current_time
            
            # Log the adjustment
            direction = "🔼" if new_scale > old_scale else "🔽" if new_scale < old_scale else "➡️"
            self.logger.info(f"Context-aware scaling: {old_scale:.2f} {direction} {new_scale:.2f}")
            
            # Log context reasoning if available
            if self.context_recommendations_history:
                latest_rec = self.context_recommendations_history[-1]['recommendations']
                for reason in latest_rec.get('reasoning', [])[:1]:  # Show top reason only
                    self.logger.debug(f"Context reasoning: {reason}")
            
            # Respect performance manager's momentum
            if self.performance_manager and self.performance_manager.consecutive_poor_detections >= 2:
                self.logger.debug(f"Performance momentum: {self.performance_manager.consecutive_poor_detections} poor detections")
            
            return True
        
        return False


    def get_scaling_statistics(self) -> Dict:
        """Get scaling statistics and insights with performance manager integration"""
        stats = {
            'current_scale': self.current_scale,
            'total_decisions': len(self.scaling_decisions),
            'average_scale': 0.0,
            'context_weight': self.scaling_params['context_weight'],
            'performance_weight': self.scaling_params['performance_weight'],
            'recent_context_stats': self.scene_analyzer.get_context_statistics(),
            'performance_manager_linked': self.performance_manager is not None
        }
        
        if self.performance_manager:
            pm_stats = self.performance_manager.get_performance_stats()
            stats['performance_manager_scale'] = pm_stats.get('current_scale', 'N/A')
            stats['pm_adjustment_cooldown'] = pm_stats.get('adjustment_cooldown', 0)
            stats['pm_dynamic_enabled'] = pm_stats.get('dynamic_adjustment_enabled', False)
        
        if self.scaling_decisions:
            scales = [d['optimal_scale'] for d in self.scaling_decisions]
            stats['average_scale'] = np.mean(scales)
            stats['scale_variance'] = np.var(scales)
            stats['scale_trend'] = 'increasing' if scales[-1] > scales[0] else 'decreasing'
        
        # Most common context recommendations
        if self.context_recommendations_history:
            recent_recs = list(self.context_recommendations_history)[-5:]  # Last 5
            common_reasons = {}
            for rec in recent_recs:
                for reason in rec['recommendations'].get('reasoning', []):
                    common_reasons[reason] = common_reasons.get(reason, 0) + 1
            
            stats['common_recommendations'] = dict(sorted(
                common_reasons.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:3])  # Top 3
        
        return stats

    def reset_scaling_history(self):
        """Reset scaling history while preserving performance manager link"""
        self.scaling_decisions.clear()
        self.performance_history.clear()
        self.context_recommendations_history.clear()
        self.adjustment_cooldown = 0
        
        if self.performance_manager:
            self.current_scale = self.performance_manager.current_processing_scale
        
        self.logger.info("Context scaling history reset")
        