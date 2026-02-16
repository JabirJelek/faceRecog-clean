# streaming/frame_utils.py
# Proposed file that can be utilized more in integrating modularity of realtime streaming

"""
Common frame processing utilities for both windowed and headless modes
"""
import cv2
import numpy as np
from typing import Tuple, Optional, Dict, List, Any

class FrameUtils:
    
    @staticmethod
    def resize_for_processing(frame: np.ndarray, scale: float = 1.0, 
                            target_size: Tuple[int, int] = (1600, 900)) -> np.ndarray:
        """Resize frame for processing (face detection/recognition)"""
        if scale != 1.0:
            # Scale-based resizing
            h, w = frame.shape[:2]
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            # Fixed size resizing
            return cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)
    
    @staticmethod
    def enhanced_resize_for_processing(frame: np.ndarray, current_scale: float) -> np.ndarray:
        """Resize frame for processing using dynamic scale with error handling"""
        try:
            if current_scale == 1.0:
                return frame
                
            h, w = frame.shape[:2]
            new_w = max(64, int(w * current_scale))  # Minimum 64px
            new_h = max(64, int(h * current_scale))  # Minimum 64px
            
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        except Exception as e:
            print(f"❌ Error in enhanced_resize_for_processing: {e}")
            return frame  # Fallback to original frame
    
    @staticmethod
    def validate_frame(frame: np.ndarray) -> bool:
        """Validate frame integrity"""
        if frame is None or frame.size == 0:
            return False
            
        if frame.shape[0] < 10 or frame.shape[1] < 10:
            return False
            
        # Check for corrupted frames (all black, all white, etc.)
        frame_mean = np.mean(frame)
        if frame_mean < 10 or frame_mean > 250:
            return False
            
        return True
    
    @staticmethod
    def calculate_frame_stats(frame: np.ndarray) -> Dict[str, float]:
        """Calculate basic frame statistics"""
        if frame is None or frame.size == 0:
            return {
                'mean_brightness': 0.0,
                'std_brightness': 0.0,
                'width': 0,
                'height': 0,
                'channels': 0
            }
        
        stats = {
            'mean_brightness': float(np.mean(frame)),
            'std_brightness': float(np.std(frame)),
            'width': frame.shape[1],
            'height': frame.shape[0]
        }
        
        # Handle different channel configurations
        if len(frame.shape) > 2:
            stats['channels'] = frame.shape[2]
        else:
            stats['channels'] = 1
            
        return stats
    
    @staticmethod
    def normalize_frame(frame: np.ndarray, target_size: Tuple[int, int] = None) -> np.ndarray:
        """Normalize frame for consistent processing"""
        # Convert to RGB if needed
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            # OpenCV uses BGR, convert to RGB for some models
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Resize if target size specified
        if target_size is not None:
            frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)
        
        # Normalize pixel values to [0, 1]
        frame = frame.astype(np.float32) / 255.0
        
        return frame
    
    @staticmethod
    def preprocess_for_detection(frame: np.ndarray, scale: float = 1.0) -> np.ndarray:
        """Preprocess frame specifically for face detection"""
        # Resize for processing
        processed_frame = FrameUtils.enhanced_resize_for_processing(frame, scale)
        
        # Convert to RGB if needed (many face detectors expect RGB)
        if len(processed_frame.shape) == 3 and processed_frame.shape[2] == 3:
            processed_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
        
        return processed_frame
    
    @staticmethod
    def create_debug_frame(original_frame: np.ndarray, results: List[Dict], 
                          debug_info: Dict[str, Any] = None) -> np.ndarray:
        """Create a debug frame with annotations (for both windowed and headless)"""
        debug_frame = original_frame.copy()
        
        # Draw bounding boxes and labels
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            identity = result['identity']
            rec_conf = result['recognition_confidence']
            det_conf = result['detection_confidence']
            mask_status = result.get('mask_status', 'unknown')
            
            # Color coding
            if identity:
                color = (0, 255, 0) if mask_status == "mask" else (0, 255, 255)  # Green/Yellow
            else:
                color = (255, 255, 0) if mask_status == "mask" else (0, 0, 255)  # Cyan/Red
            
            # Draw bounding box
            cv2.rectangle(debug_frame, (x1, y1), (x2, y2), color, 2)
            
            # Prepare label
            if identity:
                label = f"{identity} ({rec_conf:.2f}) | Mask: {mask_status}"
            else:
                label = f"Unknown ({det_conf:.2f}) | Mask: {mask_status}"
            
            # Draw label background
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(debug_frame, (x1, y1 - label_size[1] - 10), 
                         (x1 + label_size[0], y1), color, -1)
            
            # Draw label text
            cv2.putText(debug_frame, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add debug info overlay
        if debug_info:
            FrameUtils._add_debug_overlay(debug_frame, debug_info)
        
        return debug_frame
    
    @staticmethod
    def _add_debug_overlay(frame: np.ndarray, debug_info: Dict[str, Any]):
        """Add debug information overlay to frame"""
        overlay = frame.copy()
        
        # Create semi-transparent background
        h, w = frame.shape[:2]
        cv2.rectangle(overlay, (10, 10), (400, 150), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Add debug text
        y_offset = 30
        for key, value in debug_info.items():
            if y_offset < 140:  # Prevent overflow
                text = f"{key}: {value}"
                cv2.putText(frame, text, (20, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_offset += 20
        