# processing/quality_assessment.py
import cv2
import numpy as np
from typing import Dict, List, Tuple

class FaceQualityAssessor:
    def __init__(self, config: Dict):
        self.config = config
        
    def assess_face_quality(self, face_roi: np.ndarray, bbox: List[int] = None) -> Dict[str, float]:
        """Comprehensive face quality assessment"""
        quality_scores = {}
        
        # 1. Brightness and contrast
        quality_scores['brightness'] = self._assess_brightness(face_roi)
        quality_scores['contrast'] = self._assess_contrast(face_roi)
        
        # 2. Sharpness (Laplacian variance)
        quality_scores['sharpness'] = self._assess_sharpness(face_roi)
        
        # 3. Face size and position
        if bbox:
            # Get only the spatial dimensions from face_roi shape
            spatial_shape = face_roi.shape[:2]  # This gets (height, width) only
            quality_scores['size'] = self._assess_face_size(bbox, spatial_shape)
            quality_scores['position'] = self._assess_face_position(bbox, spatial_shape)
        
        # 4. Blur detection
        quality_scores['blur'] = self._assess_blur(face_roi)
        
        # 5. Overall quality score (weighted combination)
        weights = {
            'brightness': 0.15,
            'contrast': 0.15,
            'sharpness': 0.25,
            'size': 0.20,
            'position': 0.15,
            'blur': 0.10
        }
        
        overall_quality = 0.0
        for metric, score in quality_scores.items():
            if metric in weights:
                overall_quality += weights[metric] * score
        
        quality_scores['overall'] = overall_quality
        
        return quality_scores
    
    def _assess_sharpness(self, face: np.ndarray) -> float:
        """Assess image sharpness using Laplacian variance"""
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Normalize to 0-1 range (typical good values: 100-1000)
        sharpness = min(1.0, laplacian_var / 500.0)
        return sharpness
    
    def _assess_brightness(self, face: np.ndarray) -> float:
        """Assess brightness level"""
        hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
        brightness = np.mean(hsv[:,:,2]) / 255.0
        
        # Ideal brightness is around 0.5, penalize extremes
        brightness_score = 1.0 - abs(brightness - 0.5) * 2.0
        return max(0.0, brightness_score)
    
    def _assess_contrast(self, face: np.ndarray) -> float:
        """Assess contrast using standard deviation"""
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        contrast = np.std(gray) / 255.0
        return min(1.0, contrast * 2.0)  # Normalize
    
    def _assess_blur(self, face: np.ndarray) -> float:
        """Assess blur using FFT"""
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        
        # Compute FFT and shift
        fft = np.fft.fft2(gray)
        fft_shift = np.fft.fftshift(fft)
        
        # Calculate magnitude spectrum
        magnitude = 20 * np.log(np.abs(fft_shift) + 1)
        
        # High-frequency content indicates sharpness
        center_h, center_w = h // 2, w // 2
        high_freq = magnitude[center_h-10:center_h+10, center_w-10:center_w+10]
        high_freq_mean = np.mean(high_freq)
        
        # Normalize to 0-1
        blur_score = min(1.0, high_freq_mean / 30.0)
        return blur_score
    
    def _assess_face_size(self, bbox: List[int], frame_shape: Tuple[int, int]) -> float:
        """Assess if face is large enough for good recognition"""
        x1, y1, x2, y2 = bbox
        face_area = (x2 - x1) * (y2 - y1)
        frame_h, frame_w = frame_shape  # Now this will always be 2 values
        frame_area = frame_h * frame_w
        
        ratio = face_area / frame_area
        
        # Adjusted thresholds for small faces
        if ratio < 0.02:  # Reduced from 0.05 (very small)
            return ratio / 0.02  # More generous scoring
        elif ratio > 0.3:
            return 0.3 / ratio
        else:
            return 1.0
    
    def _assess_face_position(self, bbox: List[int], frame_shape: Tuple[int, int]) -> float:
        """Assess face position in frame"""
        x1, y1, x2, y2 = bbox
        frame_h, frame_w = frame_shape  # Now this will always be 2 values
        
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        
        # Distance from center (normalized)
        dist_x = abs(center_x - frame_w / 2) / (frame_w / 2)
        dist_y = abs(center_y - frame_h / 2) / (frame_h / 2)
        
        # Combined distance
        distance = np.sqrt(dist_x**2 + dist_y**2)
        
        # Score: 1.0 at center, decreasing towards edges
        position_score = max(0.0, 1.0 - distance)
        return position_score

class AdaptiveThresholdManager:
    def __init__(self, config: Dict):
        self.config = config
        self.base_threshold = config.get('recognition_threshold', 0.5)
        self.quality_weights = config.get('quality_weights', {
            'sharpness': 0.3,
            'brightness': 0.2,
            'size': 0.25,
            'position': 0.15,
            'blur': 0.1
        })
        
    def compute_adaptive_threshold(self, quality_scores: Dict[str, float]) -> float:
        """Compute adaptive threshold based on face quality"""
        if not quality_scores:
            return self.base_threshold
        
        # Calculate quality-weighted threshold adjustment
        quality_adjustment = 0.0
        total_weight = 0.0
        
        for metric, weight in self.quality_weights.items():
            if metric in quality_scores:
                # Lower quality -> higher threshold (more strict)
                adjustment = (1.0 - quality_scores[metric]) * weight
                quality_adjustment += adjustment
                total_weight += weight
        
        if total_weight > 0:
            quality_adjustment /= total_weight
        
        # Adaptive threshold: base + adjustment
        adaptive_threshold = self.base_threshold + quality_adjustment * (1.0 - self.base_threshold)
        
        # Clamp to reasonable range
        adaptive_threshold = max(self.base_threshold * 0.5, min(0.95, adaptive_threshold))
        
        return adaptive_threshold
    
    def should_process_face(self, quality_scores: Dict[str, float]) -> bool:
        """Decide whether to process face based on quality"""
        if not quality_scores:
            return True
        
        overall_quality = quality_scores.get('overall', 0.5)
        min_quality = self.config.get('min_face_quality', 0.3)
        
        return overall_quality >= min_quality