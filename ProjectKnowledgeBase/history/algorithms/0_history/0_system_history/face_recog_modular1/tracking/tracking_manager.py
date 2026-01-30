# tracking/tracking_manager.py 

import numpy as np
import time
import logging
from typing import List, Dict, Tuple, Optional, Any
from .face_tracker import SimpleFaceTracker
from .fairness_controller import FairnessController
from .progressive_mask_detector import ProgressiveMaskDetector
from queue import deque
from collections import defaultdict
import threading
class TrackingManager:
    """
    Streamlined unified manager that acts as a policy enforcer,
    relying on ProgressiveMaskDetector's stability metrics for violation verification
    """
    def __init__(self, config: Dict[str, Any]):
        # Store configuration
        self.config = config
        
        # DEBUG: Log entire config for troubleshooting
        print(f"🔧 [TrackingManager] Received config with keys: {list(config.keys())}")
        
        # ========== EXTRACT TRACKING CONFIG FIRST ==========
        tracking_config = config.get('tracking', {})
        
        # If no tracking config at root, check if config IS the tracking config
        if not tracking_config and 'confidence_frames' in config:
            tracking_config = config
            print(f"⚠️  Config appears to be tracking config itself, using as tracking_config")
        
        print(f"🔧 [TrackingManager] Tracking config: {list(tracking_config.keys())}")
        
        # Extract progressive_mask configuration
        progressive_config = {}
        
        # First, check if progressive_mask is at the root level
        if 'progressive_mask' in config:
            progressive_config = config['progressive_mask']
            print(f"✅ Found progressive_mask at root level")
        
        # If not, check if it's nested inside tracking config
        elif 'progressive_mask' in tracking_config:
            progressive_config = tracking_config['progressive_mask']
            print(f"✅ Found progressive_mask inside tracking config")
        
        # If we still don't have it, look for any nested structure
        else:
            # Search recursively for progressive_mask
            def find_progressive_config(config_dict, path=""):
                for key, value in config_dict.items():
                    if key == 'progressive_mask' and isinstance(value, dict):
                        print(f"✅ Found progressive_mask at path: {path}.{key}")
                        return value
                    elif isinstance(value, dict):
                        result = find_progressive_config(value, f"{path}.{key}")
                        if result:
                            return result
                return None
            
            progressive_config = find_progressive_config(config)
        
        # If still empty, use empty dict
        if not progressive_config:
            print(f"⚠️  No progressive_mask configuration found, using defaults")
            progressive_config = {}
        
        # DEBUG: Show what we're passing to ProgressiveMaskDetector
        print(f"🔧 [TrackingManager] Passing to ProgressiveMaskDetector:")
        print(f"   Config: {progressive_config}")
        if progressive_config:
            print(f"   Keys: {list(progressive_config.keys())}")
        
        # ========== INITIALIZE COMPONENTS IN CORRECT ORDER ==========
        
        # 1. Initialize ProgressiveMaskDetector FIRST
        self.progressive_detector = ProgressiveMaskDetector(progressive_config)
        
        # 2. Initialize Face Tracker with tracking_config
        self.face_tracker = SimpleFaceTracker(tracking_config)
        
        # 3. Extract other configuration parameters
        self.violation_verification_enabled = tracking_config.get('violation_verification_enabled', True)
        self.min_violation_frames = tracking_config.get('min_violation_frames', 1)
        self.min_violation_duration = tracking_config.get('min_violation_duration', 0.5)  # seconds
        self.tracking_enabled = tracking_config.get('enabled', True)
        self.fairness_enabled = tracking_config.get('fairness_enabled', True)
        
        # Setup logger for debugging
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # CRITICAL: Log policy threshold sanity check at initialization
        self.logger.info(f"Policy Thresholds - min_violation_frames: {self.min_violation_frames}, "
                        f"min_violation_duration: {self.min_violation_duration}s")
        
        # Initialize fairness controller if enabled
        if self.fairness_enabled:
            max_recognitions = tracking_config.get('max_recognitions_per_person', 10)
            recent_window = tracking_config.get('recent_window_size', 100)
            self.fairness_controller = FairnessController(
                max_recognitions_per_person=max_recognitions,
                recent_window_size=recent_window
            )
        
        # Simplified violation tracking
        self.violation_frames = {}  # track_id -> frame_count (for simple verification)
        self.violation_tracker = {}  # track_id -> violation data (for policy-based verification)
        self.verified_violations = []  # List of verified violations
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Statistics
        self.frame_count = 0
        self.violation_stats = {
            'violations_detected': 0,
            'violations_verified': 0,
            'false_positives_prevented': 0
        }
        
        # Debug counters
        self.cleanup_call_count = 0
        self.reset_reasons = defaultdict(int)
        
        self.logger.info("Simplified TrackingManager initialized")          
    def _consolidated_cleanup(self, current_time: float = None):
        """
        Consolidated cleanup method that handles all track removal logic.
        Removes expired tracks from all tracking components.
        """
        self.cleanup_call_count += 1
        
        if current_time is None:
            current_time = time.time()
        
        # B. AUDIT: Log when consolidated cleanup is called
        if self.cleanup_call_count % 50 == 0:  # Don't log every frame
            self.logger.debug(f"Consolidated cleanup called (count: {self.cleanup_call_count}), "
                            f"active violation tracks: {len(self.violation_tracker)}")
        
        # 1. Cleanup violation_frames (simple verification tracks)
        max_age_frames = 100  # ~5 seconds at 20 FPS
        tracks_to_remove = []
        for track_id, frame_count in list(self.violation_frames.items()):
            # Remove tracks that haven't been seen for a while
            if frame_count > max_age_frames:
                tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            # B. AUDIT: Log tracks removed due to age
            self.logger.debug(f"Removing track {track_id} from violation_frames due to age "
                            f"(frame_count: {self.violation_frames.get(track_id, 'N/A')})")
            self.violation_frames.pop(track_id, None)
            # Remove from verified_violations set if it exists
            if hasattr(self, 'verified_violations') and isinstance(self.verified_violations, set):
                self.verified_violations.discard(track_id)
        
        # 2. Cleanup violation_tracker (policy-based verification tracks)
        expired_tracks = []
        for track_id, tracker in self.violation_tracker.items():
            # Remove tracks that haven't been seen for 2x min duration
            time_since_last_seen = current_time - tracker['last_seen']
            if time_since_last_seen > (self.min_violation_duration * 2):
                expired_tracks.append(track_id)
        
        for track_id in expired_tracks:
            # B. AUDIT: Log tracks removed due to expiration
            self.logger.debug(f"Removing track {track_id} from violation_tracker due to expiration "
                            f"(time_since_last_seen: {time_since_last_seen:.2f}s)")
            self._cleanup_single_track(track_id, reason="expired_due_to_inactivity")
        
        # 3. Cleanup progressive mask detector's internal tracks
        self.progressive_detector.cleanup_expired_tracks(current_time)
        
    def _cleanup_single_track(self, track_id: str, reason: str = "unknown"):
        """
        Clean up a single track from all tracking systems and count as false positive prevented.
        
        Args:
            track_id: Track ID to clean up
            reason: Reason for cleanup (for debugging)
        """
        # B. AUDIT: Log EVERY cleanup with reason
        self.logger.info(f"CLEANUP TRACK {track_id} - Reason: {reason}")
        self.reset_reasons[reason] += 1
        
        if track_id == "0" or track_id == 0:
            self.logger.warning(f"CRITICAL: Cleaning up track_id=0 with reason: {reason}")
            # Log stack trace for track_id=0 cleanup
            import traceback
            self.logger.debug(f"Stack trace for track_id=0 cleanup:\n{traceback.format_stack()}")
        
        # Remove from progressive mask detector FIRST (enforce progressive cleanup)
        if hasattr(self, 'progressive_detector') and self.progressive_detector is not None:
            # Call the private method to remove the track from all ProgressiveMaskDetector buffers
            self.progressive_detector._remove_track(track_id)
            self.logger.debug(f"Progressive cleanup: Removed track {track_id} from ProgressiveMaskDetector")
        
        # Then clean up from violation_tracker
        if track_id in self.violation_tracker:
            tracker = self.violation_tracker[track_id]
            if not tracker['verified']:
                self.violation_stats['false_positives_prevented'] += 1
                self.logger.debug(f"Counted as false positive for track {track_id}")
            del self.violation_tracker[track_id]
            self.logger.debug(f"Removed track {track_id} from violation_tracker")
        
        # Also remove from violation_frames if present
        if track_id in self.violation_frames:
            frame_count = self.violation_frames[track_id]
            del self.violation_frames[track_id]
            self.logger.debug(f"Removed track {track_id} from violation_frames (had {frame_count} frames)")
        
        # Remove from verified_violations set if it exists
        if hasattr(self, 'verified_violations') and isinstance(self.verified_violations, set):
            if track_id in self.verified_violations:
                self.verified_violations.discard(track_id)
                self.logger.debug(f"Removed track {track_id} from verified_violations set")
        
        # Also clean up from face tracker if needed
        if hasattr(self, 'face_tracker') and self.face_tracker is not None:
            # Check if face_tracker has a method to remove tracks
            if hasattr(self.face_tracker, '_remove_track'):
                self.face_tracker._remove_track(track_id)
            elif hasattr(self.face_tracker, 'remove_track'):
                self.face_tracker.remove_track(track_id)
            self.logger.debug(f"Removed track {track_id} from face tracker")
        
        self.logger.info(f"Track {track_id} fully cleaned up from all tracking systems (reason: {reason})")

    def _apply_simple_verification(self, results: List[Dict]) -> List[Dict]:
        """Simple frame-based verification without complex state machines"""
        verified_results = []
        
        for result in results:
            result_copy = result.copy()
            track_id = result_copy.get('track_id')
            mask_status = result_copy.get('mask_status', 'unknown')
            
            # Only verify no_mask violations
            if mask_status != 'no_mask':
                result_copy['violation_verified'] = False
                verified_results.append(result_copy)
                continue
            
            # Initialize frame counter
            if track_id not in self.violation_frames:
                self.violation_frames[track_id] = 0
            
            # Increment violation frames
            self.violation_frames[track_id] += 1
            
            # Simple verification: require minimum consecutive frames
            if self.violation_frames[track_id] >= self.min_violation_frames:
                if not hasattr(self.verified_violations, 'add'):
                    self.verified_violations = set()
                if track_id not in self.verified_violations:
                    self.verified_violations.add(track_id)
                    self.violation_stats['violations_verified'] += 1
                
                result_copy['violation_verified'] = True
                result_copy['violation_frames'] = self.violation_frames[track_id]
            else:
                result_copy['violation_verified'] = False
                result_copy['verification_progress'] = (
                    self.violation_frames[track_id] / self.min_violation_frames
                )
            
            # Reset counter if mask is detected
            if mask_status == 'mask' and track_id in self.violation_frames:
                self.violation_frames[track_id] = 0
            
            verified_results.append(result_copy)
        
        # Use consolidated cleanup
        self._consolidated_cleanup()
        
        return verified_results

    def _apply_policy_based_verification(self, 
                                        results: List[Dict], 
                                        current_time: float,
                                        image_logger=None) -> List[Dict]:
        """
        Simplified policy-based verification that relies on ProgressiveMaskDetector's stability metrics
        """
        if not self.violation_verification_enabled:
            for result in results:
                result['violation_verified'] = True
                result['verification_level'] = 'disabled'
                result['violation_duration'] = 0.0
                result['violation_frames'] = 0
                result['violation_stable'] = False
            return results
        
        verified_results = []
        
        for result in results:
            result_copy = result.copy()
            track_id = result_copy.get('track_id')
            
            # C. POLICY CHECK: Log if track_id=0 has no_mask but shows 0.00 progress
            if track_id in ["0", 0]:
                progressive_data = result_copy.get('progressive_mask_data', {})
                mask_status = progressive_data.get('mask_status', 'unknown')
                verification_progress = progressive_data.get('verification_progress', 0)
                
                if mask_status == 'no_mask' and verification_progress == 0.0:
                    self.logger.warning(f"TRACK_ID=0 POLICY CHECK: no_mask but 0.00 progress, "
                                      f"is_stable={progressive_data.get('is_stable', False)}, "
                                      f"frames={progressive_data.get('frames_processed', 0)}")
            
            # Get progressive mask data - ProgressiveMaskDetector handles all analysis
            progressive_data = result_copy.get('progressive_mask_data', {})
            
            # Extract key metrics from progressive detector
            mask_status = progressive_data.get('mask_status', 'unknown')
            is_stable = progressive_data.get('is_stable', False)
            has_contradictions = progressive_data.get('has_contradictions', False)
            verification_progress = progressive_data.get('verification_progress', 0)
            frames_processed = progressive_data.get('frames_processed', 0)
            
            # Extract holding status information for stricter reset conditions
            holding_status = progressive_data.get('holding_status', 'verifying')
            time_since_commit = progressive_data.get('time_since_commit', float('inf'))
            holding_applied = progressive_data.get('holding_applied', False)
            
            # POLICY ENFORCEMENT: Simple rules based on progressive detector output
            if (mask_status == 'no_mask' and 
                is_stable and 
                not has_contradictions and
                verification_progress >= 0.55):
                
                # TRACKING POLICY: Track duration for minimum requirement
                if track_id not in self.violation_tracker:
                    # New violation track
                    self.violation_tracker[track_id] = {
                        'start_time': current_time,
                        'frames': 1,
                        'verified': False,
                        'last_seen': current_time,
                        'non_violation_frames': 0  # Track consecutive non-violation frames
                    }
                    self.violation_stats['violations_detected'] += 1
                    self.logger.debug(f"New violation track {track_id}: "
                                    f"mask_status={mask_status}, stable={is_stable}, "
                                    f"progress={verification_progress:.2f}")
                else:
                    # Update existing track
                    tracker = self.violation_tracker[track_id]
                    tracker['frames'] += 1
                    tracker['last_seen'] = current_time
                    tracker['non_violation_frames'] = 0  # Reset counter when we have a violation
                
                tracker = self.violation_tracker[track_id]
                duration = current_time - tracker['start_time']
                
                # C. POLICY CHECK: Log threshold comparison
                if track_id in ["0", 0] and tracker['frames'] % 10 == 0:
                    self.logger.debug(f"TRACK_ID=0: frames={tracker['frames']}, "
                                    f"duration={duration:.2f}s, "
                                    f"min_frames={self.min_violation_frames}, "
                                    f"min_duration={self.min_violation_duration}s")
                
                # FINAL VERIFICATION POLICY: Require minimum duration
                if (duration >= self.min_violation_duration and 
                    tracker['frames'] >= self.min_violation_frames and
                    not tracker['verified']):
                    
                    tracker['verified'] = True
                    self.violation_stats['violations_verified'] += 1
                    self.logger.info(f"Verified violation for track {track_id}: "
                                   f"duration={duration:.2f}s, frames={tracker['frames']}")
                    
                    # Record verified violation
                    verified_violation = {
                        'track_id': track_id,
                        'verified_time': current_time,
                        'duration': duration,
                        'frames': tracker['frames'],
                        'progressive_frames': frames_processed,
                        'stability_score': verification_progress,
                        'bbox': result_copy.get('bbox', [])
                    }
                    self.verified_violations.append(verified_violation)
                    if len(self.verified_violations) > 50:
                        self.verified_violations.pop(0)
                
                # Set result verification status
                result_copy['violation_verified'] = tracker.get('verified', False)
                result_copy['verification_level'] = 'verified' if tracker.get('verified') else 'pending'
                result_copy['violation_duration'] = duration
                result_copy['violation_frames'] = tracker['frames']
                result_copy['violation_stable'] = is_stable
                result_copy['verification_progress'] = verification_progress
                
            else:
                # Not a valid violation candidate
                result_copy['violation_verified'] = False
                result_copy['verification_level'] = 'none'
                result_copy['violation_duration'] = 0.0
                result_copy['violation_frames'] = 0
                result_copy['violation_stable'] = False
                result_copy['verification_progress'] = verification_progress
                
                # Clean up tracker if track exists with stricter reset conditions
                if track_id and track_id in self.violation_tracker:
                    # STRICTER RESET CONDITION: Check if we should reset the violation track
                    should_reset = False
                    reset_reason = ""
                    
                    # Condition 1: Fresh, stable mask commitment from detector
                    if holding_status == 'mask' and time_since_commit == 0:
                        reset_reason = "fresh_mask_commitment"
                        should_reset = True
                    
                    # Condition 2: Prolonged inconsistency detected by the detector
                    elif has_contradictions and frames_processed > 10:
                        # Only reset if we have enough frames to trust the inconsistency
                        reset_reason = f"prolonged_contradictions_{frames_processed}_frames"
                        should_reset = True
                    
                    # Condition 3: Detector is holding mask state and not just temporarily
                    elif (holding_status == 'mask' and 
                        not holding_applied and 
                        mask_status == 'mask' and 
                        frames_processed > 5):
                        # Detector has stable mask state that's not just being held from previous
                        reset_reason = f"stable_mask_state_{frames_processed}_frames"
                        should_reset = True
                    
                    # Condition 4: Track consecutive non-violation frames
                    elif mask_status != 'no_mask':
                        tracker = self.violation_tracker[track_id]
                        if 'non_violation_frames' not in tracker:
                            tracker['non_violation_frames'] = 0
                        tracker['non_violation_frames'] += 1
                        
                        # Reset if we've had too many consecutive non-violation frames
                        if tracker['non_violation_frames'] > 20:  # ~0.75 seconds at 20 FPS
                            reset_reason = f"consecutive_non_violation_frames_{tracker['non_violation_frames']}"
                            should_reset = True
                    
                    # B. AUDIT: Log reset decision for track_id=0
                    if track_id in ["0", 0]:
                        self.logger.warning(f"Evaluating reset for track_id=0: "
                                          f"should_reset={should_reset}, reason='{reset_reason}', "
                                          f"mask_status={mask_status}, holding={holding_status}, "
                                          f"contradictions={has_contradictions}")
                    
                    # Apply reset if conditions met
                    if should_reset:
                        # B. AUDIT: Log the specific condition that triggers cleanup
                        self.logger.info(f"Stricter reset triggered for track {track_id}: {reset_reason}")
                        self._cleanup_single_track(track_id, reason=f"policy_reset_{reset_reason}")
            
            verified_results.append(result_copy)
        
        # Use consolidated cleanup for expired tracks
        self._consolidated_cleanup(current_time)
        
        return verified_results

    def process_frame(self, source_id, recognition_results, 
                      original_shape, processed_shape, 
                      person_detections=None,
                      frame=None,
                      image_logger=None):
        """Thread-safe frame processing"""
        with self.lock:
            return self._process_frame_unsafe(
                source_id, recognition_results, original_shape, 
                processed_shape, person_detections, frame, image_logger
            )
    
    def _process_frame_unsafe(self, source_id, recognition_results, 
                            original_shape, processed_shape, 
                            person_detections=None,
                            frame=None,
                            image_logger=None):
        
        self.frame_count += 1
        current_time = time.time()
        
        # 1. Scale results to original
        scaled_results = self._scale_results_to_original(
            recognition_results, original_shape, processed_shape
        )
        
        # 2. Apply face tracking FIRST - assigns stable sequential IDs
        if self.tracking_enabled:
            tracked_results = self.face_tracker.update(scaled_results, self.frame_count)
            
            # A. DEBUG: Log track_id stability after face tracker
            for i, result in enumerate(tracked_results):
                track_id = result.get('track_id')
                if track_id in ["0", 0]:
                    self.logger.info(f"POST-TRACKER CHECK frame={self.frame_count}: "
                                   f"track_id={track_id}, "
                                   f"bbox={result.get('bbox', [])}, "
                                   f"mask_status={result.get('mask_status', 'unknown')}")
        else:
            tracked_results = scaled_results
            # Even without tracking, ensure results have track_id field (set to None)
            for result in tracked_results:
                result['track_id'] = None
        
        # A. DEBUG: Log all track_ids after face tracking
        if self.frame_count % 30 == 0:  # Log every 30 frames
            track_ids = [r.get('track_id') for r in tracked_results]
            self.logger.debug(f"Frame {self.frame_count} - Track IDs after face tracker: {track_ids}")
        
        # 3. Apply progressive mask detection (now receives stable track_id from SimpleFaceTracker)
        for i, result in enumerate(tracked_results):
            track_id = result.get('track_id')
            if track_id in ["0", 0]:
                self.logger.debug(f"Applying progressive detection to track_id={track_id}")
            tracked_results[i] = self._apply_progressive_mask_detection(result, current_time)
        
        # 4. Apply policy-based violation verification
        if self.violation_verification_enabled:
            verified_results = self._apply_policy_based_verification(
                tracked_results, current_time, image_logger
            )
        else:
            verified_results = tracked_results
            for result in verified_results:
                result['violation_verified'] = True
        
        # 5. Apply fairness (optional)
        if self.fairness_enabled:
            final_results = self.fairness_controller.ensure_fair_attention(verified_results)
        else:
            final_results = verified_results
        
        # 6. Ensure all results have necessary fields
        final_results = self._ensure_identity_in_results(final_results)
        
        return final_results

    def _apply_progressive_mask_detection(self, result: Dict, current_time: float) -> Dict:
        """Apply progressive mask detection - receives stable track_id from SimpleFaceTracker"""
        result_copy = result.copy()
        
        # Get track ID assigned by SimpleFaceTracker
        track_id = result.get('track_id')
        if not track_id:
            # If no track_id is present (tracking disabled or new face not yet assigned),
            # skip progressive mask detection or handle appropriately
            # Note: SimpleFaceTracker should have assigned a track_id by this point
            return result_copy
        
        # Get current mask detection
        mask_status = result.get('mask_status', 'unknown')
        mask_confidence = result.get('mask_confidence', 0.0)
        bbox = result.get('bbox')
        
        # ProgressiveMaskDetector now receives reliable, sequential track_id
        progressive_data = self.progressive_detector.update_track(
            track_id, mask_status, mask_confidence, bbox, current_time
        )
        
        # Add progressive mask data to result
        result_copy['progressive_mask_data'] = progressive_data
        result_copy['progressive_mask_status'] = progressive_data['mask_status']
        result_copy['progressive_mask_confidence'] = progressive_data['mask_confidence']
        result_copy['mask_verification_progress'] = progressive_data['verification_progress']
        result_copy['mask_frames_processed'] = progressive_data['frames_processed']
        result_copy['mask_is_stable'] = progressive_data['is_stable']
        result_copy['has_contradictions'] = progressive_data['has_contradictions']
        
        return result_copy

    def cleanup(self):
        """Cleanup all trackers using consolidated cleanup"""
        self._consolidated_cleanup(time.time())

    def _ensure_identity_in_results(self, results: List[Dict]) -> List[Dict]:
        """Ensure all results have identity field with proper fallback"""
        for result in results:
            if 'identity' not in result:
                result['identity'] = 'Unknown'
            if 'recognition_confidence' not in result:
                result['recognition_confidence'] = 0.0
            
            if 'violation_verified' not in result:
                result['violation_verified'] = False
                
            if 'progressive_mask_data' not in result:
                result['progressive_mask_data'] = {
                    'mask_status': result.get('mask_status', 'unknown'),
                    'mask_confidence': result.get('mask_confidence', 0.0),
                    'verification_progress': 0.0,
                    'frames_processed': 0,
                    'is_stable': False,
                    'has_contradictions': False
                }
        
        return results

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

    def get_violation_verification_stats(self) -> Dict:
        """Get simplified violation verification statistics"""
        return {
            'total_detected': self.violation_stats['violations_detected'],
            'total_verified': self.violation_stats['violations_verified'],
            'false_positives_prevented': self.violation_stats['false_positives_prevented'],
            'active_violation_tracks': len(self.violation_tracker),
            'currently_verified': sum(1 for t in self.violation_tracker.values() if t.get('verified', False)),
            'verification_accuracy': self._calculate_verification_accuracy()
        }
    
    def _calculate_verification_accuracy(self) -> float:
        """Calculate overall verification accuracy"""
        total_verified = self.violation_stats['violations_verified']
        false_positives = self.violation_stats['false_positives_prevented']
        total_decisions = total_verified + false_positives
        
        if total_decisions > 0:
            return total_verified / total_decisions * 100
        return 0.0
        
    def reset_violation_stats(self):
        """Reset violation statistics"""
        self.violation_stats = {
            'violations_detected': 0,
            'violations_verified': 0,
            'false_positives_prevented': 0
        }

    def update_violation_verification_config(self, verification_config: Dict[str, Any]):
        """Update violation verification configuration"""
        try:
            old_frames = self.min_violation_frames
            old_duration = self.min_violation_duration
            
            self.violation_verification_enabled = verification_config.get(
                'violation_verification_enabled', self.violation_verification_enabled
            )
            self.min_violation_duration = verification_config.get(
                'min_violation_duration', self.min_violation_duration
            )
            self.min_violation_frames = verification_config.get(
                'min_violation_frames', self.min_violation_frames
            )
            
            # C. POLICY CHECK: Log when thresholds change
            if old_frames != self.min_violation_frames or old_duration != self.min_violation_duration:
                self.logger.info(f"Policy thresholds updated: "
                               f"frames {old_frames}→{self.min_violation_frames}, "
                               f"duration {old_duration}→{self.min_violation_duration}s")
                
        except Exception as e:
            self.logger.error(f"Error updating violation verification config: {e}")

    def get_tracking_stats(self) -> Dict:
        """Get comprehensive tracking statistics"""
        face_stats = self.face_tracker.get_tracking_stats() if hasattr(self, 'face_tracker') else {}
        fairness_stats = self.fairness_controller.get_fairness_stats() if hasattr(self, 'fairness_controller') else {}
        
        # Get progressive mask detector stats
        progressive_stats = {}
        if hasattr(self, 'progressive_detector'):
            progressive_stats = self.progressive_detector.get_stats()
        
        return {
            'frame_count': self.frame_count,
            'tracking_enabled': self.tracking_enabled,
            'fairness_enabled': self.fairness_enabled,
            'violation_verification_enabled': self.violation_verification_enabled,
            'face_tracker': face_stats,
            'fairness_controller': fairness_stats,
            'progressive_detector': progressive_stats,
            'violation_stats': self.violation_stats,
            'debug_stats': {
                'cleanup_call_count': self.cleanup_call_count,
                'reset_reasons': dict(self.reset_reasons),
                'active_violation_tracks': len(self.violation_tracker),
                'policy_thresholds': {
                    'min_violation_frames': self.min_violation_frames,
                    'min_violation_duration': self.min_violation_duration
                }
            }
        }

    def get_config(self) -> Dict:
        """Get current tracking configuration"""
        progressive_config = {}
        if hasattr(self, 'progressive_detector'):
            progressive_config = self.progressive_detector.get_config()
            
        return {
            'tracking': {
                'enabled': self.tracking_enabled,
                'fairness_enabled': self.fairness_enabled,
                'violation_verification_enabled': self.violation_verification_enabled,
                'min_violation_duration': self.min_violation_duration,
                'min_violation_frames': self.min_violation_frames,
                'progressive_mask': progressive_config
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
            
        # Update violation verification configuration
        verification_config = {
            'violation_verification_enabled': tracking_config.get('violation_verification_enabled', self.violation_verification_enabled),
            'min_violation_duration': tracking_config.get('min_violation_duration', self.min_violation_duration),
            'min_violation_frames': tracking_config.get('min_violation_frames', self.min_violation_frames)
        }
        self.update_violation_verification_config(verification_config)
            
        # Update progressive mask detector configuration
        progressive_config = tracking_config.get('progressive_mask', {})
        if progressive_config and hasattr(self, 'progressive_detector'):
            self.progressive_detector.update_config(progressive_config)

    def toggle_violation_verification(self, enabled: bool = None):
        """Toggle violation verification"""
        if enabled is None:
            self.violation_verification_enabled = not self.violation_verification_enabled
        else:
            self.violation_verification_enabled = enabled
        status = "ENABLED" if self.violation_verification_enabled else "DISABLED"
        self.logger.info(f"Policy-based verification: {status}")

    def debug_track_id_stability(self, track_id: str = "0"):
        """
        Debug method to check stability of a specific track_id
        
        Args:
            track_id: Track ID to debug (default "0")
        """
        self.logger.info(f"DEBUG TRACK_ID={track_id}:")
        self.logger.info(f"  - In violation_tracker: {track_id in self.violation_tracker}")
        if track_id in self.violation_tracker:
            tracker = self.violation_tracker[track_id]
            self.logger.info(f"    Verified: {tracker.get('verified', False)}")
            self.logger.info(f"    Frames: {tracker.get('frames', 0)}")
            self.logger.info(f"    Duration: {time.time() - tracker.get('start_time', time.time()):.2f}s")
        
        self.logger.info(f"  - In violation_frames: {track_id in self.violation_frames}")
        if track_id in self.violation_frames:
            self.logger.info(f"    Frame count: {self.violation_frames[track_id]}")
        
        # Check if in progressive mask detector
        if hasattr(self.progressive_detector, 'track_buffers'):
            self.logger.info(f"  - In ProgressiveMaskDetector buffers: {track_id in self.progressive_detector.track_buffers}")
            