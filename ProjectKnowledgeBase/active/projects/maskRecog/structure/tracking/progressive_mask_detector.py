# tracking/progressive_mask_detector.py

import numpy as np
from typing import Dict, List, Tuple, Optional, Deque, Any
from collections import deque, defaultdict
import time
import logging
from dataclasses import dataclass, field
from enum import Enum

class MaskStatus(Enum):
    """Enum for mask status to avoid string typos"""
    MASK = "mask"
    NO_MASK = "no_mask"
    VERIFYING = "verifying"
    UNKNOWN = "unknown"

@dataclass
class MaskObservation:
    """Data class for mask observations"""
    status: MaskStatus
    confidence: float
    timestamp: float
    bbox: Optional[List[float]] = None
    spatial_consistency: float = 1.0
    original_confidence: float = 0.0

@dataclass
class TrackState:
    """Data class to hold all track-related state"""
    buffer: Deque[MaskObservation] = field(default_factory=lambda: deque(maxlen=1000))
    bbox_history: Deque[List[float]] = field(default_factory=lambda: deque(maxlen=10))
    holding_meta: Dict[str, Any] = field(default_factory=dict)
    holding_buffer: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=10))
    label_weights: Dict[str, float] = field(default_factory=dict)
    last_seen: float = 0.0
    stability_score: float = 0.5
    committed_status: MaskStatus = MaskStatus.VERIFYING
    commit_time: float = 0.0
    instability_count: int = 0

