# tracking/bytetrack_wrapper.py

import numpy as np
from typing import List, Optional, Dict

class ByteTrackWrapper:
    """Wrapper for ByteTrack to standardize interface"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.tracker = None
        self._initialize_tracker(config)
    
    def _initialize_tracker(self, config: Dict):
        """Initialize the actual ByteTrack tracker"""
        try:
            # Try to import from your existing tracking module
            from tracking.bytetrack import ByteTrack
            self.tracker = ByteTrack(
                track_thresh=config.get('track_thresh', 0.5),
                track_buffer=config.get('track_buffer', 30),
                match_thresh=config.get('match_thresh', 0.8),
                frame_rate=config.get('frame_rate', 10)
            )
        except ImportError:
            # Fallback to external ByteTrack
            try:
                from bytetracker import BYTETracker
                self.tracker = BYTETracker(
                    track_thresh=config.get('track_thresh', 0.5),
                    track_buffer=config.get('track_buffer', 30),
                    match_thresh=config.get('match_thresh', 0.8),
                    frame_rate=config.get('frame_rate', 10)
                )
            except ImportError:
                raise ImportError("ByteTrack not available in tracking module or as external package")
    
    def update(self, detections: np.ndarray, frame: Optional[np.ndarray] = None) -> List:
        """Update tracker with new detections"""
        if self.tracker is None:
            return []
        
        # Convert detections to expected format and update
        if hasattr(self.tracker, 'update'):
            return self.tracker.update(detections, frame)
        else:
            # Handle different interface variations
            return self.tracker.update(detections)
    
    def update_params(self, params: Dict):
        """Update tracker parameters"""
        for key, value in params.items():
            if hasattr(self.tracker, key):
                setattr(self.tracker, key, value)
    
    def cleanup(self):
        """Clean up tracker resources"""
        if hasattr(self.tracker, 'cleanup'):
            self.tracker.cleanup()
        self.tracker = None