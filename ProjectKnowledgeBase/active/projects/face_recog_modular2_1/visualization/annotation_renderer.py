# visualization/annotation_renderer.py
"""
Functions for drawing annotations and debug information on frames.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Optional

def draw_results(frame: np.ndarray, results: List[Dict], original_frame_size: tuple = None):
    """Draw recognition results on frame."""
    for result in results:
        x1, y1, x2, y2 = result['bbox']
        identity = result['identity']
        rec_conf = result['recognition_confidence']
        mask_status = result.get('mask_status', 'unknown')
        
        # Color coding based on mask status and recognition
        if identity:
            color = (0, 255, 0) if mask_status == "mask" else (0, 255, 255)  # Green/Yellow
        else:
            color = (255, 255, 0) if mask_status == "mask" else (0, 0, 255)  # Cyan/Red
        
        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Prepare label
        label = f"{identity or 'Unknown'} ({rec_conf:.2f}) | Mask: {mask_status}"
        
        # Draw label background
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0], y1), color, -1)
        
        # Draw label text
        cv2.putText(frame, label, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

def draw_debug_info(frame: np.ndarray, fps: float, frame_count: int, processing_count: int):
    """Draw debug information on frame."""
    debug_lines = [
        f"FPS: {fps:.1f}",
        f"Frame: {frame_count}",
        f"Processed: {processing_count}",
    ]
    
    # Draw background
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (250, 10 + len(debug_lines) * 25 + 10), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    
    # Draw text
    for i, line in enumerate(debug_lines):
        y_position = 30 + (i * 25)
        cv2.putText(frame, line, (20, y_position),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

def draw_detection_debug(frame: np.ndarray, results: List[Dict]):
    """Draw detailed detection debugging information."""
    for i, result in enumerate(results):
        x1, y1, x2, y2 = result['bbox']
        
        info_text = f"Det: {result['detection_confidence']:.2f}"
        if result['identity']:
            info_text += f" | Rec: {result['identity']} ({result['recognition_confidence']:.2f})"
        
        # Draw below bounding box
        text_y = y2 + 20
        text_size = cv2.getTextSize(info_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        cv2.rectangle(frame, (x1, text_y - text_size[1] - 5), 
                     (x1 + text_size[0], text_y + 5), (0, 0, 0), -1)
        cv2.putText(frame, info_text, (x1, text_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

def draw_mask_debug_info(frame: np.ndarray, results: List[Dict]):
    """Draw mask detection debug information."""
    for result in results:
        x1, y1, x2, y2 = result['bbox']
        mask_status = result.get('mask_status', 'unknown')
        mask_conf = result.get('mask_confidence', 0.0)
        
        status_text = f"Mask: {mask_status}({mask_conf:.2f})"
        text_y = y1 - 35
        
        # Color code based on mask status
        if mask_status == "mask":
            color = (0, 255, 0)  # Green
        elif mask_status == "no_mask":
            color = (0, 0, 255)  # Red
        else:
            color = (255, 255, 0)  # Yellow
        
        # Draw background and text
        text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        cv2.rectangle(frame, (x1, text_y - text_size[1] - 5), 
                     (x1 + text_size[0], text_y + 5), (0, 0, 0), -1)
        cv2.putText(frame, status_text, (x1, text_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def draw_dynamic_adjustment_info(frame: np.ndarray, scale: float, performance: Dict):
    """Display dynamic adjustment metrics."""
    info_lines = [
        f"Dynamic Scale: {scale:.2f}",
        f"Faces: {performance.get('detection_count', 0)}",
        f"Quality: {performance.get('detection_quality', 0):.2f}",
    ]
    
    # Draw at bottom of frame
    start_y = frame.shape[0] - len(info_lines) * 25 - 20
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, start_y), (300, frame.shape[0] - 10), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    
    for i, line in enumerate(info_lines):
        y_position = start_y + 20 + (i * 20)
        cv2.putText(frame, line, (20, y_position),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)