class ProgressiveMaskDetector:
    """
    Enhanced progressive mask detection with comprehensive temporal analysis
    Now handles ALL stability and consistency checking WITHOUT hard resets
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Create console handler if not already configured
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # Initialize default configuration with validation
        self._initialize_config()
        
        # Track management using TrackState dataclasses
        self.tracks: Dict[str, TrackState] = {}
        
        self.logger.info(f"Enhanced Progressive Mask Detector initialized")
        self.logger.info(f"  State holding duration: {self.state_hold_duration}s")
        self.logger.info(f"  Minimum stability to commit: {self.min_stability_to_commit}")
        self.logger.info(f"  Adaptive label weighting enabled")

    def _initialize_config(self) -> None:
        """Initialize and validate configuration parameters"""
        # Temporal analysis parameters
        self.buffer_size = self.config.get('mask_buffer_size', 1000)
        self.confidence_threshold = max(0.0, min(1.0, 
            self.config.get('mask_confidence_threshold', 0.0)))
        self.consistency_threshold = max(0.0, min(1.0,
            self.config.get('mask_consistency_threshold', 0.5)))
        self.min_frames_for_decision = max(1,
            self.config.get('min_mask_frames', 2))
        self.occlusion_timeout = max(0.1,
            self.config.get('occlusion_timeout', 3))
        
        # State holding parameters
        self.state_hold_duration = max(0.1,
            self.config.get('state_hold_duration', 30.0))
        self.min_stability_to_commit = max(0.0, min(1.0,
            self.config.get('min_stability_to_commit', 0.25)))
        
        # Spatial-temporal consistency
        self.spatial_consistency_weight = max(0.0, min(1.0,
            self.config.get('spatial_consistency_weight', 0.3)))
        self.max_bbox_variation = max(0.0, min(1.0,
            self.config.get('max_bbox_variation', 0.5)))
        
        # Grace period for verification
        self.verification_grace_ratio = max(0.0, min(1.0,
            self.config.get('verification_grace_ratio', 0.5)))
        
        # Weight adjustment parameters with validation
        self.weight_increase_high_conf = max(0.0, min(1.0,
            self.config.get('weight_increase_high_conf', 0.5)))
        self.weight_decrease_low_conf = max(0.0, min(1.0,
            self.config.get('weight_decrease_low_conf', 0.3)))
        self.weight_increase_opposite = max(0.0, min(1.0,
            self.config.get('weight_increase_opposite', 0.4)))
        self.max_weight = max(0.0,
            self.config.get('max_weight', 1.0))
        self.min_weight = max(0.0,
            self.config.get('min_weight', 0.0))
        
        # Smoothing factors
        self.confidence_smoothing_factor = max(0.0, min(1.0,
            self.config.get('confidence_smoothing_factor', 0.3)))
        self.stability_smoothing_factor = max(0.0, min(1.0,
            self.config.get('stability_smoothing_factor', 0.2)))
        
        # # Extreme confidence handling
        # self.extreme_confidence_threshold = max(0.0, min(1.0,
        #     self.config.get('extreme_confidence_threshold', 0.99)))
        # self.extreme_mask_penalty = max(0.0, min(1.0,
        #     self.config.get('extreme_mask_penalty', 0.9)))
        # self.extreme_no_mask_boost = max(0.0, min(1.0,
        #     self.config.get('extreme_no_mask_boost', 0.9)))
        
        # Initial weights
        self.initial_mask_weight = max(0.0, min(1.0,
            self.config.get('initial_mask_weight', 0.5)))
        self.initial_no_mask_weight = max(0.0, min(1.0,
            self.config.get('initial_no_mask_weight', 0.5)))
        
        # Early frame skepticism thresholds
        self.early_frame_threshold = self.config.get('early_frame_threshold', 1)
        self.early_confidence_threshold = self.config.get('early_confidence_threshold', 1)

    def _initialize_track(self, track_id: str, timestamp: float) -> None:
        """Initialize a new track with proper state"""
        self.logger.info(f"Initializing track {track_id} with timestamp {timestamp}")
        
        # Create new track state
        track_state = TrackState()
        track_state.buffer = deque(maxlen=self.buffer_size)
        track_state.last_seen = timestamp
        track_state.commit_time = timestamp
        
        # Initialize label weights with anti-overfitting bias
        track_state.label_weights = {
            MaskStatus.MASK.value: self.initial_mask_weight,
            MaskStatus.NO_MASK.value: self.initial_no_mask_weight,
        }
        
        # Initialize holding metadata
        track_state.holding_meta = {
            'committed_status': MaskStatus.VERIFYING,
            'commit_time': timestamp,
            'hold_start_time': timestamp,
            'instability_count': 0
        }
        
        self.tracks[track_id] = track_state
        
        self.logger.debug(f"Track {track_id} initialized with mask_weight={self.initial_mask_weight}, "
            f"no_mask_weight={self.initial_no_mask_weight}")

    def _string_to_mask_status(self, status_str: str) -> MaskStatus:
        """Convert string to MaskStatus enum"""
        try:
            return MaskStatus(status_str)
        except ValueError:
            self.logger.warning(f"Unknown mask status: {status_str}, defaulting to UNKNOWN")
            return MaskStatus.UNKNOWN

    def _update_label_weights(self, track_id: str, current_status: MaskStatus, 
                             raw_confidence: float, timestamp: float) -> None:
        """
        Dynamically adjust label weights based on current detection confidence.
        This implements the anti-overfitting mechanism by penalizing unreliable
        mask predictions and rewarding reliable no_mask predictions.
        """
        if track_id not in self.tracks:
            return
            
        track = self.tracks[track_id]
        
        # Initialize weights if not present
        if not track.label_weights:
            track.label_weights = {
                MaskStatus.MASK.value: self.initial_mask_weight,
                MaskStatus.NO_MASK.value: self.initial_no_mask_weight,
            }
            
        frame_count = len(track.buffer)
        
        # Early frame skepticism
        if frame_count < self.early_frame_threshold and raw_confidence > self.early_confidence_threshold:
            self.logger.debug(f"Early frame skepticism: {current_status.value}={raw_confidence:.2f} on frame {frame_count}")
            # For early frames, start with balanced but skeptical weights
            track.label_weights = {
                MaskStatus.MASK.value: 0.5,
                MaskStatus.NO_MASK.value: 0.5
            }
            return
        
        weights = track.label_weights
        
        # Determine which label was detected
        detected_label = current_status.value
        opposite_label = MaskStatus.NO_MASK.value if current_status == MaskStatus.MASK else MaskStatus.MASK.value
        
        # # Handle extreme confidence cases first
        # if raw_confidence >= self.extreme_confidence_threshold:
        #     if current_status == MaskStatus.MASK:
        #         # Extreme confidence mask: penalize heavily
        #         weights[MaskStatus.MASK.value] = max(
        #             self.min_weight,
        #             weights[MaskStatus.MASK.value] - self.extreme_mask_penalty
        #         )
        #         weights[MaskStatus.NO_MASK.value] = min(
        #             self.max_weight,
        #             weights[MaskStatus.NO_MASK.value] + self.extreme_no_mask_boost
        #         )
        #         self.logger.warning(f"Extreme confidence inversion: mask={raw_confidence:.2f}")
        #     elif current_status == MaskStatus.NO_MASK:
        #         # Extreme confidence no_mask: reinforce
        #         weights[MaskStatus.NO_MASK.value] = min(
        #             self.max_weight,
        #             weights[MaskStatus.NO_MASK.value] + self.weight_increase_high_conf * 1.5
        #         )
        #     return
        
        # Normal confidence adjustments
        if raw_confidence >= 0.8:  # High confidence
            weights[detected_label] = min(
                self.max_weight,
                weights[detected_label] + self.weight_increase_high_conf * 0.1
            )
            self.logger.debug(f"Weight increase for '{detected_label}' (confidence: {raw_confidence:.2f})")
            
        elif raw_confidence >= 0.4:  # Medium confidence
            if current_status == MaskStatus.MASK:
                # Moderate confidence mask: slight penalty
                weights[MaskStatus.MASK.value] = max(
                    self.min_weight,
                    weights[MaskStatus.MASK.value] - self.weight_decrease_low_conf * 0.05
                )
                weights[MaskStatus.NO_MASK.value] = min(
                    self.max_weight,
                    weights[MaskStatus.NO_MASK.value] + self.weight_increase_opposite * 0.02
                )
            else:  # NO_MASK with moderate confidence
                weights[MaskStatus.NO_MASK.value] = min(
                    self.max_weight,
                    weights[MaskStatus.NO_MASK.value] + self.weight_increase_high_conf * 0.02
                )
                
        else:  # Low confidence
            # Low confidence detections get minimal weight adjustments
            if current_status == MaskStatus.MASK:
                weights[MaskStatus.MASK.value] = max(
                    self.min_weight,
                    weights[MaskStatus.MASK.value] - self.weight_decrease_low_conf * 0.01
                )
            else:
                weights[MaskStatus.NO_MASK.value] = max(
                    self.min_weight,
                    weights[MaskStatus.NO_MASK.value] - self.weight_decrease_low_conf * 0.01
                )
        
        # Ensure weights stay within bounds and normalize if needed
        weights[MaskStatus.MASK.value] = max(self.min_weight, min(self.max_weight, weights[MaskStatus.MASK.value]))
        weights[MaskStatus.NO_MASK.value] = max(self.min_weight, min(self.max_weight, weights[MaskStatus.NO_MASK.value]))
        
        track.label_weights = weights

    def update_config(self, new_config: Dict) -> None:
        """Update configuration at runtime with validation"""
        if 'mask_buffer_size' in new_config:
            self.buffer_size = new_config['mask_buffer_size']
            for track in self.tracks.values():
                # Create new deque with updated maxlen
                new_buffer = deque(track.buffer, maxlen=self.buffer_size)
                track.buffer = new_buffer
                
        # Update other config parameters with validation
        config_updates = {
            'mask_confidence_threshold': 'confidence_threshold',
            'mask_consistency_threshold': 'consistency_threshold',
            'min_mask_frames': 'min_frames_for_decision',
            'occlusion_timeout': 'occlusion_timeout',
            'state_hold_duration': 'state_hold_duration',
            'min_stability_to_commit': 'min_stability_to_commit',
            'verification_grace_ratio': 'verification_grace_ratio',
            'weight_increase_high_conf': 'weight_increase_high_conf',
            'weight_decrease_low_conf': 'weight_decrease_low_conf',
            'weight_increase_opposite': 'weight_increase_opposite',
            'confidence_smoothing_factor': 'confidence_smoothing_factor',
            'stability_smoothing_factor': 'stability_smoothing_factor',
            'max_weight': 'max_weight',
            'min_weight': 'min_weight',
        }
        
        for config_key, attr_name in config_updates.items():
            if config_key in new_config:
                setattr(self, attr_name, new_config[config_key])
                self.logger.info(f"{attr_name} updated to {new_config[config_key]}")

    def update_track(self, track_id: str, mask_status: str, mask_confidence: float, 
                    bbox: Optional[List] = None, timestamp: Optional[float] = None) -> Dict:
        """
        Comprehensive temporal analysis of mask status with state holding
        NO hard resets - relies on weighted label progressive calculation
        """
        if timestamp is None:
            timestamp = time.time()
            
        # Convert string status to enum
        status_enum = self._string_to_mask_status(mask_status)
        
        # Initialize track if new
        if track_id not in self.tracks:
            self._initialize_track(track_id, timestamp)
        
        track = self.tracks[track_id]
        
        # Update last seen
        track.last_seen = timestamp
        
        # Update label weights
        self._update_label_weights(track_id, status_enum, mask_confidence, timestamp)
        
        # Apply confidence smoothing
        smoothed_confidence = self._smooth_confidence(track_id, mask_confidence, track)
        
        # Check spatial consistency
        spatial_consistency = self._check_spatial_consistency(track_id, bbox)
        
        # Adjust confidence based on spatial consistency
        if spatial_consistency < 0.7:
            smoothed_confidence *= 0.6
        
        # Determine final status with confidence filtering
        final_status = self._determine_filtered_status(status_enum, smoothed_confidence)
        
        # Create and store observation
        observation = MaskObservation(
            status=final_status,
            confidence=smoothed_confidence,
            timestamp=timestamp,
            bbox=bbox,
            spatial_consistency=spatial_consistency,
            original_confidence=mask_confidence
        )
        
        track.buffer.append(observation)
        
        # Update bbox history
        if bbox and len(bbox) == 4:
            track.bbox_history.append(bbox)
        
        # Log buffer size occasionally
        buffer_size = len(track.buffer)
        if buffer_size % 10 == 0:
            self.logger.debug(f"Track {track_id}: Buffer size = {buffer_size}, Status = {final_status.value}")
        
        # Generate comprehensive status analysis
        result = self._get_comprehensive_status_with_holding(track_id, timestamp)
        
        return result
    
    def _determine_filtered_status(self, status: MaskStatus, confidence: float) -> MaskStatus:
        """Determine final status based on confidence filtering"""
        if confidence < self.confidence_threshold * 0.4:
            return MaskStatus.UNKNOWN
        elif confidence < self.confidence_threshold * 0.7:
            if status == MaskStatus.NO_MASK:
                return MaskStatus.VERIFYING
        return status

    def _smooth_confidence(self, track_id: str, new_confidence: float, track: TrackState) -> float:
        """Apply exponential smoothing to confidence scores"""
        smoothed = (self.confidence_smoothing_factor * new_confidence + 
                   (1 - self.confidence_smoothing_factor) * track.stability_score)
        
        track.stability_score = smoothed
        return smoothed

    def _check_spatial_consistency(self, track_id: str, new_bbox: Optional[List]) -> float:
        """Check spatial consistency with previous detections"""
        if track_id not in self.tracks:
            return 1.0
            
        track = self.tracks[track_id]
        
        if not track.bbox_history or new_bbox is None or len(new_bbox) != 4:
            return 0.5
        
        ious = []
        for old_bbox in list(track.bbox_history)[-5:]:
            if old_bbox and len(old_bbox) == 4:
                iou = self._calculate_iou(new_bbox, old_bbox)
                ious.append(iou)
        
        return np.mean(ious) if ious else 0.5

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

    def _get_comprehensive_status_with_holding(self, track_id: str, current_time: float) -> Dict:
        """
        Generate comprehensive status with stability assessment and state holding
        """
        if track_id not in self.tracks:
            return self._get_default_status()
            
        track = self.tracks[track_id]
        buffer = track.buffer
        
        if not buffer:
            return self._get_default_status()
        
        # Comprehensive temporal analysis
        temporal_analysis = self._analyze_temporal_patterns(buffer)
        spatial_analysis = self._analyze_spatial_consistency(track_id)
        confidence_analysis = self._analyze_confidence_trends(buffer)
        
        # Calculate overall stability score
        stability_score = self._calculate_stability_score(
            temporal_analysis, spatial_analysis, confidence_analysis
        )
        
        # Determine status using weighted ratios
        candidate_status, candidate_confidence = self._determine_status_from_analysis(
            temporal_analysis, confidence_analysis, len(buffer), track_id
        )
        
        # Calculate verification progress
        verification_progress = self._calculate_verification_progress(
            temporal_analysis, len(buffer)
        )
        
        # Determine if candidate status is stable
        candidate_stable = self._is_status_stable(
            stability_score, verification_progress, len(buffer)
        )
        
        # Apply state holding logic
        return self._apply_state_holding_logic(
            track_id, current_time,
            candidate_status, candidate_confidence, candidate_stable,
            verification_progress,
            temporal_analysis, spatial_analysis, confidence_analysis
        )

    def _analyze_temporal_patterns(self, buffer: Deque[MaskObservation]) -> Dict:
        """Analyze temporal patterns in mask status"""
        buffer_list = list(buffer)
        
        # Status distribution
        status_counts = defaultdict(int)
        for obs in buffer_list:
            status_counts[obs.status.value] += 1
        
        total = len(buffer_list)
        mask_ratio = status_counts[MaskStatus.MASK.value] / total if total > 0 else 0
        no_mask_ratio = status_counts[MaskStatus.NO_MASK.value] / total if total > 0 else 0
        
        # Temporal consistency
        recent_frames = buffer_list[-min(8, len(buffer_list)):]
        recent_statuses = [obs.status.value for obs in recent_frames]
        recent_consistency = self._calculate_consistency(recent_statuses)
        
        # Status transitions (for information only, not for reset)
        transitions = self._count_status_transitions(buffer_list)
        
        return {
            'mask_ratio': mask_ratio,
            'no_mask_ratio': no_mask_ratio,
            'recent_consistency': recent_consistency,
            'total_transitions': transitions,
            'status_history': recent_statuses[-5:]
        }

    def _analyze_spatial_consistency(self, track_id: str) -> Dict:
        """Analyze spatial consistency of detections"""
        if track_id not in self.tracks:
            return {'score': 1.0, 'stable': True}
            
        track = self.tracks[track_id]
        
        if not track.bbox_history:
            return {'score': 1.0, 'stable': True}
        
        bbox_history = list(track.bbox_history)
        
        # Calculate IoU consistency
        ious = []
        for i in range(1, len(bbox_history)):
            if len(bbox_history[i]) == 4 and len(bbox_history[i-1]) == 4:
                iou = self._calculate_iou(bbox_history[i], bbox_history[i-1])
                ious.append(iou)
        
        spatial_score = np.mean(ious) if ious else 1.0
        
        # Check for sudden movements
        movement_stable = self._check_movement_stability(bbox_history)
        
        return {
            'score': spatial_score,
            'stable': movement_stable,
            'bbox_count': len(bbox_history)
        }

    def _analyze_confidence_trends(self, buffer: Deque[MaskObservation]) -> Dict:
        """Analyze confidence trends over time"""
        buffer_list = list(buffer)
        confidences = [obs.confidence for obs in buffer_list]
        
        if not confidences:
            return {'mean': 0.0, 'std': 0.0, 'trend': 'stable'}
        
        mean_confidence = np.mean(confidences)
        std_confidence = np.std(confidences) if len(confidences) > 1 else 0.0
        
        # Analyze trend
        trend = 'stable'
        if len(confidences) >= 3:
            recent_confidences = confidences[-3:]
            if all(recent_confidences[i] >= recent_confidences[i-1] for i in range(1, 3)):
                trend = 'increasing'
            elif all(recent_confidences[i] <= recent_confidences[i-1] for i in range(1, 3)):
                trend = 'decreasing'
        
        return {
            'mean': mean_confidence,
            'std': std_confidence,
            'trend': trend,
            'min': min(confidences) if confidences else 0.0,
            'max': max(confidences) if confidences else 0.0
        }

    def _calculate_stability_score(self, temporal: Dict, spatial: Dict, confidence: Dict) -> float:
        """Calculate comprehensive stability score (0-1)"""
        scores = []
        
        # Temporal consistency score
        if temporal['recent_consistency'] > 0.8:
            scores.append(0.9)
        elif temporal['recent_consistency'] > 0.6:
            scores.append(0.7)
        else:
            scores.append(0.3)
        
        # Spatial consistency score
        scores.append(spatial['score'])
        
        # Confidence stability score (low std is good)
        if confidence['std'] < 0.1:
            scores.append(0.9)
        elif confidence['std'] < 0.2:
            scores.append(0.7)
        else:
            scores.append(0.4)
        
        # Average all scores
        return float(np.mean(scores)) if scores else 0.5

    def _determine_status_from_analysis(self, temporal: Dict, confidence: Dict, 
                                       total_frames: int, track_id: str = None) -> Tuple[str, float]:
        """
        Determine mask status based on weighted ratios ONLY - NO contradiction reset
        """
        # Not enough frames for reliable decision
        if total_frames < self.min_frames_for_decision:
            return MaskStatus.VERIFYING.value, confidence['mean'] * 0.7
        
        mask_ratio = temporal['mask_ratio']
        no_mask_ratio = temporal['no_mask_ratio']
        mean_confidence = confidence['mean']
        
        # Apply adaptive label weights
        if track_id and track_id in self.tracks:
            track = self.tracks[track_id]
            weights = track.label_weights
            
            # Calculate weighted ratios
            effective_mask_ratio = mask_ratio * weights.get(MaskStatus.MASK.value, 0.5)
            effective_no_mask_ratio = no_mask_ratio * weights.get(MaskStatus.NO_MASK.value, 0.5)
            
            self.logger.debug(f"Weighted ratios: mask={effective_mask_ratio:.3f} "
                  f"(raw={mask_ratio:.3f}×w={weights.get(MaskStatus.MASK.value, 0.5):.2f}), "
                  f"no_mask={effective_no_mask_ratio:.3f} "
                  f"(raw={no_mask_ratio:.3f}×w={weights.get(MaskStatus.NO_MASK.value, 0.5):.2f})")
            
            # Use weighted ratios for decision making
            if (effective_mask_ratio >= self.consistency_threshold and 
                mean_confidence > self.confidence_threshold * 0.2):
                return MaskStatus.MASK.value, mean_confidence * weights.get(MaskStatus.MASK.value, 0.5)
            
            elif (effective_no_mask_ratio >= self.consistency_threshold + 0.5 and 
                  mean_confidence > self.confidence_threshold * 4):
                return MaskStatus.NO_MASK.value, mean_confidence * weights.get(MaskStatus.NO_MASK.value, 0.5)
        
        # Default to verifying if no clear decision
        return MaskStatus.VERIFYING.value, mean_confidence * 0.2
    
    def _calculate_verification_progress(self, temporal: Dict, total_frames: int) -> float:
        """
        Calculate verification progress (0-1) WITHOUT contradiction reset
        Adjusted weighting to prioritize frame count over volatile consistency
        """
        # Frame count progress - more stable metric
        frame_progress = min(1.0, total_frames / self.min_frames_for_decision)
        
        # Consistency progress - can be volatile due to short-term noise
        consistency_progress = temporal['recent_consistency']
        
        # Prioritize cumulative frames over volatile consistency
        progress = frame_progress * 0.6 + consistency_progress * 0.4
        
        # Apply grace period for verification
        if frame_progress >= 0.8 and consistency_progress >= self.verification_grace_ratio:
            progress = max(progress, 0.85)
            
        return min(1.0, progress)
    
    def _is_status_stable(self, stability_score: float, verification_progress: float, 
                         total_frames: int) -> bool:
        """
        Determine if the current status is stable WITHOUT contradiction dependency
        """
        if total_frames < self.min_frames_for_decision:
            return False
        
        if stability_score < 0.85:
            return False
        
        if verification_progress < 0.85:
            return False
        
        return True

    def _apply_state_holding_logic(self, track_id: str, current_time: float,
                                  candidate_status: str, candidate_confidence: float, 
                                  candidate_stable: bool, verification_progress: float,
                                  temporal_analysis: Dict, spatial_analysis: Dict, 
                                  confidence_analysis: Dict) -> Dict:
        """
        Apply state holding/hysteresis logic WITHOUT contradiction blocking
        Enhanced with grace period for temporary instability
        """
        if track_id not in self.tracks:
            return self._get_default_status()
            
        track = self.tracks[track_id]
        
        # Initialize holding buffer if not exists
        if not track.holding_buffer:
            track.holding_buffer = deque(maxlen=10)
            
        # Add current candidate to holding buffer
        track.holding_buffer.append({
            'status': candidate_status,
            'stable': candidate_stable,
            'progress': verification_progress,
            'time': current_time
        })
        
        # Extended holding period analysis
        time_since_commit = current_time - track.commit_time
        
        # Check if we should commit the candidate status
        is_final_state = candidate_status in (MaskStatus.MASK.value, MaskStatus.NO_MASK.value)
        
        # More forgiving stability check during holding period
        is_sufficiently_stable = verification_progress >= self.min_stability_to_commit
        
        # Check if we're experiencing temporary instability
        holding_buffer = list(track.holding_buffer)
        if len(holding_buffer) >= 3:
            recent_stable_frames = sum(1 for obs in holding_buffer[-3:] if obs['stable'])
            is_temporary_instability = recent_stable_frames >= 2
            
            # If temporary instability but we were recently stable, be more forgiving
            if is_temporary_instability and time_since_commit < self.state_hold_duration / 2:
                is_sufficiently_stable = True
        
        final_status = candidate_status
        final_confidence = candidate_confidence
        final_stable = candidate_stable
        holding_applied = False
        
        # Commit new stable status
        if is_final_state and is_sufficiently_stable:
            # New high-confidence, stable state locks in the held status
            track.committed_status = self._string_to_mask_status(candidate_status)
            track.commit_time = current_time
            track.instability_count = 0
            
            # Output is the newly committed status
            final_status = candidate_status
            final_stable = True
            self.logger.info(f"Committed {final_status} for track {track_id} with progress {verification_progress:.2f}")
            
        # Apply hysteresis (state holding)
        elif (track.committed_status in (MaskStatus.MASK, MaskStatus.NO_MASK) and 
              candidate_status not in (MaskStatus.MASK.value, MaskStatus.NO_MASK.value)):
            # We lost stability, check if we are within the holding duration
            if time_since_commit < self.state_hold_duration:
                # Progressive confidence decay during holding
                hold_progress = 1.0 - (time_since_commit / self.state_hold_duration)
                confidence_decay = 0.9 + (0.1 * hold_progress)
                
                # Holding: Return the last committed status, forcing temporary stability
                final_status = track.committed_status.value
                final_confidence = candidate_confidence * confidence_decay
                final_stable = True
                holding_applied = True
                
                track.instability_count += 1
                
                # Only log if instability is building up
                if track.instability_count > 3:
                    self.logger.debug(f"Holding {final_status} for track {track_id} "
                          f"(time since commit: {time_since_commit:.1f}s, "
                          f"instability: {track.instability_count})")
                
            else:
                # Time expired: Fall back to 'verifying' or candidate status
                if candidate_status == MaskStatus.UNKNOWN.value:
                    final_status = MaskStatus.UNKNOWN.value
                else:
                    final_status = MaskStatus.VERIFYING.value
                    
                final_stable = False
                
                # Reset committed status
                track.committed_status = self._string_to_mask_status(final_status)
                track.commit_time = current_time
                track.instability_count = 0
                
                self.logger.info(f"Holding expired for track {track_id}, reverting to {final_status}")
        
        # Calculate final verification progress
        if holding_applied:
            # During holding, don't let progress drop below 70%
            final_verification_progress = max(verification_progress, 0.7)
        elif final_status in (MaskStatus.MASK.value, MaskStatus.NO_MASK.value) and final_stable:
            final_verification_progress = 1.0
        else:
            final_verification_progress = verification_progress
        
        return {
            'mask_status': final_status,
            'mask_confidence': final_confidence,
            'verification_progress': final_verification_progress,
            'frames_processed': len(track.buffer),
            'is_stable': final_stable,
            'has_contradictions': False,
            'stability_score': confidence_analysis.get('mean', 0.0),
            'temporal_analysis': temporal_analysis,
            'spatial_analysis': spatial_analysis,
            'confidence_analysis': confidence_analysis,
            'holding_status': track.committed_status.value,
            'holding_applied': holding_applied,
            'time_since_commit': time_since_commit if track.committed_status in (MaskStatus.MASK, MaskStatus.NO_MASK) else 0
        }

    def _calculate_consistency(self, statuses: List[str]) -> float:
        """Calculate consistency of status sequence"""
        if not statuses:
            return 0.0
        
        same_count = 0
        for i in range(1, len(statuses)):
            if statuses[i] == statuses[i-1]:
                same_count += 1
        
        return same_count / (len(statuses) - 1) if len(statuses) > 1 else 1.0

    def _count_status_transitions(self, buffer_list: List[MaskObservation]) -> int:
        """Count status transitions (for information only)"""
        transitions = 0
        for i in range(1, len(buffer_list)):
            if buffer_list[i].status != buffer_list[i-1].status:
                transitions += 1
        return transitions

    def _check_movement_stability(self, bbox_history: List[List]) -> bool:
        """Check if movement is stable (not jumping around)"""
        if len(bbox_history) < 3:
            return True
        
        # Calculate center points
        centers = []
        for bbox in bbox_history[-5:]:
            if len(bbox) == 4:
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2
                centers.append((cx, cy))
        
        if len(centers) < 2:
            return True
        
        # Check for large jumps
        for i in range(1, len(centers)):
            dx = centers[i][0] - centers[i-1][0]
            dy = centers[i][1] - centers[i-1][1]
            distance = np.sqrt(dx*dx + dy*dy)
            
            # If jump is too large relative to bbox size
            if len(bbox_history[i]) == 4:
                bbox_width = bbox_history[i][2] - bbox_history[i][0]
                if distance > bbox_width * 0.5:
                    return False
        
        return True

    def _get_default_status(self) -> Dict:
        """Return default status for empty buffer"""
        return {
            'mask_status': MaskStatus.UNKNOWN.value,
            'mask_confidence': 0.0,
            'verification_progress': 0.0,
            'frames_processed': 0,
            'is_stable': False,
            'has_contradictions': False,
            'stability_score': 0.0,
            'temporal_analysis': {},
            'spatial_analysis': {'score': 0.0, 'stable': False},
            'confidence_analysis': {'mean': 0.0, 'std': 0.0, 'trend': 'stable'}
        }

    def get_label_weights(self, track_id: str = None) -> Dict:
        """
        Get current label weights for tracking system behavior
        """
        if track_id:
            track = self.tracks.get(track_id)
            if track:
                return track.label_weights
            return {MaskStatus.MASK.value: 0.5, MaskStatus.NO_MASK.value: 0.7}
        
        # Return average weights across all tracks
        if not self.tracks:
            return {'mask': 0.5, 'no_mask': 0.7}
        
        mask_weights = []
        no_mask_weights = []
        
        for track in self.tracks.values():
            if track.label_weights:
                mask_weights.append(track.label_weights.get(MaskStatus.MASK.value, 0.5))
                no_mask_weights.append(track.label_weights.get(MaskStatus.NO_MASK.value, 0.5))
        
        avg_mask = np.mean(mask_weights) if mask_weights else 0.5
        avg_no_mask = np.mean(no_mask_weights) if no_mask_weights else 0.5
        
        return {
            'average_mask_weight': avg_mask,
            'average_no_mask_weight': avg_no_mask,
            'total_tracks': len(self.tracks)
        }
    
    def reset_label_weights(self, track_id: str = None) -> None:
        """
        Reset label weights to initial values (useful for testing)
        """
        if track_id:
            if track_id in self.tracks:
                self.tracks[track_id].label_weights = {
                    MaskStatus.MASK.value: 0.50,
                    MaskStatus.NO_MASK.value: 0.70
                }
        else:
            for track in self.tracks.values():
                track.label_weights = {
                    MaskStatus.MASK.value: 0.50,
                    MaskStatus.NO_MASK.value: 0.70
                }

    def get_stats(self) -> Dict:
        """Get detector statistics"""
        total_tracks = len(self.tracks)
        state_counts = defaultdict(int)
        stability_scores = []
        
        for track_id, track in self.tracks.items():
            if track.buffer:
                last_obs = track.buffer[-1]
                state_counts[last_obs.status.value] += 1
            stability_scores.append(track.stability_score)
        
        # Add holding statistics
        holding_stats = {
            'tracks_in_holding': 0,
            'mask_held': 0,
            'no_mask_held': 0
        }
        
        current_time = time.time()
        for track in self.tracks.values():
            if track.committed_status in (MaskStatus.MASK, MaskStatus.NO_MASK):
                time_since_commit = current_time - track.commit_time
                if time_since_commit < self.state_hold_duration:
                    holding_stats['tracks_in_holding'] += 1
                    if track.committed_status == MaskStatus.MASK:
                        holding_stats['mask_held'] += 1
                    else:
                        holding_stats['no_mask_held'] += 1
        
        return {
            'total_tracks': total_tracks,
            'state_counts': dict(state_counts),
            'average_stability': np.mean(stability_scores) if stability_scores else 0.0,
            'stable_tracks': len([s for s in stability_scores if s > 0.7]),
            'active_buffers': sum(1 for t in self.tracks.values() if len(t.buffer) > 0),
            'holding_stats': holding_stats  
        }

    def cleanup_expired_tracks(self, current_time: Optional[float] = None) -> None:
        """Clean up tracks that haven't been seen for too long"""
        if current_time is None:
            current_time = time.time()
            
        expired_tracks = []
        
        for track_id, track in self.tracks.items():
            if current_time - track.last_seen > self.occlusion_timeout:
                expired_tracks.append(track_id)
        
        for track_id in expired_tracks:
            self._remove_track(track_id)

    def _remove_track(self, track_id: str) -> None:
        """Remove a track from all buffers"""
        if track_id in self.tracks:
            del self.tracks[track_id]

    def get_track_info(self, track_id: str) -> Optional[Dict]:
        """Get detailed information about a specific track"""
        if track_id not in self.tracks:
            return None
            
        track = self.tracks[track_id]
        
        return {
            'buffer_size': len(track.buffer),
            'last_seen': track.last_seen,
            'stability_score': track.stability_score,
            'committed_status': track.committed_status.value,
            'label_weights': track.label_weights,
            'bbox_history_size': len(track.bbox_history),
            'holding_buffer_size': len(track.holding_buffer),
            'instability_count': track.instability_count
        }