# visualization/annotation_renderer.py
"""
Functions for drawing annotations and debug information on frames.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Optional

def draw_results(frame: np.ndarray, results: List[Dict], original_frame_size: tuple = None):
    """Draw recognition results on frame."""
    if frame is None or frame.size == 0:
        return
    if not results:
        return frame
    
    h, w = frame.shape[:2]
    for result in results:
        x1, y1, x2, y2 = result['bbox']
        
        # Clip to frame edges
        x1 = max(0, min(x1, w-1))
        y1 = max(0, min(y1, h-1))
        x2 = max(x1+1, min(x2, w))   # ensure width >=1
        y2 = max(y1+1, min(y2, h))
                    
        identity = result['identity']
        mask_status = result.get('mask_status', 'unknown')
        mask_conf = result.get('mask_confidence', 0.0)
        rec_conf = result.get('recognition_confidence', 0.0)
        
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
        rect_x1 = x1
        rect_y1 = max(0, y1 - label_size[1] - 10)
        rect_x2 = min(w, x1 + label_size[0])
        rect_y2 = y1
        if rect_x2 > rect_x1 and rect_y2 > rect_y1:
            cv2.rectangle(frame, (rect_x1, rect_y1), (rect_x2, rect_y2), color, -1)
        
        # Draw label text
        cv2.putText(frame, label, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

def draw_debug_info(frame: np.ndarray, fps: float, frame_count: int, processing_count: int):
    if frame is None or frame.size == 0:
        return
    h, w = frame.shape[:2]
    debug_lines = [
        f"FPS: {fps:.1f}",
        f"Frame: {frame_count}",
        f"Processed: {processing_count}",
    ]
    overlay = frame.copy()
    rect_x1, rect_y1 = 10, 10
    rect_x2 = min(250, w - 10)
    rect_y2 = min(10 + len(debug_lines) * 25 + 10, h - 10)
    if rect_x2 > rect_x1 and rect_y2 > rect_y1:
        cv2.rectangle(overlay, (rect_x1, rect_y1), (rect_x2, rect_y2), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    for i, line in enumerate(debug_lines):
        y_position = 30 + (i * 25)
        if y_position < h - 10:
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
def draw_detection_debug(frame: np.ndarray, results: List[Dict]):
    if frame is None or frame.size == 0 or not results:
        return
    h, w = frame.shape[:2]
    for result in results:
        x1, y1, x2, y2 = result['bbox']
        x1 = max(0, min(x1, w-1))
        y1 = max(0, min(y1, h-1))
        x2 = max(x1+1, min(x2, w))
        y2 = max(y1+1, min(y2, h))
        
        det_conf = result.get('detection_confidence', 0.0)
        identity = result.get('identity', None)
        rec_conf = result.get('recognition_confidence', 0.0)
        
        info_text = f"Det: {det_conf:.2f}"
        if identity:
            info_text += f" | Rec: {identity} ({rec_conf:.2f})"
        
        text_y = y2 + 20
        if text_y + 25 > h:  # if too low, place above instead
            text_y = y1 - 25
        text_size = cv2.getTextSize(info_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        rect_x2 = min(x1 + text_size[0], w - 5)
        rect_y2 = min(text_y + 5, h - 5)
        if rect_x2 > x1 and rect_y2 > text_y - text_size[1] - 5:
            cv2.rectangle(frame, (x1, text_y - text_size[1] - 5), 
                         (rect_x2, rect_y2), (0, 0, 0), -1)
        cv2.putText(frame, info_text, (x1, text_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
def draw_mask_debug_info(frame: np.ndarray, results: List[Dict]):
    if frame is None or frame.size == 0 or not results:
        return
    h, w = frame.shape[:2]
    for result in results:
        x1, y1, x2, y2 = result['bbox']
        x1 = max(0, min(x1, w-1))
        y1 = max(0, min(y1, h-1))
        x2 = max(x1+1, min(x2, w))
        y2 = max(y1+1, min(y2, h))
        
        mask_status = result.get('mask_status', 'unknown')
        mask_conf = result.get('mask_confidence', 0.0)
        status_text = f"Mask: {mask_status}({mask_conf:.2f})"
        
        text_y = y1 - 35
        if text_y < 10:  # if too high, place below instead
            text_y = y2 + 20
        
        if mask_status == "mask":
            color = (0, 255, 0)
        elif mask_status == "no_mask":
            color = (0, 0, 255)
        else:
            color = (255, 255, 0)
        
        text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        rect_x2 = min(x1 + text_size[0], w - 5)
        rect_y1 = max(0, text_y - text_size[1] - 5)
        rect_y2 = min(text_y + 5, h - 5)
        if rect_x2 > x1 and rect_y2 > rect_y1:
            cv2.rectangle(frame, (x1, rect_y1), (rect_x2, rect_y2), (0, 0, 0), -1)
        cv2.putText(frame, status_text, (x1, text_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        

def draw_dynamic_adjustment_info(frame: np.ndarray, scale: float, performance: Dict):
    """Display dynamic adjustment metrics."""
    if frame is None or frame.size == 0:
        return
    h, w = frame.shape[:2]
    info_lines = [
        f"Dynamic Scale: {scale:.2f}",
        f"Faces: {performance.get('detection_count', 0)}",
        f"Quality: {performance.get('detection_quality', 0):.2f}",
    ]
    start_y = h - len(info_lines) * 25 - 20
    if start_y < 10:
        start_y = 10
    
    overlay = frame.copy()
    rect_x1, rect_y1 = 10, start_y
    rect_x2 = min(300, w - 10)
    rect_y2 = min(h - 10, start_y + len(info_lines) * 25 + 20)
    if rect_x2 > rect_x1 and rect_y2 > rect_y1:
        cv2.rectangle(overlay, (rect_x1, rect_y1), (rect_x2, rect_y2), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    
    for i, line in enumerate(info_lines):
        y_position = start_y + 20 + (i * 20)
        if y_position < h - 5:
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
