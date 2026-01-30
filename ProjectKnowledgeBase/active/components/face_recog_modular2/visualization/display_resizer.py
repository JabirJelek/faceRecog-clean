# visualization/display_resizer.py
import cv2
import numpy as np
from typing import Dict, Tuple

class DisplayResizer:
    """Handles multiple resizing strategies for output display"""
    
    def __init__(self):
        self.current_scale = 1.0
        self.resize_method = "fit_to_screen"
        self.target_width = 1280
        self.target_height = 720
        self.maintain_aspect_ratio = True
        self.max_display_size = (1920, 1080)
        
    def resize_frame(self, frame: np.ndarray, method: str = None, 
                    target_size: Tuple[int, int] = None, 
                    scale: float = None) -> np.ndarray:
        if method:
            self.resize_method = method
            
        if target_size:
            self.target_width, self.target_height = target_size
            
        if scale:
            self.current_scale = scale
            
        if self.resize_method == "fit_to_screen":
            return self._fit_to_screen(frame)
        elif self.resize_method == "fixed_size":
            return self._resize_fixed(frame, self.target_width, self.target_height)
        elif self.resize_method == "scale":
            return self._resize_scale(frame, self.current_scale)
        elif self.resize_method == "crop":
            return self._resize_crop(frame, self.target_width, self.target_height)
        elif self.resize_method == "letterbox":
            return self._resize_letterbox(frame, self.target_width, self.target_height)
        else:
            return frame
    
    def _fit_to_screen(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        max_w, max_h = self.max_display_size
        
        scale_w = max_w / w
        scale_h = max_h / h
        scale = min(scale_w, scale_h, 1.0)
        
        if scale == 1.0:
            return frame
            
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    def _resize_fixed(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    
    def _resize_scale(self, frame: np.ndarray, scale: float) -> np.ndarray:
        if scale == 1.0:
            return frame
            
        h, w = frame.shape[:2]
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    def _resize_crop(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        h, w = frame.shape[:2]
        
        target_aspect = width / height
        original_aspect = w / h
        
        if original_aspect > target_aspect:
            new_w = int(h * target_aspect)
            start_x = (w - new_w) // 2
            cropped = frame[:, start_x:start_x + new_w]
        else:
            new_h = int(w / target_aspect)
            start_y = (h - new_h) // 2
            cropped = frame[start_y:start_y + new_h, :]
        
        return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_AREA)
    
    def _resize_letterbox(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        h, w = frame.shape[:2]
        
        scale = min(width / w, height / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        result = np.zeros((height, width, 3), dtype=np.uint8)
        
        pad_x = (width - new_w) // 2
        pad_y = (height - new_h) // 2
        
        result[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
        
        return result
    
    def get_resize_info(self) -> Dict:
        return {
            'method': self.resize_method,
            'target_size': (self.target_width, self.target_height),
            'current_scale': self.current_scale,
            'maintain_aspect_ratio': self.maintain_aspect_ratio,
            'max_display_size': self.max_display_size
        }
