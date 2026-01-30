# tracking/tracking_manager.py
import numpy as np
from typing import List, Dict, Tuple, Optional
from .face_tracker import SimpleFaceTracker
from .fairness_controller import FairnessController
from .person_tracker import PersonTracker  # New import


class TrackingManager:
    """
    Enhanced unified manager with ByteTrack person tracking integration
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # Extract tracking-specific configuration with defaults
        tracking_config = self.config.get('tracking', {})
        
        # Initialize all trackers
        self.face_tracker = SimpleFaceTracker(
            confidence_frames=tracking_config.get('confidence_frames', 3),
            cooldown_seconds=tracking_config.get('cooldown_seconds', 5),
            min_iou=tracking_config.get('min_iou', 0.3)
        )
        
        self.fairness_controller = FairnessController(
            max_recognitions_per_person=tracking_config.get('max_recognitions_per_person', 10),
            recent_window_size=tracking_config.get('recent_window_size', 100)
        )
        
        # 🆕 NEW: Person tracker with ByteTrack
        self.person_tracker = PersonTracker(tracking_config)
        
        # Performance tracking
        self.frame_count = 0
        self.tracking_enabled = tracking_config.get('enabled', True)
        self.fairness_enabled = tracking_config.get('fairness_enabled', True)
        self.person_tracking_enabled = tracking_config.get('enable_person_tracking', True)
        
        # Advanced tracking features
        self.enable_velocity_prediction = tracking_config.get('enable_velocity_prediction', False)
        self.enable_appearance_matching = tracking_config.get('enable_appearance_matching', True)
        self.max_track_age = tracking_config.get('max_track_age', 300)  # frames
        
        print("🎯 Enhanced TrackingManager initialized with ByteTrack:")
        print(f"   - Face Tracking: {'ENABLED' if self.tracking_enabled else 'DISABLED'}")
        print(f"   - Person Tracking: {'ENABLED' if self.person_tracking_enabled else 'DISABLED'}")
        print(f"   - Fairness: {'ENABLED' if self.fairness_enabled else 'DISABLED'}")

    def process_frame(self, 
                     recognition_results: List[Dict], 
                     original_shape: Tuple[int, int],
                     processed_shape: Tuple[int, int],
                     person_detections: Optional[List[Dict]] = None,  # 🆕 NEW: YOLO person detections
                     frame: Optional[np.ndarray] = None) -> List[Dict]:
        """
        Enhanced process frame with person tracking integration
        
        Args:
            recognition_results: Raw recognition results from face system
            original_shape: (height, width) of original frame
            processed_shape: (height, width) of processed frame
            person_detections: YOLO person detections for ByteTrack (optional)
            frame: Original frame for visual tracking (optional)
            
        Returns:
            Enhanced results with both face and person tracking
        """
        self.frame_count += 1
        
        # Scale bounding boxes from processed frame to original frame
        scaled_results = self._scale_results_to_original(
            recognition_results, original_shape, processed_shape
        )
        
        # 🆕 NEW: Process person tracking if enabled and detections available
        person_tracks = []
        if (self.person_tracking_enabled and person_detections and 
            self.person_tracker.enabled):
            
            # Scale person detections to original frame
            scaled_person_detections = self._scale_results_to_original(
                person_detections, original_shape, processed_shape
            )
            
            # Update person tracker
            person_tracks = self.person_tracker.update(
                scaled_person_detections, scaled_results, self.frame_count, frame
            )
        
        # Apply face tracking if enabled
        if self.tracking_enabled:
            tracked_results = self.face_tracker.update(scaled_results, self.frame_count)
        else:
            tracked_results = scaled_results
        
        # Apply fairness control if enabled
        if self.fairness_enabled:
            final_face_results = self.fairness_controller.ensure_fair_attention(tracked_results)
        else:
            final_face_results = tracked_results
        
        # 🆕 NEW: Combine face and person tracking results
        final_results = self._combine_tracking_results(final_face_results, person_tracks)
        
        # Cleanup old tracks periodically
        if self.frame_count % 30 == 0:  # Every 30 frames
            self.face_tracker.cleanup_old_tracks(self.frame_count, self.max_track_age)
        
        return final_results

    def _combine_tracking_results(self, 
                                face_results: List[Dict], 
                                person_tracks: List[Dict]) -> List[Dict]:
        """
        Combine face tracking and person tracking results
        
        Priority: Person tracks with identities override face-only results
        """
        if not person_tracks:
            return face_results
        
        # Create a mapping of identity to best person track
        identity_to_person = {}
        for person in person_tracks:
            identity = person.get('identity', 'Unknown')
            if identity != 'Unknown':
                # Use the person track with highest confidence for each identity
                if (identity not in identity_to_person or 
                    person.get('confidence', 0) > identity_to_person[identity].get('confidence', 0)):
                    identity_to_person[identity] = person
        
        # Combine results: prefer person tracks for known identities
        combined_results = []
        used_identities = set()
        
        # First add person tracks with identities
        for identity, person_track in identity_to_person.items():
            combined_results.append(person_track)
            used_identities.add(identity)
        
        # Then add face results that don't have person tracks
        for face_result in face_results:
            identity = face_result.get('identity', 'Unknown')
            if identity not in used_identities:
                combined_results.append(face_result)
        
        # Finally add unknown person tracks
        for person_track in person_tracks:
            identity = person_track.get('identity', 'Unknown')
            if identity == 'Unknown' and person_track not in combined_results:
                combined_results.append(person_track)
        
        return combined_results

    def _scale_results_to_original(self, 
                                 results: List[Dict], 
                                 original_shape: Tuple[int, int],
                                 processed_shape: Tuple[int, int]) -> List[Dict]:
        """Scale bounding box coordinates from processed frame back to original frame"""
        if not results:
            return []
        
        orig_h, orig_w = original_shape
        proc_h, proc_w = processed_shape
        
        if proc_w == 0 or proc_h == 0:
            return results
            
        scale_x = orig_w / proc_w
        scale_y = orig_h / proc_h
        
        scaled_results = []
        for result in results:
            scaled_result = result.copy()
            bbox = result.get('bbox', [])
            
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox
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
        """Get comprehensive tracking statistics including person tracking"""
        face_stats = self.face_tracker.get_tracking_stats()
        fairness_stats = self.fairness_controller.get_fairness_stats()
        person_stats = self.person_tracker.get_tracking_stats()
        
        return {
            'frame_count': self.frame_count,
            'tracking_enabled': self.tracking_enabled,
            'person_tracking_enabled': self.person_tracking_enabled,
            'fairness_enabled': self.fairness_enabled,
            'enable_velocity_prediction': self.enable_velocity_prediction,
            'enable_appearance_matching': self.enable_appearance_matching,
            'max_track_age': self.max_track_age,
            'face_tracker': face_stats,
            'person_tracker': person_stats,
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

    def update_config(self, new_config: Dict):
        """Update configuration at runtime"""
        tracking_config = new_config.get('tracking', {})
        
        # Update enabled states
        if 'enabled' in tracking_config:
            self.tracking_enabled = tracking_config['enabled']
        if 'fairness_enabled' in tracking_config:
            self.fairness_enabled = tracking_config['fairness_enabled']
        if 'enable_person_tracking' in tracking_config:
            self.person_tracking_enabled = tracking_config['enable_person_tracking']
            
        # Update person tracker configuration
        self.person_tracker.update_config(tracking_config)
        
        # Update advanced features
        if 'enable_velocity_prediction' in tracking_config:
            self.enable_velocity_prediction = tracking_config['enable_velocity_prediction']
        if 'enable_appearance_matching' in tracking_config:
            self.enable_appearance_matching = tracking_config['enable_appearance_matching']
        if 'max_track_age' in tracking_config:
            self.max_track_age = tracking_config['max_track_age']
            
        print("🔧 Enhanced tracking configuration updated")

    def toggle_person_tracking(self, enabled: bool = None):
        """Toggle person tracking with ByteTrack"""
        if enabled is None:
            self.person_tracking_enabled = not self.person_tracking_enabled
        else:
            self.person_tracking_enabled = enabled
        
        status = "ENABLED" if self.person_tracking_enabled else "DISABLED"
        print(f"👤 Person tracking: {status}")

    def reset(self):
        """Reset all tracking state"""
        self.face_tracker.reset()
        self.fairness_controller.reset()
        self.person_tracker.reset()
        self.frame_count = 0
        print("🔄 Enhanced tracking system reset")

    def cleanup(self):
        """Cleanup all trackers"""
        self.face_tracker.cleanup_old_tracks(self.frame_count, self.max_track_age)
        self.person_tracker.cleanup()     