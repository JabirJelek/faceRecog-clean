# tracking/face_tracker.py
import numpy as np
from typing import List, Dict, Tuple, Optional, Deque
from collections import defaultdict, deque
import time
import logging

# Set up logging
logger = logging.getLogger(__name__)

class SimpleFaceTracker:
    """
    Unified face tracking with robust ID management and spatial-temporal consistency
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Tracking parameters
        self.confidence_frames = config.get('confidence_frames', 3)
        self.cooldown_seconds = config.get('cooldown_seconds', 5)
        self.min_iou = config.get('min_iou', 0.3)
        self.max_track_age = config.get('max_track_age', 1000)  # frames
        
        # Re-identification parameters (NEW)
        self.reid_threshold = config.get('reid_threshold', 0.4)
        self.reid_spatial_weight = config.get('reid_spatial_weight', 0.4)
        self.reid_appearance_weight = config.get('reid_appearance_weight', 0.4)
        self.reid_iou_threshold = config.get('reid_iou_threshold', 0.7)
        
        # Robust matching parameters
        self.enable_appearance_matching = config.get('enable_appearance_matching', True)
        self.enable_velocity_prediction = config.get('enable_velocity_prediction', True)
        self.appearance_weight = config.get('appearance_weight', 0.5)
        self.spatial_weight = config.get('spatial_weight', 0.3)
        self.size_weight = config.get('size_weight', 0.2)
        
        # Track management
        self.tracks = {}  # track_id -> Track object
        self.next_track_id = 0
        
        # Enhanced deleted tracks buffer with more info (IMPROVED)
        self.deleted_tracks = deque(maxlen=100)
        self.deleted_track_data = {}  # track_id -> comprehensive data
        
        # Feature storage for appearance matching
        self.track_features = {}  # track_id -> feature queue
        
        # Debug tracking
        self.debug_track_id = config.get('debug_track_id', 0)  # Track to debug
        self.frame_count = 0
        
        logger.info("Enhanced Face Tracker initialized with improved Re-ID")
        logger.debug(f"Debugging track_id={self.debug_track_id}")

    class Track:
        """Enhanced track representation"""
        def __init__(self, track_id: int, initial_data: Dict, frame_count: int):
            self.track_id = track_id
            self.identity = initial_data.get('identity', 'Unknown')
            self.recognition_confidence = initial_data.get('recognition_confidence', 0.0)
            self.detection_confidence = initial_data.get('detection_confidence', 0.5)
            
            # Bounding box management
            self.bbox_history = deque(maxlen=20)
            self.bbox_history.append(initial_data['bbox'])
            self.current_bbox = initial_data['bbox']
            
            # Velocity and motion prediction
            self.velocity = [0, 0, 0, 0]  # dx1, dy1, dx2, dy2
            self.predicted_bbox = None
            
            # Feature matching - STANDARDIZED: Always use 'face_embedding'
            self.features = deque(maxlen=10)  # Store recent embeddings/features
            self.fused_feature = None  # Store the most robust fused embedding
            
            # Store face embedding if available
            if 'face_embedding' in initial_data:
                feature = initial_data['face_embedding']
                self.features.append(feature)
                # If this is a fused embedding, store it separately
                if initial_data.get('embedding_type') == 'fused':
                    self.fused_feature = feature
                # Check for high-quality embeddings to use as fused feature
                elif initial_data.get('quality_score', 0) > 0.7:
                    self.fused_feature = feature
            # Handle legacy 'embedding' key
            elif 'embedding' in initial_data:
                feature = initial_data['embedding']
                self.features.append(feature)
                if initial_data.get('embedding_type') == 'fused':
                    self.fused_feature = feature
                elif initial_data.get('quality_score', 0) > 0.7:
                    self.fused_feature = feature
            
            # Tracking state
            self.confidence_count = 1 if self.identity != 'Unknown' else 0
            self.first_detected_frame = frame_count
            self.last_updated_frame = frame_count
            self.consecutive_misses = 0
            self.max_consecutive_misses = 70
            self.hit_streak = 1
            
            # Cooldown management
            self.cooldown_counter = 0
            self.track_state = 'TRACKING'  # TRACKING, COOLDOWN, EXPIRED
            
            # Reliability metrics
            self.reliability_score = 0.7
            self.bbox_consistency = 1.0
            self.identity_consistency = 1.0
            
            # Debug info
            self.creation_time = time.time()
            
            logger.debug(f"Track {track_id} created: identity={self.identity}, frame={frame_count}")
                       
        def predict_bbox(self, frame_interval: int = 1):
            """Predict next bbox position using simple linear motion model"""
            if len(self.bbox_history) < 2:
                self.predicted_bbox = self.current_bbox
                return self.predicted_bbox
            
            # Calculate velocity from last two positions
            prev_bbox = self.bbox_history[-2] if len(self.bbox_history) >= 2 else self.current_bbox
            curr_bbox = self.current_bbox
            
            # Simple linear prediction
            pred_bbox = []
            for i in range(4):
                velocity = (curr_bbox[i] - prev_bbox[i]) * 0.3  # Dampened prediction
                pred_bbox.append(curr_bbox[i] + velocity * frame_interval)
            
            self.predicted_bbox = pred_bbox
            return pred_bbox
        
        def update(self, new_data: Dict, frame_count: int):
            """Update track with new observation"""
            old_bbox = self.current_bbox
            new_bbox = new_data['bbox']
            
            # Update bbox history and current
            self.bbox_history.append(new_bbox)
            self.current_bbox = new_bbox
            
            # Update velocity
            for i in range(4):
                self.velocity[i] = (new_bbox[i] - old_bbox[i]) * 0.3 + self.velocity[i] * 0.7
            
            # Update identity with hysteresis
            new_identity = new_data.get('identity', 'Unknown')
            new_recog_conf = new_data.get('recognition_confidence', 0.0)
            
            if new_identity != 'Unknown' and new_recog_conf > 0.6:
                if new_identity == self.identity:
                    # Same identity - reinforce
                    self.recognition_confidence = max(self.recognition_confidence, new_recog_conf)
                    self.confidence_count = min(self.confidence_count + 1, 10)
                    self.identity_consistency = min(self.identity_consistency + 0.1, 1.0)
                else:
                    # Different identity - careful update
                    if new_recog_conf > self.recognition_confidence * 1.2:
                        logger.info(f"Track {self.track_id} identity changed: {self.identity} -> {new_identity}")
                        self.identity = new_identity
                        self.recognition_confidence = new_recog_conf
                        self.confidence_count = 1
                        self.identity_consistency *= 0.8
            
            # Update features - STANDARDIZED: Always use 'face_embedding'
            # Check for face_embedding first, then legacy 'embedding'
            new_feature = None
            if 'face_embedding' in new_data:
                new_feature = new_data['face_embedding']
            elif 'embedding' in new_data:
                new_feature = new_data['embedding']
            
            if new_feature is not None:
                self.features.append(new_feature)
                # Update fused feature if this is high quality or fused
                if new_data.get('embedding_type') == 'fused' or new_data.get('quality_score', 0) > 0.8:
                    self.fused_feature = new_feature
                elif self.fused_feature is None:
                    # Use as fused feature if none exists
                    self.fused_feature = new_feature
            
            # Update timestamps
            self.last_updated_frame = frame_count
            self.consecutive_misses = 0
            self.hit_streak += 1
            
            # Update reliability based on consistency
            bbox_consistency = self._calculate_bbox_consistency()
            self.reliability_score = (bbox_consistency * 0.6 + self.identity_consistency * 0.4)
                  
        def _calculate_bbox_consistency(self) -> float:
            """Calculate how consistent the bbox movement is"""
            if len(self.bbox_history) < 3:
                return 1.0
            
            # Check for sudden size/orientation changes
            recent_bboxes = list(self.bbox_history)[-3:]
            areas = []
            for bbox in recent_bboxes:
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                areas.append(w * h)
            
            area_variance = np.var(areas) / np.mean(areas) if np.mean(areas) > 0 else 0
            consistency = 1.0 - min(area_variance, 1.0)
            
            return consistency
        
        def get_state(self) -> Dict:
            """Get track state as dictionary"""
            return {
                'track_id': self.track_id,
                'identity': self.identity,
                'recognition_confidence': self.recognition_confidence,
                'bbox': self.current_bbox,
                'predicted_bbox': self.predicted_bbox,
                'confidence_count': self.confidence_count,
                'track_state': self.track_state,
                'reliability_score': self.reliability_score,
                'hit_streak': self.hit_streak,
                'age_frames': self.last_updated_frame - self.first_detected_frame,
                'last_seen': self.last_updated_frame
            }

    def _calculate_reid_score(self, deleted_track_data: Dict, detection: Dict) -> Tuple[float, Dict]:
        """
        Calculate re-identification score using appearance + spatial cues
        Returns: (score, breakdown)
        """
        scores = []
        weights = []
        breakdown = {}
        
        # 1. Appearance similarity - STANDARDIZED: Use 'face_embedding'
        # Check deleted track data for 'face_embedding' or legacy 'fused_feature'
        feature_to_compare = None
        if 'face_embedding' in deleted_track_data:
            feature_to_compare = deleted_track_data['face_embedding']
        elif 'fused_feature' in deleted_track_data:
            feature_to_compare = deleted_track_data['fused_feature']
        
        # Check detection for 'face_embedding' or legacy 'embedding'
        detection_feature = None
        if 'face_embedding' in detection:
            detection_feature = detection['face_embedding']
        elif 'embedding' in detection:
            detection_feature = detection['embedding']
        
        if feature_to_compare is not None and detection_feature is not None:
            appearance_score = self._calculate_feature_similarity(feature_to_compare, detection_feature)
            scores.append(appearance_score)
            weights.append(self.reid_appearance_weight)
            breakdown['appearance'] = appearance_score
        
        # 2. Spatial similarity (IoU) - only if we have bbox for deleted track
        if 'last_bbox' in deleted_track_data and 'bbox' in detection:
            spatial_score = self._calculate_iou(deleted_track_data['last_bbox'], detection['bbox'])
            scores.append(spatial_score)
            weights.append(self.reid_spatial_weight)
            breakdown['spatial'] = spatial_score
            
            # Special case: High spatial similarity can compensate for moderate appearance similarity
            if spatial_score > self.reid_iou_threshold and len(scores) > 0:
                # Boost the composite score
                composite_boost = min(1.0, scores[0] * 1.3) if scores else 0.0
                breakdown['spatial_boost'] = True
        
        if not scores:
            return 0.0, breakdown
        
        # Weighted composite score
        total_weight = sum(weights)
        composite_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
        breakdown['composite'] = composite_score
        
        return composite_score, breakdown
    
    def _calculate_feature_similarity(self, feature1: np.ndarray, feature2: np.ndarray) -> float:
        """Calculate cosine similarity between two feature vectors"""
        if feature1 is None or feature2 is None:
            return 0.0
        
        dot_product = np.dot(feature1, feature2)
        norm1 = np.linalg.norm(feature1)
        norm2 = np.linalg.norm(feature2)
        
        if norm1 > 0 and norm2 > 0:
            return dot_product / (norm1 * norm2)
        return 0.0
    
    def _calculate_composite_similarity(self, track: 'SimpleFaceTracker.Track', detection: Dict) -> float:
        """Calculate similarity score using multiple cues with appearance priority"""
        scores = []
        weights = []
        
        # 1. Spatial similarity (IoU) - reduced weight
        spatial_score = self._calculate_iou(
            track.predicted_bbox if track.predicted_bbox else track.current_bbox,
            detection['bbox']
        )
        scores.append(spatial_score)
        weights.append(self.spatial_weight * 0.7)
        
        # 2. Size consistency
        if len(track.bbox_history) >= 2:
            size_score = self._calculate_size_similarity(track.current_bbox, detection['bbox'])
            scores.append(size_score)
            weights.append(self.size_weight)
        
        # 3. Appearance matching - STANDARDIZED: Use 'face_embedding'
        detection_feature = None
        if 'face_embedding' in detection:
            detection_feature = detection['face_embedding']
        elif 'embedding' in detection:
            detection_feature = detection['embedding']
        
        if self.enable_appearance_matching and track.features and detection_feature is not None:
            # Prefer fused feature if available
            if track.fused_feature is not None:
                appearance_score = self._calculate_feature_similarity(track.fused_feature, detection_feature)
            else:
                appearance_score = self._calculate_appearance_similarity(track, detection_feature)
            
            scores.append(appearance_score)
            weights.append(self.appearance_weight * 1.2)
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight == 0:
            return spatial_score
        
        # Weighted composite score with appearance bias
        composite_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
        
        # Boost for highly reliable tracks
        if track.reliability_score > 0.8:
            composite_score = min(1.0, composite_score * 1.2)
        
        return composite_score
    
     
    def _calculate_size_similarity(self, bbox1: List, bbox2: List) -> float:
        """Calculate size similarity between two bounding boxes"""
        w1 = bbox1[2] - bbox1[0]
        h1 = bbox1[3] - bbox1[1]
        w2 = bbox2[2] - bbox2[0]
        h2 = bbox2[3] - bbox2[1]
        
        area1 = w1 * h1
        area2 = w2 * h2
        
        if area1 == 0 or area2 == 0:
            return 0.0
        
        ratio = min(area1, area2) / max(area1, area2)
        return ratio
    
    def _calculate_appearance_similarity(self, track: 'SimpleFaceTracker.Track', new_feature: np.ndarray) -> float:
        """Calculate appearance similarity using stored features"""
        if not track.features:
            return 0.5  # Neutral score if no features
        
        # Calculate similarity with all stored features
        similarities = []
        for feature in track.features:
            if feature is not None and new_feature is not None:
                sim = self._calculate_feature_similarity(feature, new_feature)
                similarities.append(sim)
        
        if not similarities:
            return 0.5
        
        # Weight recent features more heavily
        weighted_similarity = 0.0
        total_weight = 0.0
        
        for i, sim in enumerate(reversed(similarities)):
            weight = 0.5 ** i  # Exponential decay
            weighted_similarity += sim * weight
            total_weight += weight
        
        return weighted_similarity / total_weight if total_weight > 0 else 0.0
    
    def _calculate_iou(self, bbox1: List, bbox2: List) -> float:
        """Calculate Intersection over Union"""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        if x2 < x1 or y2 < y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        union = area1 + area2 - intersection
        return intersection / union if union > 0 else 0.0
    
    def _match_detections_to_tracks(self, detections: List[Dict], frame_count: int) -> Dict:
        """
        Match detections to existing tracks using Hungarian algorithm with composite scores
        """
        if not self.tracks or not detections:
            result = {
                'matches': [], 
                'unmatched_detections': list(range(len(detections))), 
                'unmatched_tracks': list(self.tracks.keys())
            }
            return result
        
        # Predict bbox positions for all tracks
        for track in self.tracks.values():
            track.predict_bbox()
        
        # Build cost matrix
        n_tracks = len(self.tracks)
        n_detections = len(detections)
        
        # Initialize with high cost (low similarity)
        cost_matrix = np.ones((n_tracks, n_detections)) * 1000
        
        # Map indices
        track_ids = list(self.tracks.keys())
        
        # Calculate costs (1 - similarity)
        for i, track_id in enumerate(track_ids):
            track = self.tracks[track_id]
            for j, detection in enumerate(detections):
                similarity = self._calculate_composite_similarity(track, detection)
                cost = 1.0 - similarity
                cost_matrix[i, j] = cost
        
        # Apply Hungarian algorithm for optimal matching
        try:
            from scipy.optimize import linear_sum_assignment
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            
            matches = []
            unmatched_detections = set(range(n_detections))
            unmatched_tracks = set(range(n_tracks))
            
            for i, j in zip(row_ind, col_ind):
                if cost_matrix[i, j] < 0.7:  # Similarity > 0.3
                    matches.append((track_ids[i], j))
                    unmatched_detections.discard(j)
                    unmatched_tracks.discard(i)
            
            return {
                'matches': matches,
                'unmatched_detections': list(unmatched_detections),
                'unmatched_tracks': [track_ids[i] for i in unmatched_tracks]
            }
            
        except ImportError:
            # Fallback to greedy matching
            return self._greedy_matching(detections)
    
    def _greedy_matching(self, detections: List[Dict]) -> Dict:
        """Fallback greedy matching algorithm"""
        matches = []
        unmatched_detections = list(range(len(detections)))
        unmatched_tracks = list(self.tracks.keys())
        
        # Sort tracks by reliability (most reliable first)
        sorted_tracks = sorted(self.tracks.items(), 
                              key=lambda x: x[1].reliability_score, 
                              reverse=True)
        
        for track_id, track in sorted_tracks:
            best_score = self.min_iou
            best_det_idx = -1
            
            for det_idx in unmatched_detections:
                detection = detections[det_idx]
                similarity = self._calculate_composite_similarity(track, detection)
                
                if similarity > best_score:
                    best_score = similarity
                    best_det_idx = det_idx
            
            if best_det_idx != -1:
                matches.append((track_id, best_det_idx))
                unmatched_detections.remove(best_det_idx)
                unmatched_tracks.remove(track_id)
        
        return {
            'matches': matches,
            'unmatched_detections': unmatched_detections,
            'unmatched_tracks': unmatched_tracks
        }
    
    def _create_new_tracks(self, detections: List[Dict], indices: List[int], frame_count: int):
        """Create new tracks for unmatched detections with improved re-identification"""
        for det_idx in indices:
            detection = detections[det_idx]
            
            # Enhanced re-identification check - PRIORITIZE APPEARANCE
            is_reid = False
            reid_track_id = None
            reid_score_breakdown = {}
            
            # STANDARDIZED: Check for 'face_embedding' first, then 'embedding'
            has_embedding = 'face_embedding' in detection or 'embedding' in detection
            
            if has_embedding:
                # Use 'face_embedding' if available, otherwise 'embedding'
                detection_feature = detection.get('face_embedding') or detection.get('embedding')
                
                # Check against recently deleted tracks using multi-cue re-ID
                best_reid_score = 0.0
                best_reid_data = None
                
                for deleted_id, deleted_data in self.deleted_track_data.items():
                    # Calculate re-ID score with appearance bias
                    reid_score, breakdown = self._calculate_reid_score(deleted_data, detection)
                    
                    # STRICT RE-ID: Require strong appearance match
                    if (reid_score > best_reid_score and 
                        reid_score > self.reid_threshold and
                        breakdown.get('appearance', 0) > 0.7):
                        best_reid_score = reid_score
                        best_reid_data = deleted_data
                        reid_track_id = deleted_id
                        reid_score_breakdown = breakdown
                
                if best_reid_data is not None:
                    is_reid = True
                    # Remove from deleted tracks if we're re-activating
                    if reid_track_id in self.deleted_track_data:
                        del self.deleted_track_data[reid_track_id]
                    # Also remove from deque if present
                    self.deleted_tracks = deque(
                        [item for item in self.deleted_tracks if item[0] != reid_track_id],
                        maxlen=100
                    )
                    
                    logger.info(f"Re-ID: Track {reid_track_id} re-identified with score {best_reid_score:.3f}")
            
            if is_reid and reid_track_id is not None:
                # Re-activate track with original ID
                track_id = reid_track_id
                # Update the detection with re-ID info
                detection['reidentified'] = True
                detection['reid_score'] = best_reid_score
                detection['reid_breakdown'] = reid_score_breakdown
            else:
                # Create new track with sequential ID
                track_id = self.next_track_id
                self.next_track_id += 1
            
            self.tracks[track_id] = self.Track(track_id, detection, frame_count)
                            
    def _cleanup_old_tracks(self, frame_count: int):
        """Remove tracks that are too old or unreliable with comprehensive data storage"""
        tracks_to_remove = []
        
        for track_id, track in self.tracks.items():
            # Check age
            age = frame_count - track.last_updated_frame
            if age > self.max_track_age:
                tracks_to_remove.append(track_id)
                logger.warning(f"Track {track_id} marked for removal: age {age} > max_track_age {self.max_track_age}")
                continue
            
            # Check consecutive misses
            if track.consecutive_misses > track.max_consecutive_misses:
                tracks_to_remove.append(track_id)
                logger.warning(f"Track {track_id} marked for removal: consecutive_misses {track.consecutive_misses}")
                continue
            
            # Check reliability
            if track.reliability_score < 0.3 and age > 30:
                tracks_to_remove.append(track_id)
                logger.warning(f"Track {track_id} marked for removal: reliability_score {track.reliability_score:.3f}")
                continue
        
        # Store deleted tracks with comprehensive data for potential re-ID
        for track_id in tracks_to_remove:
            track = self.tracks[track_id]
            
            # Prepare robust feature data - STANDARDIZED: Use 'face_embedding' as key
            features_to_store = list(track.features)
            fused_feature = track.fused_feature
            
            # If no fused feature, try to create one from recent high-quality features
            if fused_feature is None and features_to_store:
                # Use the most recent high-quality feature
                fused_feature = features_to_store[-1]
            
            deleted_data = {
                'features': features_to_store,
                'face_embedding': fused_feature,  # STANDARDIZED: Use 'face_embedding' as key
                'last_bbox': track.current_bbox,
                'last_velocity': track.velocity,
                'identity': track.identity,
                'reliability_score': track.reliability_score,
                'last_seen': track.last_updated_frame,
                'hit_streak': track.hit_streak,
                'quality_hint': 'fused' if track.fused_feature is not None else 'standard'
            }
            
            # Store in both structures for different access patterns
            self.deleted_tracks.append((track_id, deleted_data))
            self.deleted_track_data[track_id] = deleted_data
            
            # Log deletion
            logger.error(f"Track {track_id} DELETED")
            
            del self.tracks[track_id]
        
        # Clean up old deleted track data (keep only recent)
        max_deleted_tracks = 50
        if len(self.deleted_track_data) > max_deleted_tracks:
            # Remove oldest entries
            oldest_ids = sorted(
                self.deleted_track_data.keys(),
                key=lambda x: self.deleted_track_data[x]['last_seen']
            )[:len(self.deleted_track_data) - max_deleted_tracks]
            for old_id in oldest_ids:
                del self.deleted_track_data[old_id]
                 
    def update(self, recognition_results: List[Dict], frame_count: int) -> List[Dict]:
        """Main update method with robust tracking and improved re-ID"""
        self.frame_count = frame_count
        
        if not recognition_results:
            # Update existing tracks (missed detection)
            for track in self.tracks.values():
                track.consecutive_misses += 1
                track.last_updated_frame = frame_count
            
            self._cleanup_old_tracks(frame_count)
            return []
        
        # Match detections to existing tracks
        matching_result = self._match_detections_to_tracks(recognition_results, frame_count)
        
        # Update matched tracks
        for track_id, det_idx in matching_result['matches']:
            detection = recognition_results[det_idx]
            self.tracks[track_id].update(detection, frame_count)
        
        # Create new tracks for unmatched detections with improved re-ID
        self._create_new_tracks(recognition_results, matching_result['unmatched_detections'], frame_count)
        
        # Increment misses for unmatched tracks
        for track_idx in matching_result['unmatched_tracks']:
            self.tracks[track_idx].consecutive_misses += 1
        
        # Cleanup old tracks
        self._cleanup_old_tracks(frame_count)
        
        # Generate final results
        final_results = []
        for i, detection in enumerate(recognition_results):
            result = detection.copy()
            
            # Find matching track
            matched_track_id = None
            for track_id, det_idx in matching_result['matches']:
                if det_idx == i:
                    matched_track_id = track_id
                    break
            
            if matched_track_id:
                track = self.tracks[matched_track_id]
                result['track_id'] = track.track_id
                result['track_state'] = track.track_state
                
                # Use track identity if in cooldown OR if track has high reliability
                if track.track_state == 'COOLDOWN' or track.reliability_score > 0.8:
                    result['identity'] = track.identity
                    result['recognition_confidence'] = track.recognition_confidence
                    # Optionally, you can still show current detection but with track override
                    if 'identity' in detection and detection['identity'] != 'Unknown':
                        # Blend confidences
                        result['recognition_confidence'] = max(
                            track.recognition_confidence, 
                            detection.get('recognition_confidence', 0)
                        )
            else:
                result['track_state'] = 'NEW'
                # Check for re-identification in final results
                if detection.get('reidentified', False):
                    result['track_state'] = 'REIDENTIFIED'
            
            final_results.append(result)
        
        return final_results
    
    def get_tracking_stats(self) -> Dict:
        """Get comprehensive tracking statistics"""
        tracking_count = sum(1 for t in self.tracks.values() if t.track_state == 'TRACKING')
        cooldown_count = sum(1 for t in self.tracks.values() if t.track_state == 'COOLDOWN')
        
        reliability_scores = [t.reliability_score for t in self.tracks.values()]
        avg_reliability = np.mean(reliability_scores) if reliability_scores else 0
        
        # Count re-ID opportunities
        reid_ready_tracks = sum(1 for data in self.deleted_track_data.values() 
                               if data.get('face_embedding') is not None)
        
        return {
            'total_tracks': len(self.tracks),
            'tracking_count': tracking_count,
            'cooldown_count': cooldown_count,
            'avg_reliability': avg_reliability,
            'next_track_id': self.next_track_id,
            'deleted_tracks': len(self.deleted_track_data),
            'reid_ready_tracks': reid_ready_tracks,
            'avg_hit_streak': np.mean([t.hit_streak for t in self.tracks.values()]) if self.tracks else 0
        }
    
    def reset(self):
        """Reset all tracking state"""
        self.tracks.clear()
        self.next_track_id = 0
        self.deleted_tracks.clear()
        self.deleted_track_data.clear()
        logger.info("Enhanced face tracker reset")
        
    def debug_track_status(self, track_id: int = 0) -> Dict:
        """Get detailed debug info for a specific track"""
        if track_id in self.tracks:
            track = self.tracks[track_id]
            return {
                'track_id': track_id,
                'identity': track.identity,
                'recognition_confidence': track.recognition_confidence,
                'current_bbox': track.current_bbox,
                'predicted_bbox': track.predicted_bbox,
                'consecutive_misses': track.consecutive_misses,
                'max_consecutive_misses': track.max_consecutive_misses,
                'hit_streak': track.hit_streak,
                'reliability_score': track.reliability_score,
                'last_updated_frame': track.last_updated_frame,
                'age_frames': track.last_updated_frame - track.first_detected_frame,
                'bbox_history_size': len(track.bbox_history),
                'features_count': len(track.features),
                'has_fused_feature': track.fused_feature is not None,
                'track_state': track.track_state
            }
        elif track_id in self.deleted_track_data:
            return {
                'track_id': track_id,
                'status': 'DELETED',
                'deleted_data': self.deleted_track_data[track_id],
                'last_seen': self.deleted_track_data[track_id]['last_seen'],
                'age_since_deletion': self.frame_count - self.deleted_track_data[track_id]['last_seen']
            }
        else:
            return {
                'track_id': track_id,
                'status': 'UNKNOWN',
                'message': f'Track {track_id} not found in active or deleted tracks'
            }
            