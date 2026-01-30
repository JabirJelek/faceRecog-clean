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
        
        # Performance tracking
        self.detection_times = []
        self.total_detections = 0
        self.failed_detections = 0
        
        self.logger = logging.getLogger(__name__)
        
        # GPU optimization - safe device selection
        self.device = self._get_safe_device()
        self.logger.info(f"Using device: {self.device}")
        
        # Load model
        self._load_detection_model()
        
    def _get_safe_device(self):
        """Safely determine device (GPU/CPU) with memory considerations"""
        try:
            if torch.cuda.is_available():
                # Check available GPU memory
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9  # GB
                
                # For GTX 1650 Ti (4GB), use FP16 only if we have enough memory
                if gpu_memory >= 3.5:  # Conservative threshold
                    device = torch.device('cuda')
                    self.logger.info(f"GPU available: {gpu_memory:.1f}GB, using CUDA with FP16")
                else:
                    device = torch.device('cuda')
                    self.logger.info(f"GPU available: {gpu_memory:.1f}GB, using CUDA with FP32")
            else:
                device = torch.device('cpu')
                self.logger.info("Using CPU")
                
            return device
        except Exception as e:
            self.logger.warning(f"Failed to initialize GPU: {e}, falling back to CPU")
            return torch.device('cpu')        
        
    def _load_detection_model(self) -> bool:
        """Load YOLO face detection model with safe GPU initialization"""
        try:
            model_path = Path(self.config['detection_model_path'])
            if not model_path.exists():
                raise FileNotFoundError(f"YOLO model not found at {model_path}")
            
            # Load model
            self.detection_model = YOLO(str(model_path))
            self.detection_model.to(self.device)
            
            # Conditional FP16 - only for GPUs with sufficient memory
            if self.device.type == 'cuda':
                try:
                    # Test if FP16 works without memory issues
                    with torch.no_grad():
                        dummy = torch.randn(1, 3, 320, 320).to(self.device).half()
                        _ = self.detection_model(dummy, verbose=False, max_det=1)
                    
                    # If test passes, enable FP16
                    self.detection_model.half()
                    self.logger.info("✅ YOLO model set to FP16")
                except RuntimeError as e:
                    if "CUDA out of memory" in str(e):
                        self.logger.warning("FP16 causes OOM, falling back to FP32")
                        torch.cuda.empty_cache()
                        self.detection_model.float()
                    else:
                        raise
            
            self.model_loaded = True
            self.logger.info(f"YOLO model loaded successfully")
            
            # Verify model with safe mode (won't raise exceptions)
            verification_passed = self._verify_model(mode='safe')
            
            if not verification_passed:
                self.logger.warning("Model verification had issues but will continue")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            self.model_loaded = False
            return False
         
    def _verify_model(self, mode: str = 'safe') -> bool:
        """
        Verify that the model is working correctly.
        
        Args:
            mode: 'safe' for memory-safe verification (doesn't raise),
                'strict' for thorough verification (raises on failure)
        
        Returns:
            bool: True if verification passed, False otherwise
        """
        try:
            # Choose image size based on mode
            if mode == 'safe':
                # Safe mode: small image for memory-constrained GPUs
                img_size = 320
                max_detections = 1
                raise_on_failure = False
            else:  # 'strict' mode
                # Strict mode: standard size for thorough verification
                img_size = 640
                max_detections = 10
                raise_on_failure = True
            
            # Create dummy image
            dummy_image = np.random.randint(0, 255, (img_size, img_size, 3), dtype=np.uint8)
            
            with torch.no_grad():
                # Use appropriate precision based on model
                if self.device.type == 'cuda' and hasattr(self.detection_model, 'half'):
                    dummy_tensor = torch.from_numpy(dummy_image).to(self.device).half()
                else:
                    dummy_tensor = torch.from_numpy(dummy_image).to(self.device).float()
                
                # Run inference with mode-specific settings
                results = self.detection_model(
                    dummy_tensor, 
                    conf=0.5,
                    verbose=False,
                    max_det=max_detections
                )
            
            self.logger.info(f"Model verification successful ({mode} mode)")
            return True
            
        except Exception as e:
            error_msg = f"Model verification failed ({mode} mode): {e}"
            
            if raise_on_failure:
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                self.logger.warning(error_msg)
                # In safe mode, allow model to be used anyway
                return False
            
    def detect_faces(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect faces with memory-safe GPU operations
        """
        if not self.model_loaded or self.detection_model is None:
            self.logger.error("Detection model not loaded")
            return []
        
        import time
        start_time = time.time()
        
        try:
            # Clear GPU cache before inference
            if self.device.type == 'cuda':
                torch.cuda.empty_cache()
            
            with torch.no_grad():
                # Convert to tensor
                if self.device.type == 'cuda' and hasattr(self.detection_model, 'half'):
                    # Use half precision if available
                    frame_tensor = torch.from_numpy(frame).to(self.device).half()
                else:
                    frame_tensor = torch.from_numpy(frame).to(self.device).float()
                
                # Run inference with memory limits
                results = self.detection_model(
                    frame_tensor, 
                    conf=self.detection_confidence,
                    iou=self.detection_iou,
                    verbose=False,
                    max_det=10,  # Limit detections
                    half=self.device.type == 'cuda' and self.detection_model.dtype == torch.float16
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