# recognition/base_system.py
import cv2
import json
from pathlib import Path
from ultralytics import YOLO
from deepface import DeepFace
from sklearn.metrics.pairwise import cosine_similarity
import onnxruntime as ort
import numpy as np
from collections import deque
from typing import Dict, List, Tuple, Optional, Any
import time
import torch
import logging

class FaceRecognitionSystem:
    def __init__(self, config: Dict):
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        self.config = config
        self.detection_model = None
        self.mask_detector = None
        self.channel_format = None
        self.mask_input_size = None   
        self.embeddings_db = {}
        self.identity_centroids = {}
        
        # GPU cache cleanup configuration
        self.gpu_cache_cleanup_interval = config.get('gpu_cache_cleanup_interval', 100)
        self._frame_counter = 0        
        
        # ENHANCED: Use circular buffers to prevent memory leaks
        self.debug_stats = {
            'total_frames_processed': 0,
            'total_faces_detected': 0,
            'total_faces_recognized': 0,
            'total_masks_detected': 0,
            'detection_times': deque(maxlen=50),
            'mask_detection_times': deque(maxlen=50),
            'embedding_times': deque(maxlen=50),
            'recognition_times': deque(maxlen=50),
            'last_processing_time': 0
        }
        
        # Check GPU availability and update config
        self._verify_gpu_config()
        
        self._load_models()
        self._load_mask_detector()  
        self._load_embeddings_database()
        
        # Validate config
        self._validate_config()

    def _verify_gpu_config(self):
        """Verify and update GPU configuration based on actual availability"""
        
        if self.config.get('use_gpu', False):
            try:
                device = self.config.get('gpu_device', 0)
                torch_device = f'cuda:{device}'
                self.detection_model.to(torch_device)
                self.logger.info(f"YOLO model loaded on {torch_device}")

                # Verify the model is actually on GPU
                model_device = next(self.detection_model.model.parameters()).device
                self.logger.info(f"YOLO model verified on device: {model_device}")
            except Exception as e:
                self.logger.warning(f"Failed to load YOLO model on GPU ({e}), falling back to CPU")
                self.config['use_gpu'] = False  # Update config to reflect fallback
                # Model is already on CPU (default after loading), no further action needed
        else:
            self.logger.info("YOLO model loaded on CPU")        
        
    def _load_mask_detector(self):
        """Load ONNX mask detection model with GPU support and dynamic input size detection"""
        try:
            mask_model_path = Path(self.config.get('mask_model_path', ''))
            if not mask_model_path.exists():
                self.logger.warning("Mask model not found, continuing without mask detection")
                return
                
            # Set providers for GPU acceleration
            providers = []
            if self.config.get('use_gpu', False):
                # Try CUDA first, then fall back to CPU
                try:
                    providers = [
                        ('CUDAExecutionProvider', {
                            'device_id': self.config.get('gpu_device', 0),
                            'arena_extend_strategy': 'kNextPowerOfTwo',
                            'gpu_mem_limit': 2 * 1024 * 1024 * 1024,  # 2GB limit
                            'cudnn_conv_algo_search': 'EXHAUSTIVE',
                            'do_copy_in_default_stream': True,
                        }),
                        'CPUExecutionProvider'
                    ]
                    self.logger.info("Using CUDA for mask detection")
                except Exception as e:
                    self.logger.warning(f"CUDA not available for mask detection: {e}")
                    providers = ['CPUExecutionProvider']
            else:
                providers = ['CPUExecutionProvider']
                
            # Initialize ONNX Runtime session with providers
            self.mask_detector = ort.InferenceSession(
                str(mask_model_path), 
                providers=providers
            )
            

            input_details = self.mask_detector.get_inputs()[0]
            input_shape = input_details.shape  # e.g., (1, 3, 40, 50) or (1, 40, 50, 3)
            self.mask_input_metadata = {
                'name': input_details.name,
                'shape': input_shape,
                'dtype': input_details.type
            }
            
            # Attempt to infer layout
            if len(input_shape) == 4:
                # batch, channels, height, width (NCHW)
                if input_shape[1] in (1, 3, 4):  # common channel counts
                    self.mask_input_layout = 'NCHW'
                    self.mask_input_size = (input_shape[2], input_shape[3])
                    self.mask_input_channels = input_shape[1]
                # batch, height, width, channels (NHWC)
                elif input_shape[3] in (1, 3, 4):
                    self.mask_input_layout = 'NHWC'
                    self.mask_input_size = (input_shape[1], input_shape[2])
                    self.mask_input_channels = input_shape[3]
                else:
                    # Ambiguous layout – store both possibilities
                    self.mask_input_layout = 'UNKNOWN'
                    self.mask_input_size = (input_shape[1], input_shape[2])  # assume height, width from indices 1,2
                    self.mask_input_channels = input_shape[3] if input_shape[3] in (1,3,4) else 3
            else:
                self.mask_input_layout = 'UNKNOWN'
                self.mask_input_size = (40, 50)  # fallback
                self.mask_input_channels = 3
            
            # Validate model input/output
            input_name = input_details.name
            output_name = self.mask_detector.get_outputs()[0].name
            

            self.logger.info(f"Channel format: {self.channel_format}")
            self.logger.info(f"Input: {input_name}, Output: {output_name}")
            self.logger.info(f"Input shape: {input_shape}")
            self.logger.info(f"Using providers: {[p if isinstance(p, str) else p[0] for p in providers]}")
            
        except Exception as e:
            self.logger.error(f"Failed to load mask detection model: {e}")
            self.mask_detector = None
            self.mask_input_size = None
            # Don't raise exception, continue without mask detection
            
    def _maybe_clean_gpu_cache(self):
        """Periodically clear GPU cache to prevent memory fragmentation."""
        if not torch.cuda.is_available() or self.gpu_cache_cleanup_interval <= 0:
            return
        
        self._frame_counter += 1
        if self._frame_counter >= self.gpu_cache_cleanup_interval:
            torch.cuda.empty_cache()
            self.logger.debug(f"GPU cache cleared after {self._frame_counter} frames")
            self._frame_counter = 0     
                
    def health_check(self) -> Dict[str, Any]:
        """
        Returns the current health status of the recognition system.
        Can be called periodically by external monitoring.
        """
        status = "healthy"
        issues = []
        
        # Check detection model
        if self.detection_model is None:
            issues.append("detection_model_not_loaded")
            status = "unhealthy"
        
        # Check mask detector (optional, but warn if missing)
        mask_ok = self.mask_detector is not None
        if not mask_ok:
            issues.append("mask_detector_not_loaded")
            # Only degrade status, not make it unhealthy (mask detection is optional)
            if status == "healthy":
                status = "degraded"
        
        # Check embeddings database loaded
        if not self.identity_centroids:
            issues.append("no_identities_loaded")
            # Can still function (cold start), but degrade status
            if status == "healthy":
                status = "degraded"
        
        # GPU availability (if configured)
        gpu_available = torch.cuda.is_available()
        if self.config.get('use_gpu', False) and not gpu_available:
            issues.append("gpu_requested_but_unavailable")
            # System may fallback to CPU, so status degraded, not unhealthy
            if status == "healthy":
                status = "degraded"
        
        # Check for recent errors (optional, requires storing last error)
        if hasattr(self, '_last_error') and self._last_error:
            issues.append(f"last_error: {self._last_error}")
            status = "degraded"  # or unhealthy based on severity
        
        return {
            "status": status,
            "timestamp": time.time(),
            "issues": issues,
            "details": {
                "detection_model_loaded": self.detection_model is not None,
                "mask_detector_loaded": mask_ok,
                "identities_count": len(self.identity_centroids),
                "gpu_available": gpu_available,
                "gpu_configured": self.config.get('use_gpu', False),
                "voyager_available": hasattr(self, 'voyager_index') and self.voyager_index is not None,
            }
        }                   
            
    def _validate_config(self):
        """Validate required configuration keys and set defaults for optional ones."""
        required_keys = [
            'detection_model_path',
            'embeddings_db_path',
            'detection_confidence',
            'recognition_threshold'
        ]
        missing_keys = [key for key in required_keys if key not in self.config]
        if missing_keys:
            raise ValueError(f"Missing required configuration keys: {missing_keys}")

        # Set defaults for optional configuration parameters
        defaults = {
            'use_gpu': False,
            'gpu_device': 0,
            'roi_padding': 20,
            'mask_detection_threshold': 0.8,
            'debug': {},
            'embedding_model': 'Facenet',  # or whatever is appropriate
            'detection_iou': 0.5,
            'verbose': False,
            'enable_multi_scale': True,
            'enable_temporal_fusion': True,
            'enable_quality_aware': True,
            'min_face_quality': 0.3,
            'temporal_buffer_size': 10,
            'quality_marginal_lower': 0.3,
            'quality_marginal_upper': 0.6,
            'quality_high_threshold': 0.7,
            'min_face_size': 20,
            'near_min_size_multiplier': 1.5,
        }
        for key, value in defaults.items():
            self.config.setdefault(key, value)            
               
    def _prepare_mask_input(self, face_roi: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
        """Resize and normalize face ROI to target dimensions."""
        h, w = face_roi.shape[:2]
        scale = min(target_h / h, target_w / w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(face_roi, (new_w, new_h), interpolation=cv2.INTER_AREA)
        padded = np.zeros((target_h, target_w, 3), dtype=np.float32)
        y_off = (target_h - new_h) // 2
        x_off = (target_w - new_w) // 2
        padded[y_off:y_off+new_h, x_off:x_off+new_w] = resized
        rgb = cv2.cvtColor(padded.astype(np.uint8), cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        return normalized               
        
    def _format_input(self, image: np.ndarray, layout: str) -> np.ndarray:
        """Convert image (HWC, float32) to model's expected layout."""
        if layout == 'NCHW':
            # (H, W, C) -> (C, H, W) -> (1, C, H, W)
            return np.expand_dims(np.transpose(image, (2, 0, 1)), axis=0).astype(np.float32)
        elif layout == 'NHWC':
            # (H, W, C) -> (1, H, W, C)
            return np.expand_dims(image, axis=0).astype(np.float32)
        else:
            # Default to NHWC
            return np.expand_dims(image, axis=0).astype(np.float32)    
               
                      
    def detect_mask(self, face_roi: np.ndarray) -> Tuple[str, float]:
        if self.mask_detector is None or self.channel_format is None:
            return "no_mask", 0.0
            
        start_time = time.time()
        try:
            # Validate face ROI
            if (face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40):
                return "unknown", 0.0
            
            # Prepare input tensor with correct size
            target_h, target_w = self.mask_input_size
            input_data = self._prepare_mask_input(face_roi, target_h, target_w)
            
            # Run inference with layout detection if unknown
            if self.mask_input_layout == 'UNKNOWN':
                # Try NCHW first (common in ONNX models)
                try:
                    input_tensor = self._format_input(input_data, 'NCHW')
                    outputs = self.mask_detector.run(None, {self.mask_input_name: input_tensor})
                    # Validate output (e.g., has 2 classes)
                    if outputs and outputs[0].shape[-1] == 2:
                        self.mask_input_layout = 'NCHW'  # cache for future
                        self.logger.info("Auto-detected mask input layout: NCHW")
                    else:
                        raise ValueError("Output shape mismatch")
                except Exception:
                    # Fallback to NHWC
                    input_tensor = self._format_input(input_data, 'NHWC')
                    outputs = self.mask_detector.run(None, {self.mask_input_name: input_tensor})
                    if outputs and outputs[0].shape[-1] == 2:
                        self.mask_input_layout = 'NHWC'
                        self.logger.info("Auto-detected mask input layout: NHWC")
                    else:
                        self.logger.error("Could not determine mask input layout")
                        return "unknown", 0.0
            else:
                # Use cached layout
                input_tensor = self._format_input(input_data, self.mask_input_layout)
                outputs = self.mask_detector.run(None, {self.mask_input_name: input_tensor})
            
            # Process outputs
            predictions = outputs[0][0]
            mask_prob = float(predictions[0])
            no_mask_prob = float(predictions[1])
            threshold = self.config.get('mask_detection_threshold', 0.8)
            
            if mask_prob > no_mask_prob and mask_prob >= threshold:
                result = ("mask", mask_prob)
            else:
                result = ("no_mask", no_mask_prob)
            
            # Update stats
            self.debug_stats['mask_detection_times'].append((time.time() - start_time) * 1000)
            return result
            
        except Exception as e:
            self.logger.error(f"Mask detection error: {e}")
            return "unknown", 0.0
                
    def _load_models(self):
        """Load YOLO face detection model from local path with GPU support"""
        try:
            model_path = Path(self.config['detection_model_path'])
            if not model_path.exists():
                raise FileNotFoundError(f"YOLO model not found at {model_path}")
                
            # Load model with GPU support
            self.detection_model = YOLO(str(model_path))
            
            # Move model to GPU if available
            if self.config.get('use_gpu', False):
                device = self.config.get('gpu_device', 0)  # Default to GPU 0
                # Convert to torch device
                torch_device = f'cuda:{device}'
                self.detection_model.to(torch_device)
                self.logger.info(f"YOLO model loaded on {torch_device}")
                
                # Verify the model is actually on GPU
                model_device = next(self.detection_model.model.parameters()).device
                self.logger.info(f"YOLO model verified on device: {model_device}")
            else:
                self.logger.info(f"YOLO model loaded on CPU")
                
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            raise
               
    def _load_embeddings_database(self):
        """Load pre-computed face embeddings from JSON with your structure"""
        try:
            db_path = Path(self.config['embeddings_db_path'])
            if not db_path.exists():
                self.logger.warning("Embeddings database not found, starting fresh")
                self.embeddings_db = {"persons": {}, "metadata": {}}
                return
                
            with open(db_path, 'r') as f:
                self.embeddings_db = json.load(f)
                
            if "persons" in self.embeddings_db:
                for person_id, person_data in self.embeddings_db["persons"].items():
                    display_name = person_data["display_name"]
                    centroid = person_data["centroid_embedding"]
                    self.identity_centroids[display_name] = np.array(centroid)
                    
                self.logger.info(f"Loaded {len(self.identity_centroids)} identities from database")
                self.logger.info(f"Available persons: {list(self.identity_centroids.keys())}")
                
            else:
                self.logger.warning("No 'persons' key found in JSON database")
                
        except Exception as e:
            self.logger.error(f"Failed to load embeddings database: {e}")
            raise

    def detect_faces(self, frame: np.ndarray) -> List[Dict]:
            """Detect faces using YOLO with GPU optimization"""
            start_time = time.time()
            try:
                # Use GPU if configured - FIXED: Use proper device string
                if self.config.get('use_gpu', False):
                    device = self.config.get('gpu_device', 0)
                    device_str = f'cuda:{device}'
                else:
                    device_str = 'cpu'
                
                results = self.detection_model(
                    frame, 
                    conf=self.config['detection_confidence'],
                    iou=self.config['detection_iou'],
                    verbose=False,
                    device=device_str  # Specify device for inference
                )
                
                detections = []
                for result in results:
                    boxes = result.boxes
                    if boxes is not None:
                        for box in boxes:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()  # Ensure tensor is moved to CPU for numpy
                            confidence = box.conf[0].cpu().numpy()
                            
                            detections.append({
                                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                'confidence': float(confidence)
                            })
                
                detection_time = (time.time() - start_time) * 1000
                self.debug_stats['detection_times'].append(detection_time)
                
                if self.config.get('debug', {}).get('verbose', False):
                    self.logger.debug(f"Detected {len(detections)} faces in {detection_time:.2f}ms")
                            
                return detections
                
            except Exception as e:
                self.logger.error(f"Detection error: {e}")
                return []
                    
    def extract_embedding(self, face_roi: np.ndarray) -> Optional[np.ndarray]:
        """Optimized embedding extraction with GPU support"""
        start_time = time.time()
        
        # Validate ROI dimensions more thoroughly
        if (face_roi.size == 0 or face_roi.shape[0] < 50 or face_roi.shape[1] < 50 or 
            np.max(face_roi) - np.min(face_roi) < 10):  # Check for low contrast
            if self.config.get('debug', {}).get('verbose', False):
                self.logger.warning("Invalid face ROI for embedding extraction")
            return None
            
        try:
            # Convert to RGB and ensure proper data type
            if len(face_roi.shape) == 3:
                face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
            else:
                face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_GRAY2RGB)
            
            # Normalize pixel values
            face_rgb = face_rgb.astype(np.float32) / 255.0
            
            # Set device for DeepFace - FIXED: Use proper device format
            if self.config.get('use_gpu', False):
                device = self.config.get('gpu_device', 0)
                # DeepFace uses different device format
                device_name = f'cuda:{device}'
            else:
                device_name = 'cpu'
                
            if self.config.get('debug', {}).get('verbose', False):
                self.logger.debug(f"Extracting embedding on device: {device_name}")
                
            embedding_obj = DeepFace.represent(
                face_rgb,
                model_name=self.config['embedding_model'],
                enforce_detection=False,
                detector_backend='skip',
                align=True
            )
            
            if embedding_obj and len(embedding_obj) > 0:
                embedding_time = (time.time() - start_time) * 1000
                self.debug_stats['embedding_times'].append(embedding_time)
                
                if self.config.get('debug', {}).get('verbose', False):
                    self.logger.debug(f"Embedding extracted in {embedding_time:.2f}ms")
               
                return np.array(embedding_obj[0]['embedding'])
            else:
                if self.config.get('debug', {}).get('verbose', False):
                    self.logger.warning("No embedding extracted")
                
        except Exception as e:
            if self.config.get('verbose', False):
                self.logger.error(f"Embedding extraction error: {e}")
                
        return None
    
    def recognize_face(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Enhanced matching with multiple similarity strategies"""
        start_time = time.time()
        
        if not self.identity_centroids:
            return None, 0.0
            
        best_similarity = -1.0
        best_identity = None
        
        embedding = embedding.flatten()
        
        for identity, centroid in self.identity_centroids.items():
            centroid = centroid.flatten()
            
            # Cosine similarity (primary)
            cosine_sim = cosine_similarity([embedding], [centroid])[0][0]
            
            # Optional: Euclidean distance (normalized to 0-1)
            euclidean_dist = np.linalg.norm(embedding - centroid)
            euclidean_sim = 1 / (1 + euclidean_dist)  # Convert distance to similarity
            
            # Combine strategies (weighted)
            final_similarity = 0.8 * cosine_sim + 0.2 * euclidean_sim
            
            if final_similarity > best_similarity and final_similarity >= self.config['recognition_threshold']:
                best_similarity = final_similarity
                best_identity = identity
        
        recognition_time = (time.time() - start_time) * 1000
        self.debug_stats['recognition_times'].append(recognition_time)
        
        return best_identity, best_similarity

    def process_frame(self, frame: np.ndarray) -> List[Dict]:
        """Enhanced pipeline: detect → mask detection → extract → recognize"""
        start_time = time.time()
        results = []
        
        # Detect faces
        detections = self.detect_faces(frame)
        
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            
            padding = self.config.get('roi_padding', 20)  # Increased padding for better mask detection
            h, w = frame.shape[:2]
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)
            
            face_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            
            # Better ROI validation
            if (face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40 or
                np.std(face_roi) < 10):  # Check for low contrast
                continue
                
            # NEW: Enhanced Mask detection
            mask_status, mask_confidence = self.detect_mask(face_roi)
            
            # Continue with embedding extraction only if we have a good face ROI
            embedding = self.extract_embedding(face_roi)
            if embedding is None:
                continue
                
            identity, recognition_confidence = self.recognize_face(embedding)
            
            # Update mask statistics
            if mask_status == "mask":
                self.debug_stats['total_masks_detected'] += 1
            
            results.append({
                'bbox': detection['bbox'],
                'detection_confidence': detection['confidence'],
                'mask_status': mask_status,  
                'mask_confidence': mask_confidence,  
                'identity': identity,
                'recognition_confidence': recognition_confidence,
                'embedding': embedding.tolist()
            })
        
        # Update overall stats
        self.debug_stats['total_frames_processed'] += 1
        self.debug_stats['total_faces_detected'] += len(detections)
        self.debug_stats['total_faces_recognized'] += len([r for r in results if r['identity']])
        self.debug_stats['last_processing_time'] = (time.time() - start_time) * 1000
            
        self._maybe_clean_gpu_cache()
        return results
        
    def get_debug_stats(self) -> Dict:
        """Enhanced performance statistics"""
        stats = self.debug_stats.copy()
        
        # Calculate averages and percentiles
        stats['avg_detection_time'] = np.mean(stats['detection_times']) if stats['detection_times'] else 0
        stats['p95_detection_time'] = np.percentile(stats['detection_times'], 95) if stats['detection_times'] else 0
        stats['max_detection_time'] = np.max(stats['detection_times']) if stats['detection_times'] else 0
        
        stats['avg_embedding_time'] = np.mean(stats['embedding_times']) if stats['embedding_times'] else 0
        stats['p95_embedding_time'] = np.percentile(stats['embedding_times'], 95) if stats['embedding_times'] else 0
        
        stats['avg_recognition_time'] = np.mean(stats['recognition_times']) if stats['recognition_times'] else 0
        
        # Calculate mask detection time
        stats['avg_detection_time'] = np.mean(stats['detection_times']) if stats['detection_times'] else 0
        stats['avg_mask_detection_time'] = np.mean(stats['mask_detection_times']) if stats['mask_detection_times'] else 0
        
        # Add mask input size to stats if available
        if self.mask_input_size:
            stats['mask_input_size'] = f"{self.mask_input_size[1]}x{self.mask_input_size[0]}"
            stats['mask_channel_format'] = self.channel_format
                     
        # Calculate rates and efficiencies
        if stats['total_faces_detected'] > 0:
            stats['mask_detection_rate'] = (stats['total_masks_detected'] / stats['total_faces_detected']) * 100
            stats['recognition_rate'] = (stats['total_faces_recognized'] / stats['total_faces_detected']) * 100
        else:
            stats['mask_detection_rate'] = 0
            stats['recognition_rate'] = 0
            
        if stats['total_frames_processed'] > 0:
            stats['faces_per_frame'] = stats['total_faces_detected'] / stats['total_frames_processed']
        else:
            stats['faces_per_frame'] = 0
                
        # Memory usage (approximate)
        try:
            import psutil
            process = psutil.Process()
            stats['memory_mb'] = process.memory_info().rss / 1024 / 1024
        except ImportError:
            stats['memory_mb'] = 0
        
        return stats

    def get_known_identities(self) -> List[str]:
        """Get list of all known identities"""
        return list(self.identity_centroids.keys())

    def get_model_info(self) -> Dict:
        """Get information about loaded models"""
        info = {
            'mask_detector_loaded': self.mask_detector is not None,
            'face_detector_loaded': self.detection_model is not None,
            'known_identities_count': len(self.identity_centroids)
        }
        
        if self.mask_detector is not None:
            info['mask_input_size'] = self.mask_input_size
            info['mask_channel_format'] = self.channel_format
            info['mask_input_name'] = self.mask_detector.get_inputs()[0].name
            info['mask_output_name'] = self.mask_detector.get_outputs()[0].name
            
        return info