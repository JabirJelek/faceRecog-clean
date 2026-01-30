# processing/face_detection.py

"""
Face detection system using YOLO model.
"""

import cv2
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from ultralytics import YOLO

class FaceDetectionSystem:
    """Handles face detection using YOLO model with optimization."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.detection_model = None
        self.model_loaded = False
        
        # Detection parameters
        self.detection_confidence = config.get('detection_confidence', 0.6)
        self.detection_iou = config.get('detection_iou', 0.6)
        self.max_faces_per_frame = config.get('max_faces_per_frame', 10)
        self.min_face_size = config.get('min_face_size', 40)
        self.roi_padding = config.get('roi_padding', 20)
        
        # Performance tracking
        self.detection_times = []
        self.total_detections = 0
        self.failed_detections = 0
        
        self.logger = logging.getLogger(__name__)
        
        # GPU optimization - set device and precision
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.logger.info(f"Using device: {self.device}")
        
        # Load model during initialization
        self._load_detection_model()

    def _load_detection_model(self) -> bool:
        """Load YOLO face detection model from local path with GPU optimization."""
        try:
            model_path = Path(self.config['detection_model_path'])
            if not model_path.exists():
                raise FileNotFoundError(f"YOLO model not found at {model_path}")
                
            self.detection_model = YOLO(str(model_path))
            
            # GPU OPTIMIZATION: Move model to GPU and set to FP16
            self.detection_model.to(self.device)
            if self.device.type == 'cuda':
                self.detection_model.half()  # Convert model to half-precision
                self.logger.info("✅ YOLO model set to FP16 on CUDA for GTX 1650 Ti")
            
            self.model_loaded = True
            self.logger.info(f"YOLO model loaded from {model_path}")
            
            # Test model with a dummy input to verify it works
            self._verify_model()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            self.model_loaded = False
            return False

    def _verify_model(self):
        """Verify that the model is working with a test inference."""
        try:
            # Create a dummy image for testing
            dummy_image = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
            
            # GPU OPTIMIZATION: Move test input to GPU
            with torch.no_grad():
                if self.device.type == 'cuda':
                    dummy_tensor = torch.from_numpy(dummy_image).to(self.device).half()
                else:
                    dummy_tensor = torch.from_numpy(dummy_image).to(self.device)
                
                # Run inference
                results = self.detection_model(
                    dummy_tensor, 
                    conf=0.5,
                    verbose=False
                )
            
            self.logger.info("Model verification successful")
            
        except Exception as e:
            self.logger.error(f"Model verification failed: {e}")
            raise

    def detect_faces(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect faces in the given frame using YOLO with GPU optimization.
        
        Args:
            frame: Input image frame
            
        Returns:
            List of detection results with bounding boxes and confidence
        """
        if not self.model_loaded or self.detection_model is None:
            self.logger.error("Detection model not loaded")
            return []
        
        import time
        start_time = time.time()
        
        try:
            # GPU OPTIMIZATION: Move frame to GPU and convert to FP16
            with torch.no_grad():  # Disable gradient calculation for inference
                if self.device.type == 'cuda':
                    # Convert numpy array to PyTorch tensor, send to GPU, and convert to FP16
                    frame_tensor = torch.from_numpy(frame).to(self.device).half()
                else:
                    frame_tensor = torch.from_numpy(frame).to(self.device)
                
                # Run YOLO inference on GPU
                results = self.detection_model(
                    frame_tensor, 
                    conf=self.detection_confidence,
                    iou=self.detection_iou,
                    verbose=False,
                    max_det=self.max_faces_per_frame
                )
            
            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        
                        # Convert to integers
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                        
                        # Check minimum face size
                        face_width = x2 - x1
                        face_height = y2 - y1
                        if (face_width >= self.min_face_size and 
                            face_height >= self.min_face_size):
                            
                            detections.append({
                                'bbox': [x1, y1, x2, y2],
                                'confidence': float(confidence),
                                'width': face_width,
                                'height': face_height,
                                'area': face_width * face_height
                            })
            
            # Sort by confidence (highest first)
            detections.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Limit to max faces
            if len(detections) > self.max_faces_per_frame:
                detections = detections[:self.max_faces_per_frame]
            
            # Update performance metrics
            detection_time = (time.time() - start_time) * 1000
            self.detection_times.append(detection_time)
            self.total_detections += len(detections)
            
            if len(detections) == 0:
                self.failed_detections += 1
            
            self.logger.debug(
                f"Detected {len(detections)} faces in {detection_time:.1f}ms"
            )
            
            return detections
            
        except Exception as e:
            self.logger.error(f"Face detection error: {e}")
            self.failed_detections += 1
            return []

    def extract_face_roi(self, frame: np.ndarray, bbox: List[int], 
                        apply_padding: bool = True) -> Optional[np.ndarray]:
        """
        Extract face region of interest from the frame.
        
        Args:
            frame: Original frame
            bbox: Bounding box [x1, y1, x2, y2]
            apply_padding: Whether to apply padding around the face
            
        Returns:
            Extracted face ROI or None if invalid
        """
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        
        if apply_padding:
            # Apply padding
            padding = self.roi_padding
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)
        else:
            x1_pad, y1_pad, x2_pad, y2_pad = x1, y1, x2, y2
        
        # Extract ROI
        face_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
        
        # Validate ROI
        if (face_roi.size == 0 or face_roi.shape[0] < 20 or face_roi.shape[1] < 20 or
            np.std(face_roi) < 10):  # Check for low contrast
            return None
        
        return face_roi

    def preprocess_face_roi(self, face_roi: np.ndarray, 
                           target_size: Tuple[int, int] = (160, 160)) -> np.ndarray:
        """
        Preprocess face ROI for recognition.
        
        Args:
            face_roi: Face region of interest
            target_size: Target size for preprocessing
            
        Returns:
            Preprocessed face image
        """
        try:
            # Resize to target size
            resized = cv2.resize(face_roi, target_size, interpolation=cv2.INTER_AREA)
            
            # Convert to RGB if needed
            if len(resized.shape) == 3 and resized.shape[2] == 3:
                # Already BGR, convert to RGB for most models
                rgb_face = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            else:
                rgb_face = resized
            
            # Normalize pixel values to [0, 1]
            normalized_face = rgb_face.astype(np.float32) / 255.0
            
            return normalized_face
            
        except Exception as e:
            self.logger.error(f"Face preprocessing error: {e}")
            return face_roi

    def get_detection_statistics(self) -> Dict[str, Any]:
        """Get detection performance statistics."""
        if not self.detection_times:
            avg_time = 0
            p95_time = 0
        else:
            avg_time = np.mean(self.detection_times)
            p95_time = np.percentile(self.detection_times, 95)
        
        total_attempts = self.total_detections + self.failed_detections
        success_rate = (self.total_detections / total_attempts * 100) if total_attempts > 0 else 0
        
        return {
            'total_detections': self.total_detections,
            'failed_detections': self.failed_detections,
            'success_rate': success_rate,
            'avg_detection_time_ms': avg_time,
            'p95_detection_time_ms': p95_time,
            'model_loaded': self.model_loaded,
            'recent_detection_count': len(self.detection_times),
            'device': str(self.device),
            'precision': 'FP16' if self.device.type == 'cuda' else 'FP32'
        }

    def optimize_detection_parameters(self, current_performance: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize detection parameters based on current performance.
        
        Args:
            current_performance: Current performance metrics
            
        Returns:
            Updated parameters
        """
        optimized_params = {
            'detection_confidence': self.detection_confidence,
            'detection_iou': self.detection_iou
        }
        
        # Adjust confidence based on detection count
        detection_count = current_performance.get('detection_count', 0)
        avg_face_size = current_performance.get('avg_face_size', 0)
        
        if detection_count == 0:
            # No detections - lower confidence threshold
            optimized_params['detection_confidence'] = max(0.3, self.detection_confidence - 0.1)
        elif detection_count > 5 and avg_face_size > 100:
            # Many large faces - can increase confidence for better quality
            optimized_params['detection_confidence'] = min(0.8, self.detection_confidence + 0.05)
        
        # Adjust IoU based on overlapping detections
        if current_performance.get('overlap_ratio', 0) > 0.3:
            # Many overlapping detections - increase IoU
            optimized_params['detection_iou'] = min(0.8, self.detection_iou + 0.1)
        
        return optimized_params

    def apply_detection_parameters(self, parameters: Dict[str, Any]):
        """Apply optimized detection parameters."""
        if 'detection_confidence' in parameters:
            self.detection_confidence = parameters['detection_confidence']
        if 'detection_iou' in parameters:
            self.detection_iou = parameters['detection_iou']
        
        self.logger.info(
            f"Updated detection parameters: confidence={self.detection_confidence:.2f}, "
            f"iou={self.detection_iou:.2f}"
        )

    def reset_statistics(self):
        """Reset performance statistics."""
        self.detection_times.clear()
        self.total_detections = 0
        self.failed_detections = 0
        self.logger.info("Detection statistics reset")

    def is_model_loaded(self) -> bool:
        """Check if detection model is loaded and ready."""
        return self.model_loaded and self.detection_model is not None