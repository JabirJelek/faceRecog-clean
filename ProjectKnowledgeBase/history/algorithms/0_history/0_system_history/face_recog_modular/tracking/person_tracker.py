# tracking/person_tracker.py

import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from .bytetrack_wrapper import ByteTrackWrapper
from datetime import time

class PersonTracker:
    """
    Person-level tracking using ByteTrack for persistent tracking of individuals
    across frames, complementing the existing face tracking system.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('enable_person_tracking', True)
        
        # ByteTrack instance for person tracking
        self.byte_tracker = None
        if self.enabled:
            self._initialize_bytetrack(config)
        
        # Track identity mapping and history
        self.track_id_mapping = {}  # track_id -> identity
        self.track_history = {}     # track_id -> tracking history
        self.next_track_id = 0
        
        # Configuration
        self.min_confidence = config.get('person_track_confidence', 0.5)
        self.max_age_frames = config.get('person_track_max_age', 90)  # 3 seconds at 30 FPS
        self.iou_threshold = config.get('person_iou_threshold', 0.3)
        
        print(f"👤 Person tracking: {'ENABLED' if self.enabled else 'DISABLED'}")

    def _initialize_bytetrack(self, config: Dict):
        """Initialize ByteTrack with configuration"""
        try:
            tracker_config = {
                'track_thresh': config.get('bytetrack_track_thresh', 0.5),
                'track_buffer': config.get('bytetrack_track_buffer', 30),
                'match_thresh': config.get('bytetrack_match_thresh', 0.8),
                'frame_rate': config.get('fps', 10),
                'min_box_area': config.get('bytetrack_min_box_area', 10)
            }
            self.byte_tracker = ByteTrackWrapper(tracker_config)
            print("🎯 ByteTrack initialized for person tracking")
        except Exception as e:
            print(f"❌ ByteTrack initialization failed: {e}")
            self.enabled = False

    def update(self, 
               person_detections: List[Dict], 
               recognized_faces: List[Dict],
               frame_count: int,
               frame: Optional[np.ndarray] = None) -> List[Dict]:
        """
        Update person tracking with new detections and face recognition results
        
        Args:
            person_detections: YOLO person detections with bboxes and confidences
            recognized_faces: Face recognition results with identities
            frame_count: Current frame number
            frame: Optional frame for visual features
            
        Returns:
            List of tracked persons with persistent IDs and identities
        """
        if not self.enabled or not self.byte_tracker:
            return self._fallback_tracking(person_detections, recognized_faces, frame_count)
        
        try:
            # Convert detections to ByteTrack format
            track_detections = self._prepare_detections(person_detections)
            
            # Update ByteTrack
            tracks = self.byte_tracker.update(track_detections, frame)
            
            # Convert tracks to person results
            tracked_persons = self._tracks_to_persons(tracks, person_detections, frame_count)
            
            # Associate with face recognition results
            tracked_persons = self._associate_faces(tracked_persons, recognized_faces)
            
            # Update identity mapping and history
            self._update_tracking_data(tracked_persons, frame_count)
            
            # Clean up old tracks
            self._cleanup_old_tracks(frame_count)
            
            return tracked_persons
            
        except Exception as e:
            print(f"❌ Person tracking error, using fallback: {e}")
            return self._fallback_tracking(person_detections, recognized_faces, frame_count)

    def _prepare_detections(self, person_detections: List[Dict]) -> np.ndarray:
        """Convert person detections to ByteTrack format"""
        if not person_detections:
            return np.empty((0, 6))
        
        bytetrack_detections = []
        for det in person_detections:
            bbox = det.get('bbox', [])
            confidence = det.get('confidence', 0.5)
            
            if len(bbox) >= 4 and confidence >= self.min_confidence:
                x1, y1, x2, y2 = bbox[:4]
                class_id = 0  # Person class
                bytetrack_detections.append([x1, y1, x2, y2, confidence, class_id])
        
        return np.array(bytetrack_detections) if bytetrack_detections else np.empty((0, 6))

    def _tracks_to_persons(self, 
                          tracks: List, 
                          original_detections: List[Dict],
                          frame_count: int) -> List[Dict]:
        """Convert ByteTrack outputs to person dictionary format"""
        tracked_persons = []
        
        for track in tracks:
            track_id = int(getattr(track, 'track_id', 0))
            track_bbox = getattr(track, 'tlbr', [0, 0, 0, 0])
            confidence = getattr(track, 'score', 0.5)
            
            # Find best matching original detection for additional data
            matched_detection = self._find_matching_detection(track_bbox, original_detections)
            
            person_data = {
                'bbox': track_bbox.tolist() if hasattr(track_bbox, 'tolist') else track_bbox,
                'track_id': track_id,
                'confidence': confidence,
                'frame_count': frame_count,
                'tracking_method': 'bytetrack',
                'mask_status': matched_detection.get('mask_status', 'unknown') if matched_detection else 'unknown',
                'identity': 'Unknown',  # Will be updated by face association
                'recognition_confidence': 0.0
            }
            
            # Copy additional fields from matched detection
            if matched_detection:
                for key in ['class_name', 'detection_time', 'image_region']:
                    if key in matched_detection:
                        person_data[key] = matched_detection[key]
            
            tracked_persons.append(person_data)
            
        return tracked_persons

    def _find_matching_detection(self, 
                               track_bbox: List[float], 
                               detections: List[Dict]) -> Optional[Dict]:
        """Find the original detection that matches this track"""
        best_iou = 0.0
        best_detection = None
        
        for det in detections:
            det_bbox = det.get('bbox', [])
            if len(det_bbox) >= 4:
                iou = self._calculate_iou(track_bbox, det_bbox)
                if iou > best_iou and iou > self.iou_threshold:
                    best_iou = iou
                    best_detection = det
        
        return best_detection

    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        """Calculate Intersection over Union for two bounding boxes"""
        if len(box1) < 4 or len(box2) < 4:
            return 0.0
            
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection area
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        # Calculate union area
        box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
        box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0

    def _associate_faces(self, 
                        tracked_persons: List[Dict], 
                        recognized_faces: List[Dict]) -> List[Dict]:
        """Associate face recognition results with tracked persons"""
        if not recognized_faces:
            return tracked_persons
        
        for person in tracked_persons:
            person_bbox = person['bbox']
            best_face = None
            best_iou = 0.0
            
            # Find the best matching face within this person's bounding box
            for face in recognized_faces:
                face_bbox = face.get('bbox', [])
                if len(face_bbox) >= 4:
                    # Check if face is within person bounding box
                    if self._is_inside(face_bbox, person_bbox):
                        iou = self._calculate_iou(face_bbox, person_bbox)
                        if iou > best_iou:
                            best_iou = iou
                            best_face = face
            
            # Update person identity if we found a matching face
            if best_face and best_iou > 0.1:  # Lower threshold for containment
                person['identity'] = best_face.get('identity', 'Unknown')
                person['recognition_confidence'] = best_face.get('recognition_confidence', 0.0)
                person['face_bbox'] = best_face['bbox']
        
        return tracked_persons

    def _is_inside(self, inner_box: List[float], outer_box: List[float]) -> bool:
        """Check if inner_box is completely inside outer_box"""
        if len(inner_box) < 4 or len(outer_box) < 4:
            return False
            
        x1_i, y1_i, x2_i, y2_i = inner_box
        x1_o, y1_o, x2_o, y2_o = outer_box
        
        return (x1_i >= x1_o and y1_i >= y1_o and 
                x2_i <= x2_o and y2_i <= y2_o)

    def _update_tracking_data(self, tracked_persons: List[Dict], frame_count: int):
        """Update track identity mapping and history"""
        current_time = time.time()
        
        for person in tracked_persons:
            track_id = person['track_id']
            identity = person['identity']
            
            # Update identity mapping for recognized persons
            if identity != 'Unknown':
                self.track_id_mapping[track_id] = identity
            
            # Update track history
            if track_id not in self.track_history:
                self.track_history[track_id] = {
                    'first_seen': current_time,
                    'first_frame': frame_count,
                    'last_seen': current_time,
                    'last_frame': frame_count,
                    'identity_updates': 0,
                    'consistent_identity': identity,
                    'identity_changes': 0
                }
            else:
                history = self.track_history[track_id]
                history['last_seen'] = current_time
                history['last_frame'] = frame_count
                
                # Track identity consistency
                if identity != 'Unknown' and identity != history['consistent_identity']:
                    history['identity_changes'] += 1
                    # Only update consistent identity if we see it multiple times
                    if history['identity_changes'] < 3:
                        history['consistent_identity'] = identity
                        history['identity_updates'] += 1

    def _cleanup_old_tracks(self, frame_count: int):
        """Remove tracks that haven't been seen recently"""
        current_time = time.time()
        expired_tracks = []
        
        for track_id, history in self.track_history.items():
            frame_age = frame_count - history['last_frame']
            time_age = current_time - history['last_seen']
            
            if frame_age > self.max_age_frames:
                expired_tracks.append(track_id)
        
        for track_id in expired_tracks:
            if track_id in self.track_history:
                del self.track_history[track_id]
            if track_id in self.track_id_mapping:
                del self.track_id_mapping[track_id]

    def _fallback_tracking(self, 
                          person_detections: List[Dict], 
                          recognized_faces: List[Dict],
                          frame_count: int) -> List[Dict]:
        """Fallback tracking when ByteTrack is disabled or fails"""
        tracked_persons = []
        
        for i, detection in enumerate(person_detections):
            if detection.get('confidence', 0) >= self.min_confidence:
                person_data = detection.copy()
                person_data['track_id'] = self.next_track_id
                person_data['frame_count'] = frame_count
                person_data['tracking_method'] = 'fallback'
                person_data['identity'] = 'Unknown'
                
                # Try to associate with faces using simple spatial matching
                person_bbox = person_data['bbox']
                for face in recognized_faces:
                    face_bbox = face.get('bbox', [])
                    if len(face_bbox) >= 4 and self._is_inside(face_bbox, person_bbox):
                        person_data['identity'] = face.get('identity', 'Unknown')
                        person_data['recognition_confidence'] = face.get('recognition_confidence', 0.0)
                        break
                
                tracked_persons.append(person_data)
                self.next_track_id += 1
        
        return tracked_persons

    def get_tracking_stats(self) -> Dict:
        """Get person tracking statistics"""
        return {
            'enabled': self.enabled,
            'total_tracks': len(self.track_history),
            'track_id_mapping_size': len(self.track_id_mapping),
            'next_track_id': self.next_track_id,
            'active_tracks': len([h for h in self.track_history.values()]),
            'bytetrack_initialized': self.byte_tracker is not None
        }

    def update_config(self, config: Dict):
        """Update configuration at runtime"""
        if 'enable_person_tracking' in config:
            new_setting = config['enable_person_tracking']
            if new_setting != self.enabled:
                self.enabled = new_setting
                if self.enabled and self.byte_tracker is None:
                    self._initialize_bytetrack(config)
        
        # Update other parameters
        if 'person_track_confidence' in config:
            self.min_confidence = config['person_track_confidence']
        if 'person_track_max_age' in config:
            self.max_age_frames = config['person_track_max_age']
        if 'person_iou_threshold' in config:
            self.iou_threshold = config['person_iou_threshold']

    def reset(self):
        """Reset all tracking state"""
        self.track_id_mapping.clear()
        self.track_history.clear()
        self.next_track_id = 0
        print("🔄 Person tracking reset")

    def cleanup(self):
        """Clean up tracker resources"""
        if self.byte_tracker and hasattr(self.byte_tracker, 'cleanup'):
            self.byte_tracker.cleanup()