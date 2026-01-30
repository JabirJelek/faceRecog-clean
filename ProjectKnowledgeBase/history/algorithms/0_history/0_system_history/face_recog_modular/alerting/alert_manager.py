# alerting/alert_manager.py

# alerting/alert_manager.py

import threading
import requests
from urllib.parse import quote
from typing import Dict, List, Optional, Tuple
import time
import numpy as np

class DurationAwareAlertManager:
    def __init__(self, config: Dict):
        self.config = config
        self.server_url = config.get('alert_server_url')
        self.cooldown_seconds = config.get('alert_cooldown_seconds', 30)
        self.enabled = config.get('enable_voice_alerts', True)
        self.last_alert_time = 0
        self.alert_lock = threading.Lock()
        
        # 🆕 Duration tracking parameters
        self.min_violation_frames = config.get('min_violation_frames', 20)  # 2 seconds at 10 FPS
        self.min_violation_seconds = config.get('min_violation_seconds', 2.0)
        self.max_gap_frames = config.get('max_gap_frames', 5)  # Allow 5-frame gaps
        
        # 🆕 Violation duration tracking per identity
        self.violation_timers = {}  # identity -> {'start_time': timestamp, 'frame_count': int, 'start_frame': int, 'continuous': bool}
        self.alerted_identities = set()  # Track identities we've already alerted for
        
        # 🆕 NEW: Image logging synchronization
        self.image_log_interval = config.get('image_log_interval', 5)
        self.last_image_log_time = 0
        self.min_save_interval = config.get('min_save_interval', 2.0)
        
        print(f"🔊 Duration-aware alerts: {self.min_violation_frames} frames / {self.min_violation_seconds}s threshold")

    def update_violation_duration(self, violations: List[Dict], current_frame_count: int):
        """Update violation duration tracking for each identity"""
        current_time = time.time()
        current_violators = set()
        
        for violation in violations:
            identity = violation.get('identity', 'Unknown')
            current_violators.add(identity)
            
            # Start or update timer for this identity
            if identity not in self.violation_timers:
                self.violation_timers[identity] = {
                    'start_time': current_time,
                    'start_frame': current_frame_count,
                    'frame_count': 1,
                    'continuous': True,
                    'last_frame': current_frame_count
                }
            else:
                # Update existing timer
                timer = self.violation_timers[identity]
                
                # Check for continuity
                frame_gap = current_frame_count - timer['last_frame']
                if frame_gap <= self.max_gap_frames + 1:  # Allow small gaps
                    timer['frame_count'] += 1
                    timer['continuous'] = True
                else:
                    # Large gap detected - reset but keep identity
                    timer['start_time'] = current_time
                    timer['start_frame'] = current_frame_count
                    timer['frame_count'] = 1
                    timer['continuous'] = True
                    # Remove from alerted set since it's a new violation period
                    if identity in self.alerted_identities:
                        self.alerted_identities.remove(identity)
                
                timer['last_frame'] = current_frame_count
        
        # Remove identities that are no longer violating
        expired_identities = []
        for identity, timer in self.violation_timers.items():
            if identity not in current_violators:
                # Check if we should keep tracking for small gaps
                frame_gap = current_frame_count - timer['last_frame']
                if frame_gap > self.max_gap_frames:
                    expired_identities.append(identity)
                # else: keep in timers for gap tolerance
        
        for identity in expired_identities:
            self._reset_violation_timer(identity)
            
    def update_config(self, config: Dict):
        """Update alert manager configuration from main pipeline"""
        try:
            # Basic alert settings
            if 'enable_voice_alerts' in config:
                self.enabled = config['enable_voice_alerts']
                
            if 'alert_server_url' in config:
                self.server_url = config['alert_server_url']
                
            if 'alert_cooldown_seconds' in config:
                self.cooldown_seconds = config['alert_cooldown_seconds']
            
            # Duration tracking parameters
            if 'min_violation_frames' in config:
                self.min_violation_frames = config['min_violation_frames']
                
            if 'min_violation_seconds' in config:
                self.min_violation_seconds = config['min_violation_seconds']
                
            if 'max_gap_frames' in config:
                self.max_gap_frames = config['max_gap_frames']
                
            # 🆕 NEW: Image logging synchronization parameters
            if 'image_log_interval' in config:
                self.image_log_interval = config['image_log_interval']
                
            if 'min_save_interval' in config:
                self.min_save_interval = config['min_save_interval']
                
            # Alert content configuration
            self.alert_language = config.get('alert_language', 'id')
            self.alert_style = config.get('alert_style', 'formal')
            self.enable_individual_alerts = config.get('enable_individual_alerts', True)
            self.enable_group_alerts = config.get('enable_group_alerts', True)
            self.alert_timeout_seconds = config.get('alert_timeout_seconds', 10)
            
            print(f"🔊 Alert config updated: {self.enabled}, Cooldown: {self.cooldown_seconds}s")
            print(f"   Duration: {self.min_violation_frames}frames/{self.min_violation_seconds}s")
            print(f"   Image sync: interval={self.image_log_interval}, min_save={self.min_save_interval}s")
            
        except Exception as e:
            print(f"❌ Error updating alert config: {e}")

    def get_alert_config(self) -> Dict:
        """Get current alert configuration"""
        return {
            'enabled': self.enabled,
            'server_url': self.server_url,
            'cooldown_seconds': self.cooldown_seconds,
            'min_violation_frames': self.min_violation_frames,
            'min_violation_seconds': self.min_violation_seconds,
            'max_gap_frames': self.max_gap_frames,
            'alert_language': getattr(self, 'alert_language', 'id'),
            'alert_style': getattr(self, 'alert_style', 'formal'),
            'enable_individual_alerts': getattr(self, 'enable_individual_alerts', True),
            'enable_group_alerts': getattr(self, 'enable_group_alerts', True),
            'alert_timeout_seconds': getattr(self, 'alert_timeout_seconds', 10),
            'tracked_identities_count': len(self.violation_timers),
            'alerted_identities_count': len(self.alerted_identities),
            # 🆕 NEW: Image logging sync info
            'image_log_interval': self.image_log_interval,
            'min_save_interval': self.min_save_interval,
            'last_image_log_time': self.last_image_log_time
        }            

    def _reset_violation_timer(self, identity: str):
        """Reset violation timer for an identity"""
        if identity in self.violation_timers:
            del self.violation_timers[identity]
        if identity in self.alerted_identities:
            self.alerted_identities.remove(identity)

    def should_trigger_alert(self, identity: str) -> bool:
        """Check if violation duration meets threshold for alert"""
        if identity not in self.violation_timers:
            return False
            
        timer = self.violation_timers[identity]
        
        # Check frame count threshold
        frame_condition = timer['frame_count'] >= self.min_violation_frames
        
        # Check time duration threshold  
        time_condition = (time.time() - timer['start_time']) >= self.min_violation_seconds
        
        # Check if violation is continuous
        continuous_condition = timer.get('continuous', True)
        
        # Check if we haven't already alerted for this identity in current violation
        not_already_alerted = identity not in self.alerted_identities
        
        return frame_condition and time_condition and continuous_condition and not_already_alerted

    def get_violation_duration_info(self, identity: str) -> Dict[str, float]:
        """Get duration information for an identity"""
        if identity not in self.violation_timers:
            return {'frames': 0, 'seconds': 0.0}
        
        timer = self.violation_timers[identity]
        return {
            'frames': timer['frame_count'],
            'seconds': time.time() - timer['start_time']
        }

    def trigger_duration_alert(self, violations: List[Dict], current_frame_count: int) -> bool:
        """Main method to check and trigger duration-based alerts"""
        if not self.enabled or not self.server_url:
            return False
        
        # Update violation duration tracking
        self.update_violation_duration(violations, current_frame_count)
        
        # Find identities that meet duration threshold
        alert_identities = []
        for violation in violations:
            identity = violation.get('identity', 'Unknown')
            if self.should_trigger_alert(identity):
                alert_identities.append(identity)
        
        if not alert_identities:
            return False
        
        # Generate and send alert
        success = self._send_violation_alert(alert_identities, violations)
        
        # Mark these identities as alerted
        if success:
            for identity in alert_identities:
                self.alerted_identities.add(identity)
                duration_info = self.get_violation_duration_info(identity)
                print(f"🚨 Duration alert triggered for {identity} "
                      f"({duration_info['frames']} frames, {duration_info['seconds']:.1f}s)")
        
        return success

    def _send_violation_alert(self, alert_identities: List[str], all_violations: List[Dict]) -> bool:
        """Send voice alert for violations that meet duration threshold with configurable messages"""
        # Filter violations to only those that triggered alerts
        alert_violations = [v for v in all_violations if v.get('identity') in alert_identities]
        
        if not alert_violations:
            return False
            
        # Generate message based on configuration
        message = self._generate_alert_message(alert_violations, alert_identities)
        
        # Send the alert
        return self.send_voice_alert(message)

    def _generate_alert_message(self, alert_violations: List[Dict], alert_identities: List[str]) -> str:
        """Generate alert message in Indonesian with flexible mixing of recognized and unknown violators"""
        current_time = time.time()
        
        # Track violators within time window and remove duplicates
        unique_violations = []
        seen_identities = set()
        
        for violation in alert_violations:
            identity = violation.get('identity', 'Unknown')
            
            # Only add each identity once
            if identity not in seen_identities:
                seen_identities.add(identity)
                unique_violations.append(violation)
        
        # Count recognized vs unknown violators from unique set
        recognized = [v for v in unique_violations if v['identity'] and v['identity'] != 'Unknown']
        unknown = [v for v in unique_violations if not v['identity'] or v['identity'] == 'Unknown']
        
        style = getattr(self, 'alert_style', 'formal')
        
        # Configuration for maximum names to list
        max_names_to_list = getattr(self, 'max_names_in_alert', 4)  # Default: list up to 4 names
        
        # Helper function to format Indonesian name lists
        def format_name_list_indonesian(names):
            """Format list of names in Indonesian"""
            if len(names) == 1:
                return names[0]
            elif len(names) <= max_names_to_list:
                return ", ".join(names[:-1]) + " dan " + names[-1]
            else:
                return f"{len(names)} orang dikenal"
        
        # Get counts for flexible message generation
        recognized_count = len(recognized)
        unknown_count = len(unknown)
        total_count = recognized_count + unknown_count
        
        # Extract recognized names
        recognized_names = [v['identity'] for v in recognized]
        
        # FLEXIBLE MESSAGE GENERATION: Handle all combinations in single output
        
        # Case 1: Only one person total (either recognized or unknown)
        if total_count == 1:
            if recognized_count == 1:
                name = recognized_names[0]
                if style == 'formal':
                    message = f"Perhatian, {name} terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:  # informal
                    message = f"{name} tolong pakai masker, terima kasih."
            else:  # one unknown person
                if style == 'formal':
                    message = "Perhatian, satu orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:  # informal
                    message = "Satu orang tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 2: Mixed - both recognized and unknown people (FLEXIBLE COMBINATION)
        elif recognized_count > 0 and unknown_count > 0:
            name_string = format_name_list_indonesian(recognized_names)
            
            if style == 'formal':
                if unknown_count == 1:
                    message = f"Perhatian, {name_string} dan satu orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    message = f"Perhatian, {name_string} dan {unknown_count} orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
            else:  # informal
                if unknown_count == 1:
                    message = f"{name_string} dan satu orang tidak dikenal tolong pakai masker, terima kasih."
                else:
                    message = f"{name_string} dan {unknown_count} orang tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 3: Only recognized people (multiple)
        elif recognized_count > 0:
            name_string = format_name_list_indonesian(recognized_names)
            if style == 'formal':
                message = f"Perhatian, {name_string} terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
            else:  # informal
                message = f"{name_string} tolong pakai masker, terima kasih."
        
        # Case 4: Only unknown people (multiple)
        elif unknown_count > 0:
            if style == 'formal':
                if unknown_count == 1:
                    message = "Perhatian, satu orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    message = f"Perhatian, {unknown_count} orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
            else:  # informal
                if unknown_count == 1:
                    message = "Satu orang tidak dikenal tolong pakai masker, terima kasih."
                else:
                    message = f"{unknown_count} orang tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 5: Fallback for any other scenario (should not normally happen)
        else:
            if style == 'formal':
                message = "Perhatian, terdeteksi pelanggaran masker."
            else:
                message = "Tolong pakai masker."
        
        # Add configuration option to the class if not exists
        if not hasattr(self, 'max_names_in_alert'):
            self.max_names_in_alert = max_names_to_list
        
        # Debug information about unique violators
        debug_info = f" [Unique: {len(unique_violations)} violators: {list(seen_identities)}]"
        if getattr(self, 'debug_mode', False):
            message += debug_info
            print(f"🔊 Alert generated: {len(unique_violations)} unique violators ({recognized_count} known, {unknown_count} unknown) from {len(alert_violations)} total violations")
        
        return message

    # Synchronized alert with image logging
    def trigger_synchronized_alert(self, violations: List[Dict], processing_count: int, saved_image_count: int, max_images: int) -> bool:
        """
        Trigger audio alert synchronized with image logging conditions
        
        Args:
            violations: List of current violations
            processing_count: Current processing frame count
            saved_image_count: Number of images already saved
            max_images: Maximum images allowed per session
            
        Returns:
            bool: True if alert was sent
        """
        if not self.enabled or not self.server_url:
            return False
            
        # Check if we have violations
        if not violations:
            return False
            
        # 🆕 Apply the same conditions as image logging
        current_time = time.time()
        
        # Check image log interval (same as image logger)
        if processing_count % self.image_log_interval != 0:
            return False
            
        # Check maximum images limit (same as image logger)
        if saved_image_count >= max_images:
            return False
            
        # Check minimum time between saves (same as image logger)
        if current_time - self.last_image_log_time < self.min_save_interval:
            return False
            
        # Check rate limiting for audio alerts
        if current_time - self.last_alert_time < self.cooldown_seconds:
            return False
        
        # Generate and send alert for all current violations
        message = self._generate_alert_message(violations, [v.get('identity', 'Unknown') for v in violations])
        success = self.send_voice_alert(message)
        
        if success:
            self.last_image_log_time = current_time
            print(f"🔊 Synchronized audio alert sent with image logging: {message}")
            
            # Mark identities as alerted to avoid duplicate alerts
            for violation in violations:
                identity = violation.get('identity', 'Unknown')
                self.alerted_identities.add(identity)
        
        return success

    def send_voice_alert(self, message: str, identity: str = None, mask_status: str = None) -> bool:
        """Send voice alert to server in non-blocking thread (original method preserved)"""
        if not self.enabled or not self.server_url:
            return False
            
        # Rate limiting
        current_time = time.time()
        with self.alert_lock:
            if current_time - self.last_alert_time < self.cooldown_seconds:
                return False
            self.last_alert_time = current_time
        
        # Run in background thread to avoid blocking main processing
        thread = threading.Thread(
            target=self._send_alert_thread,
            args=(message, identity, mask_status),
            daemon=True
        )
        thread.start()
        return True

    def _send_alert_thread(self, message: str, identity: str, mask_status: str):
        """Background thread for sending alerts with configurable timeout"""
        try:
            # URL encode the message
            encoded_message = quote(message)
            alert_url = f"{self.server_url}?pesan={encoded_message}"
            
            # Use configurable timeout
            timeout = getattr(self, 'alert_timeout_seconds', 10)
            
            # Send HTTP request with configurable timeout
            response = requests.get(alert_url, timeout=timeout)
            
            if response.status_code == 200:
                print(f"🔊 Voice alert sent: {message}")
            else:
                print(f"❌ Alert server returned status: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"⏰ Alert request timed out after {timeout} seconds")
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send voice alert: {e}")
        except Exception as e:
            print(f"❌ Unexpected error in alert thread: {e}")
            
    def toggle_alerts(self):
        """Toggle voice alerts on/off"""
        self.enabled = not self.enabled
        status = "ENABLED" if self.enabled else "DISABLED"
        print(f"🔊 Voice alerts: {status}")
        return self.enabled

    def get_duration_stats(self) -> Dict:
        """Get current duration tracking statistics"""
        stats = {
            'total_tracked_identities': len(self.violation_timers),
            'alerted_identities': list(self.alerted_identities),
            'violation_timers': {}
        }
        
        for identity, timer in self.violation_timers.items():
            stats['violation_timers'][identity] = {
                'frame_count': timer['frame_count'],
                'duration_seconds': time.time() - timer['start_time'],
                'continuous': timer.get('continuous', True)
            }
        
        return stats
class ByteTrackAlertManager(DurationAwareAlertManager):
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # ByteTrack configuration
        self.enable_bytetrack = config.get('enable_bytetrack', False)
        self.tracker = None
        self.track_id_mapping = {}  # track_id -> identity mapping cache
        self.track_history = {}  # track_id -> history for re-identification
        
        # Initialize ByteTrack if enabled
        if self.enable_bytetrack:
            self._initialize_bytetrack(config)
        
        print(f"🔍 ByteTrack tracking: {'ENABLED' if self.enable_bytetrack else 'DISABLED'}")

    def _initialize_bytetrack(self, config: Dict):
        """Initialize ByteTrack tracker with configuration"""
        try:
            # Import ByteTrack - will use your existing tracking module if available
            from tracking.bytetrack_wrapper import ByteTrackWrapper
            tracker_config = {
                'track_thresh': config.get('bytetrack_track_thresh', 0.5),
                'track_buffer': config.get('bytetrack_track_buffer', 30),
                'match_thresh': config.get('bytetrack_match_thresh', 0.8),
                'frame_rate': config.get('fps', 10),
                'min_box_area': config.get('bytetrack_min_box_area', 10)
            }
            self.tracker = ByteTrackWrapper(tracker_config)
            print("🎯 ByteTrack initialized successfully")
            
        except ImportError as e:
            print(f"❌ ByteTrack import failed: {e}. Using fallback tracking.")
            self.enable_bytetrack = False
        except Exception as e:
            print(f"❌ ByteTrack initialization failed: {e}")
            self.enable_bytetrack = False

    def process_frame_with_tracking(self, 
                                  detections: List[Dict], 
                                  frame_count: int,
                                  recognized_faces: Optional[List[Dict]] = None,
                                  frame: Optional[np.ndarray] = None) -> List[Dict]:
        """
        Process detections with ByteTrack integration
        
        Args:
            detections: List of detection dictionaries from YOLO
            frame_count: Current frame number for timing
            recognized_faces: List of recognized faces with identities
            frame: Optional frame for visual tracking features
            
        Returns:
            List of violation dictionaries with tracking IDs
        """
        if self.enable_bytetrack and self.tracker is not None:
            return self._process_with_bytetrack(detections, frame_count, recognized_faces, frame)
        else:
            return self._process_with_basic_tracking(detections, frame_count, recognized_faces)

    def _process_with_bytetrack(self, 
                              detections: List[Dict], 
                              frame_count: int,
                              recognized_faces: Optional[List[Dict]] = None,
                              frame: Optional[np.ndarray] = None) -> List[Dict]:
        """Process frame using ByteTrack for persistent tracking"""
        try:
            # Convert detections to ByteTrack format
            track_detections = self._prepare_detections_for_bytetrack(detections)
            
            # Update tracker
            tracks = self.tracker.update(track_detections, frame)
            
            # Convert tracks to violations with stable IDs
            violations = self._tracks_to_violations(tracks, recognized_faces, frame_count)
            
            # Update track-identity mapping
            self._update_identity_mapping(violations, recognized_faces)
            
            return violations
            
        except Exception as e:
            print(f"❌ ByteTrack processing failed, using fallback: {e}")
            return self._process_with_basic_tracking(detections, frame_count, recognized_faces)

    def _prepare_detections_for_bytetrack(self, detections: List[Dict]) -> np.ndarray:
        """Convert detection dictionary to ByteTrack format"""
        if not detections:
            return np.empty((0, 6))
        
        bytetrack_detections = []
        for det in detections:
            bbox = det.get('bbox', [])
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[:4]
                conf = det.get('confidence', 0.5)
                class_id = 0  # Assuming person class
                
                # Format: [x1, y1, x2, y2, confidence, class]
                bytetrack_detections.append([x1, y1, x2, y2, conf, class_id])
        
        return np.array(bytetrack_detections) if bytetrack_detections else np.empty((0, 6))

    def _tracks_to_violations(self, 
                            tracks: List, 
                            recognized_faces: Optional[List[Dict]] = None,
                            frame_count: int = 0) -> List[Dict]:
        """Convert ByteTrack outputs to violation format"""
        violations = []
        
        for track in tracks:
            track_id = int(getattr(track, 'track_id', 0))
            bbox = getattr(track, 'tlbr', [0, 0, 0, 0])  # [x1, y1, x2, y2]
            confidence = getattr(track, 'score', 0.5)
            
            # Get identity from mapping or face recognition
            identity = self._get_identity_for_track(track_id, bbox, recognized_faces)
            
            violation = {
                'bbox': bbox.tolist() if hasattr(bbox, 'tolist') else bbox,
                'track_id': track_id,
                'identity': identity,
                'confidence': confidence,
                'mask_status': 'no_mask',  # Assuming all detections are violations
                'frame_count': frame_count,
                'tracking_method': 'bytetrack'
            }
            violations.append(violation)
            
        return violations

    def _get_identity_for_track(self, 
                              track_id: int, 
                              bbox: List[float],
                              recognized_faces: Optional[List[Dict]] = None) -> str:
        """Get identity for a track using mapping cache and face recognition"""
        
        # Check if we have a cached identity for this track
        if track_id in self.track_id_mapping:
            cached_identity = self.track_id_mapping[track_id]
            if cached_identity != 'Unknown':
                return cached_identity
        
        # Try to match with recognized faces using IoU
        if recognized_faces:
            matched_identity = self._match_track_with_faces(track_id, bbox, recognized_faces)
            if matched_identity and matched_identity != 'Unknown':
                self.track_id_mapping[track_id] = matched_identity
                return matched_identity
        
        # Return unknown with track ID for unique tracking
        return 'Unknown'

    def _match_track_with_faces(self, 
                              track_id: int, 
                              track_bbox: List[float],
                              recognized_faces: List[Dict]) -> Optional[str]:
        """Match track with recognized faces using spatial overlap"""
        best_iou = 0.0
        best_identity = 'Unknown'
        
        for face in recognized_faces:
            face_bbox = face.get('bbox', [])
            if len(face_bbox) >= 4:
                iou = self._calculate_iou(track_bbox, face_bbox)
                if iou > best_iou and iou > 0.3:  # Minimum IoU threshold
                    best_iou = iou
                    best_identity = face.get('identity', 'Unknown')
        
        return best_identity if best_iou > 0.3 else 'Unknown'

    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        """Calculate Intersection over Union for two bounding boxes"""
        x11, y1, x2, y2 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection area
        xi1 = max(x1_2, x1_2)
        yi1 = max(y1_2, y1_2)
        xi2 = min(x2_2, x2_2)
        yi2 = min(y2_2, y2_2)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        # Calculate union area
        box1_area = (x2 - x1_2) * (y2 - y1_2)
        box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0

    def _update_identity_mapping(self, 
                               violations: List[Dict], 
                               recognized_faces: Optional[List[Dict]] = None):
        """Update the track ID to identity mapping cache"""
        for violation in violations:
            track_id = violation.get('track_id')
            identity = violation.get('identity', 'Unknown')
            
            if track_id and identity != 'Unknown':
                self.track_id_mapping[track_id] = identity
                
                # Update track history
                if track_id not in self.track_history:
                    self.track_history[track_id] = {
                        'first_seen': time.time(),
                        'identity_updates': 0,
                        'last_identity': identity
                    }
                else:
                    self.track_history[track_id]['identity_updates'] += 1
                    self.track_history[track_id]['last_identity'] = identity

    def _process_with_basic_tracking(self, 
                                   detections: List[Dict], 
                                   frame_count: int,
                                   recognized_faces: Optional[List[Dict]] = None) -> List[Dict]:
        """Fallback method using basic tracking (your existing logic)"""
        violations = []
        
        for i, detection in enumerate(detections):
            bbox = detection.get('bbox', [])
            confidence = detection.get('confidence', 0.5)
            
            # Basic identity assignment (your existing logic)
            identity = self._assign_identity_basic(i, bbox, recognized_faces)
            
            violation = {
                'bbox': bbox,
                'track_id': None,  # No persistent tracking
                'identity': identity,
                'confidence': confidence,
                'mask_status': 'no_mask',
                'frame_count': frame_count,
                'tracking_method': 'basic'
            }
            violations.append(violation)
            
        return violations

    def _assign_identity_basic(self, 
                             detection_idx: int, 
                             bbox: List[float],
                             recognized_faces: Optional[List[Dict]] = None) -> str:
        """Basic identity assignment without ByteTrack"""
        if recognized_faces:
            # Simple spatial matching (your existing logic)
            for face in recognized_faces:
                face_bbox = face.get('bbox', [])
                if len(face_bbox) >= 4 and len(bbox) >= 4:
                    # Simple center distance check
                    det_center = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
                    face_center = [(face_bbox[0] + face_bbox[2]) / 2, (face_bbox[1] + face_bbox[3]) / 2]
                    
                    distance = ((det_center[0] - face_center[0]) ** 2 + 
                               (det_center[1] - face_center[1]) ** 2) ** 0.5
                    
                    if distance < 50:  # Distance threshold
                        return face.get('identity', 'Unknown')
        
        return 'Unknown'

    def update_violation_duration(self, violations: List[Dict], current_frame_count: int):
        """Enhanced violation duration tracking with ByteTrack support"""
        current_time = time.time()
        current_violators = set()
        
        for violation in violations:
            # Use track_id if available (ByteTrack), otherwise fallback
            track_id = violation.get('track_id')
            identity = violation.get('identity', 'Unknown')
            
            # Create stable tracking identity
            if track_id is not None:
                tracking_identity = f"track_{track_id}"
            elif identity == 'Unknown':
                # Fallback to bbox-based for non-ByteTrack mode
                bbox = violation.get('bbox', [0, 0, 0, 0])
                tracking_identity = f"Unknown_{int(bbox[0])}_{int(bbox[1])}"
            else:
                tracking_identity = identity
            
            # Store tracking ID for later use
            violation['tracking_id'] = tracking_identity
            current_violators.add(tracking_identity)
            
            # Start or update timer for this identity
            if tracking_identity not in self.violation_timers:
                self.violation_timers[tracking_identity] = {
                    'start_time': current_time,
                    'start_frame': current_frame_count,
                    'frame_count': 1,
                    'continuous': True,
                    'last_frame': current_frame_count,
                    'original_identity': identity,
                    'track_id': track_id
                }
            else:
                # Update existing timer
                timer = self.violation_timers[tracking_identity]
                
                # Check for continuity - more lenient with ByteTrack
                frame_gap = current_frame_count - timer['last_frame']
                max_gap = self.max_gap_frames * 2 if track_id is not None else self.max_gap_frames
                
                if frame_gap <= max_gap + 1:
                    timer['frame_count'] += 1
                    timer['continuous'] = True
                else:
                    # Large gap detected - reset
                    timer['start_time'] = current_time
                    timer['start_frame'] = current_frame_count
                    timer['frame_count'] = 1
                    timer['continuous'] = True
                    # Remove from alerted set
                    if tracking_identity in self.alerted_identities:
                        self.alerted_identities.remove(tracking_identity)
                
                timer['last_frame'] = current_frame_count
        
        # Remove expired identities
        expired_identities = []
        for identity, timer in self.violation_timers.items():
            if identity not in current_violators:
                frame_gap = current_frame_count - timer['last_frame']
                max_gap = self.max_gap_frames * 3 if timer.get('track_id') else self.max_gap_frames
                
                if frame_gap > max_gap:
                    expired_identities.append(identity)
        
        for identity in expired_identities:
            self._reset_violation_timer(identity)
            
            # Clean up track mapping if this was a ByteTrack identity
            if identity.startswith('track_'):
                track_id = int(identity.split('_')[1])
                if track_id in self.track_id_mapping:
                    del self.track_id_mapping[track_id]
                if track_id in self.track_history:
                    del self.track_history[track_id]

    def update_config(self, config: Dict):
        """Update configuration with ByteTrack support"""
        super().update_config(config)
        
        # Update ByteTrack settings
        if 'enable_bytetrack' in config:
            new_bytetrack_setting = config['enable_bytetrack']
            if new_bytetrack_setting != self.enable_bytetrack:
                self.enable_bytetrack = new_bytetrack_setting
                if self.enable_bytetrack and self.tracker is None:
                    self._initialize_bytetrack(config)
        
        # Update ByteTrack parameters
        if self.tracker is not None:
            tracker_params = {}
            if 'bytetrack_track_thresh' in config:
                tracker_params['track_thresh'] = config['bytetrack_track_thresh']
            if 'bytetrack_track_buffer' in config:
                tracker_params['track_buffer'] = config['bytetrack_track_buffer']
            if 'bytetrack_match_thresh' in config:
                tracker_params['match_thresh'] = config['bytetrack_match_thresh']
            
            if tracker_params:
                self.tracker.update_params(tracker_params)

    def get_tracking_stats(self) -> Dict:
        """Get ByteTrack tracking statistics"""
        stats = super().get_duration_stats()
        
        stats.update({
            'bytetrack_enabled': self.enable_bytetrack,
            'track_id_mapping_size': len(self.track_id_mapping),
            'track_history_size': len(self.track_history),
            'active_tracks': len([t for t in self.violation_timers.values() if t.get('track_id')]),
            'tracker_initialized': self.tracker is not None
        })
        
        return stats

    def cleanup(self):
        """Clean up tracker resources"""
        if self.tracker is not None:
            if hasattr(self.tracker, 'cleanup'):
                self.tracker.cleanup()
            self.tracker = None
        
        self.track_id_mapping.clear()
        self.track_history.clear()

# Backward compatibility - alias for existing code
DurationAwareAlertManager = ByteTrackAlertManager

   
    