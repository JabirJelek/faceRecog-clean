# tracking/tracking_manager.py
from typing import List, Dict, Tuple
import numpy as np
from .face_tracker import SimpleFaceTracker
from .fairness_controller import FairnessController

class TrackingManager:
    """
    Unified manager for all tracking-related functionality
    Handles face tracking, fairness control, and coordinate transformations
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # Extract tracking-specific configuration with defaults
        tracking_config = self.config.get('tracking', {})
        
        # Initialize trackers with configurable parameters
        self.face_tracker = SimpleFaceTracker(
            confidence_frames=tracking_config.get('confidence_frames', 3),
            cooldown_seconds=tracking_config.get('cooldown_seconds', 5),
            min_iou=tracking_config.get('min_iou', 0.3)
        )
        
        self.fairness_controller = FairnessController(
            max_recognitions_per_person=tracking_config.get('max_recognitions_per_person', 10),
            recent_window_size=tracking_config.get('recent_window_size', 100)
        )
        
        # Performance tracking
        self.frame_count = 0
        self.tracking_enabled = tracking_config.get('enabled', True)
        self.fairness_enabled = tracking_config.get('fairness_enabled', True)
        
        # Advanced tracking features
        self.enable_velocity_prediction = tracking_config.get('enable_velocity_prediction', False)
        self.enable_appearance_matching = tracking_config.get('enable_appearance_matching', True)
        self.max_track_age = tracking_config.get('max_track_age', 300)  # frames
        
        print("🎯 TrackingManager initialized with configuration:")
        print(f"   - Tracking: {'ENABLED' if self.tracking_enabled else 'DISABLED'}")
        print(f"   - Fairness: {'ENABLED' if self.fairness_enabled else 'DISABLED'}")
        print(f"   - Confidence Frames: {tracking_config.get('confidence_frames', 3)}")
        print(f"   - Cooldown: {tracking_config.get('cooldown_seconds', 5)}s")
        print(f"   - Min IoU: {tracking_config.get('min_iou', 0.3)}")
        
    def update_config(self, new_config: Dict):
        """Update configuration at runtime"""
        tracking_config = new_config.get('tracking', {})
        
        # Update enabled states
        if 'enabled' in tracking_config:
            self.tracking_enabled = tracking_config['enabled']
            
        if 'fairness_enabled' in tracking_config:
            self.fairness_enabled = tracking_config['fairness_enabled']
            
        # Update advanced features
        if 'enable_velocity_prediction' in tracking_config:
            self.enable_velocity_prediction = tracking_config['enable_velocity_prediction']
            
        if 'enable_appearance_matching' in tracking_config:
            self.enable_appearance_matching = tracking_config['enable_appearance_matching']
            
        if 'max_track_age' in tracking_config:
            self.max_track_age = tracking_config['max_track_age']
            
        print("🔧 Tracking configuration updated")
    
    def process_frame(self, 
                     recognition_results: List[Dict], 
                     original_shape: Tuple[int, int],
                     processed_shape: Tuple[int, int]) -> List[Dict]:
        """
        Process frame through tracking pipeline
        
        Args:
            recognition_results: Raw recognition results from face system
            original_shape: (height, width) of original frame
            processed_shape: (height, width) of processed frame
            
        Returns:
            Enhanced results with tracking and fairness applied
        """
        self.frame_count += 1
        
        # Scale bounding boxes from processed frame to original frame
        scaled_results = self._scale_results_to_original(
            recognition_results, original_shape, processed_shape
        )
        
        # Apply face tracking if enabled
        if self.tracking_enabled:
            tracked_results = self.face_tracker.update(scaled_results, self.frame_count)
        else:
            tracked_results = scaled_results
        
        # Apply fairness control if enabled
        if self.fairness_enabled:
            final_results = self.fairness_controller.ensure_fair_attention(tracked_results)
        else:
            final_results = tracked_results
        
        # Cleanup old tracks periodically
        if self.frame_count % 30 == 0:  # Every 30 frames
            self.face_tracker.cleanup_old_tracks(self.frame_count, self.max_track_age)
        
        return final_results
    
    def _scale_results_to_original(self, 
                                 results: List[Dict], 
                                 original_shape: Tuple[int, int],
                                 processed_shape: Tuple[int, int]) -> List[Dict]:
        """Scale bounding box coordinates from processed frame back to original frame"""
        if not results:
            return []
        
        orig_h, orig_w = original_shape
        proc_h, proc_w = processed_shape
        
        # Avoid division by zero
        if proc_w == 0 or proc_h == 0:
            return results
            
        scale_x = orig_w / proc_w
        scale_y = orig_h / proc_h
        
        scaled_results = []
        for result in results:
            scaled_result = result.copy()
            x1, y1, x2, y2 = result['bbox']
            
            scaled_bbox = [
                int(x1 * scale_x),
                int(y1 * scale_y),
                int(x2 * scale_x),
                int(y2 * scale_y)
            ]
            scaled_result['bbox'] = scaled_bbox
            scaled_results.append(scaled_result)
        
        return scaled_results
    
    def scale_to_display(self, 
                        results: List[Dict], 
                        original_shape: Tuple[int, int],
                        display_shape: Tuple[int, int]) -> List[Dict]:
        """Scale bounding box coordinates from original frame to display frame"""
        if not results:
            return []
        
        orig_h, orig_w = original_shape
        disp_h, disp_w = display_shape
        
        # Avoid division by zero
        if orig_w == 0 or orig_h == 0:
            return results
            
        scale_x = disp_w / orig_w
        scale_y = disp_h / orig_h
        
        display_results = []
        for result in results:
            display_result = result.copy()
            x1, y1, x2, y2 = result['bbox']
            
            display_bbox = [
                int(x1 * scale_x),
                int(y1 * scale_y),
                int(x2 * scale_x),
                int(y2 * scale_y)
            ]
            display_result['bbox'] = display_bbox
            display_results.append(display_result)
        
        return display_results
    
    def get_tracking_stats(self) -> Dict:
        """Get comprehensive tracking statistics"""
        face_stats = self.face_tracker.get_tracking_stats()
        fairness_stats = self.fairness_controller.get_fairness_stats()
        
        return {
            'frame_count': self.frame_count,
            'tracking_enabled': self.tracking_enabled,
            'fairness_enabled': self.fairness_enabled,
            'enable_velocity_prediction': self.enable_velocity_prediction,
            'enable_appearance_matching': self.enable_appearance_matching,
            'max_track_age': self.max_track_age,
            'face_tracker': face_stats,
            'fairness_controller': fairness_stats
        }
    
    def get_config(self) -> Dict:
        """Get current tracking configuration"""
        return {
            'tracking': {
                'enabled': self.tracking_enabled,
                'fairness_enabled': self.fairness_enabled,
                'confidence_frames': self.face_tracker.confidence_frames,
                'cooldown_seconds': self.face_tracker.cooldown_frames // 30,
                'min_iou': self.face_tracker.min_iou,
                'max_recognitions_per_person': self.fairness_controller.max_recognitions_per_person,
                'recent_window_size': self.fairness_controller.recent_recognitions.maxlen,
                'enable_velocity_prediction': self.enable_velocity_prediction,
                'enable_appearance_matching': self.enable_appearance_matching,
                'max_track_age': self.max_track_age
            }
        }
    
    def toggle_tracking(self, enabled: bool = None):
        """Toggle face tracking"""
        if enabled is None:
            self.tracking_enabled = not self.tracking_enabled
        else:
            self.tracking_enabled = enabled
        
        status = "ENABLED" if self.tracking_enabled else "DISABLED"
        print(f"👤 Face tracking: {status}")
    
    def toggle_fairness(self, enabled: bool = None):
        """Toggle fairness control"""
        if enabled is None:
            self.fairness_enabled = not self.fairness_enabled
        else:
            self.fairness_enabled = enabled
        
        status = "ENABLED" if self.fairness_enabled else "DISABLED"
        print(f"⚖️ Fairness control: {status}")
    
    def reset(self):
        """Reset all tracking state"""
        self.face_tracker.reset()
        self.fairness_controller.reset()
        self.frame_count = 0
        print("🔄 Tracking system reset")
    
    def cleanup(self):
        """Cleanup old tracks"""
        self.face_tracker.cleanup_old_tracks(self.frame_count, self.max_track_age)