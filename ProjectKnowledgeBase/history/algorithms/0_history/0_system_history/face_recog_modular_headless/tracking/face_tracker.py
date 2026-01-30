# tracking/face_tracker.py
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import defaultdict, deque

class SimpleFaceTracker:
    def __init__(self, confidence_frames=20, cooldown_seconds=20, min_iou=0.3):
        self.confidence_frames = confidence_frames
        self.cooldown_frames = cooldown_seconds * 30  # Convert to frames
        self.min_iou = min_iou
        self.active_tracks = {}
        self.next_track_id = 0
        
    def _calculate_iou(self, box1, box2):
        """Calculate Intersection over Union"""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection area
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        intersection = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        # Calculate union area
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _find_best_match(self, bbox, current_tracks):
        """Find best matching track for a detection"""
        best_match_id = None
        best_iou = self.min_iou
        
        for track_id, track in current_tracks.items():
            iou = self._calculate_iou(bbox, track['current_bbox'])
            if iou > best_iou:
                best_iou = iou
                best_match_id = track_id
        
        return best_match_id
    
    def _create_track(self, result, frame_count):
        """Create a new track from recognition result"""
        return {
            'identity': result['identity'],
            'recognition_confidence': result['recognition_confidence'],
            'detection_confidence': result['detection_confidence'],
            'current_bbox': result['bbox'],
            'confidence_count': 1 if result['identity'] else 0,
            'first_detected_frame': frame_count,
            'last_updated_frame': frame_count,
            'cooldown_counter': 0,
            'track_state': 'TRACKING'  # TRACKING, COOLDOWN, EXPIRED
        }
    
    def _update_track(self, track, new_result, frame_count):
        """Update existing track with new recognition"""
        updated_track = track.copy()
        updated_track['current_bbox'] = new_result['bbox']
        updated_track['last_updated_frame'] = frame_count
        
        # Only update identity if we have a good recognition
        if new_result['identity'] and new_result['recognition_confidence'] > 0.6:
            if new_result['identity'] == track['identity']:
                # Same identity - increase confidence
                updated_track['confidence_count'] += 1
                updated_track['recognition_confidence'] = new_result['recognition_confidence']
            else:
                # Different identity - reset if more confident
                if new_result['recognition_confidence'] > track['recognition_confidence']:
                    updated_track['identity'] = new_result['identity']
                    updated_track['recognition_confidence'] = new_result['recognition_confidence']
                    updated_track['confidence_count'] = 1
        
        # Check if we should enter cooldown mode
        if (updated_track['confidence_count'] >= self.confidence_frames and 
            updated_track['track_state'] == 'TRACKING'):
            updated_track['track_state'] = 'COOLDOWN'
            updated_track['cooldown_counter'] = self.cooldown_frames
        
        return updated_track
    
    def _update_cooldowns(self, updated_tracks, frame_count):
        """Update cooldown counters and handle state transitions"""
        for track_id, track in list(updated_tracks.items()):
            if track['track_state'] == 'COOLDOWN':
                track['cooldown_counter'] -= 1
                
                # Reset to tracking when cooldown ends
                if track['cooldown_counter'] <= 0:
                    track['track_state'] = 'TRACKING'
                    track['confidence_count'] = 0  # Reset for new recognition cycle
    
    def _get_final_results(self, original_results):
        """Generate final results with tracking overrides"""
        final_results = []
        
        for result in original_results:
            # Find if this result matches any track
            matched_track_id = self._find_best_match(result['bbox'], self.active_tracks)
            
            if matched_track_id and self.active_tracks[matched_track_id]['track_state'] == 'COOLDOWN':
                # Use track identity during cooldown
                track = self.active_tracks[matched_track_id]
                final_result = result.copy()
                final_result['identity'] = track['identity']
                final_result['recognition_confidence'] = track['recognition_confidence']
                final_result['track_id'] = matched_track_id
                final_result['track_state'] = 'COOLDOWN'
            else:
                # Use original recognition
                final_result = result.copy()
                if matched_track_id:
                    final_result['track_id'] = matched_track_id
                    final_result['track_state'] = self.active_tracks[matched_track_id]['track_state']
                else:
                    final_result['track_state'] = 'NEW'
            
            final_results.append(final_result)
        
        return final_results
    
    def update(self, recognition_results, frame_count):
        """Main update method"""
        if not recognition_results:
            # No detections - update cooldowns on existing tracks
            self._update_cooldowns(self.active_tracks, frame_count)
            return []
        
        # Update existing tracks and create new ones
        updated_tracks = {}
        
        for result in recognition_results:
            matched_track_id = self._find_best_match(result['bbox'], self.active_tracks)
            
            if matched_track_id is not None:
                # Update existing track
                track = self._update_track(self.active_tracks[matched_track_id], result, frame_count)
                updated_tracks[matched_track_id] = track
            else:
                # Create new track
                track_id = self.next_track_id
                self.next_track_id += 1
                new_track = self._create_track(result, frame_count)
                updated_tracks[track_id] = new_track
        
        # Update cooldowns and handle state transitions
        self._update_cooldowns(updated_tracks, frame_count)
        
        # Remove tracks that haven't been updated (missed detections)
        current_tracks = {}
        for track_id, track in updated_tracks.items():
            # Keep tracks for a few frames even if not detected
            if frame_count - track['last_updated_frame'] <= 5:  # 5 frame tolerance
                current_tracks[track_id] = track
        
        self.active_tracks = current_tracks
        
        return self._get_final_results(recognition_results)
    
    def get_tracking_stats(self) -> Dict:
        """Get tracking statistics"""
        tracking_count = sum(1 for track in self.active_tracks.values() 
                           if track['track_state'] == 'TRACKING')
        cooldown_count = sum(1 for track in self.active_tracks.values() 
                           if track['track_state'] == 'COOLDOWN')
        
        return {
            'total_tracks': len(self.active_tracks),
            'tracking_count': tracking_count,
            'cooldown_count': cooldown_count,
            'next_track_id': self.next_track_id
        }
    
    def reset(self):
        """Reset all tracks"""
        self.active_tracks = {}
        self.next_track_id = 0

    def cleanup_old_tracks(self, frame_count, max_age_frames=300):
        """Remove tracks that haven't been updated for a while"""
        current_tracks = {}
        for track_id, track in self.active_tracks.items():
            if frame_count - track['last_updated_frame'] <= max_age_frames:
                current_tracks[track_id] = track
        self.active_tracks = current_tracks